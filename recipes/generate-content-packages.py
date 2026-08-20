#!/usr/bin/env python3
"""Generate addon-only GPU packages into content/{effects,transitions}/.

These merge into effects.core / transitions.core at stage time (they are not in VideoEd).
Idempotent: re-running overwrites package files under content/.
"""

from __future__ import annotations

import json
from pathlib import Path

HERE = Path(__file__).parent
EFFECTS = HERE.parent / "content" / "effects"
TRANSITIONS = HERE.parent / "content" / "transitions"


def param(identifier: str, display: str, *, default: float, min_v: float = 0.0,
          max_v: float = 1.0, typ: str = "float") -> dict:
    p = {
        "identifier": identifier,
        "displayName": display,
        "type": typ,
        "defaultValue": default,
    }
    if typ == "float":
        p["minValue"] = min_v
        p["maxValue"] = max_v
    elif typ == "bool":
        p["minValue"] = 0
        p["maxValue"] = 1
    elif typ == "string":
        pass
    return p


def single_pass_pipeline(shader: str = "main.frag") -> dict:
    return {
        "intermediateBuffers": [],
        "passes": [{
            "passIndex": 0,
            "fragmentShader": shader,
            "inputs": [{"type": "source_texture"}],
            "output": {"type": "canvas"},
        }],
    }


def transition_pipeline(shader: str = "main.frag") -> dict:
    return {
        "intermediateBuffers": [],
        "passes": [{
            "passIndex": 0,
            "fragmentShader": shader,
            "inputs": [
                {"type": "source_texture", "index": 0},
                {"type": "source_texture", "index": 1},
            ],
            "output": {"type": "canvas"},
        }],
    }


def write_effect(eid: str, display: str, category: str, order: int,
                 parameters: list, frag: str, pipeline: dict | None = None,
                 fixed: dict | None = None) -> None:
    d = EFFECTS / eid
    d.mkdir(parents=True, exist_ok=True)
    meta = {
        "id": eid,
        "displayName": display,
        "category": category,
        "order": order,
        "parameters": parameters,
        "backend": "gpu",
        "pipeline": pipeline or single_pass_pipeline(),
    }
    if fixed:
        meta["fixedParams"] = fixed
    (d / "effect.json").write_text(json.dumps(meta, indent=2) + "\n")
    (d / "main.frag").write_text(frag if frag.endswith("\n") else frag + "\n")


def write_effect_files(eid: str, display: str, category: str, order: int,
                       parameters: list, files: dict[str, str],
                       pipeline: dict, fixed: dict | None = None) -> None:
    d = EFFECTS / eid
    d.mkdir(parents=True, exist_ok=True)
    meta = {
        "id": eid,
        "displayName": display,
        "category": category,
        "order": order,
        "parameters": parameters,
        "backend": "gpu",
        "pipeline": pipeline,
    }
    if fixed:
        meta["fixedParams"] = fixed
    (d / "effect.json").write_text(json.dumps(meta, indent=2) + "\n")
    for name, body in files.items():
        (d / name).write_text(body if body.endswith("\n") else body + "\n")


def write_transition(tid: str, display: str, category: str, order: int,
                     parameters: list, frag: str, audio: str = "crossfade") -> None:
    d = TRANSITIONS / tid
    d.mkdir(parents=True, exist_ok=True)
    meta = {
        "id": tid,
        "displayName": display,
        "category": category,
        "order": order,
        "audioCurve": audio,
        "parameters": parameters,
        "pipeline": transition_pipeline(),
    }
    (d / "transition.json").write_text(json.dumps(meta, indent=2) + "\n")
    # Shared helper header used by existing core transitions
    if "float hash11" not in frag:
        frag = TRANSITION_PREAMBLE + frag
    (d / "main.frag").write_text(frag if frag.endswith("\n") else frag + "\n")


TRANSITION_PREAMBLE = """#version 330 core
in vec2 v_texCoord;
out vec4 fragColor;

uniform sampler2D u_currentTexture;
uniform sampler2D u_fromTexture;
uniform sampler2D u_toTexture;
uniform vec2 u_resolution;
uniform float u_progress;

float hash11(float p) {
    p = fract(p * 0.1031);
    p *= p + 33.33;
    p *= p + p;
    return fract(p);
}

float hash21(vec2 p) {
    vec3 p3 = fract(vec3(p.xyx) * 0.1031);
    p3 += dot(p3, p3.yzx + 33.33);
    return fract((p3.x + p3.y) * p3.z);
}

vec2 hash22(vec2 p) {
    vec3 p3 = fract(vec3(p.xyx) * vec3(0.1031, 0.1030, 0.0973));
    p3 += dot(p3, p3.yzx + 33.33);
    return fract((p3.xx + p3.yz) * p3.zy);
}

float valueNoise(vec2 p) {
    vec2 i = floor(p);
    vec2 f = fract(p);
    f = f * f * (3.0 - 2.0 * f);
    float a = hash21(i);
    float b = hash21(i + vec2(1.0, 0.0));
    float c = hash21(i + vec2(0.0, 1.0));
    float d = hash21(i + vec2(1.0, 1.0));
    return mix(mix(a, b, f.x), mix(c, d, f.x), f.y);
}

float fbm(vec2 p) {
    float v = 0.0;
    float amp = 0.5;
    for (int i = 0; i < 5; ++i) {
        v += amp * valueNoise(p);
        p *= 2.02;
        amp *= 0.5;
    }
    return v;
}

vec4 over(vec4 top, vec4 bot) {
    float oa = top.a + bot.a * (1.0 - top.a);
    if (oa <= 0.0001) return vec4(0.0);
    vec3 rgb = (top.rgb * top.a + bot.rgb * bot.a * (1.0 - top.a)) / oa;
    return vec4(rgb, oa);
}

float aspectRatio() { return u_resolution.x / max(u_resolution.y, 1.0); }

"""


NOISE_HELPERS = """
float hash21(vec2 p) {
    vec3 p3 = fract(vec3(p.xyx) * 0.1031);
    p3 += dot(p3, p3.yzx + 33.33);
    return fract((p3.x + p3.y) * p3.z);
}
vec2 hash22(vec2 p) {
    vec3 p3 = fract(vec3(p.xyx) * vec3(0.1031, 0.1030, 0.0973));
    p3 += dot(p3, p3.yzx + 33.33);
    return fract((p3.xx + p3.yz) * p3.zy);
}
float valueNoise(vec2 p) {
    vec2 i = floor(p);
    vec2 f = fract(p);
    f = f * f * (3.0 - 2.0 * f);
    float a = hash21(i);
    float b = hash21(i + vec2(1.0, 0.0));
    float c = hash21(i + vec2(0.0, 1.0));
    float d = hash21(i + vec2(1.0, 1.0));
    return mix(mix(a, b, f.x), mix(c, d, f.x), f.y);
}
float fbm(vec2 p) {
    float v = 0.0;
    float amp = 0.5;
    for (int i = 0; i < 5; ++i) {
        v += amp * valueNoise(p);
        p *= 2.02;
        amp *= 0.5;
    }
    return v;
}
"""


def gen_effects() -> None:
    # --- Distortion ---
    write_effect(
        "turbulent_displace", "Turbulent Displace", "glitch", 700,
        [
            param("amount", "Amount", default=0.35, max_v=1),
            param("scale", "Scale", default=3.0, min_v=0.5, max_v=12),
            param("speed", "Speed", default=1.0, max_v=4),
            param("octaves", "Octaves", default=4, min_v=1, max_v=6),
            param("evolution", "Evolution", default=0.0, max_v=10),
        ],
        f"""#version 330 core
in vec2 v_texCoord; out vec4 fragColor;
uniform sampler2D u_currentTexture; uniform vec2 u_resolution; uniform float u_time;
uniform float amount; uniform float scale; uniform float speed;
uniform float octaves; uniform float evolution;
{NOISE_HELPERS}
void main() {{
    float amp = amount * 0.08;
    if (amp <= 1e-6) {{ fragColor = texture(u_currentTexture, v_texCoord); return; }}
    float aspect = u_resolution.x / max(u_resolution.y, 1.0);
    vec2 uv = v_texCoord;
    vec2 p = vec2(uv.x * aspect, uv.y) * scale;
    float t = u_time * speed + evolution;
    int n = int(clamp(floor(octaves + 0.5), 1.0, 6.0));
    vec2 warp = vec2(0.0);
    float a = 1.0;
    vec2 q = p;
    for (int i = 0; i < 6; ++i) {{
        if (i >= n) break;
        warp += a * vec2(valueNoise(q + vec2(t, 0.0)), valueNoise(q + vec2(0.0, t + 17.0)));
        q = q * 2.02 + vec2(1.7, 9.2);
        a *= 0.5;
    }}
    vec2 src = clamp(uv + (warp - 0.5) * 2.0 * amp, 0.0, 1.0);
    fragColor = texture(u_currentTexture, src);
}}
""",
    )

    write_effect(
        "spherize", "Spherize", "glitch", 710,
        [
            param("amount", "Amount", default=0.5, min_v=-1, max_v=1),
            param("radius", "Radius", default=0.55, max_v=1),
            param("centerX", "Center X", default=0.5),
            param("centerY", "Center Y", default=0.5),
        ],
        """#version 330 core
in vec2 v_texCoord; out vec4 fragColor;
uniform sampler2D u_currentTexture; uniform vec2 u_resolution;
uniform float amount; uniform float radius; uniform float centerX; uniform float centerY;
void main() {
    float aspect = u_resolution.x / max(u_resolution.y, 1.0);
    vec2 c = vec2(centerX, centerY);
    vec2 d = (v_texCoord - c) * vec2(aspect, 1.0);
    float r = length(d);
    float R = max(radius, 1e-4);
    if (r >= R || abs(amount) < 1e-5) {
        fragColor = texture(u_currentTexture, v_texCoord);
        return;
    }
    float t = r / R;
    float bulge = mix(t, sin(t * 1.5707963), amount);
    vec2 nd = (r > 1e-6) ? d * (bulge / t) : d;
    vec2 src = c + vec2(nd.x / aspect, nd.y);
    fragColor = texture(u_currentTexture, clamp(src, 0.0, 1.0));
}
""",
    )

    write_effect(
        "lens_distortion", "Lens Distortion", "glitch", 720,
        [
            param("k1", "Barrel / Pincushion", default=-0.25, min_v=-1, max_v=1),
            param("k2", "Secondary", default=0.0, min_v=-1, max_v=1),
            param("centerX", "Center X", default=0.5),
            param("centerY", "Center Y", default=0.5),
            param("scale", "Scale", default=1.0, min_v=0.5, max_v=1.5),
        ],
        """#version 330 core
in vec2 v_texCoord; out vec4 fragColor;
uniform sampler2D u_currentTexture; uniform vec2 u_resolution;
uniform float k1; uniform float k2; uniform float centerX; uniform float centerY; uniform float scale;
void main() {
    float aspect = u_resolution.x / max(u_resolution.y, 1.0);
    vec2 c = vec2(centerX, centerY);
    vec2 p = (v_texCoord - c) * vec2(aspect, 1.0) / max(scale, 1e-4);
    float r2 = dot(p, p);
    float f = 1.0 + k1 * r2 + k2 * r2 * r2;
    vec2 src = c + vec2(p.x / aspect, p.y) * f;
    if (src.x < 0.0 || src.x > 1.0 || src.y < 0.0 || src.y > 1.0) {
        fragColor = vec4(0.0);
        return;
    }
    fragColor = texture(u_currentTexture, src);
}
""",
    )

    write_effect(
        "corner_pin", "Corner Pin", "glitch", 730,
        [
            param("tlX", "Top Left X", default=0.0),
            param("tlY", "Top Left Y", default=0.0),
            param("trX", "Top Right X", default=1.0),
            param("trY", "Top Right Y", default=0.0),
            param("brX", "Bottom Right X", default=1.0),
            param("brY", "Bottom Right Y", default=1.0),
            param("blX", "Bottom Left X", default=0.0),
            param("blY", "Bottom Left Y", default=1.0),
        ],
        """#version 330 core
in vec2 v_texCoord; out vec4 fragColor;
uniform sampler2D u_currentTexture;
uniform float tlX; uniform float tlY; uniform float trX; uniform float trY;
uniform float brX; uniform float brY; uniform float blX; uniform float blY;

// Inverse bilinear map: screen UV -> unit square, then sample source.
bool invBilinear(vec2 p, vec2 a, vec2 b, vec2 c, vec2 d, out vec2 uv) {
    vec2 e = b - a;
    vec2 f = d - a;
    vec2 g = a - b + c - d;
    vec2 h = p - a;
    float k2 = g.x * f.y - g.y * f.x;
    float k1 = e.x * f.y - e.y * f.x + h.x * g.y - h.y * g.x;
    float k0 = h.x * e.y - h.y * e.x;
    float v;
    if (abs(k2) < 1e-6) {
        if (abs(k1) < 1e-6) return false;
        v = -k0 / k1;
    } else {
        float disc = k1 * k1 - 4.0 * k2 * k0;
        if (disc < 0.0) return false;
        float sd = sqrt(disc);
        float v0 = (-k1 - sd) / (2.0 * k2);
        float v1 = (-k1 + sd) / (2.0 * k2);
        v = (v0 >= 0.0 && v0 <= 1.0) ? v0 : v1;
    }
    float denom = e.x + g.x * v;
    float u = (abs(denom) > abs(e.y + g.y * v))
        ? (h.x - f.x * v) / denom
        : (h.y - f.y * v) / (e.y + g.y * v);
    uv = vec2(u, v);
    return u >= 0.0 && u <= 1.0 && v >= 0.0 && v <= 1.0;
}

void main() {
    vec2 a = vec2(tlX, tlY);
    vec2 b = vec2(trX, trY);
    vec2 c = vec2(brX, brY);
    vec2 d = vec2(blX, blY);
    vec2 uv;
    if (!invBilinear(v_texCoord, a, b, c, d, uv)) {
        fragColor = vec4(0.0);
        return;
    }
    fragColor = texture(u_currentTexture, clamp(uv, 0.0, 1.0));
}
""",
    )

    write_effect(
        "twirl", "Twirl", "glitch", 740,
        [
            param("angle", "Angle", default=2.0, min_v=-6.28, max_v=6.28),
            param("radius", "Radius", default=0.45, max_v=1),
            param("centerX", "Center X", default=0.5),
            param("centerY", "Center Y", default=0.5),
        ],
        """#version 330 core
in vec2 v_texCoord; out vec4 fragColor;
uniform sampler2D u_currentTexture; uniform vec2 u_resolution;
uniform float angle; uniform float radius; uniform float centerX; uniform float centerY;
void main() {
    float aspect = u_resolution.x / max(u_resolution.y, 1.0);
    vec2 c = vec2(centerX, centerY);
    vec2 d = (v_texCoord - c) * vec2(aspect, 1.0);
    float r = length(d);
    float R = max(radius, 1e-4);
    float fall = 1.0 - smoothstep(0.0, R, r);
    float a = atan(d.y, d.x) + angle * fall * fall;
    vec2 nd = (r > 1e-6) ? vec2(cos(a), sin(a)) * r : d;
    vec2 src = c + vec2(nd.x / aspect, nd.y);
    fragColor = texture(u_currentTexture, clamp(src, 0.0, 1.0));
}
""",
    )

    write_effect(
        "mirror", "Mirror", "glitch", 750,
        [
            param("mode", "Mode", default=0.0, max_v=3),  # 0 L, 1 R, 2 T, 3 B
            param("offset", "Offset", default=0.5),
        ],
        """#version 330 core
in vec2 v_texCoord; out vec4 fragColor;
uniform sampler2D u_currentTexture;
uniform float mode; uniform float offset;
void main() {
    vec2 uv = v_texCoord;
    int m = int(clamp(floor(mode + 0.5), 0.0, 3.0));
    float o = clamp(offset, 0.0, 1.0);
    if (m == 0) {
        if (uv.x > o) uv.x = 2.0 * o - uv.x;
    } else if (m == 1) {
        if (uv.x < o) uv.x = 2.0 * o - uv.x;
    } else if (m == 2) {
        if (uv.y > o) uv.y = 2.0 * o - uv.y;
    } else {
        if (uv.y < o) uv.y = 2.0 * o - uv.y;
    }
    fragColor = texture(u_currentTexture, clamp(uv, 0.0, 1.0));
}
""",
    )

    write_effect(
        "prism_lens", "Prism Lens", "glitch", 760,
        [
            param("amount", "Amount", default=0.4, max_v=1),
            param("slices", "Slices", default=3, min_v=2, max_v=8),
            param("dispersion", "Dispersion", default=0.5, max_v=1),
            param("centerX", "Center X", default=0.5),
            param("centerY", "Center Y", default=0.5),
        ],
        """#version 330 core
in vec2 v_texCoord; out vec4 fragColor;
uniform sampler2D u_currentTexture; uniform vec2 u_resolution;
uniform float amount; uniform float slices; uniform float dispersion;
uniform float centerX; uniform float centerY;
void main() {
    float aspect = u_resolution.x / max(u_resolution.y, 1.0);
    vec2 c = vec2(centerX, centerY);
    vec2 d = (v_texCoord - c) * vec2(aspect, 1.0);
    float r = length(d);
    int n = int(clamp(floor(slices + 0.5), 2.0, 8.0));
    float amp = amount * 0.06;
    vec3 acc = vec3(0.0);
    float wsum = 0.0;
    for (int i = 0; i < 8; ++i) {
        if (i >= n) break;
        float t = (float(i) / float(n - 1) - 0.5) * 2.0;
        float ang = t * amount * 0.35;
        float ca = cos(ang); float sa = sin(ang);
        vec2 rd = vec2(d.x * ca - d.y * sa, d.x * sa + d.y * ca);
        float shift = t * amp * (0.5 + dispersion) * (0.25 + r);
        vec2 base = c + vec2(rd.x / aspect, rd.y);
        vec2 off = normalize(vec2(rd.x / aspect, rd.y) + 1e-5) * shift;
        float w = 1.0 - abs(t) * 0.35;
        vec2 uR = clamp(base + off * (1.0 + dispersion), 0.0, 1.0);
        vec2 uG = clamp(base, 0.0, 1.0);
        vec2 uB = clamp(base - off * (1.0 + dispersion), 0.0, 1.0);
        acc += vec3(texture(u_currentTexture, uR).r,
                    texture(u_currentTexture, uG).g,
                    texture(u_currentTexture, uB).b) * w;
        wsum += w;
    }
    float a = texture(u_currentTexture, v_texCoord).a;
    fragColor = vec4(acc / max(wsum, 1e-4), a);
}
""",
    )

    # --- Blur ---
    write_effect(
        "directional_blur", "Directional Blur", "impact", 770,
        [
            param("amount", "Amount", default=0.4, max_v=1),
            param("angle", "Angle", default=0.0, max_v=360),
            param("samples", "Samples", default=12, min_v=4, max_v=24),
        ],
        """#version 330 core
in vec2 v_texCoord; out vec4 fragColor;
uniform sampler2D u_currentTexture; uniform vec2 u_resolution;
uniform float amount; uniform float angle; uniform float samples;
void main() {
    if (amount <= 1e-5) { fragColor = texture(u_currentTexture, v_texCoord); return; }
    float rad = radians(angle);
    vec2 dir = vec2(cos(rad), sin(rad)) / u_resolution * (amount * 40.0);
    int n = int(clamp(floor(samples + 0.5), 4.0, 24.0));
    vec3 acc = vec3(0.0);
    float wsum = 0.0;
    for (int i = 0; i < 24; ++i) {
        if (i >= n) break;
        float t = (float(i) / float(n - 1) - 0.5) * 2.0;
        float w = 1.0 - abs(t) * 0.5;
        acc += texture(u_currentTexture, clamp(v_texCoord + dir * t, 0.0, 1.0)).rgb * w;
        wsum += w;
    }
    fragColor = vec4(acc / max(wsum, 1e-4), texture(u_currentTexture, v_texCoord).a);
}
""",
    )

    write_effect(
        "zoom_blur", "Zoom Blur", "impact", 780,
        [
            param("amount", "Amount", default=0.35, max_v=1),
            param("centerX", "Center X", default=0.5),
            param("centerY", "Center Y", default=0.5),
            param("samples", "Samples", default=12, min_v=4, max_v=24),
        ],
        """#version 330 core
in vec2 v_texCoord; out vec4 fragColor;
uniform sampler2D u_currentTexture;
uniform float amount; uniform float centerX; uniform float centerY; uniform float samples;
void main() {
    if (amount <= 1e-5) { fragColor = texture(u_currentTexture, v_texCoord); return; }
    vec2 c = vec2(centerX, centerY);
    vec2 d = v_texCoord - c;
    int n = int(clamp(floor(samples + 0.5), 4.0, 24.0));
    vec3 acc = vec3(0.0);
    float wsum = 0.0;
    for (int i = 0; i < 24; ++i) {
        if (i >= n) break;
        float t = float(i) / float(n - 1);
        float s = 1.0 - t * amount * 0.45;
        float w = 1.0 - t * 0.55;
        acc += texture(u_currentTexture, clamp(c + d * s, 0.0, 1.0)).rgb * w;
        wsum += w;
    }
    fragColor = vec4(acc / max(wsum, 1e-4), texture(u_currentTexture, v_texCoord).a);
}
""",
    )

    write_effect(
        "tilt_shift", "Tilt Shift", "dreamy", 790,
        [
            param("blur", "Blur", default=0.55, max_v=1),
            param("focus", "Focus Y", default=0.5),
            param("range", "Focus Range", default=0.18, min_v=0.02, max_v=0.6),
            param("softness", "Softness", default=0.25, min_v=0.01, max_v=0.6),
            param("samples", "Samples", default=10, min_v=4, max_v=20),
        ],
        """#version 330 core
in vec2 v_texCoord; out vec4 fragColor;
uniform sampler2D u_currentTexture; uniform vec2 u_resolution;
uniform float blur; uniform float focus; uniform float range;
uniform float softness; uniform float samples;
void main() {
    float dist = abs(v_texCoord.y - focus);
    float m = smoothstep(range, range + softness, dist);
    float amt = m * blur;
    if (amt <= 1e-5) { fragColor = texture(u_currentTexture, v_texCoord); return; }
    vec2 px = 1.0 / u_resolution;
    int n = int(clamp(floor(samples + 0.5), 4.0, 20.0));
    vec3 acc = vec3(0.0);
    float wsum = 0.0;
    float rad = amt * 12.0;
    for (int i = 0; i < 20; ++i) {
        if (i >= n) break;
        float t = (float(i) / float(n - 1) - 0.5) * 2.0;
        float w = exp(-t * t * 2.0);
        acc += texture(u_currentTexture, clamp(v_texCoord + vec2(0.0, px.y * rad * t), 0.0, 1.0)).rgb * w;
        wsum += w;
    }
    // mild horizontal pass contribution
    for (int i = 0; i < 20; ++i) {
        if (i >= n) break;
        float t = (float(i) / float(n - 1) - 0.5) * 2.0;
        float w = exp(-t * t * 2.0) * 0.65;
        acc += texture(u_currentTexture, clamp(v_texCoord + vec2(px.x * rad * t * 0.6, 0.0), 0.0, 1.0)).rgb * w;
        wsum += w;
    }
    fragColor = vec4(acc / max(wsum, 1e-4), texture(u_currentTexture, v_texCoord).a);
}
""",
    )

    # Light rays — multi-pass: bright extract then radial blur composite
    write_effect_files(
        "light_rays", "Light Rays", "dreamy", 800,
        [
            param("intensity", "Intensity", default=0.7, max_v=2),
            param("threshold", "Threshold", default=0.7),
            param("rayLength", "Length", default=0.55, max_v=1),
            param("centerX", "Center X", default=0.5),
            param("centerY", "Center Y", default=0.35),
            param("samples", "Samples", default=16, min_v=6, max_v=32),
        ],
        {
            "bright.frag": """#version 330 core
in vec2 v_texCoord; out vec4 fragColor;
uniform sampler2D u_currentTexture;
uniform float threshold;
void main() {
    vec4 c = texture(u_currentTexture, v_texCoord);
    float lum = dot(c.rgb, vec3(0.2126, 0.7152, 0.0722));
    float m = smoothstep(threshold, min(threshold + 0.2, 1.0), lum);
    fragColor = vec4(c.rgb * m, c.a);
}
""",
            "rays.frag": """#version 330 core
in vec2 v_texCoord; out vec4 fragColor;
uniform sampler2D u_currentTexture; // bright
uniform sampler2D u_texture1;       // original
uniform float intensity; uniform float rayLength; uniform float centerX;
uniform float centerY; uniform float samples;
void main() {
    vec4 src = texture(u_texture1, v_texCoord);
    vec2 c = vec2(centerX, centerY);
    vec2 d = v_texCoord - c;
    int n = int(clamp(floor(samples + 0.5), 6.0, 32.0));
    vec3 acc = vec3(0.0);
    float wsum = 0.0;
    for (int i = 0; i < 32; ++i) {
        if (i >= n) break;
        float t = float(i) / float(n - 1);
        float w = 1.0 - t;
        vec2 uv = clamp(c + d * (1.0 - t * rayLength), 0.0, 1.0);
        acc += texture(u_currentTexture, uv).rgb * w;
        wsum += w;
    }
    vec3 rays = acc / max(wsum, 1e-4);
    fragColor = vec4(src.rgb + rays * intensity, src.a);
}
""",
        },
        {
            "intermediateBuffers": [{"id": "bright", "scale": 1.0}],
            "passes": [
                {
                    "passIndex": 0,
                    "fragmentShader": "bright.frag",
                    "inputs": [{"type": "source_texture"}],
                    "output": {"type": "buffer", "id": "bright"},
                },
                {
                    "passIndex": 1,
                    "fragmentShader": "rays.frag",
                    "inputs": [
                        {"type": "buffer", "id": "bright"},
                        {"type": "source_texture"},
                    ],
                    "output": {"type": "canvas"},
                },
            ],
        },
    )

    write_effect_files(
        "aperture_diffraction", "Aperture Diffraction", "dreamy", 810,
        [
            param("intensity", "Intensity", default=0.85, max_v=2),
            param("threshold", "Threshold", default=0.78),
            param("bladeCount", "Blades", default=6, min_v=4, max_v=10),
            param("spikeLength", "Length", default=0.45, max_v=1),
            param("rotation", "Rotation", default=0.0, max_v=1),
            param("dispersion", "Dispersion", default=0.35),
        ],
        {
            "bright.frag": """#version 330 core
in vec2 v_texCoord; out vec4 fragColor;
uniform sampler2D u_currentTexture;
uniform float threshold;
void main() {
    vec4 c = texture(u_currentTexture, v_texCoord);
    float lum = dot(c.rgb, vec3(0.2126, 0.7152, 0.0722));
    float m = smoothstep(threshold, min(threshold + 0.15, 1.0), lum);
    fragColor = vec4(c.rgb * m, c.a);
}
""",
            "streak.frag": """#version 330 core
in vec2 v_texCoord; out vec4 fragColor;
uniform sampler2D u_currentTexture; // bright
uniform sampler2D u_texture1;       // original
uniform vec2 u_resolution;
uniform float intensity; uniform float bladeCount; uniform float spikeLength;
uniform float rotation; uniform float dispersion;
void main() {
    vec4 src = texture(u_texture1, v_texCoord);
    int blades = int(clamp(floor(bladeCount + 0.5), 4.0, 10.0));
    float baseAng = rotation * 3.14159265;
    vec2 px = 1.0 / u_resolution;
    vec3 spikes = vec3(0.0);
    for (int b = 0; b < 10; ++b) {
        if (b >= blades) break;
        float ang = baseAng + float(b) * 3.14159265 / float(blades);
        vec2 dir = vec2(cos(ang), sin(ang));
        for (int s = 1; s <= 18; ++s) {
            float t = float(s) / 18.0;
            float w = (1.0 - t) * (1.0 - t);
            vec2 o = dir * px * (t * spikeLength * 120.0);
            vec3 samp = texture(u_currentTexture, clamp(v_texCoord + o, 0.0, 1.0)).rgb;
            float hue = float(b) / float(blades) + t * dispersion * 0.35;
            vec3 tint = 0.65 + 0.35 * vec3(
                0.5 + 0.5 * cos(6.2831 * (hue + 0.0)),
                0.5 + 0.5 * cos(6.2831 * (hue + 0.33)),
                0.5 + 0.5 * cos(6.2831 * (hue + 0.67)));
            spikes += samp * w * mix(vec3(1.0), tint, dispersion);
        }
    }
    fragColor = vec4(src.rgb + spikes * intensity * 0.12, src.a);
}
""",
        },
        {
            "intermediateBuffers": [{"id": "bright", "scale": 1.0}],
            "passes": [
                {
                    "passIndex": 0,
                    "fragmentShader": "bright.frag",
                    "inputs": [{"type": "source_texture"}],
                    "output": {"type": "buffer", "id": "bright"},
                },
                {
                    "passIndex": 1,
                    "fragmentShader": "streak.frag",
                    "inputs": [
                        {"type": "buffer", "id": "bright"},
                        {"type": "source_texture"},
                    ],
                    "output": {"type": "canvas"},
                },
            ],
        },
    )

    # --- Stylize ---
    write_effect(
        "color_emboss", "Color Emboss", "artistic", 820,
        [
            param("strength", "Strength", default=0.7, max_v=2),
            param("angle", "Angle", default=45.0, max_v=360),
            param("blend", "Blend", default=0.85),
        ],
        """#version 330 core
in vec2 v_texCoord; out vec4 fragColor;
uniform sampler2D u_currentTexture; uniform vec2 u_resolution;
uniform float strength; uniform float angle; uniform float blend;
void main() {
    vec2 px = 1.0 / u_resolution;
    float rad = radians(angle);
    vec2 dir = vec2(cos(rad), sin(rad)) * px;
    vec3 a = texture(u_currentTexture, clamp(v_texCoord - dir, 0.0, 1.0)).rgb;
    vec3 b = texture(u_currentTexture, clamp(v_texCoord + dir, 0.0, 1.0)).rgb;
    vec3 emb = (b - a) * strength + 0.5;
    vec3 src = texture(u_currentTexture, v_texCoord).rgb;
    fragColor = vec4(mix(src, emb, clamp(blend, 0.0, 1.0)), texture(u_currentTexture, v_texCoord).a);
}
""",
    )

    write_effect(
        "find_edges", "Find Edges", "artistic", 830,
        [
            param("strength", "Strength", default=1.0, max_v=3),
            param("invert", "Invert", default=0.0, typ="bool"),
            param("threshold", "Threshold", default=0.1),
        ],
        """#version 330 core
in vec2 v_texCoord; out vec4 fragColor;
uniform sampler2D u_currentTexture; uniform vec2 u_resolution;
uniform float strength; uniform float invert; uniform float threshold;
void main() {
    vec2 px = 1.0 / u_resolution;
    float tl = dot(texture(u_currentTexture, v_texCoord + px * vec2(-1, -1)).rgb, vec3(0.299, 0.587, 0.114));
    float t  = dot(texture(u_currentTexture, v_texCoord + px * vec2( 0, -1)).rgb, vec3(0.299, 0.587, 0.114));
    float tr = dot(texture(u_currentTexture, v_texCoord + px * vec2( 1, -1)).rgb, vec3(0.299, 0.587, 0.114));
    float l  = dot(texture(u_currentTexture, v_texCoord + px * vec2(-1,  0)).rgb, vec3(0.299, 0.587, 0.114));
    float r  = dot(texture(u_currentTexture, v_texCoord + px * vec2( 1,  0)).rgb, vec3(0.299, 0.587, 0.114));
    float bl = dot(texture(u_currentTexture, v_texCoord + px * vec2(-1,  1)).rgb, vec3(0.299, 0.587, 0.114));
    float b  = dot(texture(u_currentTexture, v_texCoord + px * vec2( 0,  1)).rgb, vec3(0.299, 0.587, 0.114));
    float br = dot(texture(u_currentTexture, v_texCoord + px * vec2( 1,  1)).rgb, vec3(0.299, 0.587, 0.114));
    float gx = -tl - 2.0*l - bl + tr + 2.0*r + br;
    float gy = -tl - 2.0*t - tr + bl + 2.0*b + br;
    float e = length(vec2(gx, gy)) * strength;
    e = smoothstep(threshold, threshold + 0.15, e);
    if (invert > 0.5) e = 1.0 - e;
    float a = texture(u_currentTexture, v_texCoord).a;
    fragColor = vec4(vec3(e), a);
}
""",
    )

    write_effect(
        "roughen_edges", "Roughen Edges", "artistic", 840,
        [
            param("amount", "Amount", default=0.45, max_v=1),
            param("scale", "Scale", default=40.0, min_v=5, max_v=120),
            param("edgeWidth", "Edge Width", default=0.35, max_v=1),
        ],
        f"""#version 330 core
in vec2 v_texCoord; out vec4 fragColor;
uniform sampler2D u_currentTexture; uniform vec2 u_resolution; uniform float u_time;
uniform float amount; uniform float scale; uniform float edgeWidth;
{NOISE_HELPERS}
void main() {{
    vec2 px = 1.0 / u_resolution;
    float a0 = texture(u_currentTexture, v_texCoord).a;
    float edge = 0.0;
    for (int y = -2; y <= 2; ++y) {{
        for (int x = -2; x <= 2; ++x) {{
            float aa = texture(u_currentTexture, clamp(v_texCoord + px * vec2(x, y), 0.0, 1.0)).a;
            edge = max(edge, abs(a0 - aa));
        }}
    }}
    float n = valueNoise(v_texCoord * scale + u_time * 0.0);
    float erode = (n - 0.5) * 2.0 * amount * edgeWidth * edge;
    vec2 off = vec2(erode, erode * 0.7) * px * 8.0;
    fragColor = texture(u_currentTexture, clamp(v_texCoord + off, 0.0, 1.0));
}}
""",
    )

    write_effect(
        "posterize", "Posterize", "artistic", 850,
        [
            param("levels", "Levels", default=6, min_v=2, max_v=32),
            param("strength", "Strength", default=1.0),
        ],
        """#version 330 core
in vec2 v_texCoord; out vec4 fragColor;
uniform sampler2D u_currentTexture;
uniform float levels; uniform float strength;
void main() {
    vec4 c = texture(u_currentTexture, v_texCoord);
    float n = max(floor(levels + 0.5), 2.0);
    vec3 q = floor(c.rgb * (n - 1.0) + 0.5) / (n - 1.0);
    fragColor = vec4(mix(c.rgb, q, clamp(strength, 0.0, 1.0)), c.a);
}
""",
    )

    write_effect(
        "mosaic_hex", "Hex Mosaic", "artistic", 860,
        [
            param("size", "Size", default=24.0, min_v=4, max_v=80),
            param("strength", "Strength", default=1.0),
        ],
        """#version 330 core
in vec2 v_texCoord; out vec4 fragColor;
uniform sampler2D u_currentTexture; uniform vec2 u_resolution;
uniform float size; uniform float strength;
vec2 hexCenter(vec2 p) {
    // axial hex grid
    vec2 r = vec2(1.0, 1.7320508);
    vec2 h = r * 0.5;
    vec2 a = mod(p, r) - h;
    vec2 b = mod(p - h, r) - h;
    return (dot(a, a) < dot(b, b)) ? a : b;
}
void main() {
    float s = max(size, 2.0);
    vec2 p = v_texCoord * u_resolution / s;
    vec2 d = hexCenter(p);
    vec2 cell = (p - d) * s / u_resolution;
    vec4 src = texture(u_currentTexture, v_texCoord);
    vec4 hex = texture(u_currentTexture, clamp(cell, 0.0, 1.0));
    fragColor = mix(src, hex, clamp(strength, 0.0, 1.0));
}
""",
    )

    # --- Color ---
    # Lightroom-style tone and HSL tools. Distinct from bundled brightness/hue/
    # saturation and from the RGB overlay `tint` already in this pack.
    write_effect(
        "adjust_exposure", "Exposure", "color", 5,
        [param("exposure", "Stops", default=0.0, min_v=-3, max_v=3)],
        """#version 330 core
in vec2 v_texCoord; out vec4 fragColor;
uniform sampler2D u_currentTexture; uniform float exposure;
void main() {
    vec4 c = texture(u_currentTexture, v_texCoord);
    fragColor = vec4(clamp(c.rgb * exp2(exposure), 0.0, 1.0), c.a);
}
""",
    )

    write_effect(
        "adjust_highlights", "Highlights", "color", 22,
        [param("highlights", "Amount", default=0.0, min_v=-1, max_v=1)],
        """#version 330 core
in vec2 v_texCoord; out vec4 fragColor;
uniform sampler2D u_currentTexture; uniform float highlights;
void main() {
    vec4 c = texture(u_currentTexture, v_texCoord);
    float l = dot(c.rgb, vec3(0.299, 0.587, 0.114));
    float w = smoothstep(0.45, 1.0, l);
    vec3 room = highlights >= 0.0 ? (1.0 - c.rgb) : c.rgb * 0.6;
    fragColor = vec4(clamp(c.rgb + highlights * w * room, 0.0, 1.0), c.a);
}
""",
    )

    write_effect(
        "adjust_shadows", "Shadows", "color", 24,
        [param("shadows", "Amount", default=0.0, min_v=-1, max_v=1)],
        """#version 330 core
in vec2 v_texCoord; out vec4 fragColor;
uniform sampler2D u_currentTexture; uniform float shadows;
void main() {
    vec4 c = texture(u_currentTexture, v_texCoord);
    float l = dot(c.rgb, vec3(0.299, 0.587, 0.114));
    float w = (1.0 - smoothstep(0.0, 0.55, l)) * smoothstep(0.0, 0.10, l);
    vec3 room = shadows >= 0.0 ? (1.0 - c.rgb) * 0.5 : c.rgb * 0.7;
    fragColor = vec4(clamp(c.rgb + shadows * w * room, 0.0, 1.0), c.a);
}
""",
    )

    write_effect(
        "adjust_whites", "Whites", "color", 26,
        [param("whites", "Amount", default=0.0, min_v=-1, max_v=1)],
        """#version 330 core
in vec2 v_texCoord; out vec4 fragColor;
uniform sampler2D u_currentTexture; uniform float whites;
void main() {
    vec4 c = texture(u_currentTexture, v_texCoord);
    float l = dot(c.rgb, vec3(0.299, 0.587, 0.114));
    float w = smoothstep(0.30, 1.0, l);
    float wp = clamp(1.0 - whites * 0.55, 0.1, 2.0);
    fragColor = vec4(clamp(mix(c.rgb, c.rgb / wp, w), 0.0, 1.0), c.a);
}
""",
    )

    write_effect(
        "adjust_blacks", "Blacks", "color", 28,
        [param("blacks", "Amount", default=0.0, min_v=-1, max_v=1)],
        """#version 330 core
in vec2 v_texCoord; out vec4 fragColor;
uniform sampler2D u_currentTexture; uniform float blacks;
void main() {
    vec4 c = texture(u_currentTexture, v_texCoord);
    float l = dot(c.rgb, vec3(0.299, 0.587, 0.114));
    float w = 1.0 - smoothstep(0.0, 0.65, l);
    float bp = -blacks * 0.25;
    vec3 v = (c.rgb - bp) / max(1.0 - bp, 0.05);
    fragColor = vec4(clamp(mix(c.rgb, v, w), 0.0, 1.0), c.a);
}
""",
    )

    write_effect(
        "adjust_vibrance", "Vibrance", "color", 32,
        [param("vibrance", "Amount", default=0.0, min_v=-1, max_v=1)],
        """#version 330 core
in vec2 v_texCoord; out vec4 fragColor;
uniform sampler2D u_currentTexture; uniform float vibrance;
void main() {
    vec4 c = texture(u_currentTexture, v_texCoord);
    float mx = max(c.r, max(c.g, c.b));
    float mn = min(c.r, min(c.g, c.b));
    float sat = mx - mn;
    float l = dot(c.rgb, vec3(0.299, 0.587, 0.114));
    float amt = vibrance * (1.0 - sat);
    float skin = smoothstep(0.0, 0.35, c.r - c.b) * step(c.b, c.g);
    amt *= 1.0 - 0.5 * skin;
    fragColor = vec4(clamp(mix(vec3(l), c.rgb, 1.0 + amt), 0.0, 1.0), c.a);
}
""",
    )

    write_effect(
        "adjust_tint", "Tint (Green/Magenta)", "color", 62,
        [param("tint", "Amount", default=0.0, min_v=-1, max_v=1)],
        """#version 330 core
in vec2 v_texCoord; out vec4 fragColor;
uniform sampler2D u_currentTexture; uniform float tint;
void main() {
    vec4 c = texture(u_currentTexture, v_texCoord);
    vec3 gain = vec3(1.0 + tint * 0.18, 1.0 - tint * 0.22, 1.0 + tint * 0.18);
    fragColor = vec4(clamp(c.rgb * gain, 0.0, 1.0), c.a);
}
""",
    )

    hsl_bands = [
        param("red", "Red", default=0.0, min_v=-1, max_v=1),
        param("orange", "Orange", default=0.0, min_v=-1, max_v=1),
        param("yellow", "Yellow", default=0.0, min_v=-1, max_v=1),
        param("green", "Green", default=0.0, min_v=-1, max_v=1),
        param("aqua", "Aqua", default=0.0, min_v=-1, max_v=1),
        param("blue", "Blue", default=0.0, min_v=-1, max_v=1),
        param("purple", "Purple", default=0.0, min_v=-1, max_v=1),
        param("magenta", "Magenta", default=0.0, min_v=-1, max_v=1),
    ]
    hsl_band_helpers = """
const float BAND_H[8]  = float[8](  0.0,  32.0,  60.0, 120.0, 180.0, 240.0, 280.0, 320.0);
const float BAND_LO[8] = float[8]( 40.0,  32.0,  28.0,  60.0,  60.0,  60.0,  40.0,  40.0);
const float BAND_HI[8] = float[8]( 32.0,  28.0,  60.0,  60.0,  60.0,  40.0,  40.0,  40.0);

vec3 rgb2hsv(vec3 c) {
    vec4 K = vec4(0.0, -1.0 / 3.0, 2.0 / 3.0, -1.0);
    vec4 p = mix(vec4(c.bg, K.wz), vec4(c.gb, K.xy), step(c.b, c.g));
    vec4 q = mix(vec4(p.xyw, c.r), vec4(c.r, p.yzx), step(p.x, c.r));
    float d = q.x - min(q.w, q.y);
    return vec3(abs(q.z + (q.w - q.y) / (6.0 * d + 1e-10)), d / (q.x + 1e-10), q.x);
}

vec3 hsv2rgb(vec3 c) {
    vec4 K = vec4(1.0, 2.0 / 3.0, 1.0 / 3.0, 3.0);
    vec3 p = abs(fract(c.xxx + K.xyz) * 6.0 - K.www);
    return c.z * mix(K.xxx, clamp(p - K.xxx, 0.0, 1.0), c.y);
}

float band(int i, float h) {
    float d = mod(h - BAND_H[i] + 540.0, 360.0) - 180.0;
    return 1.0 - smoothstep(0.0, d < 0.0 ? BAND_LO[i] : BAND_HI[i], abs(d));
}

float bandMix(float h) {
    float v[8] = float[8](red, orange, yellow, green, aqua, blue, purple, magenta);
    float sum = 0.0;
    float tot = 0.0;
    for (int i = 0; i < 8; ++i) {
        float w = band(i, h);
        sum += w * v[i];
        tot += w;
    }
    return tot > 1e-4 ? sum / tot : 0.0;
}
"""

    write_effect(
        "adjust_hsl_hue", "HSL Hue", "color", 70,
        hsl_bands,
        f"""#version 330 core
in vec2 v_texCoord; out vec4 fragColor;
uniform sampler2D u_currentTexture;
uniform float red, orange, yellow, green, aqua, blue, purple, magenta;
{hsl_band_helpers}
void main() {{
    vec4 c = texture(u_currentTexture, v_texCoord);
    vec3 hsv = rgb2hsv(c.rgb);
    float h = hsv.x * 360.0;
    float gate = smoothstep(0.04, 0.20, hsv.y);
    hsv.x = fract((h + bandMix(h) * 30.0 * gate) / 360.0);
    fragColor = vec4(clamp(hsv2rgb(hsv), 0.0, 1.0), c.a);
}}
""",
    )

    write_effect(
        "adjust_hsl_saturation", "HSL Saturation", "color", 72,
        hsl_bands,
        f"""#version 330 core
in vec2 v_texCoord; out vec4 fragColor;
uniform sampler2D u_currentTexture;
uniform float red, orange, yellow, green, aqua, blue, purple, magenta;
{hsl_band_helpers}
void main() {{
    vec4 c = texture(u_currentTexture, v_texCoord);
    vec3 hsv = rgb2hsv(c.rgb);
    float h = hsv.x * 360.0;
    float gate = smoothstep(0.04, 0.20, hsv.y);
    hsv.y = clamp(hsv.y * (1.0 + bandMix(h) * gate), 0.0, 1.0);
    fragColor = vec4(clamp(hsv2rgb(hsv), 0.0, 1.0), c.a);
}}
""",
    )

    write_effect(
        "adjust_hsl_luminance", "HSL Luminance", "color", 74,
        hsl_bands,
        f"""#version 330 core
in vec2 v_texCoord; out vec4 fragColor;
uniform sampler2D u_currentTexture;
uniform float red, orange, yellow, green, aqua, blue, purple, magenta;
{hsl_band_helpers}
void main() {{
    vec4 c = texture(u_currentTexture, v_texCoord);
    vec3 hsv = rgb2hsv(c.rgb);
    float h = hsv.x * 360.0;
    float gate = smoothstep(0.04, 0.20, hsv.y);
    hsv.z = clamp(hsv.z * (1.0 + bandMix(h) * 0.6 * gate), 0.0, 1.0);
    fragColor = vec4(clamp(hsv2rgb(hsv), 0.0, 1.0), c.a);
}}
""",
    )

    write_effect(
        "invert", "Invert", "color", 870,
        [param("strength", "Strength", default=1.0)],
        """#version 330 core
in vec2 v_texCoord; out vec4 fragColor;
uniform sampler2D u_currentTexture;
uniform float strength;
void main() {
    vec4 c = texture(u_currentTexture, v_texCoord);
    fragColor = vec4(mix(c.rgb, 1.0 - c.rgb, clamp(strength, 0.0, 1.0)), c.a);
}
""",
    )

    write_effect(
        "channel_mix", "Channel Mix", "color", 880,
        [
            param("rr", "Red←Red", default=1.0, min_v=-2, max_v=2),
            param("rg", "Red←Green", default=0.0, min_v=-2, max_v=2),
            param("rb", "Red←Blue", default=0.0, min_v=-2, max_v=2),
            param("gr", "Green←Red", default=0.0, min_v=-2, max_v=2),
            param("gg", "Green←Green", default=1.0, min_v=-2, max_v=2),
            param("gb", "Green←Blue", default=0.0, min_v=-2, max_v=2),
            param("br", "Blue←Red", default=0.0, min_v=-2, max_v=2),
            param("bg", "Blue←Green", default=0.0, min_v=-2, max_v=2),
            param("bb", "Blue←Blue", default=1.0, min_v=-2, max_v=2),
        ],
        """#version 330 core
in vec2 v_texCoord; out vec4 fragColor;
uniform sampler2D u_currentTexture;
uniform float rr; uniform float rg; uniform float rb;
uniform float gr; uniform float gg; uniform float gb;
uniform float br; uniform float bg; uniform float bb;
void main() {
    vec4 c = texture(u_currentTexture, v_texCoord);
    mat3 m = mat3(rr, gr, br, rg, gg, bg, rb, gb, bb);
    fragColor = vec4(clamp(m * c.rgb, 0.0, 1.0), c.a);
}
""",
    )

    write_effect(
        "color_pass", "Color Pass", "color", 890,
        [
            param("hue", "Hue", default=0.33),
            param("range", "Range", default=0.12, min_v=0.01, max_v=0.5),
            param("softness", "Softness", default=0.08, min_v=0.001, max_v=0.4),
            param("desaturateRest", "Gray Rest", default=1.0),
        ],
        """#version 330 core
in vec2 v_texCoord; out vec4 fragColor;
uniform sampler2D u_currentTexture;
uniform float hue; uniform float range; uniform float softness; uniform float desaturateRest;

vec3 rgb2hsv(vec3 c) {
    vec4 K = vec4(0.0, -1.0 / 3.0, 2.0 / 3.0, -1.0);
    vec4 p = mix(vec4(c.bg, K.wz), vec4(c.gb, K.xy), step(c.b, c.g));
    vec4 q = mix(vec4(p.xyw, c.r), vec4(c.r, p.yzx), step(p.x, c.r));
    float d = q.x - min(q.w, q.y);
    float e = 1.0e-10;
    return vec3(abs(q.z + (q.w - q.y) / (6.0 * d + e)), d / (q.x + e), q.x);
}

void main() {
    vec4 c = texture(u_currentTexture, v_texCoord);
    vec3 hsv = rgb2hsv(c.rgb);
    float dh = abs(hsv.x - hue);
    dh = min(dh, 1.0 - dh);
    float m = 1.0 - smoothstep(range, range + softness, dh);
    float lum = dot(c.rgb, vec3(0.2126, 0.7152, 0.0722));
    vec3 gray = vec3(lum);
    vec3 rest = mix(c.rgb, gray, clamp(desaturateRest, 0.0, 1.0));
    fragColor = vec4(mix(rest, c.rgb, m), c.a);
}
""",
    )

    write_effect(
        "color_replace", "Color Replace", "color", 900,
        [
            param("sourceR", "Source R", default=0.0),
            param("sourceG", "Source G", default=1.0),
            param("sourceB", "Source B", default=0.0),
            param("targetR", "Target R", default=1.0),
            param("targetG", "Target G", default=0.0),
            param("targetB", "Target B", default=1.0),
            param("tolerance", "Tolerance", default=0.25, min_v=0.01, max_v=1),
            param("softness", "Softness", default=0.15, min_v=0.001, max_v=0.5),
        ],
        """#version 330 core
in vec2 v_texCoord; out vec4 fragColor;
uniform sampler2D u_currentTexture;
uniform float sourceR; uniform float sourceG; uniform float sourceB;
uniform float targetR; uniform float targetG; uniform float targetB;
uniform float tolerance; uniform float softness;
void main() {
    vec4 c = texture(u_currentTexture, v_texCoord);
    vec3 sourceColor = vec3(sourceR, sourceG, sourceB);
    vec3 targetColor = vec3(targetR, targetG, targetB);
    float d = distance(c.rgb, sourceColor);
    float m = 1.0 - smoothstep(tolerance, tolerance + softness, d);
    fragColor = vec4(mix(c.rgb, targetColor, m), c.a);
}
""",
    )

    write_effect(
        "levels", "Levels", "color", 910,
        [
            param("inBlack", "Input Black", default=0.0),
            param("inWhite", "Input White", default=1.0),
            param("gamma", "Gamma", default=1.0, min_v=0.2, max_v=3),
            param("outBlack", "Output Black", default=0.0),
            param("outWhite", "Output White", default=1.0),
        ],
        """#version 330 core
in vec2 v_texCoord; out vec4 fragColor;
uniform sampler2D u_currentTexture;
uniform float inBlack; uniform float inWhite; uniform float gamma;
uniform float outBlack; uniform float outWhite;
void main() {
    vec4 c = texture(u_currentTexture, v_texCoord);
    float ib = inBlack;
    float iw = max(inWhite, ib + 1e-4);
    vec3 x = clamp((c.rgb - ib) / (iw - ib), 0.0, 1.0);
    x = pow(x, vec3(1.0 / max(gamma, 1e-4)));
    fragColor = vec4(mix(vec3(outBlack), vec3(outWhite), x), c.a);
}
""",
    )

    write_effect(
        "asc_cdl", "ASC CDL", "color", 920,
        [
            param("slopeR", "Slope R", default=1.0, min_v=0, max_v=4),
            param("slopeG", "Slope G", default=1.0, min_v=0, max_v=4),
            param("slopeB", "Slope B", default=1.0, min_v=0, max_v=4),
            param("offsetR", "Offset R", default=0.0, min_v=-1, max_v=1),
            param("offsetG", "Offset G", default=0.0, min_v=-1, max_v=1),
            param("offsetB", "Offset B", default=0.0, min_v=-1, max_v=1),
            param("powerR", "Power R", default=1.0, min_v=0.1, max_v=4),
            param("powerG", "Power G", default=1.0, min_v=0.1, max_v=4),
            param("powerB", "Power B", default=1.0, min_v=0.1, max_v=4),
            param("saturation", "Saturation", default=1.0, min_v=0, max_v=4),
        ],
        """#version 330 core
in vec2 v_texCoord; out vec4 fragColor;
uniform sampler2D u_currentTexture;
uniform float slopeR; uniform float slopeG; uniform float slopeB;
uniform float offsetR; uniform float offsetG; uniform float offsetB;
uniform float powerR; uniform float powerG; uniform float powerB;
uniform float saturation;
void main() {
    vec4 c = texture(u_currentTexture, v_texCoord);
    vec3 x = c.rgb * vec3(slopeR, slopeG, slopeB) + vec3(offsetR, offsetG, offsetB);
    x = pow(max(x, vec3(0.0)), vec3(powerR, powerG, powerB));
    float luma = dot(x, vec3(0.2126, 0.7152, 0.0722));
    x = mix(vec3(luma), x, saturation);
    fragColor = vec4(clamp(x, 0.0, 1.0), c.a);
}
""",
    )

    write_effect(
        "tint", "Tint", "color", 930,
        [
            param("tintR", "Tint R", default=0.4),
            param("tintG", "Tint G", default=0.53),
            param("tintB", "Tint B", default=1.0),
            param("strength", "Strength", default=0.35),
            param("preserveLuma", "Preserve Luma", default=1.0, typ="bool"),
        ],
        """#version 330 core
in vec2 v_texCoord; out vec4 fragColor;
uniform sampler2D u_currentTexture;
uniform float tintR; uniform float tintG; uniform float tintB;
uniform float strength; uniform float preserveLuma;
void main() {
    vec4 c = texture(u_currentTexture, v_texCoord);
    vec3 color = vec3(tintR, tintG, tintB);
    vec3 tinted = mix(c.rgb, c.rgb * color, clamp(strength, 0.0, 1.0));
    if (preserveLuma > 0.5) {
        float l0 = dot(c.rgb, vec3(0.2126, 0.7152, 0.0722));
        float l1 = dot(tinted, vec3(0.2126, 0.7152, 0.0722));
        tinted *= (l1 > 1e-5) ? (l0 / l1) : 1.0;
    }
    fragColor = vec4(clamp(tinted, 0.0, 1.0), c.a);
}
""",
    )

    write_effect(
        "extract", "Extract", "color", 940,
        [
            param("mode", "Mode", default=0.0, max_v=2),  # 0 luma, 1 red, 2 max RGB
            param("blackPoint", "Black", default=0.0),
            param("whitePoint", "White", default=1.0),
            param("asAlpha", "As Alpha", default=0.0, typ="bool"),
        ],
        """#version 330 core
in vec2 v_texCoord; out vec4 fragColor;
uniform sampler2D u_currentTexture;
uniform float mode; uniform float blackPoint; uniform float whitePoint; uniform float asAlpha;
void main() {
    vec4 c = texture(u_currentTexture, v_texCoord);
    int m = int(clamp(floor(mode + 0.5), 0.0, 2.0));
    float v;
    if (m == 1) v = c.r;
    else if (m == 2) v = max(c.r, max(c.g, c.b));
    else v = dot(c.rgb, vec3(0.2126, 0.7152, 0.0722));
    float bp = blackPoint;
    float wp = max(whitePoint, bp + 1e-4);
    v = clamp((v - bp) / (wp - bp), 0.0, 1.0);
    if (asAlpha > 0.5) fragColor = vec4(c.rgb, v * c.a);
    else fragColor = vec4(vec3(v), c.a);
}
""",
    )

    write_effect(
        "chromatic_aberration", "Chromatic Aberration", "glitch", 950,
        [
            param("amount", "Amount", default=0.4, max_v=1),
            param("falloff", "Edge Falloff", default=0.7),
            param("centerX", "Center X", default=0.5),
            param("centerY", "Center Y", default=0.5),
        ],
        """#version 330 core
in vec2 v_texCoord; out vec4 fragColor;
uniform sampler2D u_currentTexture; uniform vec2 u_resolution;
uniform float amount; uniform float falloff; uniform float centerX; uniform float centerY;
void main() {
    float aspect = u_resolution.x / max(u_resolution.y, 1.0);
    vec2 c = vec2(centerX, centerY);
    vec2 d = (v_texCoord - c) * vec2(aspect, 1.0);
    float r = length(d);
    float edge = pow(clamp(r, 0.0, 1.5) / 1.5, 1.0 + falloff);
    float shift = amount * 0.035 * edge;
    vec2 dir = (r > 1e-5) ? normalize(vec2(d.x / aspect, d.y)) : vec2(0.0);
    float R = texture(u_currentTexture, clamp(v_texCoord + dir * shift, 0.0, 1.0)).r;
    float G = texture(u_currentTexture, v_texCoord).g;
    float B = texture(u_currentTexture, clamp(v_texCoord - dir * shift, 0.0, 1.0)).b;
    float a = texture(u_currentTexture, v_texCoord).a;
    fragColor = vec4(R, G, B, a);
}
""",
    )

    write_effect(
        "camera_shake", "Camera Shake", "impact", 960,
        [
            param("amount", "Amount", default=0.35, max_v=1),
            param("speed", "Speed", default=2.0, max_v=10),
            param("rotation", "Rotation", default=0.25),
            param("roughness", "Roughness", default=0.6),
        ],
        f"""#version 330 core
in vec2 v_texCoord; out vec4 fragColor;
uniform sampler2D u_currentTexture; uniform vec2 u_resolution; uniform float u_time;
uniform float amount; uniform float speed; uniform float rotation; uniform float roughness;
{NOISE_HELPERS}
void main() {{
    float t = u_time * speed;
    float amp = amount * 0.04;
    vec2 n = vec2(
        valueNoise(vec2(t, 0.3)) - 0.5,
        valueNoise(vec2(t + 19.0, 1.7)) - 0.5);
    if (roughness > 0.01) {{
        n += (roughness) * vec2(
            valueNoise(vec2(t * 3.1, 4.2)) - 0.5,
            valueNoise(vec2(t * 3.1 + 8.0, 5.5)) - 0.5);
    }}
    float ang = (valueNoise(vec2(t * 0.7, 9.0)) - 0.5) * rotation * amount * 0.08;
    vec2 uv = v_texCoord - 0.5;
    float ca = cos(ang); float sa = sin(ang);
    uv = vec2(uv.x * ca - uv.y * sa, uv.x * sa + uv.y * ca);
    uv += 0.5 + n * amp * 2.0;
    fragColor = texture(u_currentTexture, clamp(uv, 0.0, 1.0));
}}
""",
    )

    write_effect(
        "film_grain", "Film Grain", "retro", 970,
        [
            param("amount", "Amount", default=0.35, max_v=1),
            param("size", "Size", default=1.0, min_v=0.25, max_v=4),
            param("colored", "Colored", default=0.2),
            param("softness", "Softness", default=0.3),
        ],
        f"""#version 330 core
in vec2 v_texCoord; out vec4 fragColor;
uniform sampler2D u_currentTexture; uniform vec2 u_resolution; uniform float u_time;
uniform float amount; uniform float size; uniform float colored; uniform float softness;
{NOISE_HELPERS}
void main() {{
    vec4 c = texture(u_currentTexture, v_texCoord);
    vec2 p = v_texCoord * u_resolution / max(size, 0.1);
    // Quantize time lightly so grain flickers per ~frame without wall-clock drift
    float ft = floor(u_time * 24.0);
    float n1 = valueNoise(p + ft * 1.7);
    float n2 = valueNoise(p + vec2(37.0, 91.0) + ft * 2.3);
    float n3 = valueNoise(p + vec2(11.0, 53.0) + ft * 3.1);
    vec3 grain = mix(vec3(n1), vec3(n1, n2, n3), colored);
    grain = (grain - 0.5) * 2.0;
    float lum = dot(c.rgb, vec3(0.2126, 0.7152, 0.0722));
    float resp = mix(1.0, 1.0 - abs(lum - 0.5) * 2.0, softness);
    fragColor = vec4(clamp(c.rgb + grain * amount * 0.35 * resp, 0.0, 1.0), c.a);
}}
""",
    )

    write_effect(
        "rain_overlay", "Rain", "dreamy", 980,
        [
            param("amount", "Amount", default=0.55, max_v=1),
            param("speed", "Speed", default=1.5, max_v=5),
            param("streakLength", "Streak Length", default=0.45, max_v=1),
            param("angle", "Angle", default=12.0, min_v=-30, max_v=30),
            param("opacity", "Opacity", default=0.55),
        ],
        f"""#version 330 core
in vec2 v_texCoord; out vec4 fragColor;
uniform sampler2D u_currentTexture; uniform vec2 u_resolution; uniform float u_time;
uniform float amount; uniform float speed; uniform float streakLength;
uniform float angle; uniform float opacity;
{NOISE_HELPERS}
void main() {{
    vec4 src = texture(u_currentTexture, v_texCoord);
    float aspect = u_resolution.x / max(u_resolution.y, 1.0);
    float rad = radians(angle);
    // Shear UV by rain angle so streaks follow the fall direction.
    mat2 rot = mat2(cos(rad), -sin(rad), sin(rad), cos(rad));
    float density = mix(20.0, 90.0, amount);
    vec2 uv = rot * vec2(v_texCoord.x * aspect, v_texCoord.y);
    vec2 st = uv * density;
    st.y -= u_time * speed * 8.0;
    vec2 id = floor(st);
    vec2 f = fract(st);
    float n = hash21(id);
    float streak = 0.0;
    if (n < amount * 0.55) {{
        float x = abs(f.x - 0.5);
        float y = fract(f.y + n);
        float len = mix(0.15, 0.9, streakLength);
        streak = (1.0 - smoothstep(0.0, 0.04, x)) * (1.0 - smoothstep(len, len + 0.1, y));
    }}
    vec3 rain = vec3(0.75, 0.8, 0.9) * streak * opacity;
    fragColor = vec4(src.rgb + rain, src.a);
}}
""",
    )

    write_effect(
        "snow_overlay", "Snow", "dreamy", 990,
        [
            param("amount", "Amount", default=0.5, max_v=1),
            param("speed", "Speed", default=0.8, max_v=4),
            param("size", "Size", default=0.45, max_v=1),
            param("opacity", "Opacity", default=0.7),
        ],
        f"""#version 330 core
in vec2 v_texCoord; out vec4 fragColor;
uniform sampler2D u_currentTexture; uniform vec2 u_resolution; uniform float u_time;
uniform float amount; uniform float speed; uniform float size; uniform float opacity;
{NOISE_HELPERS}
void main() {{
    vec4 src = texture(u_currentTexture, v_texCoord);
    float aspect = u_resolution.x / max(u_resolution.y, 1.0);
    float flakes = 0.0;
    for (int layer = 0; layer < 3; ++layer) {{
        float dens = mix(12.0, 40.0, amount) * (1.0 + float(layer) * 0.55);
        vec2 uv = vec2(v_texCoord.x * aspect, v_texCoord.y) * dens;
        uv.y += u_time * speed * (0.6 + float(layer) * 0.5);
        uv.x += sin(u_time * 0.4 + float(layer)) * 0.4;
        vec2 id = floor(uv);
        vec2 f = fract(uv) - 0.5;
        float n = hash21(id + float(layer) * 17.0);
        if (n < amount * 0.45) {{
            float r = mix(0.04, 0.18, size) * (0.6 + n);
            flakes += smoothstep(r, r * 0.3, length(f));
        }}
    }}
    fragColor = vec4(src.rgb + vec3(flakes * opacity), src.a);
}}
""",
    )

    write_effect(
        "holographic", "Holographic", "glitch", 1000,
        [
            param("amount", "Amount", default=0.55, max_v=1),
            param("scanlines", "Scanlines", default=0.45),
            param("glitch", "Glitch", default=0.25),
            param("tintR", "Tint R", default=0.27),
            param("tintG", "Tint G", default=1.0),
            param("tintB", "Tint B", default=0.8),
        ],
        f"""#version 330 core
in vec2 v_texCoord; out vec4 fragColor;
uniform sampler2D u_currentTexture; uniform vec2 u_resolution; uniform float u_time;
uniform float amount; uniform float scanlines; uniform float glitch;
uniform float tintR; uniform float tintG; uniform float tintB;
{NOISE_HELPERS}
void main() {{
    vec2 uv = v_texCoord;
    vec3 tint = vec3(tintR, tintG, tintB);
    float g = glitch * step(0.92, valueNoise(vec2(floor(u_time * 12.0), floor(uv.y * 40.0))));
    uv.x += (valueNoise(vec2(floor(u_time * 8.0), floor(uv.y * 20.0))) - 0.5) * g * 0.08;
    vec4 c = texture(u_currentTexture, clamp(uv, 0.0, 1.0));
    float lines = sin(uv.y * u_resolution.y * 3.14159) * 0.5 + 0.5;
    lines = mix(1.0, lines, scanlines);
    float flick = 0.92 + 0.08 * valueNoise(vec2(u_time * 6.0, 0.5));
    vec3 holo = c.rgb * tint * lines * flick;
    float band = smoothstep(0.0, 0.02, abs(fract(uv.y * 3.0 + u_time * 0.15) - 0.5));
    holo += tint * (1.0 - band) * 0.08 * amount;
    fragColor = vec4(mix(c.rgb, holo, clamp(amount, 0.0, 1.0)), c.a);
}}
""",
    )


def gen_transitions() -> None:
    write_transition(
        "page_turn", "Page Turn", "geometric", 400,
        [
            param("curl", "Curl", default=0.55),
            param("shadow", "Shadow", default=0.45),
            param("angle", "Angle", default=0.15, min_v=-0.5, max_v=0.5),
        ],
        """
uniform float curl; uniform float shadow; uniform float angle;

void main() {
    vec2 uv = v_texCoord;
    float aspect = aspectRatio();
    // Progressive peel from the right edge with a cylindrical curl.
    float p = clamp(u_progress, 0.0, 1.0);
    float edge = 1.0 - p * (1.0 + curl * 0.35);
    float x = uv.x + (uv.y - 0.5) * angle * 0.25;
    float d = x - edge;

    if (d < 0.0) {
        // Still on the outgoing page
        float sh = smoothstep(0.0, 0.25, -d) * shadow * p;
        vec4 from = texture(u_fromTexture, uv);
        from.rgb *= 1.0 - sh * 0.55;
        fragColor = over(from, texture(u_toTexture, uv));
        return;
    }

    float R = mix(0.18, 0.55, curl);
    if (d < 3.14159265 * R) {
        float theta = d / R;
        float mapped = edge - sin(theta) * R;
        float z = (1.0 - cos(theta)) * R;
        vec2 suv = vec2(mapped, uv.y);
        // Back-face of the turning page (slightly darkened mirror of from)
        if (theta > 1.5707963) {
            float backX = edge - sin(3.14159265 - theta) * R;
            suv.x = backX;
            vec4 page = texture(u_fromTexture, clamp(vec2(2.0 * edge - suv.x, suv.y), 0.0, 1.0));
            page.rgb *= 0.55;
            float sh = shadow * smoothstep(0.0, 0.4, z);
            vec4 under = texture(u_toTexture, uv);
            under.rgb *= 1.0 - sh * 0.7;
            fragColor = over(page, under);
            return;
        }
        vec4 page = texture(u_fromTexture, clamp(suv, 0.0, 1.0));
        float sh = shadow * smoothstep(0.0, 0.35, z);
        vec4 under = texture(u_toTexture, uv);
        under.rgb *= 1.0 - sh * 0.65;
        fragColor = over(page, under);
        return;
    }

    fragColor = texture(u_toTexture, uv);
}
""",
    )

    write_transition(
        "cube_flip", "Cube Flip", "geometric", 410,
        [
            param("perspective", "Perspective", default=0.55),
            param("direction", "Direction", default=0.0, max_v=3),  # 0 L,1 R,2 U,3 D
        ],
        """
uniform float perspective; uniform float direction;

void main() {
    vec2 uv = v_texCoord;
    float p = clamp(u_progress, 0.0, 1.0);
    int dir = int(clamp(floor(direction + 0.5), 0.0, 3.0));
    bool horizontal = (dir == 0 || dir == 1);
    bool reverse = (dir == 1 || dir == 3);

    float ang = p * 1.5707963;
    if (reverse) ang = -ang;
    float ca = cos(ang);
    float sa = sin(ang);
    float persp = mix(0.35, 1.2, perspective);

    vec2 q = uv * 2.0 - 1.0;
    float axis = horizontal ? q.x : q.y;
    float other = horizontal ? q.y : q.x;

    // Project rotating face
    float x1 = axis * ca;
    float z1 = axis * sa;
    float w = 1.0 + z1 * persp * 0.35;
    float xp = x1 / w;
    float yp = other / (1.0 + z1 * persp * 0.15);
    vec2 suv = horizontal ? vec2(xp, yp) : vec2(yp, xp);
    suv = suv * 0.5 + 0.5;

    bool useTo = (p > 0.5);
    // After halfway, sample the incoming face continuing the rotation
    if (useTo) {
        float ang2 = (p - 1.0) * 1.5707963;
        if (reverse) ang2 = -ang2;
        ca = cos(ang2); sa = sin(ang2);
        x1 = axis * ca;
        z1 = axis * sa;
        w = 1.0 + z1 * persp * 0.35;
        xp = x1 / w;
        yp = other / (1.0 + z1 * persp * 0.15);
        suv = horizontal ? vec2(xp, yp) : vec2(yp, xp);
        suv = suv * 0.5 + 0.5;
    }

    if (suv.x < 0.0 || suv.x > 1.0 || suv.y < 0.0 || suv.y > 1.0) {
        fragColor = vec4(0.0);
        return;
    }
    float shade = mix(1.0, 0.65, abs(sa) * 0.8);
    vec4 col = useTo ? texture(u_toTexture, suv) : texture(u_fromTexture, suv);
    col.rgb *= shade;
    fragColor = col;
}
""",
    )

    write_transition(
        "energy_burst", "Energy Burst", "stylized", 420,
        [
            param("glow", "Glow", default=0.55),
            param("rays", "Rays", default=0.45),
            param("centerX", "Center X", default=0.5),
            param("centerY", "Center Y", default=0.5),
        ],
        """
uniform float glow; uniform float rays; uniform float centerX; uniform float centerY;

void main() {
    vec2 uv = v_texCoord;
    float aspect = aspectRatio();
    vec2 c = vec2(centerX, centerY);
    vec2 d = (uv - c) * vec2(aspect, 1.0);
    float r = length(d);
    float p = clamp(u_progress, 0.0, 1.0);
    float wave = p * 1.35;
    float edge = smoothstep(wave - 0.12, wave + 0.02, r);
    float ring = 1.0 - smoothstep(0.0, 0.08, abs(r - wave));

    float ang = atan(d.y, d.x);
    float ray = pow(abs(sin(ang * 12.0 + p * 6.0)), 4.0) * rays * ring;

    vec4 fromCol = texture(u_fromTexture, uv);
    vec4 toCol = texture(u_toTexture, uv);
    vec4 mixed = mix(toCol, fromCol, edge);
    vec3 energy = vec3(0.6, 0.85, 1.0) * (ring * glow + ray);
    mixed.rgb += energy;
    fragColor = mixed;
}
""",
    )

    write_transition(
        "prism_wipe", "Prism Wipe", "stylized", 430,
        [
            param("dispersion", "Dispersion", default=0.55),
            param("softness", "Softness", default=0.2, min_v=0.01, max_v=0.5),
            param("angle", "Angle", default=25.0, max_v=180),
        ],
        """
uniform float dispersion; uniform float softness; uniform float angle;

void main() {
    vec2 uv = v_texCoord;
    float rad = radians(angle);
    vec2 n = vec2(cos(rad), sin(rad));
    float c = dot(uv - 0.5, n) + 0.5;
    float edge = mix(-softness, 1.0 + softness, u_progress);
    float m = smoothstep(edge - softness, edge + softness, c);

    float shift = dispersion * 0.04 * (1.0 - abs(m - 0.5) * 2.0);
    vec2 dir = n * shift;

    vec4 fromC = texture(u_fromTexture, uv);
    vec4 toR = texture(u_toTexture, clamp(uv + dir, 0.0, 1.0));
    vec4 toG = texture(u_toTexture, uv);
    vec4 toB = texture(u_toTexture, clamp(uv - dir, 0.0, 1.0));
    vec4 toC = vec4(toR.r, toG.g, toB.b, toG.a);

    fragColor = mix(fromC, toC, m);
}
""",
    )

    write_transition(
        "twirl_transition", "Twirl", "distortion", 440,
        [
            param("angle", "Angle", default=4.0, min_v=0, max_v=10),
            param("radius", "Radius", default=0.75),
        ],
        """
uniform float angle; uniform float radius;

void main() {
    vec2 uv = v_texCoord;
    float aspect = aspectRatio();
    vec2 d = (uv - 0.5) * vec2(aspect, 1.0);
    float r = length(d);
    float p = clamp(u_progress, 0.0, 1.0);
    float amt = sin(p * 3.14159265);
    float fall = 1.0 - smoothstep(0.0, max(radius, 1e-4), r);
    float a = atan(d.y, d.x) + angle * amt * fall * fall;
    vec2 nd = (r > 1e-6) ? vec2(cos(a), sin(a)) * r : d;
    vec2 suv = vec2(nd.x / aspect, nd.y) + 0.5;
    vec4 fromC = texture(u_fromTexture, clamp(suv, 0.0, 1.0));
    vec4 toC = texture(u_toTexture, clamp(suv, 0.0, 1.0));
    fragColor = mix(fromC, toC, p);
}
""",
    )

    write_transition(
        "spherize_transition", "Spherize", "distortion", 450,
        [
            param("amount", "Amount", default=0.85),
            param("radius", "Radius", default=0.7),
        ],
        """
uniform float amount; uniform float radius;

void main() {
    vec2 uv = v_texCoord;
    float aspect = aspectRatio();
    vec2 d = (uv - 0.5) * vec2(aspect, 1.0);
    float r = length(d);
    float p = clamp(u_progress, 0.0, 1.0);
    float bulgeAmt = amount * sin(p * 3.14159265);
    float R = max(radius, 1e-4);
    vec2 suv = uv;
    if (r < R && abs(bulgeAmt) > 1e-5) {
        float t = r / R;
        float bulge = mix(t, sin(t * 1.5707963), bulgeAmt);
        vec2 nd = d * (bulge / max(t, 1e-5));
        suv = vec2(nd.x / aspect, nd.y) + 0.5;
    }
    vec4 fromC = texture(u_fromTexture, clamp(suv, 0.0, 1.0));
    vec4 toC = texture(u_toTexture, clamp(suv, 0.0, 1.0));
    fragColor = mix(fromC, toC, smoothstep(0.2, 0.8, p));
}
""",
    )


def main() -> None:
    EFFECTS.mkdir(parents=True, exist_ok=True)
    TRANSITIONS.mkdir(parents=True, exist_ok=True)
    gen_effects()
    gen_transitions()
    n_fx = len(list(EFFECTS.iterdir()))
    n_tr = len(list(TRANSITIONS.iterdir()))
    print(f"content/effects: {n_fx} packages")
    print(f"content/transitions: {n_tr} packages")


if __name__ == "__main__":
    main()
