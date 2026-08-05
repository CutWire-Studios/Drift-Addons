#version 330 core
in vec2 v_texCoord; out vec4 fragColor;
uniform sampler2D u_currentTexture; uniform vec2 u_resolution; uniform float radius;
void main() {
    int r = int(clamp(radius, 1.0, 30.0));
    vec2 px = vec2(0.0, 1.0 / u_resolution.y);
    vec4 sum = texture(u_currentTexture, v_texCoord);
    float wsum = 1.0;
    for (int i = 1; i <= 30; ++i) {
        if (i > r) break;
        sum += texture(u_currentTexture, v_texCoord + px * float(i));
        sum += texture(u_currentTexture, v_texCoord - px * float(i));
        wsum += 2.0;
    }
    fragColor = sum / wsum;
}
