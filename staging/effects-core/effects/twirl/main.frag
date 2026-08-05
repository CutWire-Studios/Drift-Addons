#version 330 core
in vec2 v_texCoord; out vec4 fragColor;
uniform sampler2D u_currentTexture; uniform vec2 u_resolution;
uniform float angle; uniform float radius; uniform float centerX; uniform float centerY;
void main() {
    float aspect = u_resolution.x / max(u_resolution.y, 1.0);
    vec2 c = vec2(centerX, centerY);
    vec2 d = (v_texCoord - c) * vec2(aspect, 1.0);
    float r = length(d);
    float R = max(radius, 1e-4);
    float fall = 1.0 - smoothstep(0.0, R, r);
    float a = atan(d.y, d.x) + angle * fall * fall;
    vec2 nd = (r > 1e-6) ? vec2(cos(a), sin(a)) * r : d;
    vec2 src = c + vec2(nd.x / aspect, nd.y);
    fragColor = texture(u_currentTexture, clamp(src, 0.0, 1.0));
}
