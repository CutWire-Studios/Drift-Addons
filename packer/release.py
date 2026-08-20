#!/usr/bin/env python3
"""Refresh the GitHub release that mirrors the current packages.

    ./release.py                # sync assets and notes from ../dist
    ./release.py --dry-run      # show what would change

Run after publish.py. That uploads to R2, which is where Drift actually fetches from; this
keeps the public GitHub mirror in step so the two do not drift apart.

The release carries exactly the newest build of each package — publishing 1.4.0 removes the
1.3.0 asset, because a release holding two versions of one addon just invites the wrong
download. Notes are regenerated every run from what is actually attached.

The tag is deliberately not a version (packages move independently), so it is reused rather
than created fresh. The script never moves it: after a force-push the tag keeps pointing at
whatever commit it was cut from, which is harmless for an asset host.
"""

import argparse
import json
import subprocess
from pathlib import Path

import driftpkg

REPO = "CutWire-Studios/Drift-Addons"
TAG = "packages"
TITLE = "Addon packages"
DIST = Path(__file__).parent.parent / "dist"


def _gh(*args: str, check: bool = True) -> subprocess.CompletedProcess:
    return subprocess.run(["gh", *args, "--repo", REPO],
                          check=check, text=True, capture_output=True)


def latest_packages() -> list[tuple[dict, Path]]:
    """Newest build of each addon id in dist/, as (manifest, path)."""
    best: dict[str, tuple[tuple[int, ...], dict, Path]] = {}
    for path in sorted(DIST.glob("*.driftpkg")):
        meta = driftpkg.read_metadata(path)
        key = tuple(int(part) for part in meta["version"].split("."))
        current = best.get(meta["id"])
        if current is None or key > current[0]:
            best[meta["id"]] = (key, meta, path)
    return [(meta, path) for _, meta, path in sorted(best.values(), key=lambda b: b[1]["id"])]


def current_assets() -> dict[str, int] | None:
    """Attached asset name -> size, or None when the release does not exist yet."""
    done = _gh("release", "view", TAG, "--json", "assets", check=False)
    if done.returncode != 0:
        return None
    return {a["name"]: a["size"] for a in json.loads(done.stdout)["assets"]}


def notes(rows: list[tuple[dict, Path, str]]) -> str:
    total = sum(path.stat().st_size for _, path, _ in rows)
    lines = [
        "The current release of every Drift addon package. Older versions are not included — each",
        "row below is the newest build of that package.",
        "",
        "You do not need to download these by hand. Drift installs addons for you from **Extra "
        "packs**",
        "in its settings, and verifies each package's signature before installing it. These files "
        "are",
        "here for mirroring, offline installs, and anyone who wants to inspect what the app fetches.",
        "",
        "| Package | Name | Version | Size |",
        "| --- | --- | --- | --- |",
    ]
    for meta, path, _ in rows:
        lines.append(f"| `{meta['id']}` | {meta['name']} | {meta['version']} | "
                     f"{path.stat().st_size / 1e6:.1f} MB |")
    lines += [
        "",
        f"{len(rows)} packages, {total / 1e6:.0f} MB total.",
        "",
        "## Verifying a download",
        "",
        "Every package is signed with the Ed25519 key Drift trusts, and the app checks that "
        "signature",
        "before it installs anything. The SHA-256 sums below let you check a download "
        "independently:",
        "",
        "```",
    ]
    lines += [f"{digest}  {path.name}" for _, path, digest in rows]
    lines.append("```")
    return "\n".join(lines) + "\n"


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--force", action="store_true",
                        help="re-upload every asset, not just the ones that look changed")
    args = parser.parse_args()

    packages = latest_packages()
    if not packages:
        raise SystemExit(f"no packages in {DIST}")

    attached = current_assets()
    wanted = {path.name: path for _, path in packages}
    stale = sorted(set(attached) - set(wanted)) if attached else []
    # Size is the only cheap thing GitHub reports back, so a rebuild that lands on the same byte
    # count is not detected. --clobber on every upload would cost a full re-push of 1 GB, so
    # prefer the cheap check and let a same-size rebuild be re-pushed with --force.
    missing = [p for name, p in wanted.items()
               if args.force or attached is None or attached.get(name) != p.stat().st_size]

    for name in stale:
        print(f"- {name}")
    for path in missing:
        print(f"+ {path.name}  {path.stat().st_size / 1e6:.1f} MB")
    if not stale and not missing:
        print("assets already in sync")

    if args.dry_run:
        return

    print("hashing…")
    rows = [(meta, path, driftpkg.file_sha256(path)) for meta, path in packages]
    body = notes(rows)

    if attached is None:
        _gh("release", "create", TAG, "--title", TITLE, "--notes", body)
        print(f"created release {TAG}")
    else:
        _gh("release", "edit", TAG, "--notes", body)

    for name in stale:
        _gh("release", "delete-asset", TAG, name, "--yes")
    for path in missing:
        print(f"uploading {path.name}…")
        _gh("release", "upload", TAG, str(path), "--clobber")

    print(f"{TAG}: {len(rows)} assets, notes refreshed")


if __name__ == "__main__":
    main()
