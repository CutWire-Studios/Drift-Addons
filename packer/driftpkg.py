"""Build and sign .driftpkg addon packages for Drift.

Container layout (little-endian), mirroring src/engine/AddonPackage.h in the app repo:

    "DRIFTPKG"          8
    formatVersion       4   uint32, currently 1
    metadataLength      4   uint32
    metadata            n   UTF-8 JSON
    payloadCompressed   8   uint64
    payloadRaw          8   uint64
    payload             n   one zstd frame, every file's bytes concatenated
    digest             32   SHA-256 over everything above
    signature          64   Ed25519 over digest

Pure stdlib plus the `zstd` and `openssl` command-line tools, matching the style of the other
build scripts. The signing key never leaves `.secrets/addon-signing.key`.
"""

import hashlib
import json
import os
import struct
import subprocess
import tempfile
from pathlib import Path

import config as drift_config

MAGIC = b"DRIFTPKG"
FORMAT_VERSION = 1
SCHEMA = 1
DEFAULT_KEY = drift_config.SIGNING_KEY
ZSTD_LEVEL = 19


def _collect(source: Path) -> list[Path]:
    """Every regular file under source, sorted so packages are reproducible."""
    files = [p for p in source.rglob("*") if p.is_file() and not p.is_symlink()]
    return sorted(files, key=lambda p: p.relative_to(source).as_posix())


def _sign(digest: bytes, key_path: Path) -> bytes:
    if not key_path.exists():
        raise SystemExit(f"signing key not found: {key_path}")
    with tempfile.TemporaryDirectory() as tmp:
        message = Path(tmp) / "digest.bin"
        message.write_bytes(digest)
        signature = Path(tmp) / "sig.bin"
        subprocess.run(
            ["openssl", "pkeyutl", "-sign", "-rawin", "-inkey", str(key_path),
             "-in", str(message), "-out", str(signature)],
            check=True,
        )
        return signature.read_bytes()


def build(recipe: dict, source: Path, out_path: Path, key_path: Path = DEFAULT_KEY) -> dict:
    """Pack `source`'s contents into out_path. Returns the metadata that was embedded."""
    source = source.resolve()
    files = _collect(source)
    if not files:
        raise SystemExit(f"no files under {source}")

    with tempfile.TemporaryDirectory() as tmp:
        raw_path = Path(tmp) / "payload.raw"
        table = []
        offset = 0
        # One solid stream: concatenate first, compress once. Per-file compression would cost
        # several MB on a font pack, since the faces share so much structure.
        with raw_path.open("wb") as raw:
            for path in files:
                data = path.read_bytes()
                table.append({
                    "path": path.relative_to(source).as_posix(),
                    "offset": offset,
                    "size": len(data),
                    "sha256": hashlib.sha256(data).hexdigest(),
                })
                raw.write(data)
                offset += len(data)

        payload_raw = offset
        compressed_path = Path(tmp) / "payload.zst"
        # Level 19 pays for itself on text-shaped content like font tables, but ONNX fp16 weights
        # are close to incompressible and the extra hours buy a fraction of a percent — those
        # recipes set a lower level.
        level = recipe.get("zstdLevel", ZSTD_LEVEL)
        subprocess.run(
            ["zstd", f"-{level}", "-q", "-f", "-T0", "--long=27",
             str(raw_path), "-o", str(compressed_path)],
            check=True,
        )
        payload = compressed_path.read_bytes()

    provides = []
    for entry in recipe["provides"]:
        root = source / entry["root"]
        if not root.is_dir():
            raise SystemExit(f"provides root {entry['root']!r} is not a directory in {source}")
        items = entry.get("items")
        if items is None:
            items = sum(1 for child in root.iterdir() if child.is_dir()) or 1
        provides.append({"kind": entry["kind"], "root": entry["root"], "items": items})

    metadata = {
        "schema": SCHEMA,
        "id": recipe["id"],
        "version": recipe["version"],
        "name": recipe["name"],
        "description": recipe.get("description", ""),
        # Optional deeper copy for power users — shown behind an info control, not in the
        # catalogue row. Leave it out for packs that have nothing technical to say.
        "details": recipe.get("details", ""),
        "author": recipe.get("author", "CutWire"),
        "license": recipe.get("license", ""),
        "minAppVersion": recipe.get("minAppVersion", "0.1.0"),
        # Set only by packages carrying native code (the ONNX Runtime and execution provider
        # addons). Drift refuses to install one whose platform is not its own — a mismatched
        # native package installs perfectly and then fails to load, which is far harder to
        # explain than a refusal. Content packages leave it out and run anywhere.
        "platform": recipe.get("platform", ""),
        "installedSize": payload_raw,
        "provides": provides,
        "files": table,
    }
    meta_bytes = json.dumps(metadata, separators=(",", ":"), sort_keys=True).encode()

    body = bytearray()
    body += MAGIC
    body += struct.pack("<II", FORMAT_VERSION, len(meta_bytes))
    body += meta_bytes
    body += struct.pack("<QQ", len(payload), payload_raw)
    body += payload

    digest = hashlib.sha256(body).digest()
    signature = _sign(digest, key_path)
    if len(signature) != 64:
        raise SystemExit(f"unexpected Ed25519 signature length {len(signature)}")

    out_path.parent.mkdir(parents=True, exist_ok=True)
    with out_path.open("wb") as out:
        out.write(body)
        out.write(digest)
        out.write(signature)

    metadata["_packedSize"] = out_path.stat().st_size
    return metadata


def read_metadata(path: Path) -> dict:
    """Parse the manifest out of a built package, without touching the payload."""
    with path.open("rb") as f:
        header = f.read(16)
        if header[:8] != MAGIC:
            raise SystemExit(f"{path} is not a .driftpkg")
        version, meta_length = struct.unpack("<II", header[8:16])
        if version != FORMAT_VERSION:
            raise SystemExit(f"{path} uses format version {version}")
        return json.loads(f.read(meta_length))


def file_sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            digest.update(chunk)
    return digest.hexdigest()


def public_key(key_path: Path = DEFAULT_KEY) -> bytes:
    """Raw 32-byte Ed25519 public key — the trailing bytes of the DER SubjectPublicKeyInfo."""
    der = subprocess.run(
        ["openssl", "pkey", "-in", str(key_path), "-pubout", "-outform", "DER"],
        check=True, capture_output=True,
    ).stdout
    return der[-32:]
