#version 330 core
in vec2 v_texCoord; out vec4 fragColor;
uniform sampler2D u_currentTexture; uniform vec2 u_resolution; uniform float u_time;
uniform float amount; uniform float scale; uniform float edgeWidth;

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
    vec2 px = 1.0 / u_resolution;
    float a0 = texture(u_currentTexture, v_texCoord).a;
    float edge = 0.0;
    for (int y = -2; y <= 2; ++y) {
        for (int x = -2; x <= 2; ++x) {
            float aa = texture(u_currentTexture, clamp(v_texCoord + px * vec2(x, y), 0.0, 1.0)).a;
            edge = max(edge, abs(a0 - aa));
        }
    }
    float n = valueNoise(v_texCoord * scale + u_time * 0.0);
    float erode = (n - 0.5) * 2.0 * amount * edgeWidth * edge;
    vec2 off = vec2(erode, erode * 0.7) * px * 8.0;
    fragColor = texture(u_currentTexture, clamp(v_texCoord + off, 0.0, 1.0));
}
