#!/usr/bin/env python3
"""Stage the Qwen3.5 4B local-agent model (Q4_K_M GGUF).

    ./fetch-qwen35-4b.py

Q4_K_M is the CPU quant: about 2.7 GB, and llama.cpp's CPU kernels run it. The BF16
file is 8.4 GB and slower on a processor. No vision projector — the agent uses text
tools only. The weight file is cached under ../staging/.cache and is not committed.
"""

import hashlib
import subprocess
import sys
from pathlib import Path

HERE = Path(__file__).parent
STAGING = HERE.parent / "staging"
CACHE = STAGING / ".cache"

sys.path.insert(0, str(HERE))
import staging_hashes  # noqa: E402

REVISION = "e87f176479d0855a907a41277aca2f8ee7a09523"
FILENAME = "Qwen3.5-4B-Q4_K_M.gguf"
URL = f"https://huggingface.co/unsloth/Qwen3.5-4B-GGUF/resolve/{REVISION}/{FILENAME}"
# Hugging Face LFS oid (x-linked-etag). A changed file under this revision fails the check.
MODEL_SHA256 = "00fe7986ff5f6b463e62455821146049db6f9313603938a70800d1fb69ef11a4"

NOTICE = f"""Qwen3.5-4B
Copyright 2026 Alibaba Cloud
Licensed under the Apache License, Version 2.0.
Weights: https://huggingface.co/Qwen/Qwen3.5-4B
GGUF (Q4_K_M): https://huggingface.co/unsloth/Qwen3.5-4B-GGUF (revision {REVISION})
Quantized by Unsloth. Text weights only; the vision projector is not included.
"""


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
    out = STAGING / "qwen35-4b" / "models" / "qwen35-4b"
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
    staging_hashes.write_sidecars_under(STAGING / "qwen35-4b")
    print(f"staged  {out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
