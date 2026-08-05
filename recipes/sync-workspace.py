#!/usr/bin/env python3
"""Sync staging/ and dist/ with the private R2 LFS bucket.

Large build artefacts stay out of GitHub; teammates share them through this bucket instead.

    python3 recipes/sync-workspace.py push              # upload local staging+dist
    python3 recipes/sync-workspace.py pull              # download into local dirs
    python3 recipes/sync-workspace.py push --only dist  # one tree
    python3 recipes/sync-workspace.py status

Uses `.secrets/r2_lfs.env` (Object Read & Write on the LFS bucket). Publish still uses `r2.env`
for the public catalogue bucket. Bucket names live in `.secrets/config.env`.

Layout in the bucket:

    staging/<relative path>
    dist/<relative path>
    _meta/staging.manifest.json
    _meta/dist.manifest.json
"""

from __future__ import annotations

import argparse
import hashlib
import json
import sys
import time
from pathlib import Path

HERE = Path(__file__).parent
ROOT = HERE.parent
sys.path.insert(0, str(ROOT / "packer"))
import config as drift_config  # noqa: E402
import s3  # noqa: E402

import staging_hashes  # noqa: E402

LFS_SECRETS = ROOT / ".secrets" / "r2_lfs.env"
TREES = ("staging", "dist")
SKIP_DIR_NAMES = {".cache", "__pycache__", "node_modules"}
CACHE_PATH = ROOT / ".secrets" / "workspace-sync-cache.json"


def file_sha256(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        while chunk := f.read(8 * 1024 * 1024):
            h.update(chunk)
    return h.hexdigest()


def load_cache() -> dict:
    if CACHE_PATH.is_file():
        return json.loads(CACHE_PATH.read_text())
    return {}


def save_cache(cache: dict) -> None:
    CACHE_PATH.parent.mkdir(parents=True, exist_ok=True)
    CACHE_PATH.write_text(json.dumps(cache, indent=2, sort_keys=True) + "\n")


def cached_sha(cache: dict, path: Path) -> str:
    """Hash path, using a mtime/size cache so unchanged multi-hundred-MB files are free."""
    st = path.stat()
    key = str(path.relative_to(ROOT))
    entry = cache.get(key)
    if entry and entry.get("size") == st.st_size and entry.get("mtime") == st.st_mtime_ns:
        return entry["sha256"]
    digest = file_sha256(path)
    cache[key] = {"size": st.st_size, "mtime": st.st_mtime_ns, "sha256": digest}
    return digest


def iter_local_files(tree: str) -> list[Path]:
    root = ROOT / tree
    if not root.is_dir():
        return []
    files: list[Path] = []
    for path in root.rglob("*"):
        if not path.is_file():
            continue
        if any(part in SKIP_DIR_NAMES for part in path.relative_to(root).parts):
            continue
        files.append(path)
    return sorted(files)


def local_manifest(tree: str, cache: dict) -> dict[str, dict]:
    out: dict[str, dict] = {}
    root = ROOT / tree
    for path in iter_local_files(tree):
        rel = path.relative_to(root).as_posix()
        out[rel] = {
            "sha256": cached_sha(cache, path),
            "size": path.stat().st_size,
        }
    return out


def remote_manifest(bucket: str, tree: str) -> dict[str, dict]:
    raw = s3.get_bytes(bucket, f"_meta/{tree}.manifest.json")
    if not raw:
        return {}
    data = json.loads(raw)
    if not isinstance(data, dict):
        return {}
    return data.get("files", data)


def write_remote_manifest(bucket: str, tree: str, files: dict[str, dict]) -> None:
    body = json.dumps({
        "tree": tree,
        "generated": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "files": files,
    }, indent=2, sort_keys=True) + "\n"
    tmp = ROOT / ".secrets" / f"{tree}.manifest.json"
    tmp.parent.mkdir(parents=True, exist_ok=True)
    tmp.write_text(body)
    try:
        s3.put_file(bucket, f"_meta/{tree}.manifest.json", tmp, "application/json")
    finally:
        tmp.unlink(missing_ok=True)


def push_tree(bucket: str, tree: str, dry_run: bool, delete: bool) -> None:
    cache = load_cache()
    print(f"hashing local {tree}/ …", flush=True)
    local = local_manifest(tree, cache)
    save_cache(cache)
    remote = remote_manifest(bucket, tree)

    uploads = [rel for rel, meta in local.items()
               if remote.get(rel, {}).get("sha256") != meta["sha256"]]
    deletes = [rel for rel in remote if rel not in local] if delete else []

    print(f"{tree}: {len(local)} local, {len(uploads)} to upload, "
          f"{len(deletes)} to delete, {len(local) - len(uploads)} unchanged")

    root = ROOT / tree
    for i, rel in enumerate(uploads, 1):
        path = root / rel
        key = f"{tree}/{rel}"
        mb = path.stat().st_size / 1e6
        print(f"  [{i}/{len(uploads)}] put {key} ({mb:.1f} MB)", flush=True)
        if not dry_run:
            s3.put_path(bucket, key, path)

    for rel in deletes:
        key = f"{tree}/{rel}"
        print(f"  delete {key}", flush=True)
        if not dry_run:
            s3.delete_object(bucket, key)

    if not dry_run:
        write_remote_manifest(bucket, tree, local)
        print(f"{tree}: manifest updated")


def pull_tree(bucket: str, tree: str, dry_run: bool, delete: bool) -> None:
    cache = load_cache()
    remote = remote_manifest(bucket, tree)
    if not remote:
        # Fall back to listing objects if no manifest yet.
        prefix = f"{tree}/"
        remote = {}
        for obj in s3.list_objects(bucket, prefix):
            rel = obj["key"][len(prefix):]
            if not rel or rel.endswith("/"):
                continue
            remote[rel] = {"sha256": obj.get("etag", ""), "size": obj["size"]}
        if not remote:
            print(f"{tree}: nothing on remote")
            return

    print(f"checking local {tree}/ …", flush=True)
    local = local_manifest(tree, cache) if (ROOT / tree).is_dir() else {}
    save_cache(cache)

    downloads = []
    for rel, meta in remote.items():
        path = ROOT / tree / rel
        if not path.is_file():
            downloads.append(rel)
            continue
        # Prefer sha when the remote manifest has a real sha256 (64 hex); etag fallback is size-only.
        remote_sha = meta.get("sha256", "")
        if len(remote_sha) == 64 and local.get(rel, {}).get("sha256") == remote_sha:
            continue
        if len(remote_sha) != 64 and path.stat().st_size == meta.get("size"):
            continue
        downloads.append(rel)

    deletes = [rel for rel in local if rel not in remote] if delete else []

    print(f"{tree}: {len(remote)} remote, {len(downloads)} to download, "
          f"{len(deletes)} to delete, {len(remote) - len(downloads)} unchanged")

    for i, rel in enumerate(downloads, 1):
        key = f"{tree}/{rel}"
        path = ROOT / tree / rel
        mb = remote[rel].get("size", 0) / 1e6
        print(f"  [{i}/{len(downloads)}] get {key} ({mb:.1f} MB)", flush=True)
        if not dry_run:
            s3.download_file(bucket, key, path)
            # Refresh cache entry after download.
            cache = load_cache()
            cached_sha(cache, path)
            save_cache(cache)
            if tree == "staging" and staging_hashes.is_large_artifact(path):
                if staging_hashes.sidecar_path(path).is_file():
                    staging_hashes.verify_artifact(path)

    for rel in deletes:
        path = ROOT / tree / rel
        print(f"  delete local {path.relative_to(ROOT)}", flush=True)
        if not dry_run and path.is_file():
            path.unlink()


def status_tree(bucket: str, tree: str) -> None:
    cache = load_cache()
    local = local_manifest(tree, cache) if (ROOT / tree).is_dir() else {}
    save_cache(cache)
    try:
        remote = remote_manifest(bucket, tree)
    except SystemExit as err:
        print(f"{tree}: remote unreachable ({err})")
        return
    only_local = sorted(set(local) - set(remote))
    only_remote = sorted(set(remote) - set(local))
    changed = sorted(
        rel for rel in set(local) & set(remote)
        if local[rel].get("sha256") != remote[rel].get("sha256")
    )
    print(f"{tree}: local={len(local)} remote={len(remote)} "
          f"changed={len(changed)} only-local={len(only_local)} only-remote={len(only_remote)}")
    for label, rows in (("changed", changed), ("only-local", only_local),
                        ("only-remote", only_remote)):
        for rel in rows[:10]:
            print(f"  {label}: {rel}")
        if len(rows) > 10:
            print(f"  … {len(rows) - 10} more {label}")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__,
                                     formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("action", choices=("push", "pull", "status"))
    parser.add_argument("--only", choices=TREES, action="append",
                        help="limit to staging and/or dist (repeatable)")
    parser.add_argument("--delete", action="store_true",
                        help="also remove files that exist only on the destination side")
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--bucket", default=None,
                        help="R2 bucket (default: LFS_BUCKET from .secrets/config.env)")
    args = parser.parse_args()

    bucket = args.bucket or drift_config.lfs_bucket()
    trees = tuple(args.only) if args.only else TREES

    if not LFS_SECRETS.is_file():
        raise SystemExit(
            f"missing {LFS_SECRETS}\n"
            "Put R2_ACCOUNT_ID / R2_ACCESS_KEY_ID / R2_SECRET_ACCESS_KEY for the "
            "LFS token there (separate from .secrets/r2.env used for publish)."
        )
    s3.use_secrets(LFS_SECRETS)

    # Fail fast with a clear message if the token cannot see the LFS bucket.
    try:
        s3.list_objects(bucket, "_meta/")
    except SystemExit as err:
        raise SystemExit(
            f"{err}\n\n"
            f"The R2 API token in {LFS_SECRETS} must allow Object Read & Write on "
            f"bucket `{bucket}`."
        ) from err

    for tree in trees:
        if args.action == "push":
            push_tree(bucket, tree, args.dry_run, args.delete)
        elif args.action == "pull":
            pull_tree(bucket, tree, args.dry_run, args.delete)
        else:
            status_tree(bucket, tree)


if __name__ == "__main__":
    main()
