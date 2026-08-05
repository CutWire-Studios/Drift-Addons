#version 330 core
in vec2 v_texCoord; out vec4 fragColor;
uniform sampler2D u_currentTexture; uniform vec2 u_resolution;
uniform float u_faceValid; uniform float u_faceHasContours;
uniform vec2 u_faceOval[36];
uniform float u_faceCheekLeftX; uniform float u_faceCheekLeftY;
uniform float u_faceCheekRightX; uniform float u_faceCheekRightY;
uniform float u_faceRx;
uniform vec3 shade; uniform float intensity; uniform float size; uniform float feather;

vec2 toLocal(vec2 uv, float aspect) { return vec2(uv.x, uv.y * aspect); }

// See effects/face_lipstick/main.frag for why this is a macro and why it runs at full resolution.
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

SD_POLY(sdOval, u_faceOval, 36)

void main() {
    vec4 src = texture(u_currentTexture, v_texCoord);
    if (u_faceValid < 0.5 || u_faceHasContours < 0.5) { fragColor = src; return; }

    float aspect = u_resolution.y / u_resolution.x;
    vec2 p = toLocal(v_texCoord, aspect);
    vec2 cl = toLocal(vec2(u_faceCheekLeftX, u_faceCheekLeftY), aspect);
    vec2 cr = toLocal(vec2(u_faceCheekRightX, u_faceCheekRightY), aspect);

    // Gaussian falloff rather than a hard disc: blush has no edge, and a smoothstep circle reads as
    // a sticker the moment the head turns.
    float r = max(u_faceRx * size, 1e-5);
    float gl = exp(-dot(p - cl, p - cl) / (r * r));
    float gr = exp(-dot(p - cr, p - cr) / (r * r));
    float amount = clamp(max(gl, gr), 0.0, 1.0);

    // Clipped to the face oval so a wide radius cannot bleed onto hair or background. Feather is
    // measured inward from the boundary.
    float fw = max(feather * 0.25 * u_faceRx, 1e-5);
    amount *= 1.0 - smoothstep(-fw, 0.0, sdOval(p));
    if (amount <= 0.0) { fragColor = src; return; }

    // Screen rather than mix: blush is light coming back through skin, not pigment sitting on top,
    // and mixing toward the shade flattens the cheek into a painted patch.
    vec3 tint = shade * amount * intensity;
    fragColor = vec4(clamp(src.rgb + tint * (1.0 - src.rgb), 0.0, 1.0), src.a);
}
