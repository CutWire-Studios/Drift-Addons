#!/usr/bin/env python3
"""Stage the speaker labelling addon (pyannote segmentation-3.0 + 3D-Speaker ERes2Net).

    ./fetch-diarization.py

Downloads the two ONNX models sherpa-onnx publishes for offline speaker diarization and stages
them as models/diarization/{segmentation,embedding}.onnx. Drift's SpeakerDiarizer reads the
window and receptive-field constants from the segmentation model's metadata and the feature
normalisation from the embedding model's, so both must be these sherpa exports (which carry that
metadata), not the raw pyannote / 3D-Speaker checkpoints.
"""

import hashlib
import json
import sys
import tarfile
import urllib.request
from pathlib import Path

HERE = Path(__file__).parent
STAGING = HERE.parent / "staging"
CACHE = STAGING / ".cache"

sys.path.insert(0, str(HERE))
import staging_hashes  # noqa: E402

RELEASES = "https://github.com/k2-fsa/sherpa-onnx/releases/download"
SEGMENTATION_URL = f"{RELEASES}/speaker-segmentation-models/sherpa-onnx-pyannote-segmentation-3-0.tar.bz2"
SEGMENTATION_SHA256 = "24615ee884c897d9d2ba09bb4d30da6bb1b15e685065962db5b02e76e4996488"
SEGMENTATION_MODEL_SHA256 = "220ad67ca923bef2fa91f2390c786097bf305bceb5e261d4af67b38e938e1079"
# sic: the release tag really is spelled "recongition".
EMBEDDING_URL = f"{RELEASES}/speaker-recongition-models/3dspeaker_speech_eres2net_base_sv_zh-cn_3dspeaker_16k.onnx"
EMBEDDING_SHA256 = "1a331345f04805badbb495c775a6ddffcdd1a732567d5ec8b3d5749e3c7a5e4b"

NOTICE = """pyannote segmentation-3.0
Copyright (c) 2023 CNRS. Licensed under the MIT License.
Source: https://huggingface.co/pyannote/segmentation-3.0

3D-Speaker ERes2Net (speech_eres2net_base_sv_zh-cn_3dspeaker_16k)
Copyright (c) Alibaba, Inc. and its affiliates. Licensed under the Apache License, Version 2.0.
Source: https://github.com/modelscope/3D-Speaker

ONNX exports with inference metadata by sherpa-onnx (Apache-2.0):
https://github.com/k2-fsa/sherpa-onnx
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
    out = STAGING / "speaker-diarization" / "models" / "diarization"
    out.mkdir(parents=True, exist_ok=True)

    archive = download(SEGMENTATION_URL, CACHE / "sherpa-onnx-pyannote-segmentation-3-0.tar.bz2", SEGMENTATION_SHA256)
    with tarfile.open(archive) as tar:
        member = tar.getmember("sherpa-onnx-pyannote-segmentation-3-0/model.onnx")
        data = tar.extractfile(member).read()
    if hashlib.sha256(data).hexdigest() != SEGMENTATION_MODEL_SHA256:
        raise SystemExit("segmentation model hash mismatch inside the archive")
    (out / "segmentation.onnx").write_bytes(data)

    embedding = download(EMBEDDING_URL, CACHE / "3dspeaker_eres2net_base_16k.onnx", EMBEDDING_SHA256)
    (out / "embedding.onnx").write_bytes(embedding.read_bytes())

    (out / "diarize.json").write_text(json.dumps({
        "segmentation": "pyannote/segmentation-3.0",
        "embedding": "3dspeaker_speech_eres2net_base_sv_zh-cn_3dspeaker_16k",
        "window_shift_ratio": 0.1,
        "threshold": 0.5,
    }, indent=1) + "\n")
    (out / "NOTICE.txt").write_text(NOTICE)

    staging_hashes.write_sidecars_under(STAGING / "speaker-diarization")
    print(f"staged  {out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
