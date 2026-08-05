#version 330 core
in vec2 v_texCoord; out vec4 fragColor;
uniform sampler2D u_currentTexture; uniform vec2 u_resolution; uniform float u_timeUs;
uniform float jitter; uniform float lineStrength; uniform float colorShift; uniform float speed;

uint hashMix(uint v) {
    v ^= v >> 16u; v *= 0x7feb352du; v ^= v >> 15u; v *= 0x846ca68bu; v ^= v >> 16u; return v;
}
uint blockGlitchHash(float seed, float timeUs, int col, int row) {
    uint t = uint(abs(timeUs));
    uint h = uint(abs(seed)) ^ t ^ (t >> 16u);
    h = hashMix(h + uint(col) * 374761393u);
    h = hashMix(h + uint(row) * 668265263u);
    return h;
}
float hash01(uint h) { return float(h & 0xFFFFu) / 65535.0; }
float hash01h(uint h) { return float((h >> 16u) & 0xFFFFu) / 65535.0; }

void main() {
    vec2 res = u_resolution;
    int y = int(v_texCoord.y * res.y);
    float animatedTime = u_timeUs * max(speed, 0.001);
    uint h = blockGlitchHash(-1.0, animatedTime, y, 1);
    float jitterNorm = hash01(h);
    float tearNorm = float((h >> 8u) & 0xFFFFu) / 65535.0;
    int sourceY = y;
    if (tearNorm < jitter * 0.2)
        sourceY = clamp(y + int((tearNorm * 2.0 - 0.5) * jitter * 6.0), 0, int(res.y) - 1);
    float maxJitterPx = jitter * 40.0;
    float hOff = (jitterNorm * 2.0 - 1.0) * maxJitterPx;
    float sx = clamp(v_texCoord.x * res.x - hOff, 0.0, res.x - 1.0);
    float sy = float(sourceY);
    vec3 col;
    if (colorShift > 0.0) {
        float r = texture(u_currentTexture, vec2(clamp(sx + colorShift, 0.0, res.x-1.0), sy) / res).r;
        float g = texture(u_currentTexture, vec2(sx, sy) / res).g;
        float b = texture(u_currentTexture, vec2(clamp(sx - colorShift, 0.0, res.x-1.0), sy) / res).b;
        col = vec3(r,g,b);
    } else {
        col = texture(u_currentTexture, vec2(sx, sy) / res).rgb;
    }
    if ((y & 1) == 0) col *= (1.0 - lineStrength * 0.55);
    fragColor = vec4(col, 1.0);
}
