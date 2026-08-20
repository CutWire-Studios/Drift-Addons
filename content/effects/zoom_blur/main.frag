#version 330 core
in vec2 v_texCoord; out vec4 fragColor;
uniform sampler2D u_currentTexture;
uniform float amount; uniform float centerX; uniform float centerY; uniform float samples;
void main() {
    if (amount <= 1e-5) { fragColor = texture(u_currentTexture, v_texCoord); return; }
    vec2 c = vec2(centerX, centerY);
    vec2 d = v_texCoord - c;
    int n = int(clamp(floor(samples + 0.5), 4.0, 24.0));
    vec3 acc = vec3(0.0);
    float wsum = 0.0;
    for (int i = 0; i < 24; ++i) {
        if (i >= n) break;
        float t = float(i) / float(n - 1);
        float s = 1.0 - t * amount * 0.45;
        float w = 1.0 - t * 0.55;
        acc += texture(u_currentTexture, clamp(c + d * s, 0.0, 1.0)).rgb * w;
        wsum += w;
    }
    fragColor = vec4(acc / max(wsum, 1e-4), texture(u_currentTexture, v_texCoord).a);
}
