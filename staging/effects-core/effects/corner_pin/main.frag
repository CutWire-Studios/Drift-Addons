#version 330 core
in vec2 v_texCoord; out vec4 fragColor;
uniform sampler2D u_currentTexture;
uniform float tlX; uniform float tlY; uniform float trX; uniform float trY;
uniform float brX; uniform float brY; uniform float blX; uniform float blY;

// Inverse bilinear map: screen UV -> unit square, then sample source.
bool invBilinear(vec2 p, vec2 a, vec2 b, vec2 c, vec2 d, out vec2 uv) {
    vec2 e = b - a;
    vec2 f = d - a;
    vec2 g = a - b + c - d;
    vec2 h = p - a;
    float k2 = g.x * f.y - g.y * f.x;
    float k1 = e.x * f.y - e.y * f.x + h.x * g.y - h.y * g.x;
    float k0 = h.x * e.y - h.y * e.x;
    float v;
    if (abs(k2) < 1e-6) {
        if (abs(k1) < 1e-6) return false;
        v = -k0 / k1;
    } else {
        float disc = k1 * k1 - 4.0 * k2 * k0;
        if (disc < 0.0) return false;
        float sd = sqrt(disc);
        float v0 = (-k1 - sd) / (2.0 * k2);
        float v1 = (-k1 + sd) / (2.0 * k2);
        v = (v0 >= 0.0 && v0 <= 1.0) ? v0 : v1;
    }
    float denom = e.x + g.x * v;
    float u = (abs(denom) > abs(e.y + g.y * v))
        ? (h.x - f.x * v) / denom
        : (h.y - f.y * v) / (e.y + g.y * v);
    uv = vec2(u, v);
    return u >= 0.0 && u <= 1.0 && v >= 0.0 && v <= 1.0;
}

void main() {
    vec2 a = vec2(tlX, tlY);
    vec2 b = vec2(trX, trY);
    vec2 c = vec2(brX, brY);
    vec2 d = vec2(blX, blY);
    vec2 uv;
    if (!invBilinear(v_texCoord, a, b, c, d, uv)) {
        fragColor = vec4(0.0);
        return;
    }
    fragColor = texture(u_currentTexture, clamp(uv, 0.0, 1.0));
}
