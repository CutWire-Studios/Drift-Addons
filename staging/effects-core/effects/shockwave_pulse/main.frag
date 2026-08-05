#version 330 core
in vec2 v_texCoord; out vec4 fragColor;
uniform sampler2D u_currentTexture; uniform vec2 u_resolution; uniform float u_time;
uniform float centerX; uniform float centerY; uniform float radius;
uniform float width; uniform float strength; uniform float speed;
float envelope(float nd, float wr, float w) {
    float delta = abs(nd - wr);
    float halfW = max(w * 0.5, 1e-6);
    if (delta >= halfW) return 0.0;
    float t = 1.0 - delta / halfW;
    return t * t * (3.0 - 2.0 * t);
}
void main() {
    vec2 res = u_resolution;
    vec2 pos = v_texCoord * res;
    vec2 c = vec2(centerX, centerY) * (res - 1.0);
    vec2 d = pos - c;
    float dist = length(d);
    if (dist < 1e-3 || strength <= 0.0) { fragColor = texture(u_currentTexture, v_texCoord); return; }
    float maxR = max(length(c), 1.0);
    float wr = (speed > 0.0) ? fract(u_time * speed + radius) : radius;
    float env = envelope(dist / maxR, wr, width);
    float maxDisp = strength * min(res.x, res.y) * 0.25;
    vec2 n = d / dist;
    vec2 src = clamp((pos - n * env * maxDisp) / res, 0.0, 1.0);
    fragColor = texture(u_currentTexture, src);
}
