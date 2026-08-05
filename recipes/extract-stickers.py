#!/usr/bin/env python3
"""Extract a curated emoji sticker set from a CBDT/CBLC colour-bitmap font.

The font itself is not committed (it is ~44 MB); drop HarmonyOS_4.0.ttf into emoji-fonts/
and this pulls ~100 popular emoji out of it as individual PNGs plus a stickers.json manifest
that the app reads. Same spirit as fetch-fonts.py: pure stdlib, re-runnable, and a missing
font is a warning (empty sticker set) rather than a hard failure so offline builds still work.

The font stores each glyph as an embedded PNG in the CBDT table, indexed by CBLC. We map the
curated Unicode code points to glyph ids via the cmap, then copy each glyph's PNG straight out.
"""

import argparse
import json
import struct
import sys
from pathlib import Path

# Curated single-code-point emoji: (code point, id/filename stem, label, category).
# Multi-code-point sequences (ZWJ, flags, skin tones) are intentionally excluded — they need
# GSUB resolution the font stores separately, and these single glyphs cover the popular set.
CATEGORIES = [
    ("smileys", "Smileys"),
    ("hearts", "Hearts & Symbols"),
    ("hands", "Hands & Gestures"),
    ("animals", "Animals & Nature"),
    ("food", "Food & Drink"),
    ("activities", "Activities & Objects"),
    ("signs", "Signs & Arrows"),
]

EMOJI = [
    # --- Smileys ---
    (0x1F600, "grinning", "Grinning", "smileys"),
    (0x1F603, "smiley", "Smiley", "smileys"),
    (0x1F604, "grin", "Grin", "smileys"),
    (0x1F601, "beaming", "Beaming", "smileys"),
    (0x1F606, "laughing", "Laughing", "smileys"),
    (0x1F605, "sweat-smile", "Sweat Smile", "smileys"),
    (0x1F602, "joy", "Joy", "smileys"),
    (0x1F923, "rofl", "ROFL", "smileys"),
    (0x1F60A, "blush", "Blush", "smileys"),
    (0x1F642, "slight-smile", "Slight Smile", "smileys"),
    (0x1F643, "upside-down", "Upside Down", "smileys"),
    (0x1F609, "wink", "Wink", "smileys"),
    (0x1F60C, "relieved", "Relieved", "smileys"),
    (0x1F60D, "heart-eyes", "Heart Eyes", "smileys"),
    (0x1F970, "smiling-hearts", "Smiling Hearts", "smileys"),
    (0x1F618, "blow-kiss", "Blow a Kiss", "smileys"),
    (0x1F61A, "kissing", "Kissing", "smileys"),
    (0x1F60B, "yum", "Yum", "smileys"),
    (0x1F61C, "wink-tongue", "Wink Tongue", "smileys"),
    (0x1F92A, "zany", "Zany", "smileys"),
    (0x1F914, "thinking", "Thinking", "smileys"),
    (0x1F644, "roll-eyes", "Rolling Eyes", "smileys"),
    (0x1F60F, "smirk", "Smirk", "smileys"),
    (0x1F612, "unamused", "Unamused", "smileys"),
    (0x1F60E, "sunglasses", "Sunglasses", "smileys"),
    (0x1F929, "star-struck", "Star-Struck", "smileys"),
    (0x1F973, "partying", "Partying", "smileys"),
    (0x1F634, "sleeping", "Sleeping", "smileys"),
    (0x1F62D, "sob", "Sobbing", "smileys"),
    (0x1F621, "rage", "Rage", "smileys"),
    (0x1F620, "angry", "Angry", "smileys"),
    (0x1F631, "scream", "Screaming", "smileys"),
    (0x1F975, "hot-face", "Hot Face", "smileys"),
    (0x1F976, "cold-face", "Cold Face", "smileys"),
    (0x1F637, "mask", "Mask", "smileys"),
    (0x1F921, "clown", "Clown", "smileys"),
    (0x1F480, "skull", "Skull", "smileys"),
    (0x1F47B, "ghost", "Ghost", "smileys"),
    (0x1F47D, "alien", "Alien", "smileys"),
    (0x1F916, "robot", "Robot", "smileys"),
    (0x1F4A9, "poop", "Pile of Poo", "smileys"),
    # --- Hearts & Symbols ---
    (0x2764, "red-heart", "Red Heart", "hearts"),
    (0x1F9E1, "orange-heart", "Orange Heart", "hearts"),
    (0x1F49B, "yellow-heart", "Yellow Heart", "hearts"),
    (0x1F49A, "green-heart", "Green Heart", "hearts"),
    (0x1F499, "blue-heart", "Blue Heart", "hearts"),
    (0x1F49C, "purple-heart", "Purple Heart", "hearts"),
    (0x1F5A4, "black-heart", "Black Heart", "hearts"),
    (0x1F90D, "white-heart", "White Heart", "hearts"),
    (0x1F494, "broken-heart", "Broken Heart", "hearts"),
    (0x1F495, "two-hearts", "Two Hearts", "hearts"),
    (0x1F497, "growing-heart", "Growing Heart", "hearts"),
    (0x1F496, "sparkling-heart", "Sparkling Heart", "hearts"),
    (0x1F498, "cupid", "Cupid", "hearts"),
    (0x1F4AF, "hundred", "Hundred", "hearts"),
    (0x1F4A5, "collision", "Collision", "hearts"),
    (0x1F4A6, "sweat-drops", "Sweat Drops", "hearts"),
    (0x1F4A8, "dash", "Dash", "hearts"),
    (0x1F525, "fire", "Fire", "hearts"),
    (0x2B50, "star", "Star", "hearts"),
    (0x1F31F, "glowing-star", "Glowing Star", "hearts"),
    (0x2728, "sparkles", "Sparkles", "hearts"),
    (0x26A1, "high-voltage", "High Voltage", "hearts"),
    (0x1F308, "rainbow", "Rainbow", "hearts"),
    # --- Hands & Gestures ---
    (0x1F44D, "thumbs-up", "Thumbs Up", "hands"),
    (0x1F44E, "thumbs-down", "Thumbs Down", "hands"),
    (0x1F44C, "ok-hand", "OK Hand", "hands"),
    (0x270C, "victory", "Victory", "hands"),
    (0x1F91E, "crossed-fingers", "Crossed Fingers", "hands"),
    (0x1F44F, "clap", "Clapping", "hands"),
    (0x1F64C, "raising-hands", "Raising Hands", "hands"),
    (0x1F450, "open-hands", "Open Hands", "hands"),
    (0x1F91D, "handshake", "Handshake", "hands"),
    (0x1F64F, "folded-hands", "Folded Hands", "hands"),
    (0x270A, "raised-fist", "Raised Fist", "hands"),
    (0x1F44A, "fist-bump", "Fist Bump", "hands"),
    (0x1F44B, "wave", "Waving", "hands"),
    (0x270B, "raised-hand", "Raised Hand", "hands"),
    (0x1F596, "vulcan", "Vulcan Salute", "hands"),
    (0x1F918, "horns", "Sign of the Horns", "hands"),
    (0x1F919, "call-me", "Call Me", "hands"),
    (0x1F448, "point-left", "Point Left", "hands"),
    (0x1F449, "point-right", "Point Right", "hands"),
    (0x1F446, "point-up", "Point Up", "hands"),
    (0x1F447, "point-down", "Point Down", "hands"),
    (0x1F4AA, "muscle", "Flexed Biceps", "hands"),
    # --- Animals & Nature ---
    (0x1F436, "dog", "Dog", "animals"),
    (0x1F431, "cat", "Cat", "animals"),
    (0x1F430, "rabbit", "Rabbit", "animals"),
    (0x1F98A, "fox", "Fox", "animals"),
    (0x1F43B, "bear", "Bear", "animals"),
    (0x1F43C, "panda", "Panda", "animals"),
    (0x1F42F, "tiger", "Tiger", "animals"),
    (0x1F981, "lion", "Lion", "animals"),
    (0x1F437, "pig", "Pig", "animals"),
    (0x1F438, "frog", "Frog", "animals"),
    (0x1F435, "monkey", "Monkey", "animals"),
    (0x1F648, "see-no-evil", "See-No-Evil", "animals"),
    (0x1F414, "chicken", "Chicken", "animals"),
    (0x1F427, "penguin", "Penguin", "animals"),
    (0x1F986, "duck", "Duck", "animals"),
    (0x1F41D, "bee", "Bee", "animals"),
    (0x1F98B, "butterfly", "Butterfly", "animals"),
    (0x1F984, "unicorn", "Unicorn", "animals"),
    (0x1F433, "whale", "Whale", "animals"),
    (0x1F419, "octopus", "Octopus", "animals"),
    (0x1F340, "clover", "Four Leaf Clover", "animals"),
    (0x1F338, "cherry-blossom", "Cherry Blossom", "animals"),
    (0x1F33B, "sunflower", "Sunflower", "animals"),
    (0x1F339, "rose", "Rose", "animals"),
    # --- Food & Drink ---
    (0x1F355, "pizza", "Pizza", "food"),
    (0x1F354, "burger", "Burger", "food"),
    (0x1F35F, "fries", "Fries", "food"),
    (0x1F32E, "taco", "Taco", "food"),
    (0x1F369, "donut", "Donut", "food"),
    (0x1F370, "cake", "Cake", "food"),
    (0x1F382, "birthday-cake", "Birthday Cake", "food"),
    (0x1F36A, "cookie", "Cookie", "food"),
    (0x1F366, "ice-cream", "Ice Cream", "food"),
    (0x1F34E, "apple", "Apple", "food"),
    (0x1F34C, "banana", "Banana", "food"),
    (0x1F347, "grapes", "Grapes", "food"),
    (0x1F353, "strawberry", "Strawberry", "food"),
    (0x1F349, "watermelon", "Watermelon", "food"),
    (0x1F351, "peach", "Peach", "food"),
    (0x1F352, "cherries", "Cherries", "food"),
    (0x2615, "coffee", "Coffee", "food"),
    (0x1F37A, "beer", "Beer", "food"),
    (0x1F379, "cocktail", "Tropical Drink", "food"),
    # --- Activities & Objects ---
    (0x26BD, "soccer", "Soccer", "activities"),
    (0x1F3C0, "basketball", "Basketball", "activities"),
    (0x1F3C8, "football", "Football", "activities"),
    (0x1F3AE, "video-game", "Video Game", "activities"),
    (0x1F3B8, "guitar", "Guitar", "activities"),
    (0x1F3B5, "music", "Music Note", "activities"),
    (0x1F3A7, "headphones", "Headphones", "activities"),
    (0x1F4F7, "camera", "Camera", "activities"),
    (0x1F4A1, "bulb", "Light Bulb", "activities"),
    (0x1F381, "gift", "Gift", "activities"),
    (0x1F388, "balloon", "Balloon", "activities"),
    (0x1F389, "party-popper", "Party Popper", "activities"),
    (0x1F38A, "confetti", "Confetti", "activities"),
    (0x1F3C6, "trophy", "Trophy", "activities"),
    (0x1F947, "gold-medal", "Gold Medal", "activities"),
    (0x1F680, "rocket", "Rocket", "activities"),
    (0x1F697, "car", "Car", "activities"),
    (0x23F0, "alarm-clock", "Alarm Clock", "activities"),
    (0x1F4B0, "money-bag", "Money Bag", "activities"),
    (0x1F511, "key", "Key", "activities"),
    (0x1F512, "lock", "Lock", "activities"),
    # --- Signs & Arrows ---
    (0x2705, "check-mark", "Check Mark", "signs"),
    (0x274C, "cross-mark", "Cross Mark", "signs"),
    (0x2757, "exclamation", "Exclamation", "signs"),
    (0x2753, "question", "Question", "signs"),
    (0x26A0, "warning", "Warning", "signs"),
    (0x1F6AB, "prohibited", "Prohibited", "signs"),
    (0x2B06, "arrow-up", "Arrow Up", "signs"),
    (0x2B07, "arrow-down", "Arrow Down", "signs"),
    (0x27A1, "arrow-right", "Arrow Right", "signs"),
    (0x2B05, "arrow-left", "Arrow Left", "signs"),
    (0x1F53A, "red-triangle-up", "Red Triangle Up", "signs"),
    (0x1F53B, "red-triangle-down", "Red Triangle Down", "signs"),
    (0x1F4C8, "chart-up", "Chart Up", "signs"),
    (0x1F4C9, "chart-down", "Chart Down", "signs"),
    (0x2795, "plus", "Plus", "signs"),
    (0x2796, "minus", "Minus", "signs"),
    (0x1F51D, "top", "TOP Arrow", "signs"),
    (0x1F195, "new", "NEW Button", "signs"),
]

ATTRIBUTION = """\
Sticker images are extracted at build time from HarmonyOS_4.0.ttf (HarmonyOS MFFM Emoji),
which is derived from Google's Noto Emoji (github.com/googlefonts/noto-emoji), licensed under
the Apache License 2.0. The font is not distributed with this project. These PNGs are generated
locally and are not committed to the repository.
"""


def read_table_directory(data):
    num_tables = struct.unpack(">H", data[4:6])[0]
    tables = {}
    for i in range(num_tables):
        off = 12 + i * 16
        tag = data[off:off + 4].decode("latin-1")
        toff, tlen = struct.unpack(">II", data[off + 8:off + 16])
        tables[tag] = (toff, tlen)
    return tables


def parse_cmap(data, base):
    """Return {code point: glyph id} from the best Unicode subtable (format 12 preferred)."""
    _, num = struct.unpack(">HH", data[base:base + 4])
    best = None  # (score, offset, fmt)
    for i in range(num):
        pid, eid, offset = struct.unpack(">HHI", data[base + 4 + i * 8:base + 4 + i * 8 + 8])
        fmt = struct.unpack(">H", data[base + offset:base + offset + 2])[0]
        if fmt not in (4, 12):
            continue
        score = 2 if fmt == 12 else 1
        if best is None or score > best[0]:
            best = (score, base + offset, fmt)
    if best is None:
        raise ValueError("no usable cmap subtable")

    _, sub_off, fmt = best
    mapping = {}
    if fmt == 12:
        n_groups = struct.unpack(">I", data[sub_off + 12:sub_off + 16])[0]
        p = sub_off + 16
        for _ in range(n_groups):
            start, end, start_gid = struct.unpack(">III", data[p:p + 12])
            for cp in range(start, end + 1):
                mapping[cp] = start_gid + (cp - start)
            p += 12
    else:  # format 4
        seg_x2 = struct.unpack(">H", data[sub_off + 6:sub_off + 8])[0]
        seg = seg_x2 // 2
        o = sub_off + 14
        ends = struct.unpack(">%dH" % seg, data[o:o + seg_x2]); o += seg_x2 + 2
        starts = struct.unpack(">%dH" % seg, data[o:o + seg_x2]); o += seg_x2
        deltas = struct.unpack(">%dh" % seg, data[o:o + seg_x2]); o += seg_x2
        ro_base = o
        ranges = struct.unpack(">%dH" % seg, data[o:o + seg_x2])
        for i in range(seg):
            for cp in range(starts[i], ends[i] + 1):
                if cp == 0xFFFF:
                    continue
                if ranges[i] == 0:
                    gid = (cp + deltas[i]) & 0xFFFF
                else:
                    gi = ro_base + i * 2 + ranges[i] + (cp - starts[i]) * 2
                    gid = struct.unpack(">H", data[gi:gi + 2])[0]
                    if gid != 0:
                        gid = (gid + deltas[i]) & 0xFFFF
                if gid:
                    mapping[cp] = gid
    return mapping


def parse_cblc(data, base):
    """Return {glyph id: (cbdt_data_offset, length, image_format)} for the first strike."""
    num_sizes = struct.unpack(">I", data[base + 4:base + 8])[0]
    if num_sizes == 0:
        return {}
    # First bitmapSizeTable only — these fonts ship a single colour strike.
    rec = data[base + 8:base + 8 + 48]
    idx_array_off, _, num_idx_sub = struct.unpack(">III", rec[0:12])
    array_base = base + idx_array_off

    glyphs = {}
    for k in range(num_idx_sub):
        entry = data[array_base + k * 8:array_base + k * 8 + 8]
        first_g, last_g, add_off = struct.unpack(">HHI", entry)
        sub = array_base + add_off
        index_format, image_format, image_data_off = struct.unpack(">HHI", data[sub:sub + 8])
        count = last_g - first_g + 1

        if index_format == 1:  # uint32 offsets
            offs = struct.unpack(">%dI" % (count + 1), data[sub + 8:sub + 8 + 4 * (count + 1)])
        elif index_format == 3:  # uint16 offsets
            offs = struct.unpack(">%dH" % (count + 1), data[sub + 8:sub + 8 + 2 * (count + 1)])
        elif index_format == 2:  # constant size
            image_size = struct.unpack(">I", data[sub + 8:sub + 12])[0]
            for i in range(count):
                glyphs[first_g + i] = (image_data_off + i * image_size, image_size, image_format)
            continue
        else:
            print(f"  .. skipping index subtable format {index_format}", file=sys.stderr)
            continue

        for i in range(count):
            length = offs[i + 1] - offs[i]
            if length > 0:
                glyphs[first_g + i] = (image_data_off + offs[i], length, image_format)
    return glyphs


def extract_png(cbdt_data, base, data_off, length, image_format):
    """Pull the embedded PNG out of a CBDT glyph record."""
    p = base + data_off
    if image_format == 17:      # smallGlyphMetrics(5) + uint32 len + PNG
        png_len = struct.unpack(">I", cbdt_data[p + 5:p + 9])[0]
        start = p + 9
    elif image_format == 18:    # bigGlyphMetrics(8) + uint32 len + PNG
        png_len = struct.unpack(">I", cbdt_data[p + 8:p + 12])[0]
        start = p + 12
    elif image_format == 19:    # uint32 len + PNG (metrics shared in CBLC)
        png_len = struct.unpack(">I", cbdt_data[p:p + 4])[0]
        start = p + 4
    else:
        return None
    png = cbdt_data[start:start + png_len]
    if png[:8] != b"\x89PNG\r\n\x1a\n":
        return None
    return png


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    repo = Path(__file__).resolve().parent.parent
    ap.add_argument("--font", default=str(repo / "emoji-fonts" / "HarmonyOS_4.0.ttf"))
    ap.add_argument("--out", default=str(repo / "resources" / "stickers"))
    ap.add_argument("--force", action="store_true", help="re-extract PNGs that already exist")
    args = ap.parse_args()

    font_path = Path(args.font)
    out_dir = Path(args.out)
    out_dir.mkdir(parents=True, exist_ok=True)

    if not font_path.exists():
        print(f"!! emoji font not found at {font_path} — stickers will be empty.\n"
              f"   Drop HarmonyOS_4.0.ttf into {font_path.parent}/ and re-run.", file=sys.stderr)
        # Write an empty manifest so the build has something well-formed to embed.
        (out_dir / "stickers.json").write_text(json.dumps(
            {"categories": [{"id": c, "label": l} for c, l in CATEGORIES], "stickers": []},
            indent=2) + "\n")
        return 0

    data = font_path.read_bytes()
    tables = read_table_directory(data)
    for req in ("cmap", "CBLC", "CBDT"):
        if req not in tables:
            print(f"!! font has no {req} table — not a colour-bitmap emoji font", file=sys.stderr)
            return 1

    cmap = parse_cmap(data, tables["cmap"][0])
    glyph_loc = parse_cblc(data, tables["CBLC"][0])
    cbdt_base = tables["CBDT"][0]

    stickers = []
    missing = []
    for cp, sid, label, category in EMOJI:
        gid = cmap.get(cp)
        loc = glyph_loc.get(gid) if gid else None
        if not loc:
            missing.append((cp, sid))
            continue
        png = extract_png(data, cbdt_base, loc[0], loc[1], loc[2])
        if png is None:
            missing.append((cp, sid))
            continue
        fname = f"{sid}.png"
        if args.force or not (out_dir / fname).exists():
            (out_dir / fname).write_bytes(png)
        stickers.append({"id": sid, "label": label, "category": category, "file": fname})

    manifest = {
        "categories": [{"id": c, "label": l} for c, l in CATEGORIES
                       if any(s["category"] == c for s in stickers)],
        "stickers": stickers,
    }
    (out_dir / "stickers.json").write_text(json.dumps(manifest, indent=2) + "\n")
    (out_dir / "ATTRIBUTION.txt").write_text(ATTRIBUTION)

    print(f"  {len(stickers)}/{len(EMOJI)} stickers extracted to {out_dir}")
    if missing:
        print("  missing (no glyph/bitmap): "
              + ", ".join(f"U+{cp:04X} {sid}" for cp, sid in missing), file=sys.stderr)
    return 0


if __name__ == "__main__":
    sys.exit(main())
