#version 330 core
in vec2 v_texCoord; out vec4 fragColor;
uniform sampler2D u_currentTexture; uniform vec2 u_resolution; uniform float u_timeUs;
uniform float intensity; uniform float blockSize; uniform float shiftAmount;
uniform float frequency; uniform float seed;

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
    float block = clamp(blockSize, 4.0, 128.0);
    ivec2 pix = ivec2(v_texCoord * res);
    int col = int(floor(float(pix.x) / block));
    int row = int(floor(float(pix.y) / block));
    uint h = blockGlitchHash(seed, u_timeUs, col, row);
    if (hash01(h) > frequency) { fragColor = texture(u_currentTexture, v_texCoord); return; }
    float shiftNorm = hash01h(h);
    float shift = (shiftNorm * 2.0 - 1.0) * shiftAmount * intensity;
    vec2 uv = vec2(clamp((float(pix.x) - shift) / res.x, 0.0, 1.0), v_texCoord.y);
    fragColor = texture(u_currentTexture, uv);
}
