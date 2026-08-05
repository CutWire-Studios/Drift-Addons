#version 330 core
in vec2 v_texCoord; out vec4 fragColor;
uniform sampler2D u_currentTexture; uniform vec2 u_resolution;
uniform float k1; uniform float k2; uniform float centerX; uniform float centerY; uniform float scale;
void main() {
    float aspect = u_resolution.x / max(u_resolution.y, 1.0);
    vec2 c = vec2(centerX, centerY);
    vec2 p = (v_texCoord - c) * vec2(aspect, 1.0) / max(scale, 1e-4);
    float r2 = dot(p, p);
    float f = 1.0 + k1 * r2 + k2 * r2 * r2;
    vec2 src = c + vec2(p.x / aspect, p.y) * f;
    if (src.x < 0.0 || src.x > 1.0 || src.y < 0.0 || src.y > 1.0) {
        fragColor = vec4(0.0);
        return;
    }
    fragColor = texture(u_currentTexture, src);
}
