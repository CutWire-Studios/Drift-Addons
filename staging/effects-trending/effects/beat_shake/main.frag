#version 330 core
in vec2 v_texCoord; out vec4 fragColor;
uniform sampler2D u_currentTexture; uniform vec2 u_resolution; uniform float u_time;
uniform float amount; uniform float rotation; uniform float seed;

float hash11(float p) { return fract(sin(p * 127.1) * 43758.5453); }

void main() {
    if (amount <= 1e-5) {
        fragColor = texture(u_currentTexture, v_texCoord);
        return;
    }

    float a = clamp(amount, 0.0, 1.0);
    float overscan = 1.0 + a * 0.12;
    vec2 c = vec2(0.5);
    vec2 p = (v_texCoord - c) * overscan + c;

    float t = u_time * 48.0 + seed * 97.0;
    vec2 jitter = vec2(sin(t * 1.7), cos(t * 2.3)) * a * 0.035;
    jitter += vec2(hash11(t), hash11(t + 3.1)) * a * 0.02 - a * 0.01;

    float rot = a * rotation * 0.08 * sin(t * 3.1);
    float ca = cos(rot);
    float sa = sin(rot);
    vec2 q = p - c;
    q = vec2(q.x * ca - q.y * sa, q.x * sa + q.y * ca) + c + jitter;

    fragColor = texture(u_currentTexture, clamp(q, 0.0, 1.0));
}
