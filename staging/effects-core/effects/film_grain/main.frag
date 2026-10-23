#version 330 core
in vec2 v_texCoord; out vec4 fragColor;
uniform sampler2D u_currentTexture; uniform vec2 u_resolution; uniform int u_frameIndex;
uniform float amount; uniform float size; uniform float colored; uniform float softness;
uniform float lumaResponse; uniform float animated;

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
    vec4 src = texture(u_currentTexture, v_texCoord);
    vec3 c = src.rgb / max(src.a, 1e-5);
    // Grain is sized against a 1080-line frame, not the pass, so a reduced-scale preview matches
    // the export.
    float aspect = u_resolution.x / max(u_resolution.y, 1.0);
    vec2 p = v_texCoord * vec2(aspect, 1.0) * 1080.0 / max(size, 0.1);
    float ft = float(u_frameIndex) * animated;
    float n1 = valueNoise(p + ft * 1.7);
    float n2 = valueNoise(p + vec2(37.0, 91.0) + ft * 2.3);
    float n3 = valueNoise(p + vec2(11.0, 53.0) + ft * 3.1);
    vec3 grain = mix(vec3(n1), vec3(n1, n2, n3), colored);
    grain = (grain - 0.5) * 2.0;
    float lum = dot(c, vec3(0.2126, 0.7152, 0.0722));
    float resp = mix(1.0, 1.0 - abs(lum - 0.5) * 2.0, softness);
    resp *= mix(1.0, 4.0 * lum * (1.0 - lum), lumaResponse);
    fragColor = vec4(clamp(c + grain * amount * 0.35 * resp, 0.0, 1.0) * src.a, src.a);
}
