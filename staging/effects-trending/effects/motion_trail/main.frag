#version 330 core
in vec2 v_texCoord; out vec4 fragColor;
uniform sampler2D u_currentTexture; uniform vec2 u_resolution;
uniform float amount; uniform float angle; uniform float length;

const int kSteps = 16;

void main() {
    vec4 src = texture(u_currentTexture, v_texCoord);
    if (amount <= 1e-5) {
        fragColor = src;
        return;
    }

    float a = angle * 6.2831853;
    vec2 dir = vec2(cos(a), sin(a));
    float lenPx = mix(8.0, 120.0, clamp(length, 0.0, 1.0));
    vec3 acc = src.rgb;
    float wsum = 1.0;

    for (int i = 1; i <= kSteps; ++i) {
        float t = float(i) / float(kSteps);
        vec2 uv = v_texCoord - dir * (t * lenPx) / u_resolution;
        float w = (1.0 - t) * amount;
        acc += texture(u_currentTexture, clamp(uv, 0.0, 1.0)).rgb * w;
        wsum += w;
    }
    fragColor = vec4(clamp(acc / wsum, 0.0, 1.0), src.a);
}
