#version 330 core
in vec2 v_texCoord; out vec4 fragColor;
uniform sampler2D u_currentTexture; uniform vec2 u_resolution;
uniform float u_faceValid; uniform float u_faceHasContours;
uniform vec2 u_faceLipInner[20];
uniform float whiten; uniform float brighten; uniform float threshold;

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

SD_POLY(sdLipInner, u_faceLipInner, 20)

void main() {
    vec4 src = texture(u_currentTexture, v_texCoord);
    if (u_faceValid < 0.5 || u_faceHasContours < 0.5) { fragColor = src; return; }

    float aspect = u_resolution.y / u_resolution.x;
    vec2 p = toLocal(v_texCoord, aspect);

    // The inner lip loop is the mouth opening: the only place teeth can be. Geometry does the
    // coarse work so the colour test below can stay loose enough to catch dim teeth.
    float mouthWidth = length(u_faceLipInner[10] - u_faceLipInner[0]);
    float fw = max(0.04 * mouthWidth, 1e-5);
    float inMouth = 1.0 - smoothstep(-fw, 0.0, sdLipInner(p));
    if (inMouth <= 0.0) { fragColor = src; return; }

    // Teeth are the bright, weakly saturated, yellow-leaning pixels in there; gums and tongue are
    // strongly red and the gap behind them is dark.
    float mx = max(max(src.r, src.g), src.b);
    float mn = min(min(src.r, src.g), src.b);
    float sat = mx > 1e-4 ? (mx - mn) / mx : 0.0;
    float bright = smoothstep(threshold, threshold + 0.18, mx);
    float notRed = 1.0 - smoothstep(0.30, 0.55, sat);
    // Yellow shows up as blue sitting below the other two channels.
    float yellowness = clamp((min(src.r, src.g) - src.b) * 4.0, 0.0, 1.0);
    float mask = inMouth * bright * notRed * clamp(0.35 + yellowness, 0.0, 1.0);
    if (mask <= 0.0) { fragColor = src; return; }

    // Pull the blue channel up toward the others rather than desaturating everything: that removes
    // the yellow cast while leaving the tooth's own shading alone.
    float grey = (src.r + src.g + src.b) / 3.0;
    vec3 neutral = mix(src.rgb, vec3(grey), whiten);
    vec3 result = clamp(neutral + brighten * mask, 0.0, 1.0);
    fragColor = vec4(mix(src.rgb, result, mask), src.a);
}
