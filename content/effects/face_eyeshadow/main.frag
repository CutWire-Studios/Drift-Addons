#version 330 core
in vec2 v_texCoord; out vec4 fragColor;
uniform sampler2D u_currentTexture; uniform vec2 u_resolution;
uniform float u_faceValid; uniform float u_faceHasContours;
uniform vec2 u_faceEyeLeft[16];
uniform vec2 u_faceEyeRight[16];
uniform vec2 u_faceBrowLeft[10];
uniform vec2 u_faceBrowRight[10];
uniform vec3 shade; uniform float intensity; uniform float spread; uniform float feather;

vec2 toLocal(vec2 uv, float aspect) { return vec2(uv.x, uv.y * aspect); }

float sdSegment(vec2 p, vec2 a, vec2 b) {
    vec2 e = b - a, w = p - a;
    return length(w - e * clamp(dot(w, e) / max(dot(e, e), 1e-12), 0.0, 1.0));
}

float sdRing(vec2 p, vec2 ring[16]) {
    vec2 d0 = p - ring[0];
    float d = dot(d0, d0);
    float s = 1.0;
    for (int i = 0, j = 15; i < 16; j = i, i++) {
        vec2 e = ring[j] - ring[i];
        vec2 w = p - ring[i];
        vec2 b = w - e * clamp(dot(w, e) / dot(e, e), 0.0, 1.0);
        d = min(d, dot(b, b));
        bvec3 c = bvec3(p.y >= ring[i].y, p.y < ring[j].y, e.x * w.y > e.y * w.x);
        if (all(c) || all(not(c))) s = -s;
    }
    return s * sqrt(d);
}

// Unsigned distance to the brow polygon's lower edge is overkill; the brow's centroid height is
// enough to keep shadow from climbing over it.
float browHeight(vec2 brow[10]) {
    float sum = 0.0;
    for (int i = 0; i < 10; i++) sum += brow[i].y;
    return sum / 10.0;
}

float shadowFor(vec2 p, vec2 ring[16], vec2 brow[10]) {
    float eyeWidth = length(ring[8] - ring[0]);
    float reach = max(eyeWidth * spread * 0.55, 1e-5);

    // Distance to the lash line, then a falloff upward from it. Measured to the arc rather than to
    // the whole ring so shadow does not also grow downward off the lower lid.
    float best = 1e9;
    for (int i = 0; i < 8; i++)
        best = min(best, sdSegment(p, ring[i], ring[i + 1]));

    float band = 1.0 - smoothstep(reach * (1.0 - feather * 0.8), reach, best);

    // Only above the lid. Image y grows downward, so "above" is the smaller-y side of the lash
    // line; the eye centroid gives a stable reference for which side that is.
    float cy = 0.0;
    for (int i = 0; i < 16; i++) cy += ring[i].y;
    cy /= 16.0;
    band *= smoothstep(0.0, reach * 0.35, cy - p.y + reach * 0.12);

    // Never on the eyeball itself.
    band *= smoothstep(-eyeWidth * 0.02, eyeWidth * 0.05, sdRing(p, ring));

    // Faded out before the brow, or the shadow reads as a bruise running into the hair.
    float bh = browHeight(brow);
    band *= smoothstep(bh - reach * 0.1, bh + reach * 0.45, p.y);

    return clamp(band, 0.0, 1.0);
}

void main() {
    vec4 src = texture(u_currentTexture, v_texCoord);
    if (u_faceValid < 0.5 || u_faceHasContours < 0.5) { fragColor = src; return; }

    float aspect = u_resolution.y / u_resolution.x;
    vec2 p = toLocal(v_texCoord, aspect);

    float cover = max(shadowFor(p, u_faceEyeLeft, u_faceBrowLeft),
                      shadowFor(p, u_faceEyeRight, u_faceBrowRight));
    if (cover <= 0.0) { fragColor = src; return; }

    // Multiplied into the skin rather than mixed toward the shade: powder darkens what is under it,
    // and mixing washes the lid to a flat patch of colour.
    vec3 tinted = src.rgb * mix(vec3(1.0), shade * 1.6, cover * intensity);
    fragColor = vec4(clamp(tinted, 0.0, 1.0), src.a);
}
