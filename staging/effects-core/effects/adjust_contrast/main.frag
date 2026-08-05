#version 330 core
in vec2 v_texCoord; out vec4 fragColor;
uniform sampler2D u_currentTexture; uniform float contrast;
void main() {
    vec4 c = texture(u_currentTexture, v_texCoord);
    fragColor = vec4((c.rgb - 0.5) * contrast + 0.5, c.a);
}
