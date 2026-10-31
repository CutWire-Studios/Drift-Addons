#!/usr/bin/env python3
"""Validate, compile and upload the store catalog the Worker serves at /v1/catalog.

    ./catalog.py --dry-run          print the compiled JSON and a validation summary
    ./catalog.py --out catalog.json write the compiled JSON to a file
    ./catalog.py                    upload catalog.json and media to R2

Object layout in the bucket:

    catalog/catalog.json              compiled catalog
    catalog/media/<stem>.<hash>.<ext> content-hashed images, immutable

Entries are matched against the live index, falling back to recipes/ with --offline.
"""

import argparse
import fnmatch
import hashlib
import json
import mimetypes
import shutil
import sys
import tempfile
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).parent.parent
CATALOG_DIR = ROOT / "catalog"
RECIPES_DIR = ROOT / "recipes"
CATALOG_KEY = "catalog/catalog.json"
MEDIA_PREFIX = "catalog/media/"
SCHEMA = 1

ENTRY_KEYS = {
    "id", "match", "tagline", "summary", "categories", "keywords", "icon", "accent",
    "useCases", "howTo", "unlocks", "requires", "recommends", "images", "links",
    "hidden", "order",
}


def _load(path: Path):
    try:
        return json.loads(path.read_text())
    except (OSError, json.JSONDecodeError) as error:
        raise SystemExit(f"{path}: {error}")


def recipe_rows() -> list[dict]:
    rows = []
    for path in sorted(RECIPES_DIR.glob("*.json")) + sorted(RECIPES_DIR.glob("*/*.json")):
        data = json.loads(path.read_text())
        if isinstance(data, dict) and "id" in data and "provides" in data:
            rows.append({"id": data["id"], "kind": data["provides"][0]["kind"],
                         "provides": data["provides"], "platforms": [data["platform"]] if data.get("platform") else []})
    return rows


def known_rows(index: dict | None) -> list[dict]:
    rows = {r["id"]: r for r in recipe_rows()}
    for row in (index or {}).get("addons", []):
        rows[row["id"]] = row
    return list(rows.values())


def covers(entry: dict, addon_id: str) -> bool:
    if "id" in entry:
        return entry["id"] == addon_id
    return fnmatch.fnmatchcase(addon_id, entry.get("match", ""))


def load_source() -> tuple[list, list, list]:
    categories = _load(CATALOG_DIR / "categories.json")
    collections = _load(CATALOG_DIR / "collections.json")
    entries = [_load(p) for p in sorted((CATALOG_DIR / "addons").glob("*.json"))]
    return categories, collections, entries


def validate(categories, collections, entries, rows, offline_note: str) -> tuple[list[str], list[str]]:
    errors: list[str] = []
    warnings: list[str] = []
    ids = {r["id"] for r in rows}
    kinds: dict[str, set[str]] = {}
    for r in rows:
        for p in r.get("provides", [{"kind": r.get("kind")}]):
            kinds.setdefault(p["kind"], set()).add(r["id"])
    category_ids = {c["id"] for c in categories}
    if len(category_ids) != len(categories):
        errors.append("duplicate category ids")

    def name(e):
        return e.get("id") or e.get("match") or "<unnamed>"

    for e in entries:
        label = name(e)
        if ("id" in e) == ("match" in e):
            errors.append(f"{label}: exactly one of id / match is required")
        for key in e:
            if key not in ENTRY_KEYS:
                warnings.append(f"{label}: unknown key '{key}'")
        if "id" in e and e["id"] not in ids:
            errors.append(f"{label}: id not in index or recipes")
        if "match" in e and not any(covers(e, i) for i in ids):
            errors.append(f"{label}: match covers no addon")
        for c in e.get("categories", []):
            if c not in category_ids:
                errors.append(f"{label}: unknown category '{c}'")
        for dep in e.get("requires", []):
            if "id" in dep:
                if dep["id"] not in ids:
                    errors.append(f"{label}: requires unknown id '{dep['id']}'")
            elif dep.get("kind") not in kinds:
                errors.append(f"{label}: requires kind '{dep.get('kind')}' that no addon provides")
            else:
                for target in [*dep.get("prefer", {}).values(), dep.get("default")]:
                    if target and target not in ids:
                        errors.append(f"{label}: prefer/default id '{target}' not in index or recipes")
        for rec in e.get("recommends", []):
            if rec.get("id") not in ids:
                errors.append(f"{label}: recommends unknown id '{rec.get('id')}'")
        for img in e.get("images", []):
            if not (CATALOG_DIR / "media" / img.get("src", "")).is_file():
                errors.append(f"{label}: missing media file '{img.get('src')}'")

    for col in collections:
        for a in col["addons"]:
            if a not in ids:
                errors.append(f"collection {col['id']}: unknown addon '{a}'")

    for r in rows:
        if not any(covers(e, r["id"]) for e in entries):
            warnings.append(f"{r['id']}: no catalog entry")

    entry_of = lambda i: next((name(e) for e in entries if covers(e, i)), None)
    graph: dict[str, set[str]] = {name(e): set() for e in entries}
    for e in entries:
        for dep in e.get("requires", []):
            targets = [dep["id"]] if "id" in dep else [
                *dep.get("prefer", {}).values(), dep.get("default"), *kinds.get(dep.get("kind"), ())]
            for t in targets:
                owner = entry_of(t) if t else None
                if owner and owner != name(e):
                    graph[name(e)].add(owner)
    state: dict[str, int] = {}

    def visit(node, path):
        if state.get(node) == 2:
            return
        if state.get(node) == 1:
            errors.append("dependency cycle: " + " -> ".join(path[path.index(node):] + [node]))
            return
        state[node] = 1
        for nxt in sorted(graph[node]):
            visit(nxt, path + [node])
        state[node] = 2

    for node in sorted(graph):
        visit(node, [])
    if offline_note:
        warnings.append(offline_note)
    return errors, warnings


def compile_catalog(categories, collections, entries, media_dir: Path | None = None) -> dict:
    """Rewrites image src to content-hashed names and copies the files into media_dir if given."""
    compiled = []
    for e in entries:
        e = json.loads(json.dumps(e))
        for img in e.get("images", []):
            src = CATALOG_DIR / "media" / img["src"]
            digest = hashlib.sha256(src.read_bytes()).hexdigest()[:8]
            hashed = f"{src.stem}.{digest}{src.suffix}"
            if media_dir is not None:
                shutil.copyfile(src, media_dir / hashed)
            img["src"] = hashed
        compiled.append(e)
    compiled.sort(key=lambda e: (e.get("order", 0), e.get("id") or e.get("match")))
    body = {
        "schema": SCHEMA,
        "categories": sorted(categories, key=lambda c: (c.get("order", 0), c["id"])),
        "collections": collections,
        "entries": compiled,
    }
    canonical = json.dumps(body, sort_keys=True, separators=(",", ":"), ensure_ascii=False)
    revision = hashlib.sha256(canonical.encode()).hexdigest()[:16]
    return {
        "schema": SCHEMA,
        "revision": revision,
        "generated": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        **{k: body[k] for k in ("categories", "collections", "entries")},
    }


def load_index(offline: bool) -> tuple[dict | None, str]:
    if offline:
        return None, "offline: validated against recipes only"
    import publish
    return publish._fetch_index(), ""


def build(index: dict | None, offline_note: str = "", media_dir: Path | None = None):
    categories, collections, entries = load_source()
    errors, warnings = validate(categories, collections, entries, known_rows(index), offline_note)
    return compile_catalog(categories, collections, entries, media_dir) if not errors else None, errors, warnings


def report(errors: list[str], warnings: list[str]) -> None:
    for w in warnings:
        print(f"warning: {w}", file=sys.stderr)
    for e in errors:
        print(f"error: {e}", file=sys.stderr)
    print(f"{len(errors)} errors, {len(warnings)} warnings", file=sys.stderr)


def upload(index: dict | None, offline_note: str = "") -> None:
    import publish
    with tempfile.TemporaryDirectory() as tmp:
        media_dir = Path(tmp) / "media"
        media_dir.mkdir()
        compiled, errors, warnings = build(index, offline_note, media_dir)
        report(errors, warnings)
        if errors:
            raise SystemExit(1)
        for path in sorted(media_dir.iterdir()):
            publish._put(MEDIA_PREFIX + path.name, path,
                         mimetypes.guess_type(path.name)[0] or "application/octet-stream")
        out = Path(tmp) / "catalog.json"
        out.write_text(json.dumps(compiled, indent=2, ensure_ascii=False))
        publish._put(CATALOG_KEY, out, "application/json")
    print(f"catalog.json uploaded: revision {compiled['revision']}, {len(compiled['entries'])} entries")


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--out", type=Path)
    parser.add_argument("--offline", action="store_true", help="validate against recipes only")
    args = parser.parse_args()

    index, note = load_index(args.offline)
    if not (args.dry_run or args.out):
        upload(index, note)
        return
    compiled, errors, warnings = build(index, note)
    report(errors, warnings)
    if errors:
        raise SystemExit(1)
    text = json.dumps(compiled, indent=2, ensure_ascii=False)
    if args.out:
        args.out.write_text(text + "\n")
    else:
        print(text)


if __name__ == "__main__":
    main()
