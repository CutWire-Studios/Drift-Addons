#!/usr/bin/env python3
"""Stage the multilingual text-to-speech addon (Chatterbox Multilingual).

    ./fetch-chatterbox.py

Downloads a pinned revision of onnx-community's ONNX export of Resemble AI's Chatterbox
Multilingual (speech encoder, token embedding and q4 language model) plus the tokenizer, the
Cangjie table used for Chinese, and the default reference voice. Cached under ../staging/.cache.

The S3Gen decoder is not taken from that export: its conditional_decoder.onnx unrolls the
flow-matching solver and takes about a minute to load. ./export-chatterbox-s3gen.py exports it
from the PyTorch checkpoint as three graphs and Drift runs the solver; run it after this script.

The graphs reference their external weights by file name (*.onnx_data), so every file is staged
flat under the same name as published. constants.json carries the special tokens and the
decoder geometry Drift needs to drive the autoregressive loop and the flow-matching solver.
"""

import hashlib
import json
import shutil
import sys
import urllib.request
from pathlib import Path

HERE = Path(__file__).parent
STAGING = HERE.parent / "staging"
CACHE = STAGING / ".cache"

sys.path.insert(0, str(HERE))
import staging_hashes  # noqa: E402

REVISION = "452d3f434aa592098f1eedac9099f33642ab2da5"
BASE = f"https://huggingface.co/onnx-community/chatterbox-multilingual-ONNX/resolve/{REVISION}"
FILES = {
    # published path: (staged name, sha256)
    "onnx/speech_encoder.onnx": ("speech_encoder.onnx", "8f1c8a0f89b77bf9cd5dd8f2e034eb2c79dc00fe70d41196b28c257643b00ccb"),
    "onnx/speech_encoder.onnx_data": ("speech_encoder.onnx_data", "92f8f290fc9720e169bc2412c507209e20b03f6564bc3243739e25c56f7dfb8f"),
    "onnx/embed_tokens.onnx": ("embed_tokens.onnx", "f785819ca4f6271262d5bb8971d62796c3a909e3b031982c113dbe83a4c3b854"),
    "onnx/embed_tokens.onnx_data": ("embed_tokens.onnx_data", "2a15f7dd73b2ee47f6edf87740324011594b5a528ed6471ae55e327ed6cad68c"),
    "onnx/language_model_q4.onnx": ("language_model_q4.onnx", "7f8cdca83b2493536cbf3acf421199808a3d68736f55f4eabd20ef8a99da4313"),
    "onnx/language_model_q4.onnx_data": ("language_model_q4.onnx_data", "e79ab8784122a501718868b9631ff46e151c552d9b24e50f25d721f375e3526c"),
    "tokenizer.json": ("tokenizer.json", "29d48c4a178f6af3ad5130097c34744639e9294847b38a7b912c8c68027cb819"),
    "Cangjie5_TC.json": ("Cangjie5_TC.json", "7073fd9de919443ae88e0bd2449917a65fe54898a4413ed1edcc4b67f28bce8c"),
    "default_voice.wav": ("default_voice.wav", "3ebc531cdaba358a327099c1c4f0448026719957bcf4d8e9868767f227e02f4e"),
}

CONSTANTS = {
    "variant": "q4",
    "sampleRate": 24000,
    "startSpeechToken": 6561,
    "stopSpeechToken": 6562,
    "exaggerationToken": 6563,
    "bosToken": 255,
    "eosToken": 0,
    "numLayers": 30,
    "numKvHeads": 16,
    "headDim": 64,
    "repetitionPenalty": 1.2,
    "cfmSteps": 10,
    "cfmCfgRate": 0.7,
    "cfmSchedule": "cosine",
    "cfmTemperature": 1.0,
    "melBins": 80,
    "samplesPerMelFrame": 480,
    "languages": [
        "ar", "da", "de", "el", "en", "es", "fi", "fr", "hi", "it", "ko", "ms", "nl", "no",
        "pl", "pt", "ru", "sv", "sw", "tr", "zh",
    ],
}

S3GEN_REVISION = "5bb1f6ee58e50c3b8d408bc82a6d3740c2db6e18"
S3GEN_SHA256 = "2b78103c654207393955e4900aac14a12de8ef25f4b09424f1ef91941f161d4e"

NOTICE = f"""Chatterbox Multilingual
Copyright (c) Resemble AI.
Licensed under the MIT License.
Model: https://github.com/resemble-ai/chatterbox
ONNX export: https://huggingface.co/onnx-community/chatterbox-multilingual-ONNX (revision {REVISION})
ONNX export by onnx-community (Xenova) and Vladislav Bronzov.
S3Gen decoder (s3gen_prepare, s3gen_estimator, s3gen_vocoder): exported by recipes/export-chatterbox-s3gen.py
from https://huggingface.co/ResembleAI/chatterbox (revision {S3GEN_REVISION}, s3gen.safetensors,
sha256 {S3GEN_SHA256}).
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
    out = STAGING / "chatterbox-multilingual" / "models" / "chatterbox-multilingual"
    out.mkdir(parents=True, exist_ok=True)
    for published, (name, sha) in FILES.items():
        cached = download(f"{BASE}/{published}", CACHE / f"chatterbox-multilingual-{REVISION[:8]}-{name}", sha)
        shutil.copyfile(cached, out / name)

    (out / "constants.json").write_text(json.dumps(CONSTANTS, indent=1) + "\n")
    (out / "NOTICE.txt").write_text(NOTICE)

    staging_hashes.write_sidecars_under(STAGING / "chatterbox-multilingual")
    print(f"staged  {out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
