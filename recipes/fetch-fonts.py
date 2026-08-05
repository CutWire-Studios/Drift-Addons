#!/usr/bin/env python3
"""Fetch the bundled font packages into fonts/.

The google/fonts repo now ships variable-only TTFs for most of these families, and Qt's
variable-font support is unreliable before 6.7. The CSS2 API, asked with a legacy User-Agent,
serves static instances instead — and answers 400 for a weight the family does not have, so
each family's real weight ladder is discovered rather than hand-maintained.

Re-runnable: existing files are left alone unless --force.
"""

import argparse
import json
import re
import struct
import sys
import urllib.error
import urllib.request
from pathlib import Path

# The API only hands out static .ttf instances to a browser too old to know about woff2.
LEGACY_UA = ("Mozilla/5.0 (Linux; U; Android 2.2; en-us; DROID2 GLOBAL Build/S273) "
             "AppleWebKit/533.1 (KHTML, like Gecko) Version/4.0 Mobile Safari/533.1")

CSS2 = "https://fonts.googleapis.com/css2?family="
GF_RAW = "https://raw.githubusercontent.com/google/fonts/main/"

WEIGHTS = [100, 200, 300, 400, 500, 600, 700, 800, 900]
DEFAULT_ITALIC_WEIGHTS = [400, 700]

# id, family, google/fonts path, category, order-within-category
FAMILIES = [
    ("bebasneue", "Bebas Neue", "ofl/bebasneue", "impact", 10),
    ("anton", "Anton", "ofl/anton", "impact", 20),
    ("archivoblack", "Archivo Black", "ofl/archivoblack", "impact", 30),
    ("oswald", "Oswald", "ofl/oswald", "impact", 40),
    ("montserrat", "Montserrat", "ofl/montserrat", "impact", 50),
    ("poppins", "Poppins", "ofl/poppins", "impact", 60),
    ("leaguespartan", "League Spartan", "ofl/leaguespartan", "impact", 70),
    ("rubik", "Rubik", "ofl/rubik", "impact", 80),
    ("rubikone", "Rubik One", "ofl/rubikone", "impact", 90),
    ("inter", "Inter", "ofl/inter", "clean", 10),
    ("plusjakartasans", "Plus Jakarta Sans", "ofl/plusjakartasans", "clean", 20),
    ("dmsans", "DM Sans", "ofl/dmsans", "clean", 30),
    ("outfit", "Outfit", "ofl/outfit", "clean", 40),
    ("ubuntu", "Ubuntu", "ufl/ubuntu", "clean", 50),
    ("playfairdisplay", "Playfair Display", "ofl/playfairdisplay", "editorial", 10),
    ("cormorantgaramond", "Cormorant Garamond", "ofl/cormorantgaramond", "editorial", 20),
    ("cinzel", "Cinzel", "ofl/cinzel", "editorial", 30),
    ("fraunces", "Fraunces", "ofl/fraunces", "editorial", 40),
    ("bodonimoda", "Bodoni Moda", "ofl/bodonimoda", "editorial", 50),
    ("fredoka", "Fredoka", "ofl/fredoka", "playful", 10),
    ("pacifico", "Pacifico", "ofl/pacifico", "playful", 20),
]


def get(url, ua=None):
    req = urllib.request.Request(url, headers={"User-Agent": ua} if ua else {})
    with urllib.request.urlopen(req, timeout=30) as r:
        return r.read()


def probe(family, weight, italic):
    """Return the static .ttf URL for this face, or None when the family has no such face."""
    name = family.replace(" ", "+")
    axis = f"ital,wght@1,{weight}" if italic else f"wght@{weight}"
    try:
        css = get(f"{CSS2}{name}:{axis}", ua=LEGACY_UA).decode("utf-8")
    except urllib.error.HTTPError as e:
        if e.code == 400:  # the API's way of saying "that face does not exist"
            return None
        raise
    m = re.search(r"url\((https://fonts\.gstatic\.com/[^)]+\.ttf)\)", css)
    return m.group(1) if m else None


def style_name(ttf_path):
    """Typographic subfamily (name id 17), falling back to subfamily (id 2).

    usWeightClass lies for the light end of several of these families (Montserrat Thin and
    Inter Thin both report 250), so QFont::setWeight cannot select a face reliably. The style
    name can, which is why it goes into family.json.
    """
    data = ttf_path.read_bytes()
    num_tables = struct.unpack(">H", data[4:6])[0]
    name_off = name_len = None
    for i in range(num_tables):
        off = 12 + i * 16
        tag = data[off:off + 4]
        if tag == b"name":
            name_off, name_len = struct.unpack(">II", data[off + 8:off + 16])
            break
    if name_off is None:
        return "Regular"

    tbl = data[name_off:name_off + name_len]
    count, string_off = struct.unpack(">HH", tbl[2:6])
    found = {}
    for i in range(count):
        rec = 6 + i * 12
        platform, _enc, _lang, name_id, length, off = struct.unpack(">HHHHHH", tbl[rec:rec + 12])
        if name_id not in (2, 17):
            continue
        raw = tbl[string_off + off:string_off + off + length]
        text = raw.decode("utf-16-be" if platform == 3 else "latin-1", "replace").strip()
        # Windows records (platform 3) win over Mac ones when both are present.
        if text and (name_id not in found or platform == 3):
            found[name_id] = text
    return found.get(17) or found.get(2) or "Regular"


def fetch_family(entry, out_root, italic_weights, force):
    fid, family, gf_path, category, order = entry
    pkg = out_root / fid
    pkg.mkdir(parents=True, exist_ok=True)

    faces = []
    for weight in WEIGHTS:
        for italic in (False, True):
            if italic and weight not in italic_weights:
                continue
            fname = f"{family.replace(' ', '')}-{weight}{'italic' if italic else ''}.ttf"
            dest = pkg / fname

            if dest.exists() and not force:
                faces.append({"weight": weight, "italic": italic,
                              "styleName": style_name(dest), "file": fname})
                continue

            url = probe(family, weight, italic)
            if url is None:
                continue
            dest.write_bytes(get(url, ua=LEGACY_UA))
            faces.append({"weight": weight, "italic": italic,
                          "styleName": style_name(dest), "file": fname})

    if not faces:
        print(f"  !! {family}: no faces resolved", file=sys.stderr)
        return None

    # Ubuntu is the one family here under the Ubuntu Font Licence rather than the OFL.
    license_file, license_id = ("UFL.txt", "UFL-1.0") if gf_path.startswith("ufl/") \
        else ("OFL.txt", "OFL-1.1")
    lic = pkg / license_file
    if not lic.exists() or force:
        lic.write_bytes(get(f"{GF_RAW}{gf_path}/{license_file}"))

    (pkg / "family.json").write_text(json.dumps({
        "id": fid,
        "family": family,
        "category": category,
        "order": order,
        "license": license_id,
        "licenseFile": license_file,
        "faces": faces,
    }, indent=2) + "\n")
    return faces


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--out", default=str(Path(__file__).resolve().parent.parent / "fonts"))
    ap.add_argument("--force", action="store_true", help="re-download files that already exist")
    ap.add_argument("--all-italics", action="store_true",
                    help="fetch an italic for every weight, not just 400 and 700")
    args = ap.parse_args()

    out_root = Path(args.out)
    italic_weights = WEIGHTS if args.all_italics else DEFAULT_ITALIC_WEIGHTS

    total_bytes = 0
    failed = []
    for entry in FAMILIES:
        fid, family = entry[0], entry[1]
        try:
            faces = fetch_family(entry, out_root, italic_weights, args.force)
        except (urllib.error.URLError, OSError) as e:
            print(f"  !! {family}: {e}", file=sys.stderr)
            failed.append(family)
            continue
        if faces is None:
            failed.append(family)
            continue
        size = sum(f.stat().st_size for f in (out_root / fid).glob("*.ttf"))
        total_bytes += size
        weights = sorted({f["weight"] for f in faces if not f["italic"]})
        italics = sorted({f["weight"] for f in faces if f["italic"]})
        print(f"  {family:<20} {len(faces):>2} faces  "
              f"weights={weights}  italics={italics or '-'}  {size / 1e6:.1f} MB")

    print(f"\n{len(FAMILIES) - len(failed)}/{len(FAMILIES)} families, {total_bytes / 1e6:.1f} MB")
    if failed:
        print(f"failed: {', '.join(failed)}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
