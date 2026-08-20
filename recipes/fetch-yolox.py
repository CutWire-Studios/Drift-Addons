#!/usr/bin/env python3
"""Stage the object detection addon (YOLOX-Tiny).

    ./fetch-yolox.py

Downloads the ONNX model Megvii publishes with the YOLOX release and writes the constants
Drift reads beside it. Like fetch-onnxruntime.py this downloads rather than copying a local
asset, so it needs network on first run; the archive is cached under ../staging/.cache.

Why YOLOX rather than an Ultralytics YOLO: Ultralytics release their *trained weights* under
AGPL-3.0, not just the training code. Drift is GPL-3.0 and GPLv3 s13 permits the combination,
but the addon would then carry AGPL terms and this bucket would be the thing distributing it.
YOLOX is Apache-2.0 and has the same COCO 80 classes.

The published export does NOT bake in the grid decode — its raw cx/cy come out around -2..2
rather than spanning the 416px input — so Drift's ObjectDetector reapplies grid and stride.
Anything restaged here has to keep that property or the boxes land in the wrong place.
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

MODEL_URL = (
    "https://github.com/Megvii-BaseDetection/YOLOX/releases/download/"
    "0.1.1rc0/yolox_tiny.onnx"
)
# Pinned: a release asset that changed underneath us would silently change what ships.
MODEL_SHA256 = "427cc366d34e27ff7a03e2899b5e3671425c262ea2291f88bb942bc1cc70b0f7"

# YOLOX-Tiny takes a 416x416 letterbox. The class list is COCO's, in the model's own order —
# the index into this list is what the network emits, so the order is part of the contract.
INPUT_SIZE = 416
COCO_CLASSES = [
    "person", "bicycle", "car", "motorcycle", "airplane", "bus", "train", "truck", "boat",
    "traffic light", "fire hydrant", "stop sign", "parking meter", "bench", "bird", "cat",
    "dog", "horse", "sheep", "cow", "elephant", "bear", "zebra", "giraffe", "backpack",
    "umbrella", "handbag", "tie", "suitcase", "frisbee", "skis", "snowboard", "sports ball",
    "kite", "baseball bat", "baseball glove", "skateboard", "surfboard", "tennis racket",
    "bottle", "wine glass", "cup", "fork", "knife", "spoon", "bowl", "banana", "apple",
    "sandwich", "orange", "broccoli", "carrot", "hot dog", "pizza", "donut", "cake", "chair",
    "couch", "potted plant", "bed", "dining table", "toilet", "tv", "laptop", "mouse",
    "remote", "keyboard", "cell phone", "microwave", "oven", "toaster", "sink", "refrigerator",
    "book", "clock", "vase", "scissors", "teddy bear", "hair drier", "toothbrush",
]

NOTICE = """YOLOX
Copyright (c) 2021-2022 Megvii Inc. All rights reserved.
Licensed under the Apache License, Version 2.0.
Source: https://github.com/Megvii-BaseDetection/YOLOX

The bundled yolox_tiny.onnx is the export published with YOLOX release 0.1.1rc0.
Trained on COCO 2017 (https://cocodataset.org), CC BY 4.0.
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
    out = STAGING / "yolox-tiny" / "models" / "yolox-tiny"
    out.mkdir(parents=True, exist_ok=True)

    model = download(MODEL_URL, CACHE / "yolox_tiny.onnx", MODEL_SHA256)
    (out / "yolox_tiny.onnx").write_bytes(model.read_bytes())

    # Drift refuses a model directory unless every file is present, so constants.json is not
    # optional — a half-staged folder must not look installed.
    (out / "constants.json").write_text(
        json.dumps({"inputSize": INPUT_SIZE, "classes": COCO_CLASSES}, indent=1) + "\n"
    )
    (out / "NOTICE.txt").write_text(NOTICE)

    staging_hashes.write_sidecars_under(STAGING / "yolox-tiny")
    print(f"staged  {out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
