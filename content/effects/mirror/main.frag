#version 330 core
in vec2 v_texCoord; out vec4 fragColor;
uniform sampler2D u_currentTexture;
uniform float mode; uniform float offset;
void main() {
    vec2 uv = v_texCoord;
    int m = int(clamp(floor(mode + 0.5), 0.0, 3.0));
    float o = clamp(offset, 0.0, 1.0);
    if (m == 0) {
        if (uv.x > o) uv.x = 2.0 * o - uv.x;
    } else if (m == 1) {
        if (uv.x < o) uv.x = 2.0 * o - uv.x;
    } else if (m == 2) {
        if (uv.y > o) uv.y = 2.0 * o - uv.y;
    } else {
        if (uv.y < o) uv.y = 2.0 * o - uv.y;
    }
    fragColor = texture(u_currentTexture, clamp(uv, 0.0, 1.0));
}
