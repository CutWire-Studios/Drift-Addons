#!/usr/bin/env python3
"""Stage the ONNX Runtime addons and write their recipes.

    ./fetch-onnxruntime.py                  # every variant/platform in the table below
    ./fetch-onnxruntime.py cpu:linux-x64 webgpu:linux-x64

Drift no longer links ONNX Runtime — it dlopens whichever build the user installed, so the
runtime ships as an addon and the CPU / CUDA / WebGPU choice belongs to them. Two kinds come out
of here:

  onnxruntime      a complete runtime distribution. Replaces the core, one per platform, and is
                   what Microsoft publishes as a release archive.
  onnxruntime-ep   a plugin execution provider (ONNX Runtime >= 1.23) that layers onto whichever
                   core is loaded. WebGPU is the only one so far, and it is how AMD and Intel GPUs
                   get accelerated without a second 200 MB core.

Unlike the other staging scripts this one downloads rather than copying local assets, and it can
stage any platform from any platform — the packages are cross-built by construction. Recipes are
generated rather than committed by hand because they are eleven near-identical files whose only
real content is this table.

The CUDA addon also unpacks pinned NVIDIA redistributable wheels (cublas, cudnn, nvrtc, …) into
the same runtime/lib/ folder, skips TensorRT and PDBs, and on Linux runs patchelf so the CUDA EP
finds those libraries via RUNPATH=$ORIGIN.

The archives are large and are cached under ../staging/.cache.
"""

import argparse
import hashlib
import json
import shutil
import subprocess
import sys
import tempfile
import zipfile
from pathlib import Path

HERE = Path(__file__).parent
STAGING = HERE.parent / "staging"
CACHE = STAGING / ".cache"

import staging_hashes  # noqa: E402

ORT_VERSION = "1.27.0"
ORT_API_VERSION = 27
# Addon package version shown in the catalogue — independent of the upstream ORT release.
PACKAGE_VERSION = "1.0.0"
# CUDA 1.1.0 bundles NVIDIA redistributables and drops TensorRT / PDBs.
CUDA_PACKAGE_VERSION = "1.1.0"
# Windows needs AddDllDirectory (unreleased as of Drift 0.3.0). Linux works with
# patchelf alone, but both CUDA packs share this floor so the catalogue is honest.
CUDA_MIN_APP_VERSION = "0.3.1"
ORT_RELEASE = f"https://github.com/microsoft/onnxruntime/releases/download/v{ORT_VERSION}"

# The WebGPU plugin EP is versioned and published separately from the core, which is the whole
# point of the plugin architecture: it iterates on its own cadence and works against any core from
# 1.24.4 on. NuGet is the only place it ships as native binaries; a .nupkg is a plain zip.
WEBGPU_VERSION = "0.1.0"
WEBGPU_NUPKG = ("https://www.nuget.org/api/v2/package/"
                f"Microsoft.ML.OnnxRuntime.EP.WebGpu/{WEBGPU_VERSION}")
WEBGPU_MIN_API = 24

# variant -> platform -> (archive name, sha256). Only what Microsoft actually publishes: there is
# no ROCm (removed from ONNX Runtime in 1.23) and no OpenVINO C/C++ package at all.
CORES = {
    "cpu": {
        "linux-x64": (f"onnxruntime-linux-x64-{ORT_VERSION}.tgz",
                      "547e40a48f1fe73e3f812d7c88a948612c23f896b91e4e2ee1e232d7b468246f"),
        "linux-arm64": (f"onnxruntime-linux-aarch64-{ORT_VERSION}.tgz",
                        "3e4d83ac06924a32a07b6d7f91ce6f852876153fc0bbdf931bf517a140bfbe48"),
        "osx-arm64": (f"onnxruntime-osx-arm64-{ORT_VERSION}.tgz",
                      "545e81c58152353acb0d1e8bd6ce4b62f830c0961f5b3acfedc790ffd76e477a"),
        "win-x64": (f"onnxruntime-win-x64-{ORT_VERSION}.zip",
                    "c5c81710938e68079ff1a192b04897faabe4b43830d48f39f27ecd4e16138bfc"),
        "win-arm64": (f"onnxruntime-win-arm64-{ORT_VERSION}.zip",
                      "a32f2650575b3c20df462e337519fd1cc4105356130d11dba9771c6f374d952f"),
    },
    "cuda": {
        "linux-x64": (f"onnxruntime-linux-x64-gpu_cuda13-{ORT_VERSION}.tgz",
                      "1a3227e1dc2f53d9f877c93278af500b15e26d99aa5ade877692138b3ab7d351"),
        "win-x64": (f"onnxruntime-win-x64-gpu_cuda13-{ORT_VERSION}.zip",
                    "d3e0d908bc9b59dcb59b8f453493f173c087dda105d8c110df0588d22d7c8b3e"),
    },
}

# NuGet runtime identifier -> the extra files that ride along with the EP library. The Windows
# builds need the DirectX shader compiler beside them.
WEBGPU_PLATFORMS = {
    "linux-x64": ("libonnxruntime_providers_webgpu.so", []),
    "osx-arm64": ("libonnxruntime_providers_webgpu.dylib", []),
    "win-x64": ("onnxruntime_providers_webgpu.dll", ["dxil.dll", "dxcompiler.dll"]),
    "win-arm64": ("onnxruntime_providers_webgpu.dll", ["dxil.dll", "dxcompiler.dll"]),
}

CORE_COPY = {
    "cpu": {
        "name": "AI Engine — Any computer",
        "description": (
            "Powers auto captions, subject cutout, funny face effects, and noise removal. "
            "Works on every computer — install this first unless you know you want a faster "
            "graphics option."
        ),
        "details": (
            "Complete ONNX Runtime build that Drift dlopens for AI features. Ships the CPU "
            "execution provider only. Upstream: Microsoft ONNX Runtime {version}."
        ),
    },
    "cuda": {
        "name": "AI Engine — NVIDIA graphics (faster)",
        "description": (
            "Same AI features, sped up by an NVIDIA graphics card. Needs NVIDIA driver 580 or "
            "newer; CUDA and cuDNN are included. Falls back to this computer if the card can't "
            "be used."
        ),
        "details": (
            "Complete ONNX Runtime build with the CUDA execution provider. CUDA 13 and cuDNN 9 "
            "runtimes are bundled — not the full CUDA Toolkit. The host still needs a recent "
            "NVIDIA driver (Linux ≥ 580.65 for CUDA 13.0). Falls back to CPU when the device "
            "cannot be used. Licensed MIT (ONNX Runtime) plus NVIDIA CUDA and cuDNN "
            "redistributable terms. Upstream: Microsoft ONNX Runtime {version}."
        ),
    },
}

# NVIDIA redistributables unpacked into runtime/lib/ next to the CUDA EP.
# Pins follow onnxruntime-gpu 1.27 extras (CUDA 13 / cuDNN 9) under NVIDIA's current names:
# toolkit wheels dropped the -cu13 suffix; cuDNN still uses nvidia-cudnn-cu13.
# cublas 13.3.0.5 is the newest 13.3 build that publishes both manylinux and win_amd64
# (13.6+ is Linux-only on PyPI today). nvcudart_hybrid64.dll is a driver component, like
# nvcuda.dll, and is not in the cuda-runtime wheel — do not bundle either.
def _wheel(filename: str, sha256: str, url: str) -> dict[str, str]:
    return {"filename": filename, "sha256": sha256, "url": url}


CUDA_WHEELS: dict[str, list[dict[str, str]]] = {
    "linux-x64": [
        _wheel(
            "nvidia_cuda_runtime-13.3.29-py3-none-manylinux2014_x86_64.manylinux_2_17_x86_64.whl",
            "e04420616e72f563167a7733272992d7e6df6dc5cb54b2f94f9f1520ea9e30c1",
            "https://files.pythonhosted.org/packages/97/be/5699b6e642b372f7d24c59c2f41383e2696825e20bab85f7399c7c6a56f7/nvidia_cuda_runtime-13.3.29-py3-none-manylinux2014_x86_64.manylinux_2_17_x86_64.whl",
        ),
        _wheel(
            "nvidia_cublas-13.3.0.5-py3-none-manylinux_2_27_x86_64.whl",
            "366568e2dc59e6fe71ffd179f9f2a38b8b2772aed626320a64008651b1e72974",
            "https://files.pythonhosted.org/packages/3c/7c/ae5d1751819acff18b0fac29c0a4e93d06d36cfabebe36365ddacc7c32a9/nvidia_cublas-13.3.0.5-py3-none-manylinux_2_27_x86_64.whl",
        ),
        _wheel(
            "nvidia_cufft-12.3.0.29-py3-none-manylinux2014_x86_64.manylinux_2_17_x86_64.whl",
            "edb25c0626bd202ee5acc035b5dd361a3b89ed3b75a81a52df72c89150cb57c2",
            "https://files.pythonhosted.org/packages/e7/00/fab4a29fa1d7eb43bc6b94de4e86312c5e425d5582e58b9641300b9dffc7/nvidia_cufft-12.3.0.29-py3-none-manylinux2014_x86_64.manylinux_2_17_x86_64.whl",
        ),
        _wheel(
            "nvidia_curand-10.4.3.29-py3-none-manylinux_2_27_x86_64.whl",
            "1859bf37a62754d2c65001393096ca79de399f995971fa7826d0adfd88c3cf7b",
            "https://files.pythonhosted.org/packages/ee/49/4ca4ce4a9334c9a1ef68ab85b358f019bf85e8c3f51c2471d4cc257a273d/nvidia_curand-10.4.3.29-py3-none-manylinux_2_27_x86_64.whl",
        ),
        _wheel(
            "nvidia_cuda_nvrtc-13.3.33-py3-none-manylinux2010_x86_64.manylinux_2_12_x86_64.whl",
            "82530788b8c6164a54d3fd9ae8bcca8893d397c4aeb998861982a03bbe41e204",
            "https://files.pythonhosted.org/packages/8b/2c/86916c8a34dcdb0c3ddd1c0e30545041bd781184e437b9cb76fcda70560b/nvidia_cuda_nvrtc-13.3.33-py3-none-manylinux2010_x86_64.manylinux_2_12_x86_64.whl",
        ),
        _wheel(
            "nvidia_nvjitlink-13.3.33-py3-none-manylinux2010_x86_64.manylinux_2_12_x86_64.whl",
            "26a6de7fb4c8fdaa7703d3dad720d6d427ddfea5c48a528fd97c11733ad830e5",
            "https://files.pythonhosted.org/packages/f0/ee/580ca6f29dcab0221db8706badca1bbbb084f1975c4d4e83329c3a7e31f0/nvidia_nvjitlink-13.3.33-py3-none-manylinux2010_x86_64.manylinux_2_12_x86_64.whl",
        ),
        _wheel(
            "nvidia_cudnn_cu13-9.25.0.15-py3-none-manylinux_2_27_x86_64.whl",
            "b910b8108975ba34866bbacc598305d70724646f7da28f24ada6256ce46c53e1",
            "https://files.pythonhosted.org/packages/73/e0/0e168dd11772e040700413ca4843617d32dd939885d753078ee682afc674/nvidia_cudnn_cu13-9.25.0.15-py3-none-manylinux_2_27_x86_64.whl",
        ),
    ],
    "win-x64": [
        _wheel(
            "nvidia_cuda_runtime-13.3.29-py3-none-win_amd64.whl",
            "0667ec61c3d897388efa305ed4f7609ace88849a753ba9c6311d06dca55fff4f",
            "https://files.pythonhosted.org/packages/d2/27/b53a5e0397842a5c11f0e1a39d4e5b2f22638a4126e83b3c4e196f62c969/nvidia_cuda_runtime-13.3.29-py3-none-win_amd64.whl",
        ),
        _wheel(
            "nvidia_cublas-13.3.0.5-py3-none-win_amd64.whl",
            "065b944083560334e02299050979b7cfd91ec79e5fc5c23d602f7f35c0d1356c",
            "https://files.pythonhosted.org/packages/f8/6f/7ed17e69ac6799098d7ab9ff46789c10ea58d49f75726ba351badc5f109d/nvidia_cublas-13.3.0.5-py3-none-win_amd64.whl",
        ),
        _wheel(
            "nvidia_cufft-12.3.0.29-py3-none-win_amd64.whl",
            "510036a2bbab5c83ae93dc5c907c3a49d3518e3066ac3a2052ff0f7f9b27dfc4",
            "https://files.pythonhosted.org/packages/94/64/8e9d808720559d3cbfcd1d1bc8a2e6f55deb29d692513d5a93c8d417b7e5/nvidia_cufft-12.3.0.29-py3-none-win_amd64.whl",
        ),
        _wheel(
            "nvidia_curand-10.4.3.29-py3-none-win_amd64.whl",
            "34b18d5a2a8e5db4c3846475ae4eef0cacdf3ac5e9c501f3a4efb422f137a74e",
            "https://files.pythonhosted.org/packages/2a/eb/63f7710fc84837e0118002bc29671542807921aef3a0c710da83a5e7e711/nvidia_curand-10.4.3.29-py3-none-win_amd64.whl",
        ),
        _wheel(
            "nvidia_cuda_nvrtc-13.3.33-py3-none-win_amd64.whl",
            "7d2af818851c0c224d5f92221e9226e51ee23c236df4b51f9194563979c888be",
            "https://files.pythonhosted.org/packages/a1/42/edce72f2c5a0f587168109c867f25f4a9a6cd7289ecf0d68ed2b1070f273/nvidia_cuda_nvrtc-13.3.33-py3-none-win_amd64.whl",
        ),
        _wheel(
            "nvidia_nvjitlink-13.3.33-py3-none-win_amd64.whl",
            "4297ee49639b4f2e07255a1d69b3acc7ab2d011bb892b403e91ac98368962e3b",
            "https://files.pythonhosted.org/packages/67/f2/ec9c05a108095828dfc58840978c627b3c313fdf2a567c6de9ffbbb46901/nvidia_nvjitlink-13.3.33-py3-none-win_amd64.whl",
        ),
        _wheel(
            "nvidia_cudnn_cu13-9.25.0.15-py3-none-win_amd64.whl",
            "af0f35094dcc100c7edb1d08ebda980c67d9ade65ca1dec9c351040ffcd78e4e",
            "https://files.pythonhosted.org/packages/18/d4/c09b11336981836c3183f28a6ca309e08ad080311edb6ff6c28cecdb5f24/nvidia_cudnn_cu13-9.25.0.15-py3-none-win_amd64.whl",
        ),
    ],
}


def _download(url: str, name: str, sha256: str | None) -> Path:
    CACHE.mkdir(parents=True, exist_ok=True)
    path = CACHE / name
    if not path.exists():
        print(f"downloading {url}")
        subprocess.run(["curl", "-sSfL", url, "-o", str(path)], check=True)

    if sha256:
        digest = hashlib.sha256()
        with path.open("rb") as f:
            for chunk in iter(lambda: f.read(1 << 20), b""):
                digest.update(chunk)
        if digest.hexdigest() != sha256:
            path.unlink()
            sys.exit(f"{name} failed its checksum — deleted, try again")
    return path


def _extract(archive: Path, into: Path) -> Path:
    """Unpack and return the single top-level directory the release archives all have."""
    into.mkdir(parents=True, exist_ok=True)
    shutil.unpack_archive(str(archive), str(into))
    children = [p for p in into.iterdir() if p.is_dir()]
    if len(children) != 1:
        sys.exit(f"expected one top-level directory in {archive.name}, found {len(children)}")
    return children[0]


def _reset(name: str) -> Path:
    target = STAGING / name
    if target.exists():
        shutil.rmtree(target)
    target.mkdir(parents=True)
    return target


def _copy_real(src: Path, dst: Path) -> None:
    """Copy resolving symlinks — the packer skips them, and the app looks for the plain names."""
    shutil.copy2(src.resolve(), dst)


def _is_native_lib(name: str) -> bool:
    lower = name.lower()
    if lower.endswith((".dll", ".so", ".dylib")):
        return True
    # Versioned SONAMEs must keep the minor, e.g. libnvrtc-builtins.so.13.3
    return ".so." in lower


def _is_license_file(path: Path) -> bool:
    posix = path.as_posix().replace("\\", "/")
    if "/licenses/" in posix.lower() and path.suffix.lower() in {".txt", ".md", ""}:
        return True
    return path.name.lower() in {"license", "license.txt", "license.md", "eula.txt"}


def _stage_nvidia_wheels(platform: str, lib: Path, root: Path) -> None:
    wheels = CUDA_WHEELS.get(platform)
    if not wheels:
        sys.exit(f"no NVIDIA wheels pinned for {platform}")

    seen_license_hashes: set[str] = set()
    for wheel in wheels:
        archive = _download(wheel["url"], wheel["filename"], wheel["sha256"])
        with tempfile.TemporaryDirectory() as tmp:
            with zipfile.ZipFile(archive) as zf:
                zf.extractall(tmp)
            for source in Path(tmp).rglob("*"):
                if source.is_symlink():
                    resolved = source.resolve()
                    if not resolved.is_file():
                        continue
                elif source.is_file():
                    resolved = source
                else:
                    continue

                if _is_native_lib(source.name):
                    dest = lib / source.name
                    _copy_real(source, dest)
                    continue

                if not _is_license_file(source):
                    continue
                digest = hashlib.sha256(resolved.read_bytes()).hexdigest()
                if digest in seen_license_hashes:
                    continue
                seen_license_hashes.add(digest)
                if "cudnn" in source.as_posix().lower():
                    dest_name = "NVIDIA_CUDNN_LICENSE.txt"
                else:
                    dest_name = "NVIDIA_CUDA_EULA.txt"
                dest = root / dest_name
                # cuDNN and CUDA EULAs can both want the same filename after the first unique
                # CUDA copy; keep a package-prefixed fallback if that happens.
                if dest.exists():
                    dest = root / f"{source.name}"
                    if dest.exists():
                        dest = root / f"{archive.stem}-{source.name}"
                _copy_real(source, dest)


# libcudnn.so.9 dlopens these without a SONAME suffix. DT_NEEDED entries already
# carry versions (libcublas.so.13, …) and must not be duplicated.
_DLOPEN_UNVERSIONED = {
    "libcudnn_adv.so",
    "libcudnn_cnn.so",
    "libcudnn_engines_precompiled.so",
    "libcudnn_engines_runtime_compiled.so",
    "libcudnn_engines_tensor_ir.so",
    "libcudnn_ext.so",
    "libcudnn_graph.so",
    "libcudnn_heuristic.so",
    "libcudnn_ops.so",
    "libnvrtc-builtins.so",
    "libnvrtc.so",
}


def _copy_unversioned_aliases(lib: Path) -> None:
    """Copy SONAME files to the unversioned names cuDNN dlopens.

    The packer skips symlinks, so each alias is a real copy.
    """
    for source in list(lib.iterdir()):
        if not source.is_file():
            continue
        name = source.name
        if ".so." not in name:
            continue
        alias_name = name[: name.index(".so.") + 3]
        if alias_name not in _DLOPEN_UNVERSIONED:
            continue
        alias = lib / alias_name
        if alias.exists():
            continue
        _copy_real(source, alias)


def _patchelf_cuda_ep(lib: Path) -> None:
    ep = lib / "libonnxruntime_providers_cuda.so"
    if not ep.exists():
        return
    if shutil.which("patchelf") is None:
        sys.exit("patchelf is required to set RUNPATH=$ORIGIN on libonnxruntime_providers_cuda.so")
    subprocess.run(["patchelf", "--set-rpath", "$ORIGIN", str(ep)], check=True)


def _write_recipe(recipe: dict) -> Path:
    out_dir = HERE / "onnxruntime"
    out_dir.mkdir(exist_ok=True)
    path = out_dir / f"{recipe['id']}.json"
    path.write_text(json.dumps(recipe, indent=2) + "\n")
    return path


def stage_core(variant: str, platform: str) -> None:
    archive_name, sha256 = CORES[variant][platform]
    archive = _download(f"{ORT_RELEASE}/{archive_name}", archive_name, sha256)

    name = f"onnxruntime-{variant}-{platform}"
    target = _reset(name)
    root = target / "runtime"
    lib = root / "lib"
    lib.mkdir(parents=True)

    with tempfile.TemporaryDirectory() as tmp:
        prefix = _extract(archive, Path(tmp))
        # The release ships libonnxruntime.so, .so.1 and .so.1.27.0 as two symlinks to one file.
        # Only the plain name is staged: the loader looks for it first, and three copies of a
        # 23 MB library would otherwise land in the package, since the packer skips symlinks.
        # NVIDIA SONAMEs are copied separately and must not be flattened (libnvrtc-builtins.so.13.3).
        skip_suffixes = {".a", ".lib", ".pdb"}
        for source in sorted((prefix / "lib").iterdir()):
            if source.is_dir():
                continue
            if "tensorrt" in source.name.lower():
                continue
            if source.suffix.lower() in skip_suffixes:
                continue
            resolved = source.resolve()
            stem = resolved.name
            # libonnxruntime.so.1.27.0 -> libonnxruntime.so ; the .dll/.dylib names are already flat
            if ".so." in stem:
                stem = stem[:stem.index(".so.") + 3]
            _copy_real(source, lib / stem)

        for extra in ("LICENSE", "ThirdPartyNotices.txt", "Privacy.md", "README.md"):
            if (prefix / extra).is_file():
                shutil.copy2(prefix / extra, root / extra)

    if variant == "cuda":
        _stage_nvidia_wheels(platform, lib, root)
        if platform.startswith("linux"):
            _copy_unversioned_aliases(lib)
            _patchelf_cuda_ep(lib)

    (root / "runtime.json").write_text(json.dumps({
        "variant": variant,
        "ortVersion": ORT_VERSION,
        "apiVersion": ORT_API_VERSION,
        "platform": platform,
    }, indent=2) + "\n")

    copy = CORE_COPY[variant]
    cuda = variant == "cuda"
    recipe = _write_recipe({
        "id": f"onnxruntime.{variant}.{platform}",
        "version": CUDA_PACKAGE_VERSION if cuda else PACKAGE_VERSION,
        # Platform stays in the id / platform field; the app filters by OS already, so
        # beginners don't need "(linux-x64)" in the store title.
        "name": copy["name"],
        "description": copy["description"],
        "details": copy["details"].format(version=ORT_VERSION) + f" Platform: {platform}.",
        "author": "Microsoft, NVIDIA" if cuda else "Microsoft",
        "license": "MIT + NVIDIA CUDA/cuDNN" if cuda else "MIT",
        "minAppVersion": CUDA_MIN_APP_VERSION if cuda else "0.1.0",
        "platform": platform,
        "source": f"../../staging/{name}",
        "provides": [{"kind": "onnxruntime", "root": "runtime", "items": 1}],
        # Native libraries are already close to incompressible; level 19 costs minutes and buys
        # a fraction of a percent over the CUDA package's 200 MB.
        "zstdLevel": 6,
    })
    size = sum(f.stat().st_size for f in target.rglob("*") if f.is_file())
    print(f"{name}: {size / 1e6:.0f} MB -> {recipe.relative_to(HERE.parent)}")


def stage_webgpu(platform: str) -> None:
    library, extras = WEBGPU_PLATFORMS[platform]
    # NuGet packages are immutable but unversioned in the URL's eyes, so there is no published
    # checksum to pin against; the transport is HTTPS and the package is re-signed by us anyway.
    nupkg = _download(WEBGPU_NUPKG, f"onnxruntime-ep-webgpu-{WEBGPU_VERSION}.nupkg", None)

    name = f"onnxruntime-ep-webgpu-{platform}"
    target = _reset(name)
    root = target / "ep"
    lib = root / "lib"
    lib.mkdir(parents=True)

    with zipfile.ZipFile(nupkg) as zf:
        native = f"runtimes/{platform}/native/"
        for member in [library, *extras]:
            with zf.open(native + member) as src, (lib / member).open("wb") as dst:
                shutil.copyfileobj(src, dst)
        for extra in ("LICENSE", "ThirdPartyNotices.txt", "README.md"):
            if extra in zf.namelist():
                with zf.open(extra) as src, (root / extra).open("wb") as dst:
                    shutil.copyfileobj(src, dst)

    # No epName: the library names its own execution providers, and Drift reads the name back out
    # of the env after registering it rather than trusting a string written here.
    (root / "ep.json").write_text(json.dumps({
        "variant": "webgpu",
        "library": library,
        "minApiVersion": WEBGPU_MIN_API,
        "platform": platform,
    }, indent=2) + "\n")

    recipe = _write_recipe({
        "id": f"onnxruntime.ep.webgpu.{platform}",
        "version": PACKAGE_VERSION,
        "name": "Speed boost — Any graphics card",
        "description": "Makes AI features faster using your graphics card (AMD, Intel, or NVIDIA) "
                       "— no extra toolkit to install. Install an AI Engine first; this just "
                       "speeds it up.",
        "details": (
            "Plugin execution provider (onnxruntime-ep) for WebGPU. Layers onto whichever AI "
            f"Engine is already loaded — it does not replace the core. Upstream: "
            f"Microsoft.ML.OnnxRuntime.EP.WebGpu {WEBGPU_VERSION}. Platform: {platform}."
        ),
        "author": "Microsoft",
        "license": "MIT",
        "minAppVersion": "0.1.0",
        "platform": platform,
        "source": f"../../staging/{name}",
        "provides": [{"kind": "onnxruntime-ep", "root": "ep", "items": 1}],
        "zstdLevel": 6,
    })
    size = sum(f.stat().st_size for f in target.rglob("*") if f.is_file())
    print(f"{name}: {size / 1e6:.0f} MB -> {recipe.relative_to(HERE.parent)}")


def all_targets() -> list[str]:
    targets = [f"{variant}:{platform}"
               for variant, platforms in CORES.items() for platform in platforms]
    targets += [f"webgpu:{platform}" for platform in WEBGPU_PLATFORMS]
    return targets


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("targets", nargs="*", metavar="VARIANT:PLATFORM",
                        help="defaults to every combination that upstream publishes")
    args = parser.parse_args()

    for target in args.targets or all_targets():
        variant, _, platform = target.partition(":")
        if variant == "webgpu":
            if platform not in WEBGPU_PLATFORMS:
                sys.exit(f"no WebGPU EP for {platform}")
            stage_webgpu(platform)
        elif variant in CORES:
            if platform not in CORES[variant]:
                sys.exit(f"upstream publishes no {variant} build for {platform}")
            stage_core(variant, platform)
        else:
            sys.exit(f"unknown variant {variant!r}")

    print("sha256 sidecars:")
    staging_hashes.write_sidecars_under(STAGING)


if __name__ == "__main__":
    main()
