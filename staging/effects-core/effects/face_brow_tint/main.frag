#version 330 core
in vec2 v_texCoord; out vec4 fragColor;
uniform sampler2D u_currentTexture; uniform vec2 u_resolution;
uniform float u_faceValid; uniform float u_faceHasContours;
uniform vec2 u_faceBrowLeft[10];
uniform vec2 u_faceBrowRight[10];
uniform vec3 shade; uniform float strength; uniform float density; uniform float feather;

vec2 toLocal(vec2 uv, float aspect) { return vec2(uv.x, uv.y * aspect); }
vec2 fromLocal(vec2 q, float aspect) { return vec2(q.x, q.y / aspect); }

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

SD_POLY(sdBrowLeft, u_faceBrowLeft, 10)
SD_POLY(sdBrowRight, u_faceBrowRight, 10)

float luma(vec3 c) { return dot(c, vec3(0.2126, 0.7152, 0.0722)); }

// Luminance of the skin immediately above and below a brow. Hair has to be recognised relative to
// the face it is on: an absolute threshold picks nothing on a dark-skinned or backlit subject and
// everything on a pale one, and it also fails whenever the face is small enough that brow pixels
// have blended toward skin.
float skinReference(vec2 brow[10], float aspect) {
    vec2 c = vec2(0.0);
    for (int i = 0; i < 10; i++) c += brow[i];
    c /= 10.0;

    float halfHeight = 0.0;
    for (int i = 0; i < 10; i++) halfHeight = max(halfHeight, abs(brow[i].y - c.y));
    float reach = max(halfHeight * 2.6, 1e-4);

    // Above is forehead, below is the lid — both skin, and straddling the brow cancels out any
    // top-to-bottom lighting gradient across the face.
    float sum = 0.0;
    sum += luma(texture(u_currentTexture, fromLocal(c + vec2(0.0, -reach), aspect)).rgb);
    sum += luma(texture(u_currentTexture, fromLocal(c + vec2(0.0, reach), aspect)).rgb);
    sum += luma(texture(u_currentTexture, fromLocal(c + vec2(-reach, -reach), aspect)).rgb);
    sum += luma(texture(u_currentTexture, fromLocal(c + vec2(reach, -reach), aspect)).rgb);
    return sum * 0.25;
}

void main() {
    vec4 src = texture(u_currentTexture, v_texCoord);
    if (u_faceValid < 0.5 || u_faceHasContours < 0.5) { fragColor = src; return; }

    float aspect = u_resolution.y / u_resolution.x;
    vec2 p = toLocal(v_texCoord, aspect);

    float browWidth = length(u_faceBrowLeft[4] - u_faceBrowLeft[0]);
    float fw = max(feather * 0.18 * browWidth, 1e-5);
    float dl = sdBrowLeft(p);
    float dr = sdBrowRight(p);
    float inside = 1.0 - smoothstep(-fw, fw, min(dl, dr));
    if (inside <= 0.0) { fragColor = src; return; }

    // The brow polygon covers hair *and* the skin showing through it. Weighting by how much darker
    // a pixel is than the surrounding skin picks out the hairs: tinting the whole polygon floods
    // the gaps and reads as a drawn-on shape.
    float ref = skinReference(dl < dr ? u_faceBrowLeft : u_faceBrowRight, aspect);
    float L = luma(src.rgb);
    // density widens the band, so a sparse brow can still take colour across its whole shape.
    float band = mix(0.05, 0.30, density);
    float hair = smoothstep(ref - 0.02, ref - 0.02 - band, L);
    float mask = inside * hair;
    if (mask <= 0.0) { fragColor = src; return; }

    // Multiply, so the tint deepens what is already there instead of replacing it. A brow hair keeps
    // its own highlight and the result still looks like hair.
    vec3 tinted = src.rgb * mix(vec3(1.0), shade * 2.0, strength * mask);
    fragColor = vec4(clamp(tinted, 0.0, 1.0), src.a);
}
