#version 330 core
in vec2 v_texCoord; out vec4 fragColor;
uniform sampler2D u_currentTexture;
uniform float strength;
void main() {
    vec4 c = texture(u_currentTexture, v_texCoord);
    fragColor = vec4(mix(c.rgb, 1.0 - c.rgb, clamp(strength, 0.0, 1.0)), c.a);
}
