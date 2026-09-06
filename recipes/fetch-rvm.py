#!/usr/bin/env python3
"""Stage the people-cutout addons (Robust Video Matting).

    ./fetch-rvm.py

Downloads the ONNX exports Peter Lin publishes with the RVM v1.0.0 release and writes the constants
Drift reads beside them. Like fetch-yolox.py this downloads rather than copying a local asset, so it
needs network on first run; the files are cached under ../staging/.cache.

Two packages, because they are two different trade-offs rather than two qualities of one thing:

    rvm-mobilenetv3   22 MB, fp32 + fp16, several times faster — the one to install
    rvm-resnet50     107 MB, fp32 only, better edges on hard footage

Both declare kind "rvm-model" and are identified at runtime by the "variant" in their constants.json,
not by their directory name, so they install side by side and Drift offers the choice.

Why RVM alongside SAM2 rather than instead of it: RVM takes no prompt and knows only one subject —
people — so it cannot be told which object to cut out. In exchange it needs no interaction, runs an
order of magnitude faster, and produces soft alpha plus a colour-decontaminated foreground, which is
what makes hair survive the cutout.

RVM is GPL-3.0, unlike every other model addon here. Drift is GPL-3.0 too, so redistributing it is
fine, but the recipe's license field has to say so.

Both exports declare dynamic height and width, but the recurrent decoder halves the feature map four
times, so only multiples of 16 actually work — Drift's RvmMatter pads frames up and crops the
outputs back. Anything restaged here has to keep that property.
"""

import hashlib
import json
import sys
import urllib.request
from pathlib import Path

HERE = Path(__file__).parent
STAGING = HERE.parent / "staging"
CACHE = STAGING / ".cache"

sys.path.insert(0, str(HERE))
import staging_hashes  # noqa: E402

RELEASE = "https://github.com/PeterL1n/RobustVideoMatting/releases/download/v1.0.0"

# Pinned: a release asset that changed underneath us would silently change what ships.
WEIGHTS = {
    "rvm_mobilenetv3_fp32.onnx": "88d4531297118f595bf2fd60f6f566aec2e559393802d1f436c380f0cbbd2828",
    "rvm_mobilenetv3_fp16.onnx": "6a0d5ce6cc17702613be548559879b4521ed424cfe14ddc48d1acaa44d616f64",
    "rvm_resnet50_fp32.onnx": "25db300fcb6ee27f941a1b52c97856e8d1f13c7f35817f81a612f89af0e8a85c",
}

# staging dir -> (package root, constants.json). "files" is the contract with RvmMatter: a precision
# only counts as installed when the file it names is actually on disk, so a half-synced addon does
# not look complete. fp16 is optional and is only used when a GPU execution provider is active.
PACKAGES = {
    "rvm-mobilenetv3": (
        "models/rvm",
        {
            "model": "rvm_mobilenetv3",
            "variant": "mobilenetv3",
            "files": {
                "fp32": "rvm_mobilenetv3_fp32.onnx",
                "fp16": "rvm_mobilenetv3_fp16.onnx",
            },
        },
    ),
    "rvm-resnet50": (
        "models/rvm-resnet50",
        {
            "model": "rvm_resnet50",
            "variant": "resnet50",
            "files": {"fp32": "rvm_resnet50_fp32.onnx"},
        },
    ),
}

NOTICE = """Robust Video Matting
Copyright (c) 2021 Peter Lin
Licensed under the GNU General Public License v3.0.
Source: https://github.com/PeterL1n/RobustVideoMatting

The bundled weights are the ONNX exports published with RVM release v1.0.0.
Trained on VideoMatte240K, Distinctions-646 and Adobe Image Matting.
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


def main() -> int:
    for name, digest in WEIGHTS.items():
        download(f"{RELEASE}/{name}", CACHE / name, digest)

    for package, (root, constants) in PACKAGES.items():
        out = STAGING / package / root
        out.mkdir(parents=True, exist_ok=True)
        for name in constants["files"].values():
            (out / name).write_bytes((CACHE / name).read_bytes())
        (out / "constants.json").write_text(json.dumps(constants, indent=1) + "\n")
        (out / "NOTICE.txt").write_text(NOTICE)
        staging_hashes.write_sidecars_under(STAGING / package)
        print(f"staged  {out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
