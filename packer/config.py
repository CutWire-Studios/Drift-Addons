"""Load non-credential infra settings from `.secrets/config.env`.

    PUBLISH_BUCKET=...   # public catalogue R2 bucket (Worker + publish.py)
    LFS_BUCKET=...       # private staging/dist sync bucket (sync-workspace.py)
    WORKER_URL=...       # deployed Worker origin
"""

from __future__ import annotations

from pathlib import Path

ROOT = Path(__file__).parent.parent
SECRETS_DIR = ROOT / ".secrets"
CONFIG_PATH = SECRETS_DIR / "config.env"
SIGNING_KEY = SECRETS_DIR / "addon-signing.key"
WORKER_DIR = ROOT / "worker"
WRANGLER_TEMPLATE = WORKER_DIR / "wrangler.jsonc"
# Written next to the template so relative paths (main, $schema) keep resolving.
WRANGLER_GENERATED = WORKER_DIR / "wrangler.local.jsonc"

_BUCKET_PLACEHOLDER = "__PUBLISH_BUCKET__"


def load_env_file(path: Path) -> dict[str, str]:
    values: dict[str, str] = {}
    if not path.is_file():
        return values
    for line in path.read_text().splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, _, value = line.partition("=")
        values[key.strip()] = value.strip()
    return values


def config() -> dict[str, str]:
    if not CONFIG_PATH.is_file():
        raise SystemExit(
            f"missing {CONFIG_PATH}\n"
            "Create it with PUBLISH_BUCKET, LFS_BUCKET, and WORKER_URL."
        )
    return load_env_file(CONFIG_PATH)


def require(key: str) -> str:
    values = config()
    value = values.get(key, "").strip()
    if not value:
        raise SystemExit(f"{key} is not set in {CONFIG_PATH}")
    return value


def publish_bucket() -> str:
    return require("PUBLISH_BUCKET")


def lfs_bucket() -> str:
    return require("LFS_BUCKET")


def worker_url() -> str:
    return require("WORKER_URL")


def materialize_wrangler() -> Path:
    """Write a wrangler config with the real publish bucket; returns the path to pass to wrangler."""
    bucket = publish_bucket()
    text = WRANGLER_TEMPLATE.read_text()
    if _BUCKET_PLACEHOLDER not in text:
        raise SystemExit(
            f"{WRANGLER_TEMPLATE} is missing {_BUCKET_PLACEHOLDER!r} in bucket_name"
        )
    WRANGLER_GENERATED.parent.mkdir(parents=True, exist_ok=True)
    WRANGLER_GENERATED.write_text(text.replace(_BUCKET_PLACEHOLDER, bucket))
    return WRANGLER_GENERATED


if __name__ == "__main__":
    path = materialize_wrangler()
    print(path)
