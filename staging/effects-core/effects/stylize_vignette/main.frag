#version 330 core
in vec2 v_texCoord; out vec4 fragColor;
uniform sampler2D u_currentTexture; uniform vec2 u_resolution;
uniform float amount; uniform float feather; uniform float roundness;
uniform vec3 color; uniform vec2 center;
void main() {
    vec4 c = texture(u_currentTexture, v_texCoord);
    vec2 p = v_texCoord * 2.0 - center * 2.0;
    float aspect = u_resolution.x / max(u_resolution.y, 1.0);
    p.x *= mix(1.0, aspect, roundness);
    float r2 = dot(p, p);
    float vig = clamp(1.0 - amount * mix(r2, r2 * r2, feather), 0.0, 1.0);
    vec3 tint = color * c.a;
    fragColor = vec4(mix(tint, c.rgb, vig), c.a);
}
