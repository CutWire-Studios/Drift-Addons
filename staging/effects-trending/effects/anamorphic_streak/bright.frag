#version 330 core
in vec2 v_texCoord;
out vec4 fragColor;
uniform sampler2D u_currentTexture;
uniform float threshold;

void main() {
    vec3 c = max(texture(u_currentTexture, v_texCoord).rgb, 0.0);
    float l = max(c.r, max(c.g, c.b));
    float knee = 0.08;
    float soft = clamp(l - threshold + knee, 0.0, 2.0 * knee);
    soft = soft * soft / (4.0 * knee);
    float w = max(soft, l - threshold) / max(l, 1e-4);
    fragColor = vec4(c * w / max(1.0 - threshold, 0.05), 1.0);
}
