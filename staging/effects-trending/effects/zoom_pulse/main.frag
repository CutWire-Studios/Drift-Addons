#version 330 core
in vec2 v_texCoord; out vec4 fragColor;
uniform sampler2D u_currentTexture; uniform vec2 u_resolution;
uniform float punch; uniform float centerX; uniform float centerY; uniform float blur;

const int kSteps = 12;

void main() {
    if (punch <= 1e-5) {
        fragColor = texture(u_currentTexture, v_texCoord);
        return;
    }

    vec2 c = vec2(centerX, centerY);
    vec2 d = v_texCoord - c;
    float dist = length(d);
    float p = clamp(punch, 0.0, 1.0);
    float zoom = 1.0 - p * 0.18;
    float smear = mix(0.0, 0.06, clamp(blur, 0.0, 1.0)) * p;

    vec3 acc = vec3(0.0);
    float wsum = 0.0;
    for (int i = 0; i < kSteps; ++i) {
        float t = float(i) / float(kSteps - 1) - 0.5;
        vec2 uv = c + d * (zoom + smear * t);
        float w = 1.0 - abs(t) * 2.0;
        acc += texture(u_currentTexture, clamp(uv, 0.0, 1.0)).rgb * w;
        wsum += w;
    }
    fragColor = vec4(acc / max(wsum, 1e-4), texture(u_currentTexture, v_texCoord).a);
}
