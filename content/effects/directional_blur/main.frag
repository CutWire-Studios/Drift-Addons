#version 330 core
in vec2 v_texCoord; out vec4 fragColor;
uniform sampler2D u_currentTexture; uniform vec2 u_resolution;
uniform float amount; uniform float angle; uniform float samples;
void main() {
    if (amount <= 1e-5) { fragColor = texture(u_currentTexture, v_texCoord); return; }
    float rad = radians(angle);
    vec2 dir = vec2(cos(rad), sin(rad)) / u_resolution * (amount * 40.0);
    int n = int(clamp(floor(samples + 0.5), 4.0, 24.0));
    vec3 acc = vec3(0.0);
    float wsum = 0.0;
    for (int i = 0; i < 24; ++i) {
        if (i >= n) break;
        float t = (float(i) / float(n - 1) - 0.5) * 2.0;
        float w = 1.0 - abs(t) * 0.5;
        acc += texture(u_currentTexture, clamp(v_texCoord + dir * t, 0.0, 1.0)).rgb * w;
        wsum += w;
    }
    fragColor = vec4(acc / max(wsum, 1e-4), texture(u_currentTexture, v_texCoord).a);
}
