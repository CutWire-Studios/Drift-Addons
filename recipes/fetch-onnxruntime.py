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
            "Same AI features, sped up by an NVIDIA graphics card. Needs recent NVIDIA drivers "
            "with CUDA support already installed on your system (not included here). Falls back "
            "to this computer if the card can't be used."
        ),
        "details": (
            "Complete ONNX Runtime build with the CUDA execution provider. Requires CUDA 13 and "
            "cuDNN 9 already installed on the host — neither is bundled. Falls back to CPU when "
            "the device cannot be used. Upstream: Microsoft ONNX Runtime {version}."
        ),
    },
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
        for source in sorted((prefix / "lib").iterdir()):
            if source.is_dir() or source.suffix in {".a", ".lib"}:
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

    (root / "runtime.json").write_text(json.dumps({
        "variant": variant,
        "ortVersion": ORT_VERSION,
        "apiVersion": ORT_API_VERSION,
        "platform": platform,
    }, indent=2) + "\n")

    copy = CORE_COPY[variant]
    recipe = _write_recipe({
        "id": f"onnxruntime.{variant}.{platform}",
        "version": PACKAGE_VERSION,
        # Platform stays in the id / platform field; the app filters by OS already, so
        # beginners don't need "(linux-x64)" in the store title.
        "name": copy["name"],
        "description": copy["description"],
        "details": copy["details"].format(version=ORT_VERSION) + f" Platform: {platform}.",
        "author": "Microsoft",
        "license": "MIT",
        "minAppVersion": "0.1.0",
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
