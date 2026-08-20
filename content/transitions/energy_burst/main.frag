#version 330 core
in vec2 v_texCoord;
out vec4 fragColor;

uniform sampler2D u_currentTexture;
uniform sampler2D u_fromTexture;
uniform sampler2D u_toTexture;
uniform vec2 u_resolution;
uniform float u_progress;

float hash11(float p) {
    p = fract(p * 0.1031);
    p *= p + 33.33;
    p *= p + p;
    return fract(p);
}

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

vec4 over(vec4 top, vec4 bot) {
    float oa = top.a + bot.a * (1.0 - top.a);
    if (oa <= 0.0001) return vec4(0.0);
    vec3 rgb = (top.rgb * top.a + bot.rgb * bot.a * (1.0 - top.a)) / oa;
    return vec4(rgb, oa);
}

float aspectRatio() { return u_resolution.x / max(u_resolution.y, 1.0); }


uniform float glow; uniform float rays; uniform float centerX; uniform float centerY;

void main() {
    vec2 uv = v_texCoord;
    float aspect = aspectRatio();
    vec2 c = vec2(centerX, centerY);
    vec2 d = (uv - c) * vec2(aspect, 1.0);
    float r = length(d);
    float p = clamp(u_progress, 0.0, 1.0);
    float wave = p * 1.35;
    float edge = smoothstep(wave - 0.12, wave + 0.02, r);
    float ring = 1.0 - smoothstep(0.0, 0.08, abs(r - wave));

    float ang = atan(d.y, d.x);
    float ray = pow(abs(sin(ang * 12.0 + p * 6.0)), 4.0) * rays * ring;

    vec4 fromCol = texture(u_fromTexture, uv);
    vec4 toCol = texture(u_toTexture, uv);
    vec4 mixed = mix(toCol, fromCol, edge);
    vec3 energy = vec3(0.6, 0.85, 1.0) * (ring * glow + ray);
    mixed.rgb += energy;
    fragColor = mixed;
}
