#version 330 core
in vec2 v_texCoord; out vec4 fragColor;
uniform sampler2D u_currentTexture; uniform vec2 u_resolution; uniform float u_time;
uniform float amount; uniform float speed; uniform float size; uniform float opacity;

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
    float aspect = u_resolution.x / max(u_resolution.y, 1.0);
    float flakes = 0.0;
    for (int layer = 0; layer < 3; ++layer) {
        float dens = mix(12.0, 40.0, amount) * (1.0 + float(layer) * 0.55);
        vec2 uv = vec2(v_texCoord.x * aspect, v_texCoord.y) * dens;
        uv.y += u_time * speed * (0.6 + float(layer) * 0.5);
        uv.x += sin(u_time * 0.4 + float(layer)) * 0.4;
        vec2 id = floor(uv);
        vec2 f = fract(uv) - 0.5;
        float n = hash21(id + float(layer) * 17.0);
        if (n < amount * 0.45) {
            float r = mix(0.04, 0.18, size) * (0.6 + n);
            flakes += smoothstep(r, r * 0.3, length(f));
        }
    }
    fragColor = vec4(src.rgb + vec3(flakes * opacity), src.a);
}
