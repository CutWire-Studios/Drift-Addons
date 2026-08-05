#version 330 core
in vec2 v_texCoord; out vec4 fragColor;
uniform sampler2D u_currentTexture;
uniform float sourceR; uniform float sourceG; uniform float sourceB;
uniform float targetR; uniform float targetG; uniform float targetB;
uniform float tolerance; uniform float softness;
void main() {
    vec4 c = texture(u_currentTexture, v_texCoord);
    vec3 sourceColor = vec3(sourceR, sourceG, sourceB);
    vec3 targetColor = vec3(targetR, targetG, targetB);
    float d = distance(c.rgb, sourceColor);
    float m = 1.0 - smoothstep(tolerance, tolerance + softness, d);
    fragColor = vec4(mix(c.rgb, targetColor, m), c.a);
}
