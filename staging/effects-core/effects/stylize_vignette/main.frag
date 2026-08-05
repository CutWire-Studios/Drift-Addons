#version 330 core
in vec2 v_texCoord; out vec4 fragColor;
uniform sampler2D u_currentTexture;
void main() {
    vec4 c = texture(u_currentTexture, v_texCoord);
    vec2 p = v_texCoord * 2.0 - 1.0;
    float vig = clamp(1.0 - dot(p, p) * 0.55, 0.0, 1.0);
    fragColor = vec4(c.rgb * vig, c.a);
}
