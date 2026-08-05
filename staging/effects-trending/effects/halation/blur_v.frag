#version 330 core
in vec2 v_texCoord; out vec4 fragColor;
uniform sampler2D u_currentTexture; uniform vec2 u_resolution; uniform float blurRadius;
void main() {
    float r = clamp(blurRadius, 1.0, 30.0);
    vec2 px = vec2(0.0, 1.0 / u_resolution.y);
    vec4 sum = vec4(0.0);
    float count = 0.0;
    for (int k = -30; k <= 30; ++k) {
        if (abs(float(k)) > r) continue;
        sum += texture(u_currentTexture, v_texCoord + px * float(k));
        count += 1.0;
    }
    fragColor = sum / max(count, 1.0);
}
