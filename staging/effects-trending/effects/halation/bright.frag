#version 330 core
in vec2 v_texCoord; out vec4 fragColor;
uniform sampler2D u_currentTexture; uniform float threshold; uniform float warmth;
void main() {
    // Halation is light scattering off the film base and reflecting back through the
    // emulsion — red penetrates deepest, so the bleed is red-weighted, not neutral.
    vec3 c = texture(u_currentTexture, v_texCoord).rgb;
    vec3 over = max(c - vec3(threshold), 0.0) / max(1.0 - threshold, 1e-3);
    vec3 weight = mix(vec3(1.0), vec3(1.0, 0.45, 0.2), clamp(warmth, 0.0, 1.0));
    fragColor = vec4(over * weight, 1.0);
}
