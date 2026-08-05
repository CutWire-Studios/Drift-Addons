#version 330 core
in vec2 v_texCoord; out vec4 fragColor;
uniform sampler2D u_currentTexture; uniform vec2 u_resolution; uniform float u_time;
uniform float amount; uniform float scale; uniform float speed;
uniform float octaves; uniform float evolution;

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

void main() {
    float amp = amount * 0.08;
    if (amp <= 1e-6) { fragColor = texture(u_currentTexture, v_texCoord); return; }
    float aspect = u_resolution.x / max(u_resolution.y, 1.0);
    vec2 uv = v_texCoord;
    vec2 p = vec2(uv.x * aspect, uv.y) * scale;
    float t = u_time * speed + evolution;
    int n = int(clamp(floor(octaves + 0.5), 1.0, 6.0));
    vec2 warp = vec2(0.0);
    float a = 1.0;
    vec2 q = p;
    for (int i = 0; i < 6; ++i) {
        if (i >= n) break;
        warp += a * vec2(valueNoise(q + vec2(t, 0.0)), valueNoise(q + vec2(0.0, t + 17.0)));
        q = q * 2.02 + vec2(1.7, 9.2);
        a *= 0.5;
    }
    vec2 src = clamp(uv + (warp - 0.5) * 2.0 * amp, 0.0, 1.0);
    fragColor = texture(u_currentTexture, src);
}
