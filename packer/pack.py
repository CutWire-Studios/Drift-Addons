#!/usr/bin/env python3
"""Pack one addon from a recipe.

    ./pack.py ../recipes/fonts-essentials.json [-o ../dist]

A recipe is JSON:

    {
      "id": "fonts.essentials",
      "version": "1.0.0",
      "name": "Essential Fonts",
      "description": "...",          # short, beginner-friendly row copy
      "details": "...",              # optional; deeper tech notes behind an info popup
      "license": "OFL-1.1",
      "source": "../staging/fonts-essentials",   # relative to the recipe file
      "provides": [{ "kind": "fonts", "root": "fonts" }]
    }

`source` is a directory whose *contents* become the package root, so `provides[].root` names a
subdirectory of it.
"""

import argparse
import json
from pathlib import Path

import driftpkg


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("recipe", type=Path)
    parser.add_argument("-o", "--outdir", type=Path, default=Path(__file__).parent.parent / "dist")
    parser.add_argument("--key", type=Path, default=driftpkg.DEFAULT_KEY)
    args = parser.parse_args()

    recipe = json.loads(args.recipe.read_text())
    source = (args.recipe.parent / recipe["source"]).resolve()
    out_path = args.outdir / f"{recipe['id']}-{recipe['version']}.driftpkg"

    metadata = driftpkg.build(recipe, source, out_path, args.key)

    packed = metadata["_packedSize"]
    raw = metadata["installedSize"]
    ratio = (100 * packed / raw) if raw else 0
    print(f"{out_path}")
    print(f"  {len(metadata['files'])} files, {raw / 1e6:.1f} MB raw "
          f"-> {packed / 1e6:.1f} MB packed ({ratio:.0f}%)")


if __name__ == "__main__":
    main()
