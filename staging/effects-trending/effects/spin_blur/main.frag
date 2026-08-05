#version 330 core
in vec2 v_texCoord; out vec4 fragColor;
uniform sampler2D u_currentTexture;
uniform float amount; uniform float centerX; uniform float centerY; uniform float samples;

void main() {
    if (amount <= 1e-5) {
        fragColor = texture(u_currentTexture, v_texCoord);
        return;
    }

    vec2 c = vec2(centerX, centerY);
    vec2 d = v_texCoord - c;
    int n = int(clamp(floor(samples + 0.5), 4.0, 24.0));
    float span = amount * 0.35;
    vec3 acc = vec3(0.0);
    float wsum = 0.0;

    for (int i = 0; i < 24; ++i) {
        if (i >= n)
            break;
        float t = (float(i) / float(n - 1) - 0.5) * 2.0;
        float ang = t * span;
        float ca = cos(ang);
        float sa = sin(ang);
        vec2 q = vec2(d.x * ca - d.y * sa, d.x * sa + d.y * ca) + c;
        float w = 1.0 - abs(t) * 0.5;
        acc += texture(u_currentTexture, clamp(q, 0.0, 1.0)).rgb * w;
        wsum += w;
    }
    fragColor = vec4(acc / max(wsum, 1e-4), texture(u_currentTexture, v_texCoord).a);
}
