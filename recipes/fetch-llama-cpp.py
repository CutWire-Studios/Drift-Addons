#!/usr/bin/env python3
"""Stage the CPU llama.cpp runtime addons (every desktop platform).

    ./fetch-llama-cpp.py                 # all platforms
    ./fetch-llama-cpp.py linux-x64 ...   # a subset

Pins a llama.cpp release that can load Qwen3.5 (hybrid linear attention). Older builds
reject that architecture. Each official CPU archive is unpacked flat under runtime/ and trimmed to llama-server plus what it
loads. Linux RUNPATH is $ORIGIN, macOS uses @rpath with an @loader_path LC_RPATH, and Windows
resolves DLLs beside the exe. Symlinks are copied out to the name the loader asks for (SONAME /
install name), because the packer skips links. Linux still needs the system libssl.so.3 and
libgomp.so.1; the macOS builds link Metal (arm64) and Accelerate from the OS.

The archive is cached under ../staging/.cache.
"""

import hashlib
import json
import shutil
import subprocess
import sys
import tarfile
import zipfile
import urllib.request
from pathlib import Path

HERE = Path(__file__).parent
STAGING = HERE.parent / "staging"
CACHE = STAGING / ".cache"

sys.path.insert(0, str(HERE))
import staging_hashes  # noqa: E402

TAG = "b11693"
BASE = f"https://github.com/ggml-org/llama.cpp/releases/download/{TAG}"

# platform -> (archive suffix, sha256 from the GitHub release asset digest)
ARCHIVES = {
    "linux-x64": ("ubuntu-x64.tar.gz", "7bf55821d226ca35f7850cc0922a1c959a84dbd6a37161d9f2d2dcc8319a518a"),
    "linux-arm64": ("ubuntu-arm64.tar.gz", "79b6e4c298820aa994f344cae760f24b2f58a23042b0ea583233e2ff120c32c5"),
    "win-x64": ("win-cpu-x64.zip", "6a05baf458405f0e8bd8e95f1a18874f9b8299471049adb389f0c42223aad699"),
    "win-arm64": ("win-cpu-arm64.zip", "b45cefce077565f4f373070a74c8fd677d0fd3d8bc90676a8fd7c05bf3041ab0"),
    "osx-arm64": ("macos-arm64.tar.gz", "ecd140680f54968e3af35aa29c73d4cc539ca1cf65de5f2be8a52b7ff6ea2f20"),
    "osx-x64": ("macos-x64.tar.gz", "c0ff346567c8cdc9b0dcad9bf18b0ef1051621517f5ddb6689c9aa40ecbdfbea"),
}

# Names the loader asks for (DT_NEEDED / install names / import tables), not the archive's
# versioned file names. Missing optional entries are skipped; missing required ones abort.
LINUX_LIBS = ("libllama-server-impl.so", "libggml.so.0", "libggml-base.so.0", "libllama.so.0",
              "libllama-common.so.0", "libmtmd.so.0")
MAC_LIBS = ("libllama-server-impl.dylib", "libllama-common.0.dylib", "libmtmd.0.dylib", "libllama.0.dylib",
            "libggml.0.dylib", "libggml-cpu.0.dylib", "libggml-blas.0.dylib", "libggml-rpc.0.dylib",
            "libggml-base.0.dylib")
MAC_OPTIONAL = ("libggml-metal.0.dylib",)  # arm64 only
WIN_LIBS = ("llama-server-impl.dll", "llama-common.dll", "mtmd.dll", "llama.dll", "ggml.dll",
            "ggml-base.dll", "libomp.dll")

NOTICE = f"""llama.cpp
Copyright (c) 2023-2026 The llama.cpp authors
Licensed under the MIT License.
Source: https://github.com/ggml-org/llama.cpp (release {TAG}, CPU build)
"""


def sha256_of(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1 << 20), b""):
            digest.update(chunk)
    return digest.hexdigest()


def download(url: str, dest: Path, expected: str) -> Path:
    dest.parent.mkdir(parents=True, exist_ok=True)
    if dest.exists() and sha256_of(dest) == expected:
        print(f"cached  {dest.name}")
        return dest
    print(f"fetch   {url}")
    urllib.request.urlretrieve(url, dest)
    actual = sha256_of(dest)
    if actual != expected:
        dest.unlink(missing_ok=True)
        raise SystemExit(f"sha256 mismatch for {url}\n  expected {expected}\n  got      {actual}")
    return dest


def copy_file(source: Path, dest: Path, required: bool = True) -> None:
    if not source.exists():
        if required:
            raise SystemExit(f"missing in archive: {source.name}")
        return
    dest.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(source.resolve(), dest)


def extract(archive: Path, platform: str) -> Path:
    out = CACHE / f"llama-{TAG}-{platform}-extract"
    if out.exists():
        shutil.rmtree(out)
    out.mkdir(parents=True)
    if archive.suffix == ".zip":
        with zipfile.ZipFile(archive) as z:
            z.extractall(out)
        return out
    with tarfile.open(archive) as tar:
        tar.extractall(out, filter="data")
    return next(p for p in out.iterdir() if p.is_dir())


def stage(platform: str) -> None:
    suffix, sha = ARCHIVES[platform]
    archive = download(f"{BASE}/llama-{TAG}-bin-{suffix}", CACHE / f"llama-{TAG}-bin-{suffix}", sha)
    name = f"llama-cpp-cpu-{platform}"
    target = STAGING / name
    if target.exists():
        shutil.rmtree(target)
    root = target / "runtime"
    root.mkdir(parents=True)
    src = extract(archive, platform)

    if platform.startswith("win-"):
        server = "llama-server.exe"
        copy_file(src / server, root / server)
        for lib in WIN_LIBS:
            copy_file(src / lib, root / lib)
        for cpu in sorted(src.glob("ggml-cpu*.dll")):
            copy_file(cpu, root / cpu.name)
        copy_file(src / "LICENSE-LLVM-OpenMP", root / "LICENSE-LLVM-OpenMP", required=False)
    elif platform.startswith("osx-"):
        server = "llama-server"
        copy_file(src / server, root / server)
        for lib in MAC_LIBS:
            copy_file(src / lib, root / lib)
        for lib in MAC_OPTIONAL:
            copy_file(src / lib, root / lib, required=False)
    else:
        server = "llama-server"
        copy_file(src / server, root / server)
        for lib in LINUX_LIBS:
            copy_file(src / lib, root / lib)
        for cpu in sorted(src.glob("libggml-cpu-*.so")):
            if cpu.is_file():
                copy_file(cpu, root / cpu.name)
    if not platform.startswith("win-"):
        (root / server).chmod(0o755)
    if (src / "LICENSE").is_file():
        shutil.copy2(src / "LICENSE", root / "LICENSE")
    (root / "NOTICE.txt").write_text(NOTICE)
    (root / "runtime.json").write_text(json.dumps({
        "llamaVersion": TAG,
        "platform": platform,
        "server": server,
    }, indent=2) + "\n")

    # The official Linux binary already has RUNPATH=$ORIGIN. Refuse a build that does not, so a
    # future archive cannot land libs the loader will not find beside the binary.
    if platform.startswith("linux-") and shutil.which("patchelf"):
        runpath = subprocess.run(["patchelf", "--print-rpath", str(root / server)],
                                  check=True, capture_output=True, text=True).stdout.strip()
        if runpath != "$ORIGIN":
            raise SystemExit(f"llama-server RUNPATH is {runpath!r}, expected $ORIGIN")

    recipe = {
        "id": f"llama.cpp.cpu.{platform}",
        "version": "1.0.0",
        "name": "Local Assistant Engine (llama.cpp)",
        "description": "Runs a language model on this computer's processor, so the local agent "
                       "can edit the project without a graphics card.",
        "details": f"llama.cpp {TAG}, CPU build for {platform} (llama-server). "
                   f"Package id: llama.cpp.cpu.{platform}.",
        "author": "llama.cpp authors",
        "license": "MIT",
        "minAppVersion": "0.9.3",
        "platform": platform,
        "source": f"../staging/{name}",
        "provides": [{"kind": "llama-runtime", "root": "runtime", "items": 1}],
        "zstdLevel": 6,
    }
    recipe_path = HERE / f"{name}.json"
    recipe_path.write_text(json.dumps(recipe, indent=2) + "\n")

    staging_hashes.write_sidecars_under(target)
    size = sum(f.stat().st_size for f in target.rglob("*") if f.is_file() and not f.name.endswith(".sha256"))
    print(f"staged  {root} ({size / 1e6:.0f} MB) -> {recipe_path.name}")


def main() -> int:
    wanted = sys.argv[1:] or list(ARCHIVES)
    for platform in wanted:
        if platform not in ARCHIVES:
            raise SystemExit(f"unknown platform {platform}; known: {', '.join(ARCHIVES)}")
        stage(platform)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
