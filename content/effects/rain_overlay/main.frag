#version 330 core
in vec2 v_texCoord; out vec4 fragColor;
uniform sampler2D u_currentTexture; uniform vec2 u_resolution; uniform float u_time;
uniform float amount; uniform float speed; uniform float streakLength;
uniform float angle; uniform float opacity;

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
    float rad = radians(angle);
    // Shear UV by rain angle so streaks follow the fall direction.
    mat2 rot = mat2(cos(rad), -sin(rad), sin(rad), cos(rad));
    float density = mix(20.0, 90.0, amount);
    vec2 uv = rot * vec2(v_texCoord.x * aspect, v_texCoord.y);
    vec2 st = uv * density;
    st.y -= u_time * speed * 8.0;
    vec2 id = floor(st);
    vec2 f = fract(st);
    float n = hash21(id);
    float streak = 0.0;
    if (n < amount * 0.55) {
        float x = abs(f.x - 0.5);
        float y = fract(f.y + n);
        float len = mix(0.15, 0.9, streakLength);
        streak = (1.0 - smoothstep(0.0, 0.04, x)) * (1.0 - smoothstep(len, len + 0.1, y));
    }
    vec3 rain = vec3(0.75, 0.8, 0.9) * streak * opacity;
    fragColor = vec4(src.rgb + rain, src.a);
}
