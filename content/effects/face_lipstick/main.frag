#version 330 core
in vec2 v_texCoord; out vec4 fragColor;
uniform sampler2D u_currentTexture; uniform vec2 u_resolution;
uniform float u_faceValid; uniform float u_faceHasContours;
uniform vec2 u_faceLipOuter[20];
uniform vec2 u_faceLipInner[20];
uniform vec3 shade; uniform float opacity; uniform float gloss; uniform float feather;
uniform float coverInner;

// Anchors arrive in uv but the contour loops are already width-normalized: uv with y scaled by the
// aspect, so a distance means the same thing along both axes. Move the pixel into that space and
// every polygon measurement below is isotropic.
vec2 toLocal(vec2 uv, float aspect) { return vec2(uv.x, uv.y * aspect); }

// Signed distance to a closed polygon, negative inside: per-segment distance for the magnitude and
// a winding-number crossing count for the sign (Inigo Quilez). Written as a macro because GLSL 330
// cannot take a runtime-sized array parameter, and each loop has its own fixed length.
//
// Evaluated at full resolution rather than into a half-res buffer: the FBO pool hands out RGBA8,
// so a stored distance would quantize to roughly a pixel and a half at 4K — fine for a soft lip
// edge, visible as stair-steps on anything thin. Forty segments a pixel is affordable.
#define SD_POLY(NAME, ARR, N)                                                                      \
    float NAME(vec2 p) {                                                                           \
        vec2 d0 = p - ARR[0];                                                                      \
        float d = dot(d0, d0);                                                                     \
        float s = 1.0;                                                                             \
        for (int i = 0, j = N - 1; i < N; j = i, i++) {                                            \
            vec2 e = ARR[j] - ARR[i];                                                              \
            vec2 w = p - ARR[i];                                                                   \
            vec2 b = w - e * clamp(dot(w, e) / dot(e, e), 0.0, 1.0);                               \
            d = min(d, dot(b, b));                                                                 \
            bvec3 c = bvec3(p.y >= ARR[i].y, p.y < ARR[j].y, e.x * w.y > e.y * w.x);               \
            if (all(c) || all(not(c))) s = -s;                                                     \
        }                                                                                          \
        return s * sqrt(d);                                                                        \
    }

SD_POLY(sdLipOuter, u_faceLipOuter, 20)
SD_POLY(sdLipInner, u_faceLipInner, 20)

float luma(vec3 c) { return dot(c, vec3(0.2126, 0.7152, 0.0722)); }

void main() {
    vec4 src = texture(u_currentTexture, v_texCoord);
    // A clip scanned before contours existed still drives the warp effects, so passing through is
    // the correct answer here rather than an error.
    if (u_faceValid < 0.5 || u_faceHasContours < 0.5) { fragColor = src; return; }

    float aspect = u_resolution.y / u_resolution.x;
    vec2 p = toLocal(v_texCoord, aspect);

    // Feather scaled by the mouth's own width, so the softness looks the same on a close-up and on
    // a face across the room. Index 0 and 10 are the two mouth corners.
    float lipWidth = length(u_faceLipOuter[10] - u_faceLipOuter[0]);
    float fw = max(feather * 0.15 * lipWidth, 1e-5);

    float dOuter = sdLipOuter(p);
    float cover = 1.0 - smoothstep(-fw, fw, dOuter);
    // The inner loop is the mouth opening. Cutting it out keeps teeth and tongue their own colour;
    // filling it is what a closed mouth wants, where the "opening" is just the lip seam.
    if (coverInner < 0.5) {
        float dInner = sdLipInner(p);
        cover *= smoothstep(-fw, fw, dInner);
    }
    if (cover <= 0.0) { fragColor = src; return; }

    // Rescale the shade so its luminance matches the pixel's. That replaces hue and saturation
    // while leaving every bit of the lip's own shading and specular structure intact — the thing
    // that separates lipstick from a painted-on shape.
    float L = luma(src.rgb);
    vec3 tinted = clamp(shade * (L / max(luma(shade), 1e-3)), 0.0, 1.0);

    // Gloss rides on the highlights the lips already have, so it lands where the light actually is.
    float hl = max(L - 0.62, 0.0);
    tinted += vec3(gloss * 2.5 * hl * hl * hl);

    fragColor = vec4(mix(src.rgb, clamp(tinted, 0.0, 1.0), cover * opacity), src.a);
}
