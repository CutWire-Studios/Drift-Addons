#version 330 core
in vec2 v_texCoord; out vec4 fragColor;
uniform sampler2D u_currentTexture; uniform float gamma;
void main() {
    vec4 c = texture(u_currentTexture, v_texCoord);
    float g = max(gamma, 0.001);
    fragColor = vec4(pow(max(c.rgb, 0.0), vec3(1.0 / g)), c.a);
}
