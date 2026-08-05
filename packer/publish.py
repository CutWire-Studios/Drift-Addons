#!/usr/bin/env python3
"""Upload built packages to R2 and regenerate the index the Worker serves.

    ./publish.py ../dist/*.driftpkg

Object layout in the bucket:

    addons/<id>/<version>/<id>-<version>.driftpkg    immutable
    index.json                                        the only mutable object

The index is rebuilt from whatever is passed in plus whatever is already in the index, so
publishing one addon does not drop the others. The Worker rewrites each entry's `key` into a
signed, expiring URL before handing the index to a client.
"""

import argparse
import json
import os
import subprocess
import sys
import tempfile
from datetime import datetime, timezone
from pathlib import Path

import config as drift_config
import driftpkg
import s3

INDEX_KEY = "index.json"
WORKER_DIR = Path(__file__).parent.parent / "worker"
# wrangler refuses anything larger; above this we sign a multipart upload ourselves.
WRANGLER_MAX_BYTES = 300 * 1024 * 1024


def _bucket() -> str:
    return drift_config.publish_bucket()


def _use_s3() -> bool:
    if s3.SECRETS.exists():
        return True
    return bool(os.environ.get("R2_ACCESS_KEY_ID") and os.environ.get("R2_SECRET_ACCESS_KEY"))


def _wrangler(*args: str, capture: bool = False) -> subprocess.CompletedProcess:
    config_path = drift_config.materialize_wrangler()
    return subprocess.run(
        ["bunx", "wrangler", *args, "--config", str(config_path), "--remote"],
        cwd=WORKER_DIR, check=True, text=True,
        capture_output=capture,
    )


def _put(key: str, path: Path, content_type: str) -> None:
    bucket = _bucket()
    if _use_s3():
        if path.stat().st_size > WRANGLER_MAX_BYTES:
            s3.upload(bucket, key, path, content_type)
        else:
            s3.put_file(bucket, key, path, content_type)
        return
    if path.stat().st_size > WRANGLER_MAX_BYTES:
        s3.upload(bucket, key, path, content_type)
        return
    # Absolute: wrangler runs with cwd=WORKER_DIR so relative paths in the config still resolve.
    _wrangler("r2", "object", "put", f"{bucket}/{key}",
              "--file", str(path.resolve()), "--content-type", content_type)


def _fetch_index() -> dict:
    bucket = _bucket()
    if _use_s3():
        raw = s3.get_bytes(bucket, INDEX_KEY)
        if raw is None:
            return {"schema": 1, "addons": []}
        index = json.loads(raw)
        if not isinstance(index, dict):
            return {"schema": 1, "addons": []}
        return index
    with tempfile.TemporaryDirectory() as tmp:
        target = Path(tmp) / "index.json"
        try:
            _wrangler("r2", "object", "get", f"{bucket}/{INDEX_KEY}",
                      "--file", str(target), capture=True)
        except subprocess.CalledProcessError:
            return {"schema": 1, "addons": []}
        return json.loads(target.read_text())


def entry_for(package: Path) -> dict:
    meta = driftpkg.read_metadata(package)
    version = meta["version"]
    addon_id = meta["id"]
    # One index serves every platform. A row that names none is offered to everyone; a row that
    # names some is dropped by clients that are not on the list, which is how the per-platform
    # runtime packages stay invisible to the wrong machines.
    platforms = [meta["platform"]] if meta.get("platform") else []
    return {
        "id": addon_id,
        "version": version,
        "name": meta["name"],
        "description": meta.get("description", ""),
        "details": meta.get("details", ""),
        "author": meta.get("author", ""),
        "license": meta.get("license", ""),
        "minAppVersion": meta.get("minAppVersion", "0.1.0"),
        # The primary kind drives filtering in the Addon Manager; `provides` carries the rest.
        "kind": meta["provides"][0]["kind"],
        "provides": [{"kind": p["kind"], "items": p["items"]} for p in meta["provides"]],
        "platforms": platforms,
        "installedSize": meta["installedSize"],
        "downloadSize": package.stat().st_size,
        "sha256": driftpkg.file_sha256(package),
        "key": f"addons/{addon_id}/{version}/{package.name}",
    }


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("packages", nargs="+", type=Path)
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()

    index = _fetch_index() if not args.dry_run else {"schema": 1, "addons": []}
    by_id = {addon["id"]: addon for addon in index.get("addons", [])}

    for package in args.packages:
        entry = entry_for(package)
        print(f"{entry['id']} {entry['version']}  {entry['downloadSize'] / 1e6:.1f} MB")
        if not args.dry_run:
            _put(entry["key"], package, "application/octet-stream")
        by_id[entry["id"]] = entry

    index = {
        "schema": 1,
        "generated": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "addons": sorted(by_id.values(), key=lambda a: a["id"]),
    }

    if args.dry_run:
        json.dump(index, sys.stdout, indent=2)
        print()
        return

    with tempfile.TemporaryDirectory() as tmp:
        path = Path(tmp) / "index.json"
        path.write_text(json.dumps(index, indent=2))
        _put(INDEX_KEY, path, "application/json")

    print(f"index.json updated: {len(index['addons'])} addons")


if __name__ == "__main__":
    main()
