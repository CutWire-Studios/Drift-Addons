#version 330 core
in vec2 v_texCoord; out vec4 fragColor;
uniform sampler2D u_currentTexture; uniform vec2 u_resolution;
uniform float u_faceValid; uniform float u_faceHasContours;
uniform vec2 u_faceEyeLeft[16];
uniform vec2 u_faceEyeRight[16];
uniform float u_faceLeftEyeX; uniform float u_faceLeftEyeY;
uniform float u_faceRightEyeX; uniform float u_faceRightEyeY;
uniform float u_faceEyeRadius;
uniform vec3 shade; uniform float strength; uniform float brighten; uniform float pupilKeep;

vec2 toLocal(vec2 uv, float aspect) { return vec2(uv.x, uv.y * aspect); }

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

// The iris is a disc at the tracked centre; the eyelid ring is what decides how much of it shows.
// Without the lid clip the colour smears across the skin on a blink, which is the single most
// obvious failure this effect has.
float irisCoverage(vec2 p, vec2 centre, vec2 ring[16]) {
    float r = max(u_faceEyeRadius, 1e-5);
    float dist = length(p - centre);
    float disc = 1.0 - smoothstep(r * 0.88, r * 1.06, dist);
    // The pupil stays black or the eye looks like a contact lens sitting on top of it.
    disc *= smoothstep(r * pupilKeep * 0.95, r * (pupilKeep + 0.12), dist);
    disc *= 1.0 - smoothstep(-r * 0.12, r * 0.04, sdRing(p, ring));
    return clamp(disc, 0.0, 1.0);
}

float luma(vec3 c) { return dot(c, vec3(0.2126, 0.7152, 0.0722)); }

void main() {
    vec4 src = texture(u_currentTexture, v_texCoord);
    if (u_faceValid < 0.5 || u_faceHasContours < 0.5) { fragColor = src; return; }

    float aspect = u_resolution.y / u_resolution.x;
    vec2 p = toLocal(v_texCoord, aspect);

    float cover = max(irisCoverage(p, toLocal(vec2(u_faceLeftEyeX, u_faceLeftEyeY), aspect),
                                   u_faceEyeLeft),
                      irisCoverage(p, toLocal(vec2(u_faceRightEyeX, u_faceRightEyeY), aspect),
                                   u_faceEyeRight));
    if (cover <= 0.0) { fragColor = src; return; }

    // Luminance-matched recolour, the same trick lipstick uses: the iris keeps all its own radial
    // fibre detail and its catchlight, and only hue and saturation move.
    float L = luma(src.rgb);
    vec3 tinted = clamp(shade * (L / max(luma(shade), 1e-3)), 0.0, 1.0);
    tinted = clamp(tinted + brighten * cover, 0.0, 1.0);

    fragColor = vec4(mix(src.rgb, tinted, cover * strength), src.a);
}
