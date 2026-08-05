#version 330 core
in vec2 v_texCoord; out vec4 fragColor;
uniform sampler2D u_currentTexture; uniform float threshold;
void main() {
    vec4 c = texture(u_currentTexture, v_texCoord);
    fragColor = vec4(max(c.rgb - vec3(threshold), 0.0), c.a);
}
