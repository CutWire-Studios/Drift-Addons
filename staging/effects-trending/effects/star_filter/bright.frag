#version 330 core
in vec2 v_texCoord; out vec4 fragColor;
uniform sampler2D u_currentTexture; uniform float threshold;
void main() {
    vec3 c = texture(u_currentTexture, v_texCoord).rgb;
    float lum = dot(c, vec3(0.2126, 0.7152, 0.0722));
    float m = smoothstep(threshold, min(threshold + 0.2, 1.0), lum);
    fragColor = vec4(c * m, 1.0);
}
