#!/usr/bin/env python3
"""Stage the PDFium addons and write their recipes.

    ./fetch-pdfium.py                  # every platform in the table below
    ./fetch-pdfium.py linux-x64 win-x64

Drift dlopens PDFium to rasterise PDF pages at whatever zoom the timeline asks for, so the library
ships as an addon rather than being linked. Upstream is bblanchon/pdfium-binaries, which publishes
the non-V8 builds as .tgz archives for every desktop platform; the stable chromium/<n> tag is the
PDFium revision.

Unlike the ONNX Runtime archives these have no wrapping folder (lib/, bin/, include/, LICENSE sit
at the top level), so extraction is its own routine. Only the shared library, the license and the
bundled third-party licenses are staged; import libraries, headers and build metadata are skipped.

The archives are cached under ../staging/.cache.
"""

import argparse
import hashlib
import json
import shutil
import subprocess
import sys
import tarfile
import tempfile
from pathlib import Path

HERE = Path(__file__).parent
STAGING = HERE.parent / "staging"
CACHE = STAGING / ".cache"

import staging_hashes  # noqa: E402

CHROMIUM = "8086"
PACKAGE_VERSION = "1.0.0"
RELEASE = f"https://github.com/bblanchon/pdfium-binaries/releases/download/chromium%2F{CHROMIUM}"

# Drift platform tag -> (archive name, sha256, path of the shared library inside the archive).
PLATFORMS = {
    "linux-x64": ("pdfium-linux-x64.tgz",
                  "588577cf52dabc1a444988bac841920df54cc2f141801424de97ab04f4fbb935",
                  "lib/libpdfium.so"),
    "linux-arm64": ("pdfium-linux-arm64.tgz",
                    "e7e2fe4686925618330103cb167950aca5a84bb00fd977a41b86be59dd1480a2",
                    "lib/libpdfium.so"),
    "osx-arm64": ("pdfium-mac-arm64.tgz",
                  "e98679e052c07edbb5a627980902abb823d4b3f35744d877bd21668bd9fc13ab",
                  "lib/libpdfium.dylib"),
    "osx-x64": ("pdfium-mac-x64.tgz",
                "933a85a138f6027243c56bff8676375c33ceeb767401389415ffc44d689ca85d",
                "lib/libpdfium.dylib"),
    "win-x64": ("pdfium-win-x64.tgz",
                "1fd8af952832dbb0eb16d9249f68fe09e5f5ebf7c3dd9f6066ea2720cc28487d",
                "bin/pdfium.dll"),
    "win-arm64": ("pdfium-win-arm64.tgz",
                  "1799b8034e6d64946fec0ae79f3edfc8ba58ccd80c70a46194803b1eba408344",
                  "bin/pdfium.dll"),
}


def _download(url: str, name: str, sha256: str) -> Path:
    CACHE.mkdir(parents=True, exist_ok=True)
    path = CACHE / name
    if not path.exists():
        print(f"downloading {url}")
        subprocess.run(["curl", "-sSfL", url, "-o", str(path)], check=True)

    digest = hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            digest.update(chunk)
    if digest.hexdigest() != sha256:
        path.unlink()
        sys.exit(f"{name} failed its checksum — deleted, try again")
    return path


def _extract(archive: Path, into: Path) -> None:
    """Unpack a flat archive, refusing anything that is not a plain file or directory."""
    with tarfile.open(archive) as tf:
        for member in tf.getmembers():
            parts = Path(member.name).parts
            if member.name.startswith("/") or ".." in parts:
                sys.exit(f"unsafe path in {archive.name}: {member.name}")
            if not (member.isfile() or member.isdir()):
                continue
            tf.extract(member, into, filter="data")


def _reset(name: str) -> Path:
    target = STAGING / name
    if target.exists():
        shutil.rmtree(target)
    target.mkdir(parents=True)
    return target


def _write_recipe(recipe: dict) -> Path:
    out_dir = HERE / "pdfium"
    out_dir.mkdir(exist_ok=True)
    path = out_dir / f"{recipe['id']}.json"
    path.write_text(json.dumps(recipe, indent=2) + "\n")
    return path


def stage(platform: str) -> None:
    archive_name, sha256, library = PLATFORMS[platform]
    archive = _download(f"{RELEASE}/{archive_name}", archive_name, sha256)

    name = f"pdfium-{platform}"
    target = _reset(name)
    root = target / "pdfium"
    lib = root / "lib"
    lib.mkdir(parents=True)

    with tempfile.TemporaryDirectory() as tmp:
        _extract(archive, Path(tmp))
        prefix = Path(tmp)
        source = prefix / library
        if not source.is_file():
            sys.exit(f"{archive_name} has no {library}")
        shutil.copy2(source, lib / source.name)
        shutil.copy2(prefix / "LICENSE", root / "LICENSE")
        if (prefix / "licenses").is_dir():
            shutil.copytree(prefix / "licenses", root / "licenses")

    (root / "pdfium.json").write_text(json.dumps({
        "chromium": CHROMIUM,
        "platform": platform,
    }, indent=2) + "\n")

    recipe = _write_recipe({
        "id": f"pdfium.{platform}",
        "version": PACKAGE_VERSION,
        "name": "PDF Viewer",
        "description": "Shows PDF pages on the timeline, sharp at any zoom.",
        "details": (
            "Google's PDFium rendering library, used to rasterise PDF pages at the zoom the "
            f"timeline needs. Upstream: chromium/{CHROMIUM} build by bblanchon/pdfium-binaries. "
            f"Platform: {platform}."
        ),
        "author": "Google (PDFium)",
        "license": "BSD-3-Clause",
        "minAppVersion": "0.8.0",
        "platform": platform,
        "source": f"../../staging/{name}",
        "provides": [{"kind": "pdfium", "root": "pdfium", "items": 1}],
        "zstdLevel": 6,
    })
    size = sum(f.stat().st_size for f in target.rglob("*") if f.is_file())
    print(f"{name}: {size / 1e6:.0f} MB -> {recipe.relative_to(HERE.parent)}")


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("platforms", nargs="*", metavar="PLATFORM",
                        help="defaults to every platform upstream publishes")
    args = parser.parse_args()

    for platform in args.platforms or list(PLATFORMS):
        if platform not in PLATFORMS:
            sys.exit(f"upstream publishes no PDFium build for {platform}")
        stage(platform)

    print("sha256 sidecars:")
    staging_hashes.write_sidecars_under(STAGING)


if __name__ == "__main__":
    main()
