#version 330 core
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
