#version 330 core
in vec2 v_texCoord; out vec4 fragColor;
uniform sampler2D u_currentTexture; uniform vec2 u_resolution;
uniform float size; uniform float strength;
vec2 hexCenter(vec2 p) {
    // axial hex grid
    vec2 r = vec2(1.0, 1.7320508);
    vec2 h = r * 0.5;
    vec2 a = mod(p, r) - h;
    vec2 b = mod(p - h, r) - h;
    return (dot(a, a) < dot(b, b)) ? a : b;
}
void main() {
    float s = max(size, 2.0);
    vec2 p = v_texCoord * u_resolution / s;
    vec2 d = hexCenter(p);
    vec2 cell = (p - d) * s / u_resolution;
    vec4 src = texture(u_currentTexture, v_texCoord);
    vec4 hex = texture(u_currentTexture, clamp(cell, 0.0, 1.0));
    fragColor = mix(src, hex, clamp(strength, 0.0, 1.0));
}
