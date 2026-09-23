#!/usr/bin/env python3
"""Stage the speech detection addon (Silero VAD v5).

    ./fetch-silero-vad.py

Downloads silero_vad.onnx from a pinned Silero release and writes the constants Drift checks
beside it. The archive is cached under ../staging/.cache.

The v5 graph takes 64 samples of context from the previous window plus 512 new samples at
16 kHz, a [2,1,128] recurrent state and the sample rate, and returns one speech probability per
window. Drift's SileroVad feeds it exactly that; a different export (v4 had h/c states, 16 kHz
windows of 512 without context) would load but read garbage.
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

TAG = "v5.1.2"
MODEL_URL = f"https://github.com/snakers4/silero-vad/raw/{TAG}/src/silero_vad/data/silero_vad.onnx"
# Pinned: a changed asset under the same tag would silently change what ships.
MODEL_SHA256 = "2623a2953f6ff3d2c1e61740c6cdb7168133479b267dfef114a4a3cc5bdd788f"

NOTICE = f"""Silero VAD
Copyright (c) 2020-present Silero Team
Licensed under the MIT License.
Source: https://github.com/snakers4/silero-vad (release {TAG})
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
    out = STAGING / "silero-vad" / "models" / "silero-vad"
    out.mkdir(parents=True, exist_ok=True)

    model = download(MODEL_URL, CACHE / f"silero_vad-{TAG}.onnx", MODEL_SHA256)
    (out / "silero_vad.onnx").write_bytes(model.read_bytes())
    (out / "config.json").write_text(
        json.dumps({"sample_rate": 16000, "window": 512, "context": 64, "version": TAG}, indent=1) + "\n"
    )
    (out / "NOTICE.txt").write_text(NOTICE)

    staging_hashes.write_sidecars_under(STAGING / "silero-vad")
    print(f"staged  {out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
