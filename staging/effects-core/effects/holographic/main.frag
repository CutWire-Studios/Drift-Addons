#version 330 core
in vec2 v_texCoord; out vec4 fragColor;
uniform sampler2D u_currentTexture; uniform vec2 u_resolution; uniform float u_time;
uniform float amount; uniform float scanlines; uniform float glitch;
uniform float tintR; uniform float tintG; uniform float tintB;

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
    vec2 uv = v_texCoord;
    vec3 tint = vec3(tintR, tintG, tintB);
    float g = glitch * step(0.92, valueNoise(vec2(floor(u_time * 12.0), floor(uv.y * 40.0))));
    uv.x += (valueNoise(vec2(floor(u_time * 8.0), floor(uv.y * 20.0))) - 0.5) * g * 0.08;
    vec4 c = texture(u_currentTexture, clamp(uv, 0.0, 1.0));
    float lines = sin(uv.y * u_resolution.y * 3.14159) * 0.5 + 0.5;
    lines = mix(1.0, lines, scanlines);
    float flick = 0.92 + 0.08 * valueNoise(vec2(u_time * 6.0, 0.5));
    vec3 holo = c.rgb * tint * lines * flick;
    float band = smoothstep(0.0, 0.02, abs(fract(uv.y * 3.0 + u_time * 0.15) - 0.5));
    holo += tint * (1.0 - band) * 0.08 * amount;
    fragColor = vec4(mix(c.rgb, holo, clamp(amount, 0.0, 1.0)), c.a);
}
