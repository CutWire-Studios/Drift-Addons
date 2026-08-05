#version 330 core
in vec2 v_texCoord; out vec4 fragColor;
uniform sampler2D u_currentTexture; uniform float threshold;
void main() {
    // rgb keeps the highlight's own colour so sparkles can be tinted by what lit them;
    // alpha is the mask the sparkle pass tests to decide whether a cell gets a star.
    vec3 c = texture(u_currentTexture, v_texCoord).rgb;
    float lum = dot(c, vec3(0.2126, 0.7152, 0.0722));
    float m = smoothstep(threshold, min(threshold + 0.25, 1.0), lum);
    fragColor = vec4(c, m);
}
