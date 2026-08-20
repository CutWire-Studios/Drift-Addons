#version 330 core
in vec2 v_texCoord; out vec4 fragColor;
uniform sampler2D u_currentTexture;
uniform float threshold;
void main() {
    vec4 c = texture(u_currentTexture, v_texCoord);
    float lum = dot(c.rgb, vec3(0.2126, 0.7152, 0.0722));
    float m = smoothstep(threshold, min(threshold + 0.15, 1.0), lum);
    fragColor = vec4(c.rgb * m, c.a);
}
