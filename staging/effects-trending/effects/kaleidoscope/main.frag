#version 330 core
in vec2 v_texCoord; out vec4 fragColor;
uniform sampler2D u_currentTexture;
uniform float segments; uniform float rotation; uniform float centerX; uniform float centerY; uniform float zoom;

const float PI = 3.14159265;

void main() {
    vec2 c = vec2(centerX, centerY);
    vec2 p = v_texCoord - c;
    float r = length(p);
    float a = atan(p.y, p.x) + rotation * 2.0 * PI;
    int seg = int(clamp(floor(segments + 0.5), 2.0, 12.0));
    float slice = 2.0 * PI / float(seg);
    a = mod(a, slice);
    if (mod(floor((atan(p.y, p.x) + rotation * 2.0 * PI) / slice + 1000.0), 2.0) > 0.5)
        a = slice - a;
    vec2 uv = vec2(cos(a), sin(a)) * r / max(zoom, 0.5) + c;
    fragColor = texture(u_currentTexture, clamp(uv, 0.0, 1.0));
}
