#!/usr/bin/env python3
"""Convert upstream gl-transitions shaders into Drift transition packages.

Upstream (vendor/gl-transitions, MIT) writes `vec4 transition(vec2 uv)` against contextual
`progress` / `ratio` / `getFromColor()` / `getToColor()`, with uv.y == 0 at the BOTTOM.
Drift wants a plain `#version 330 core` fragment shader sampling u_fromTexture / u_toTexture at
v_texCoord, with v_texCoord.y == 0 at the TOP. A generated preamble bridges the two.

Four upstream quirks have to be repaired on the way through, all of them verified against the
corpus rather than guessed:

  * `progress` and `ratio` must be real mutable globals, not #defines. StereoViewer.glsl takes
    `float ratio` as a function parameter and undulatingBurnOut.glsl declares a local of that
    name; a macro turns both into a syntax error. Globals let them shadow legally.
  * Ten files initialise a global from a uniform. GLSL 330 requires constant expressions there,
    so those pass on NVIDIA and fail on Mesa and Android. The declaration is split from the
    assignment, which moves to the top of transition().
  * dissolve.glsl carries `#ifdef GL_ES / precision mediump float;`. On GLES 3.00 GL_ES is
    defined, so that runs after the loader's `precision highp` and quietly downgrades everything
    below it.
  * texture2D() no longer exists in 330 core.

Parameters are the other half of the job. Drift binds float and bool uniforms by name and nothing
else, so int/ivec2/vec2/vec4 uniforms are bound as floats under a mangled name and #defined back
to a primary expression -- `#define steps int(p_steps)`. The #define form matters: rewriting use
sites instead would break `In ? a : b`, since a float is not a legal ternary condition.

Usage:
    python3 recipes/import-gl-transitions.py            # convert everything
    python3 recipes/import-gl-transitions.py --only fade cube
    python3 recipes/import-gl-transitions.py --list-skipped
"""

import argparse
import json
import re
import subprocess
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parent
VENDOR = ROOT / "vendor" / "gl-transitions" / "transitions"
OUT = ROOT / "content" / "transitions"
OVERRIDES = HERE / "gl-transitions-overrides.json"
# The upstream commit these ports were generated from; recorded in ATTRIBUTION.md too.
UPSTREAM_PIN = "902218a1b63773ac0d0d9f491951da3392365bfe"

GLSL_TYPES = r"(?:float|int|bool|vec2|vec3|vec4|ivec2|ivec3|ivec4|mat2|mat3|mat4)"

# Ported by hand or already covered by a better Drift original. Keyed by upstream stem.
SKIP = {
    "displacement": "needs a shipped displacement map; Drift ships rgb_displacement",
    "luma": "needs a shipped luma map; Drift ships luma_fade",
    # The four upstream wipes would want the frozen ids wipe_left/right/up/down, and Drift's
    # originals are better anyway -- they take a `softness` parameter these have no equivalent of.
    "wipeDown": "Drift ships wipe_down with a softness parameter",
    "wipeLeft": "Drift ships wipe_left with a softness parameter",
    "wipeRight": "Drift ships wipe_right with a softness parameter",
    "wipeUp": "Drift ships wipe_up with a softness parameter",
    # Drift's cross_zoom_swirl has three tuned parameters against upstream's one, and upstream's
    # also carries a self-referential local that reads as undefined behaviour.
    "CrossZoom": "Drift ships cross_zoom_swirl, which is a better version of the same idea",
}

# The nine ids frozen by the project-file format. A generated package must never claim one.
FROZEN_IDS = {
    "crossfade", "dip", "dip_white", "wipe_left", "wipe_right",
    "wipe_up", "wipe_down", "push_left", "zoom_in",
}

CATEGORY_KEYWORDS = [
    ("glitch", ("glitch", "static", "tv", "datamosh", "noise", "interference", "signal", "displace")),
    ("liquid", ("water", "ripple", "wave", "melt", "liquid", "burn", "ink", "dissolve", "perlin", "undulat")),
    ("geometric", ("square", "grid", "tile", "hexagon", "polka", "rect", "box", "star", "triangle",
                   "cross", "blinds", "windowslice", "chessboard", "puzzle", "doom", "bars")),
    ("distortion", ("warp", "zoom", "swirl", "twirl", "kaleido", "morph", "spherize", "pinwheel",
                    "flyeye", "blur", "bounce", "stereo", "polar", "mosaic")),
    ("cinematic", ("film", "flare", "light", "dreamy", "luminance", "overexposure", "colorphase",
                   "fadecolor", "fadegray", "hsv", "colour", "defocus")),
    ("stylized", ("page", "curl", "book", "cube", "fold", "door", "roll", "slide", "flip", "revolve")),
]


def fail(msg):
    sys.exit(f"import-gl-transitions: {msg}")


# ---------------------------------------------------------------------------- naming


def snake(stem):
    """CamelCase / kebab / mixed upstream filenames into a Drift package id."""
    s = stem.replace("-", "_")
    s = re.sub(r"(?<=[a-z0-9])(?=[A-Z])", "_", s)
    s = re.sub(r"(?<=[A-Z])(?=[A-Z][a-z])", "_", s)
    s = re.sub(r"_+", "_", s)
    return s.lower().strip("_")


def title(stem):
    words = snake(stem).split("_")
    return " ".join(w.capitalize() for w in words)


def guess_category(stem):
    low = snake(stem)
    for name, keys in CATEGORY_KEYWORDS:
        if any(k in low for k in keys):
            return name
    return "basic"


# ---------------------------------------------------------------------------- parsing


def strip_gl_es(src):
    """Drop `#ifdef GL_ES ... #endif` precision blocks; the loader emits its own precision."""
    return re.sub(r"#ifdef\s+GL_ES\b.*?#endif\s*\n?", "", src, flags=re.S)


def split_header(src):
    """Peel the leading comment block (Author / License / credits) off the body."""
    lines = src.splitlines()
    head = []
    i = 0
    while i < len(lines) and (lines[i].startswith("//") or not lines[i].strip()):
        head.append(lines[i])
        i += 1
    while head and not head[-1].strip():
        head.pop()
    return "\n".join(head), "\n".join(lines[i:])


UNIFORM_RE = re.compile(
    r"^uniform\s+(?P<type>\w+)\s+(?P<name>\w+)\s*"
    r"(?:/\*\s*=\s*(?P<blockdef>.*?)\s*\*/\s*)?;"
    r"(?:\s*//\s*=\s*(?P<linedef>.*?))?\s*$"
)


def extract_uniforms(body):
    """Pull every `uniform ...` line out of the body, returning them in declaration order."""
    kept, uniforms = [], []
    for line in body.splitlines():
        m = UNIFORM_RE.match(line.strip())
        if not m:
            kept.append(line)
            continue
        default = m.group("blockdef") or m.group("linedef")
        uniforms.append({
            "type": m.group("type"),
            "name": m.group("name"),
            "default": default.strip() if default else None,
        })
    return uniforms, "\n".join(kept)


def hoist_globals(body):
    """Split global initialisers that read uniforms into a declaration plus an assignment.

    Illegal as written in GLSL 330 (initialisers must be constant expressions) but accepted by
    NVIDIA, so this is the class of bug a desktop-only test run will not catch. Order is
    preserved -- pixelize.glsl chains d -> dist -> squareSize.
    """
    decls, assigns, kept = [], [], []
    depth = 0
    pattern = re.compile(rf"^({GLSL_TYPES})\s+(\w+)\s*=\s*(.+);\s*$")
    for line in body.splitlines():
        stripped = line.strip()
        m = pattern.match(stripped) if depth == 0 else None
        if m and not stripped.startswith("const"):
            decls.append(f"{m.group(1)} {m.group(2)};")
            assigns.append(f"    {m.group(2)} = {m.group(3)};")
        else:
            kept.append(line)
        depth += line.count("{") - line.count("}")
    return decls, assigns, "\n".join(kept)


def inject_into_transition(body, assigns):
    """Put the hoisted assignments at the top of transition()'s body."""
    if not assigns:
        return body
    m = re.search(r"vec4\s+transition\s*\(\s*vec2\s+\w+\s*\)\s*\{", body)
    if not m:
        fail("no transition() entry point to hoist into")
    at = m.end()
    return body[:at] + "\n" + "\n".join(assigns) + body[at:]


# ---------------------------------------------------------------------------- parameters


def scalars(default, count):
    """Unpack a GLSL constructor default (`vec2(0.5)`, `ivec2(10, 10)`, `1.0`) into components."""
    if default is None:
        return [0.0] * count
    # Two files trail prose after the value: `// = 0.4 ; // if 0.0, there is no black phase`.
    default = default.split(";", 1)[0].strip()
    m = re.match(r"^\s*[iub]?vec[234]\s*\((?P<args>[^)]*)\)", default)
    if m:
        parts = [p.strip() for p in m.group("args").split(",") if p.strip()]
    else:
        lead = re.match(r"^[-+]?\d*\.?\d+(?:[eE][-+]?\d+)?", default)
        if not lead:
            fail(f"cannot read a numeric default from {default!r}")
        parts = [lead.group(0)]
    vals = [float(p) for p in parts]
    if len(vals) == 1 and count > 1:
        vals = vals * count
    if len(vals) < count:
        vals += [0.0] * (count - len(vals))
    return vals[:count]


def range_for(name, default, integral=False):
    """Upstream ships defaults but never ranges, so derive one and let overrides correct it."""
    low = name.lower()
    if any(k in low for k in ("center", "centre")):
        return 0.0, 1.0
    if "direction" in low:
        return -1.0, 1.0
    if default == 0:
        lo, hi = (-1.0, 1.0) if integral else (0.0, 1.0)
    elif default > 0:
        lo, hi = 0.0, default * 2.0
    else:
        lo, hi = default * 2.0, -default * 2.0
    if integral:
        lo, hi = float(int(lo)), float(max(int(hi), int(default) + 1))
    return lo, hi


def hexcolor(vals):
    r, g, b = (max(0.0, min(1.0, v)) for v in vals[:3])
    return "#{:02x}{:02x}{:02x}".format(round(r * 255), round(g * 255), round(b * 255))


def label_for(name):
    s = re.sub(r"^(u|p)_?(?=[A-Z])", "", name)
    s = re.sub(r"(?<=[a-z0-9])(?=[A-Z])", " ", s).replace("_", " ")
    return s[:1].upper() + s[1:]


def build_params(uniforms, over):
    """Emit the GLSL for the parameter block plus the JSON parameters / fixedParams.

    Non-float/bool uniforms bind as floats under a mangled name and are #defined back to a
    primary expression, so every upstream use site keeps working verbatim.
    """
    glsl, params, fixed = [], [], {}
    forced = over.get("fixedParams", {})
    ranges = over.get("ranges", {})

    def add_float(key, default, label, integral=False):
        lo, hi = ranges.get(key, range_for(key, default, integral))
        params.append({
            "identifier": key,
            "displayName": label,
            "type": "float",
            "minValue": lo,
            "maxValue": hi,
            "defaultValue": default,
        })

    for u in uniforms:
        name, kind = u["name"], u["type"]
        if name in forced:
            continue
        if kind == "float":
            glsl.append(f"uniform float {name};")
            add_float(name, scalars(u["default"], 1)[0], label_for(name))
        elif kind == "bool":
            glsl.append(f"uniform float p_{name};")
            glsl.append(f"#define {name} (p_{name} > 0.5)")
            default = 1.0 if (u["default"] or "").strip() == "true" else 0.0
            params.append({
                "identifier": f"p_{name}",
                "displayName": label_for(name),
                "type": "bool",
                "minValue": 0.0,
                "maxValue": 1.0,
                "defaultValue": default,
            })
        elif kind == "int":
            glsl.append(f"uniform float p_{name};")
            glsl.append(f"#define {name} int(p_{name})")
            add_float(f"p_{name}", scalars(u["default"], 1)[0], label_for(name), integral=True)
        elif kind in ("vec2", "ivec2"):
            vals = scalars(u["default"], 2)
            cast = "int" if kind == "ivec2" else ""
            comps = ", ".join(f"{cast}(p_{name}_{a})" if cast else f"p_{name}_{a}" for a in "xy")
            glsl.append(f"uniform float p_{name}_x;")
            glsl.append(f"uniform float p_{name}_y;")
            glsl.append(f"#define {name} {kind}({comps})")
            for axis, val in zip("xy", vals):
                add_float(f"p_{name}_{axis}", val, f"{label_for(name)} {axis.upper()}",
                          integral=(kind == "ivec2"))
        elif kind == "vec3":
            # Colours ship as fixedParams, not as an editable `color` param: the color type did
            # not exist at v0.1.0 and an old build would bind 0.0 to the vec3 and render black.
            glsl.append(f"uniform vec3 {name};")
            fixed[name] = hexcolor(scalars(u["default"], 3))
        elif kind == "vec4":
            vals = scalars(u["default"], 4)
            if over.get("vec4_scalars", {}).get(name):
                for axis, val in zip("xyzw", vals):
                    glsl.append(f"uniform float p_{name}_{axis};")
                    add_float(f"p_{name}_{axis}", val, f"{label_for(name)} {axis.upper()}")
                comps = ", ".join(f"p_{name}_{a}" for a in "xyzw")
                glsl.append(f"#define {name} vec4({comps})")
            else:
                # Background colour + alpha. Alpha defaults to 0 so the transition reveals the
                # track underneath instead of painting an opaque rectangle over it.
                glsl.append(f"uniform vec3 p_{name};")
                glsl.append(f"uniform float p_{name}_a;")
                glsl.append(f"#define {name} vec4(p_{name}, p_{name}_a)")
                fixed[f"p_{name}"] = hexcolor(vals)
                add_float(f"p_{name}_a", 0.0, f"{label_for(name)} Opacity")
        else:
            fail(f"unhandled uniform type '{kind}' on '{name}'")

    fixed.update(forced)
    return glsl, params, fixed


# ---------------------------------------------------------------------------- emit

PREAMBLE = """#version 330 core
in vec2 v_texCoord;
out vec4 fragColor;

uniform sampler2D u_fromTexture;
uniform sampler2D u_toTexture;
uniform vec2 u_resolution;
uniform float u_progress;

// Real mutable globals rather than #defines: StereoViewer takes `float ratio` as a function
// parameter and undulatingBurnOut declares a local of that name, both of which a macro would
// turn into a syntax error. Globals let them shadow legally.
float progress;
float ratio;

// Upstream works in WebGL's bottom-left uv space; v_texCoord.y == 0 is the top of a Drift frame.
// The flip here and the one in main() are a single round trip, not a double negation.
// The clamp makes the CLAMP_TO_EDGE behaviour upstream assumes explicit rather than inherited
// from sampler state -- about two dozen shaders sample outside [0,1] unguarded.
vec4 getFromColor(vec2 uv) {
    uv = clamp(uv, 0.0, 1.0);
    return texture(u_fromTexture, vec2(uv.x, 1.0 - uv.y));
}

vec4 getToColor(vec2 uv) {
    uv = clamp(uv, 0.0, 1.0);
    return texture(u_toTexture, vec2(uv.x, 1.0 - uv.y));
}
"""

EPILOGUE = """
void main() {
    progress = u_progress;
    ratio = u_resolution.x / max(u_resolution.y, 1.0);
    fragColor = transition(vec2(v_texCoord.x, 1.0 - v_texCoord.y));
}
"""


def convert(path, over, order):
    stem = path.stem
    src = strip_gl_es(path.read_text())
    header, body = split_header(src)
    uniforms, body = extract_uniforms(body)
    body = body.replace("texture2D(", "texture(")

    for old, new in over.get("patches", []):
        if old not in body:
            fail(f"{stem}: patch text not found: {old!r}")
        body = body.replace(old, new, 1)

    # "nothing here" should be transparent, not an opaque black rectangle over the track below.
    body = body.replace("vec4 black = vec4(0.0, 0.0, 0.0, 1.0)", "vec4 black = vec4(0.0)")

    decls, assigns, body = hoist_globals(body)
    body = inject_into_transition(body, assigns)

    glsl_params, params, fixed = build_params(uniforms, over)

    pkg_id = over.get("id", snake(stem))
    if pkg_id in FROZEN_IDS:
        fail(f"{stem}: generated id '{pkg_id}' collides with a frozen project-format id")

    parts = [PREAMBLE]
    if header:
        parts.append(f"\n// --- upstream: {path.name} ---\n{header}\n")
    if glsl_params:
        parts.append("\n" + "\n".join(glsl_params) + "\n")
    if decls:
        parts.append("\n// Hoisted: these initialisers read uniforms, which GLSL 330 does not\n"
                     "// allow at global scope. Assigned at the top of transition() instead.\n"
                     + "\n".join(decls) + "\n")
    parts.append("\n" + body.strip("\n") + "\n")
    parts.append(EPILOGUE)

    manifest = {
        "id": pkg_id,
        "displayName": over.get("displayName", title(stem)),
        "category": over.get("category", guess_category(stem)),
        "order": over.get("order", order),
        "parameters": params,
    }
    if fixed:
        manifest["fixedParams"] = fixed
    if "audioCurve" in over:
        manifest["audioCurve"] = over["audioCurve"]
    manifest["pipeline"] = {
        "intermediateBuffers": [],
        "passes": [{
            "passIndex": 0,
            "fragmentShader": "main.frag",
            "inputs": [
                {"type": "source_texture", "index": 0},
                {"type": "source_texture", "index": 1},
            ],
            "output": {"type": "canvas"},
        }],
    }

    dest = OUT / pkg_id
    dest.mkdir(parents=True, exist_ok=True)
    (dest / "main.frag").write_text("".join(parts))
    (dest / "transition.json").write_text(json.dumps(manifest, indent=2) + "\n")
    return pkg_id, header


GENERATED_INDEX = OUT / ".gl-generated.json"


def prune_stale(current):
    """Drop packages a previous run generated but this one no longer does.

    Only ids recorded in the index are ever removed, so hand-authored packages sharing the
    directory (energy_burst, page_turn, ...) are never touched.
    """
    if not GENERATED_INDEX.is_file():
        return []
    previous = set(json.loads(GENERATED_INDEX.read_text()))
    stale = sorted(previous - set(current))
    for pkg_id in stale:
        target = OUT / pkg_id
        if target.is_dir():
            for child in target.iterdir():
                child.unlink()
            target.rmdir()
    return stale


def write_attribution(entries):
    lines = [
        "# Attribution",
        "",
        "Transitions under `content/transitions/` marked below are ported from",
        "[gl-transitions](https://github.com/gl-transitions/gl-transitions) (MIT), pinned at",
        "`" + UPSTREAM_PIN + "`. The shader bodies are upstream's; the",
        "surrounding preamble, parameter plumbing and package metadata are generated by",
        "`recipes/import-gl-transitions.py`.",
        "",
        "| Package | Upstream file | Credit |",
        "| --- | --- | --- |",
    ]
    for pkg_id, source, header in sorted(entries):
        credit = " ".join(
            l.lstrip("/ ").strip() for l in header.splitlines() if l.strip().startswith("//")
        ) or "unattributed"
        lines.append(f"| `{pkg_id}` | `{source}` | {credit} |")
    (OUT / "ATTRIBUTION.md").write_text("\n".join(lines) + "\n")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--only", nargs="*", help="upstream file stems to convert")
    ap.add_argument("--list-skipped", action="store_true")
    args = ap.parse_args()

    if args.list_skipped:
        for stem, why in sorted(SKIP.items()):
            print(f"{stem}: {why}")
        return

    if not VENDOR.is_dir():
        fail(f"missing {VENDOR} -- run:\n"
             f"  git clone https://github.com/gl-transitions/gl-transitions "
             f"{VENDOR.parent}\n"
             f"  git -C {VENDOR.parent} checkout {UPSTREAM_PIN}")

    head = subprocess.run(["git", "-C", str(VENDOR.parent), "rev-parse", "HEAD"],
                          capture_output=True, text=True)
    if head.returncode == 0 and head.stdout.strip() != UPSTREAM_PIN:
        print(f"warning: upstream is at {head.stdout.strip()[:12]}, "
              f"not the pinned {UPSTREAM_PIN[:12]}")

    overrides = json.loads(OVERRIDES.read_text()) if OVERRIDES.is_file() else {}
    sources = sorted(VENDOR.glob("*.glsl"))
    if args.only:
        wanted = set(args.only)
        sources = [s for s in sources if s.stem in wanted]
        missing = wanted - {s.stem for s in sources}
        if missing:
            fail(f"no such upstream file(s): {', '.join(sorted(missing))}")

    entries, skipped = [], 0
    for i, path in enumerate(sources):
        if path.stem in SKIP:
            skipped += 1
            continue
        pkg_id, header = convert(path, overrides.get(path.stem, {}), 600 + i * 2)
        entries.append((pkg_id, path.name, header))

    if not args.only:
        stale = prune_stale([e[0] for e in entries])
        GENERATED_INDEX.write_text(json.dumps(sorted(e[0] for e in entries), indent=2) + "\n")
        write_attribution(entries)
        if stale:
            print(f"pruned {len(stale)} stale package(s): {', '.join(stale)}")
    print(f"converted {len(entries)} transitions, skipped {skipped} -> {OUT}")


if __name__ == "__main__":
    main()
