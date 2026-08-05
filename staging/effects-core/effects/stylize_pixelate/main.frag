#version 330 core
in vec2 v_texCoord; out vec4 fragColor;
uniform sampler2D u_currentTexture; uniform vec2 u_resolution;
uniform float width; uniform float height;
void main() {
    vec2 block = max(vec2(width, height), vec2(1.0));
    vec2 uv = floor(v_texCoord * u_resolution / block) * block / u_resolution;
    fragColor = texture(u_currentTexture, uv + 0.5 * block / u_resolution);
}
