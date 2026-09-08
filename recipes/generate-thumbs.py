#!/usr/bin/env python3
"""Generate effect thumbnails and transition preview strips for content/.

Always uses assets/base-image.jpeg so browser previews stay consistent.

    ./generate-thumbs.py              # only packages missing thumbs
    ./generate-thumbs.py --force      # rewrite every content package
"""

from __future__ import annotations

import argparse
import subprocess
import sys
from pathlib import Path

HERE = Path(__file__).parent
ROOT = HERE.parent
ASSETS = ROOT / "assets"
BASE = ASSETS / "base-image.jpeg"
# Transitions need two visibly different frames to read at all: a cool road scene
# against a warm barley field separates on both colour and structure.
TRANSITION_BASE_A = ASSETS / "transitions" / "road.jpg"
TRANSITION_BASE_B = ASSETS / "transitions" / "barley.jpg"
EFFECTS = ROOT / "content" / "effects"
TRANSITIONS = ROOT / "content" / "transitions"

# Built next to the Drift app tree this repo already stages from.
EFFECTTHUMBS = Path.home() / "Projects" / "VideoEd" / "build" / "tools" / "effectthumbs"
TRANSITIONTHUMBS = Path.home() / "Projects" / "VideoEd" / "build" / "tools" / "transitionthumbs"


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--force", action="store_true",
                        help="rewrite thumbnails that already exist")
    parser.add_argument("--effects-only", action="store_true")
    parser.add_argument("--transitions-only", action="store_true")
    parser.add_argument("--size", type=int, default=256)
    args = parser.parse_args()

    if not BASE.is_file():
        sys.exit(f"missing base image: {BASE}\n"
                 f"Copy the portrait JPEG to assets/base-image.jpeg first.")

    do_effects = not args.transitions_only
    do_transitions = not args.effects_only

    if do_effects:
        if not EFFECTTHUMBS.is_file():
            sys.exit(f"missing {EFFECTTHUMBS} — build VideoEd tools first")
        if not EFFECTS.is_dir() or not any(EFFECTS.iterdir()):
            sys.exit(f"no effect packages under {EFFECTS}")
        cmd = [str(EFFECTTHUMBS), "--effects", str(EFFECTS),
               "--base", str(BASE), "--size", str(args.size)]
        if args.force:
            cmd.append("--force")
        subprocess.run(cmd, check=True)

    if do_transitions:
        if not TRANSITIONTHUMBS.is_file():
            sys.exit(f"missing {TRANSITIONTHUMBS} — build VideoEd tools first")
        if not TRANSITIONS.is_dir() or not any(TRANSITIONS.iterdir()):
            sys.exit(f"no transition packages under {TRANSITIONS}")
        # Two different photos, not one: passing the same image as both bases made every
        # preview a transition between identical frames, which shows nothing.
        for base in (TRANSITION_BASE_A, TRANSITION_BASE_B):
            if not base.is_file():
                sys.exit(f"missing {base}")
        cmd = [str(TRANSITIONTHUMBS), "--transitions", str(TRANSITIONS),
               "--base-a", str(TRANSITION_BASE_A), "--base-b", str(TRANSITION_BASE_B),
               "--size", "128", "--frames", "12"]
        # transitionthumbs always rewrites named packages; no --force flag needed
        subprocess.run(cmd, check=True)


if __name__ == "__main__":
    main()
