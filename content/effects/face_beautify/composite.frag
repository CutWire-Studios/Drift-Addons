#version 330 core
in vec2 v_texCoord; out vec4 fragColor;
uniform sampler2D u_currentTexture; // original frame
uniform sampler2D u_texture1;       // the blurred pair of passes, at half resolution
uniform vec2 u_resolution;
uniform float u_faceValid; uniform float u_faceHasContours;
uniform vec2 u_faceOval[36];
uniform vec2 u_faceLipOuter[20];
uniform vec2 u_faceEyeLeft[16];
uniform vec2 u_faceEyeRight[16];
uniform vec2 u_faceBrowLeft[10];
uniform vec2 u_faceBrowRight[10];
uniform float u_faceRx;
uniform float amount; uniform float detailKeep; uniform float evenness; uniform float glow;
uniform float feather;

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
SD_POLY(sdLips, u_faceLipOuter, 20)
SD_POLY(sdEyeL, u_faceEyeLeft, 16)
SD_POLY(sdEyeR, u_faceEyeRight, 16)
SD_POLY(sdBrowL, u_faceBrowLeft, 10)
SD_POLY(sdBrowR, u_faceBrowRight, 10)

float luma(vec3 c) { return dot(c, vec3(0.2126, 0.7152, 0.0722)); }

void main() {
    vec4 src = texture(u_currentTexture, v_texCoord);
    if (u_faceValid < 0.5 || u_faceHasContours < 0.5) { fragColor = src; return; }

    float aspect = u_resolution.y / u_resolution.x;
    vec2 p = toLocal(v_texCoord, aspect);

    // Skin is the oval minus every feature. Excluding the features is what lets the blur be as
    // strong as it is: the eyelashes, lip edge and brow hairs that would otherwise smear are
    // simply never touched, and it is also why the separable approximation upstream holds up.
    float fw = max(feather * 0.12 * u_faceRx, 1e-5);
    float ovalD = sdOval(p);
    float skin = 1.0 - smoothstep(-fw, fw * 0.4, ovalD);

    float featureD = min(min(sdLips(p), min(sdEyeL(p), sdEyeR(p))),
                         min(sdBrowL(p), sdBrowR(p)));
    float guard = max(u_faceRx * 0.05, 1e-5);
    skin *= smoothstep(-guard * 0.2, guard, featureD);
    if (skin <= 0.0) { fragColor = src; return; }

    vec3 smoothed = texture(u_texture1, v_texCoord).rgb;

    // Frequency split: the blurred image carries the low frequencies, the difference carries pores,
    // stubble and blemishes. Scaling only the difference removes texture without the plastic look
    // that mixing toward the blur produces, because the shading underneath is left alone.
    vec3 detail = src.rgb - smoothed;
    float keep = mix(1.0, detailKeep, skin * amount);
    vec3 result = smoothed + detail * keep;

    // Even tone: pull local colour toward the blurred average, which is where redness and patches
    // live. Luminance is left out of it so this does not double up on the smoothing.
    float srcL = max(luma(result), 1e-4);
    float blurL = max(luma(smoothed), 1e-4);
    vec3 evened = smoothed * (srcL / blurL);
    result = mix(result, evened, skin * evenness);

    // Glow keyed off depth into the oval, so it lands on the cheekbones and forehead rather than
    // tracing the jawline.
    float core = clamp(-ovalD / max(u_faceRx * 0.55, 1e-5), 0.0, 1.0);
    float hl = max(luma(result) - 0.55, 0.0);
    result += vec3(glow * 0.55 * core * skin * hl);

    fragColor = vec4(clamp(result, 0.0, 1.0), src.a);
}
