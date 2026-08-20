#version 330 core
in vec2 v_texCoord; out vec4 fragColor;
uniform sampler2D u_currentTexture;
uniform float slopeR; uniform float slopeG; uniform float slopeB;
uniform float offsetR; uniform float offsetG; uniform float offsetB;
uniform float powerR; uniform float powerG; uniform float powerB;
uniform float saturation;
void main() {
    vec4 c = texture(u_currentTexture, v_texCoord);
    vec3 x = c.rgb * vec3(slopeR, slopeG, slopeB) + vec3(offsetR, offsetG, offsetB);
    x = pow(max(x, vec3(0.0)), vec3(powerR, powerG, powerB));
    float luma = dot(x, vec3(0.2126, 0.7152, 0.0722));
    x = mix(vec3(luma), x, saturation);
    fragColor = vec4(clamp(x, 0.0, 1.0), c.a);
}
