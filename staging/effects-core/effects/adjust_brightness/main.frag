#version 330 core
in vec2 v_texCoord; out vec4 fragColor;
uniform sampler2D u_currentTexture; uniform float brightness;
void main() {
    vec4 c = texture(u_currentTexture, v_texCoord);
    fragColor = vec4(clamp(c.rgb + brightness, 0.0, 1.0), c.a);
}
