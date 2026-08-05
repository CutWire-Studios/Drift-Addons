"""SHA-256 sidecars for large staging artefacts that stay out of git.

Git tracks fonts, images, JSON, shaders under staging/. Weights and native libs
(*.onnx, *.bin, *.so, *.dylib, *.dll) are gitignored; a sibling `<name>.sha256`
is committed instead so clones know the expected digest. The bytes themselves
still travel via the LFS bucket (`recipes/sync-workspace.py`).
"""

from __future__ import annotations

import argparse
import hashlib
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
STAGING = ROOT / "staging"

# Must stay in sync with .gitignore patterns under staging/.
LARGE_SUFFIXES = (".onnx", ".bin", ".so", ".dylib", ".dll")
SKIP_DIR_NAMES = {".cache", "__pycache__", "node_modules"}


def is_large_artifact(path: Path) -> bool:
    name = path.name.lower()
    return any(name.endswith(suffix) for suffix in LARGE_SUFFIXES)


def sidecar_path(path: Path) -> Path:
    return path.with_name(path.name + ".sha256")


def file_sha256(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        while chunk := f.read(8 * 1024 * 1024):
            h.update(chunk)
    return h.hexdigest()


def read_sidecar(path: Path) -> str | None:
    side = sidecar_path(path)
    if not side.is_file():
        return None
    # Accept a bare digest or `sha256sum`-style "<digest>  <name>".
    first = side.read_text().splitlines()[0].strip().split()[0]
    return first.lower() if first else None


def write_sidecar(path: Path) -> Path:
    digest = file_sha256(path)
    side = sidecar_path(path)
    side.write_text(digest + "\n")
    return side


def iter_large_artifacts(root: Path) -> list[Path]:
    files: list[Path] = []
    if not root.is_dir():
        return files
    for path in root.rglob("*"):
        if not path.is_file() or not is_large_artifact(path):
            continue
        if any(part in SKIP_DIR_NAMES for part in path.relative_to(root).parts):
            continue
        files.append(path)
    return sorted(files)


def write_sidecars_under(root: Path) -> list[Path]:
    written: list[Path] = []
    for path in iter_large_artifacts(root):
        side = write_sidecar(path)
        written.append(side)
        print(f"  {side.relative_to(root)}  ({path.stat().st_size / 1e6:.1f} MB)")
    return written


def verify_artifact(path: Path) -> None:
    expected = read_sidecar(path)
    if expected is None:
        raise SystemExit(f"missing sidecar for {path}")
    if len(expected) != 64 or any(c not in "0123456789abcdef" for c in expected):
        raise SystemExit(f"malformed sidecar {sidecar_path(path)}")
    actual = file_sha256(path)
    if actual != expected:
        raise SystemExit(
            f"checksum mismatch for {path}\n"
            f"  expected {expected}\n"
            f"  actual   {actual}"
        )


def verify_under(root: Path) -> int:
    checked = 0
    for path in iter_large_artifacts(root):
        verify_artifact(path)
        checked += 1
        print(f"  ok {path.relative_to(root)}")
    return checked


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__,
                                     formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("action", nargs="?", default="write", choices=("write", "verify"),
                        help="write sidecars (default) or verify existing large files")
    parser.add_argument("--root", type=Path, default=STAGING,
                        help=f"directory to scan (default: {STAGING})")
    args = parser.parse_args()

    root = args.root.resolve()
    if not root.is_dir():
        raise SystemExit(f"not a directory: {root}")

    if args.action == "write":
        print(f"writing sidecars under {root}")
        written = write_sidecars_under(root)
        print(f"{len(written)} sidecar(s)")
    else:
        print(f"verifying large artefacts under {root}")
        checked = verify_under(root)
        if checked == 0:
            print("no large artefacts found", file=sys.stderr)
        else:
            print(f"{checked} file(s) match their sidecars")


if __name__ == "__main__":
    main()
