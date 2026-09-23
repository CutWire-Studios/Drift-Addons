#!/usr/bin/env python3
"""Stage the English word-timing addon (wav2vec2-base-960h CTC).

    ./fetch-wav2vec2.py

Downloads a pinned revision of Xenova's ONNX export of facebook/wav2vec2-base-960h (the 8-bit
quantized graph, ~95 MB) plus its vocabulary, and writes the aligner.json Drift's CtcAligner
reads. Cached under ../staging/.cache.

The graph takes input_values [1, T] (16 kHz, zero-mean/unit-variance per call) and returns
logits [1, frames, 32], one frame per 20 ms. Index 0 (<pad>) is the CTC blank and "|" separates
words; the letters are upper case. A different model can be staged for another language by
writing the same three files: model.onnx, vocab.json and aligner.json with its language code.
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

REVISION = "a19f851b3d42865797e410752b4c570c871e4825"
BASE = f"https://huggingface.co/Xenova/wav2vec2-base-960h/resolve/{REVISION}"
FILES = {
    # published path: (staged name, sha256)
    "onnx/model_quantized.onnx": ("model.onnx", "cd5040c147381580ed73258143dd8e0c28e800a09e74ee42ee2b3e8cb4d760a3"),
    "vocab.json": ("vocab.json", None),
}

NOTICE = f"""wav2vec2-base-960h
Copyright (c) Facebook, Inc. and its affiliates.
Licensed under the Apache License, Version 2.0.
Model: https://huggingface.co/facebook/wav2vec2-base-960h
ONNX export: https://huggingface.co/Xenova/wav2vec2-base-960h (revision {REVISION})
Fine-tuned on LibriSpeech (http://www.openslr.org/12), CC BY 4.0.
"""


def sha256_of(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1 << 20), b""):
            digest.update(chunk)
    return digest.hexdigest()


def download(url: str, dest: Path, expected) -> Path:
    dest.parent.mkdir(parents=True, exist_ok=True)
    if dest.exists() and (expected is None or sha256_of(dest) == expected):
        print(f"cached  {dest.name}")
        return dest
    print(f"fetch   {url}")
    urllib.request.urlretrieve(url, dest)
    if expected is not None:
        actual = sha256_of(dest)
        if actual != expected:
            dest.unlink(missing_ok=True)
            raise SystemExit(f"sha256 mismatch for {url}\n  expected {expected}\n  got      {actual}")
    return dest


def main() -> int:
    out = STAGING / "wav2vec2-en" / "models" / "align" / "en"
    out.mkdir(parents=True, exist_ok=True)
    for published, (name, sha) in FILES.items():
        cached = download(f"{BASE}/{published}", CACHE / f"wav2vec2-en-{REVISION[:8]}-{name}", sha)
        (out / name).write_bytes(cached.read_bytes())

    vocab = json.loads((out / "vocab.json").read_text())
    if vocab.get("<pad>") != 0 or "|" not in vocab:
        raise SystemExit("unexpected vocabulary: <pad> must be 0 and | present")
    (out / "aligner.json").write_text(json.dumps({
        "language": "en",
        "model": "model.onnx",
        "blank": 0,
        "word_sep": "|",
        "upper": True,
        "normalize": True,
        "stride": 320,
    }, indent=1) + "\n")
    (out / "NOTICE.txt").write_text(NOTICE)

    staging_hashes.write_sidecars_under(STAGING / "wav2vec2-en")
    print(f"staged  {out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
