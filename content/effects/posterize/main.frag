#version 330 core
in vec2 v_texCoord; out vec4 fragColor;
uniform sampler2D u_currentTexture;
uniform float levels; uniform float strength;
void main() {
    vec4 c = texture(u_currentTexture, v_texCoord);
    float n = max(floor(levels + 0.5), 2.0);
    vec3 q = floor(c.rgb * (n - 1.0) + 0.5) / (n - 1.0);
    fragColor = vec4(mix(c.rgb, q, clamp(strength, 0.0, 1.0)), c.a);
}
