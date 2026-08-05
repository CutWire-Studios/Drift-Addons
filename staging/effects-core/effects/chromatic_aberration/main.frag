#version 330 core
in vec2 v_texCoord; out vec4 fragColor;
uniform sampler2D u_currentTexture; uniform vec2 u_resolution;
uniform float amount; uniform float falloff; uniform float centerX; uniform float centerY;
void main() {
    float aspect = u_resolution.x / max(u_resolution.y, 1.0);
    vec2 c = vec2(centerX, centerY);
    vec2 d = (v_texCoord - c) * vec2(aspect, 1.0);
    float r = length(d);
    float edge = pow(clamp(r, 0.0, 1.5) / 1.5, 1.0 + falloff);
    float shift = amount * 0.035 * edge;
    vec2 dir = (r > 1e-5) ? normalize(vec2(d.x / aspect, d.y)) : vec2(0.0);
    float R = texture(u_currentTexture, clamp(v_texCoord + dir * shift, 0.0, 1.0)).r;
    float G = texture(u_currentTexture, v_texCoord).g;
    float B = texture(u_currentTexture, clamp(v_texCoord - dir * shift, 0.0, 1.0)).b;
    float a = texture(u_currentTexture, v_texCoord).a;
    fragColor = vec4(R, G, B, a);
}
