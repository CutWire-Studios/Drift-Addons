#version 330 core
in vec2 v_texCoord; out vec4 fragColor;
uniform sampler2D u_currentTexture; uniform float saturation;
void main() {
    vec4 c = texture(u_currentTexture, v_texCoord);
    float l = dot(c.rgb, vec3(0.299, 0.587, 0.114));
    fragColor = vec4(mix(vec3(l), c.rgb, saturation), c.a);
}
