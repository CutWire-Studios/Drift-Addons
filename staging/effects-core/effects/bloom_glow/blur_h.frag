#version 330 core
in vec2 v_texCoord; out vec4 fragColor;
uniform sampler2D u_currentTexture; uniform vec2 u_resolution; uniform float blurRadius;
void main() {
    // Separable horizontal box blur (matches CPU bloom_glow).
    float r = clamp(blurRadius, 1.0, 30.0);
    vec2 px = vec2(1.0 / u_resolution.x, 0.0);
    vec4 sum = vec4(0.0);
    float count = 0.0;
    for (int k = -30; k <= 30; ++k) {
        if (abs(float(k)) > r) continue;
        sum += texture(u_currentTexture, v_texCoord + px * float(k));
        count += 1.0;
    }
    fragColor = sum / max(count, 1.0);
}
