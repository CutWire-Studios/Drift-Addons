#version 330 core
in vec2 v_texCoord; out vec4 fragColor;
uniform sampler2D u_currentTexture;
uniform vec2 u_resolution;

// One jump-flood step. Each texel holds the offset to its nearest boundary seed, 12 bits per
// axis biased by 2048 (0 means "no seed yet"), packed into rgb. Buffers are RGBA8, so absolute
// coordinates would not fit; offsets do, and they bound the reach at 2047 px.
//
// Every pass runs this same file, so the step size cannot come from the pipeline. Alpha carries
// the pass counter instead: step k jumps 1024 >> k, and the twelfth pass repeats a 1-pixel step,
// which cleans up the few texels plain JFA gets wrong.

vec3 bytesOf(vec4 c) { return floor(c.rgb * 255.0 + 0.5); }

bool unpack(vec4 c, out vec2 off)
{
    vec3 b = bytesOf(c);
    float hi = floor(b.g / 16.0);
    vec2 v = vec2(b.r * 16.0 + hi, (b.g - hi * 16.0) * 256.0 + b.b);
    off = v - 2048.0;
    return v.x > 0.0;
}

vec4 pack(vec2 off, bool valid, float counter)
{
    if (!valid)
        return vec4(0.0, 0.0, 0.0, counter / 255.0);
    vec2 v = off + 2048.0;
    float hx = floor(v.x / 16.0);
    float hy = floor(v.y / 256.0);
    return vec4(hx, (v.x - hx * 16.0) * 16.0 + hy, v.y - hy * 256.0, counter) / 255.0;
}

void main()
{
    ivec2 p = ivec2(gl_FragCoord.xy);
    ivec2 size = ivec2(u_resolution);
    vec4 self = texelFetch(u_currentTexture, p, 0);
    float k = floor(self.a * 255.0 + 0.5);
    int jump = k < 11.0 ? int(1024.0 / exp2(k)) : 1;

    vec2 best = vec2(0.0);
    float bestLen = 1e20;
    bool found = false;
    for (int j = -1; j <= 1; ++j) {
        for (int i = -1; i <= 1; ++i) {
            ivec2 q = p + ivec2(i, j) * jump;
            if (q.x < 0 || q.y < 0 || q.x >= size.x || q.y >= size.y)
                continue;
            vec2 o;
            if (!unpack(texelFetch(u_currentTexture, q, 0), o))
                continue;
            vec2 cand = vec2(q - p) + o;
            float l = dot(cand, cand);
            if (l < bestLen && max(abs(cand.x), abs(cand.y)) < 2047.0) {
                bestLen = l;
                best = cand;
                found = true;
            }
        }
    }
    fragColor = pack(best, found, k + 1.0);
}
