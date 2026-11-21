#!/usr/bin/env python3
"""Stage the Drift command-bar model (Qwen3-0.6B fine-tune, Q6_K GGUF).

    ./fetch-drift-command-qwen3.py

Fine-tuned by CutWire Studios to turn typed editing commands into tool calls. About 495 MB.
The weight file is cached under ../staging/.cache and is not committed.
"""

import hashlib
import json
import subprocess
import sys
from pathlib import Path

HERE = Path(__file__).parent
STAGING = HERE.parent / "staging"
CACHE = STAGING / ".cache"

sys.path.insert(0, str(HERE))
import staging_hashes  # noqa: E402

REVISION = "4962a7c8aaf3f3f22a8eed0498372dba57035d3d"
FILENAME = "drift-command-qwen3-0.6b.Q6_K.gguf"
URL = f"https://huggingface.co/CutWire-Studios/drift-command-qwen3-0.6b/resolve/{REVISION}/gguf/{FILENAME}"
# Hugging Face LFS oid (x-linked-etag). A changed file under this revision fails the check.
MODEL_SHA256 = "1fd406e0428b17131cbb8aa068a287a2a07500193c583f5cb2dc5e63b593f34e"

NOTICE = f"""Drift Command Bar Model (drift-command-qwen3-0.6b)
Licensed under the Apache License, Version 2.0.
Base model: Qwen/Qwen3-0.6B (Copyright 2025 Alibaba Cloud), https://huggingface.co/Qwen/Qwen3-0.6B
Fine-tuned by CutWire Studios on the dataset CutWire-Studios/drift-command-calls.
Weights: https://huggingface.co/CutWire-Studios/drift-command-qwen3-0.6b (revision {REVISION}), Q6_K GGUF.
"""

MODEL_JSON = {"format": "qwen3-chat", "variant": "full", "context": 8192, "tools_k": 10,
              "decode": "raw-completion"}


def sha256_of(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(8 << 20), b""):
            digest.update(chunk)
    return digest.hexdigest()


def download(url: str, dest: Path, expected: str) -> Path:
    dest.parent.mkdir(parents=True, exist_ok=True)
    if dest.exists() and sha256_of(dest) == expected:
        print(f"cached  {dest.name}")
        return dest
    print(f"fetch   {url}")
    subprocess.run(["curl", "-fL", "--retry", "5", "-C", "-", "-o", str(dest), url], check=True)
    actual = sha256_of(dest)
    if actual != expected:
        dest.unlink(missing_ok=True)
        raise SystemExit(f"sha256 mismatch for {url}\n  expected {expected}\n  got      {actual}")
    return dest


def main() -> int:
    model = download(URL, CACHE / FILENAME, MODEL_SHA256)
    out = STAGING / "drift-command-qwen3" / "models" / "drift-command-qwen3"
    out.mkdir(parents=True, exist_ok=True)
    dest = out / FILENAME
    if not dest.exists() or dest.stat().st_size != model.stat().st_size:
        # Hard link when the cache and the staging tree share a filesystem; the weight
        # file is 2.7 GB and a second copy is only needed if the link fails.
        if dest.exists():
            dest.unlink()
        try:
            dest.hardlink_to(model)
        except OSError:
            subprocess.run(["cp", "-a", str(model), str(dest)], check=True)
    (out / "NOTICE.txt").write_text(NOTICE)
    (out / "model.json").write_text(json.dumps(MODEL_JSON, indent=2) + "\n")
    staging_hashes.write_sidecars_under(STAGING / "drift-command-qwen3")
    print(f"staged  {out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
