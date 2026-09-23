#!/usr/bin/env python3
"""Generate effect thumbnails and transition preview strips for content/.

Effects render from the photos in assets/thumbs/, chosen per effect by assets/thumbs/bases.json:
faces for face effects, a lake for colour, a neon sign for glitch, and so on — each picked so the
effect reads at a glance. Every photo there is CC0; see assets/thumbs/CREDITS.md. Face and depth
effects use the real models when DRIFT_FACE_MODEL_DIR / DRIFT_DEPTH_MODEL_DIR point at them.

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
BASES = ASSETS / "thumbs" / "bases.json"
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

    if not BASES.is_file():
        sys.exit(f"missing {BASES}")

    do_effects = not args.transitions_only
    do_transitions = not args.effects_only

    if do_effects:
        if not EFFECTTHUMBS.is_file():
            sys.exit(f"missing {EFFECTTHUMBS} — build VideoEd tools first")
        if not EFFECTS.is_dir() or not any(EFFECTS.iterdir()):
            sys.exit(f"no effect packages under {EFFECTS}")
        cmd = [str(EFFECTTHUMBS), "--effects", str(EFFECTS),
               "--bases", str(BASES), "--size", str(args.size)]
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
