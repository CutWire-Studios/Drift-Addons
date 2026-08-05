#version 330 core
in vec2 v_texCoord; out vec4 fragColor;
uniform sampler2D u_currentTexture;
uniform float mode; uniform float blackPoint; uniform float whitePoint; uniform float asAlpha;
void main() {
    vec4 c = texture(u_currentTexture, v_texCoord);
    int m = int(clamp(floor(mode + 0.5), 0.0, 2.0));
    float v;
    if (m == 1) v = c.r;
    else if (m == 2) v = max(c.r, max(c.g, c.b));
    else v = dot(c.rgb, vec3(0.2126, 0.7152, 0.0722));
    float bp = blackPoint;
    float wp = max(whitePoint, bp + 1e-4);
    v = clamp((v - bp) / (wp - bp), 0.0, 1.0);
    if (asAlpha > 0.5) fragColor = vec4(c.rgb, v * c.a);
    else fragColor = vec4(vec3(v), c.a);
}
