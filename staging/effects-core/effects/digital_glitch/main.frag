#version 330 core
in vec2 v_texCoord; out vec4 fragColor;
uniform sampler2D u_currentTexture; uniform vec2 u_resolution; uniform float u_timeUs;
uniform float intensity; uniform float frequency; uniform float rgbAmount;
uniform float blockAmount; uniform float flashAmount; uniform float seed;

uint hashMix(uint v) {
    v ^= v >> 16u; v *= 0x7feb352du; v ^= v >> 15u; v *= 0x846ca68bu; v ^= v >> 16u; return v;
}
uint blockGlitchHash(float seed, float timeUs, int bx, int by) {
    uint t = uint(abs(timeUs));
    uint h = uint(abs(seed)) ^ t ^ (t >> 16u);
    h = hashMix(h + uint(bx) * 374761393u);
    h = hashMix(h + uint(by) * 668265263u);
    return h;
}
float hash01(uint h) { return float(h & 0xFFFFu) / 65535.0; }
float hash01h(uint h) { return float((h >> 16u) & 0xFFFFu) / 65535.0; }

void main() {
    if (intensity <= 1e-5) {
        fragColor = texture(u_currentTexture, v_texCoord);
        return;
    }
    vec2 res = u_resolution;
    ivec2 pix = ivec2(v_texCoord * res);
    float block = 24.0;
    int bcol = int(floor(float(pix.x) / block));
    int brow = int(floor(float(pix.y) / block));
    uint hb = blockGlitchHash(seed, u_timeUs, bcol, brow);
    float sx = float(pix.x);
    if (hash01(hb) <= frequency) {
        float shift = (hash01h(hb) * 2.0 - 1.0) * 40.0 * intensity * blockAmount * intensity;
        sx = clamp(sx - shift, 0.0, res.x - 1.0);
    }
    uint hs = blockGlitchHash(seed, u_timeUs, pix.y, 1);
    float j = frequency * intensity * 0.75;
    float hOff = (hash01(hs) * 2.0 - 1.0) * j * 40.0;
    sx = clamp(sx - hOff, 0.0, res.x - 1.0);
    float sy = float(pix.y);
    uint ha = blockGlitchHash(seed, u_timeUs, 3, 3);
    float ang = hash01(ha) * 6.2831853;
    vec2 delta = vec2(cos(ang), sin(ang)) * rgbAmount * intensity;
    float r = texture(u_currentTexture, clamp(vec2(sx + delta.x, sy + delta.y) / res, 0.0, 1.0)).r;
    float g = texture(u_currentTexture, clamp(vec2(sx, sy) / res, 0.0, 1.0)).g;
    float b = texture(u_currentTexture, clamp(vec2(sx - delta.x, sy - delta.y) / res, 0.0, 1.0)).b;
    vec3 rgb = vec3(r, g, b);
    uint hn = blockGlitchHash(seed, u_timeUs, pix.x, pix.y);
    float n = float(hn & 0xFFu) / 127.5 - 1.0;
    float amp = frequency * intensity * 0.5 * 36.0 / 255.0;
    rgb += vec3(n * amp, n * amp * 0.92, n * amp * 0.85);
    uint hf = blockGlitchHash(seed, u_timeUs, 7, 3);
    if (hash01(hf) < flashAmount * intensity) {
        float flash = hash01h(hf) * flashAmount * intensity;
        rgb += (vec3(1.0) - rgb) * flash;
    }
    uint hj = blockGlitchHash(seed, u_timeUs, 11, 5);
    if (hash01(hj) < frequency * 0.2) {
        float jumpY = hash01h(hj) * 14.0 - 7.0;
        sy = clamp(sy - jumpY, 0.0, res.y - 1.0);
        rgb = texture(u_currentTexture, vec2(sx, sy) / res).rgb;
    }
    fragColor = vec4(clamp(rgb, 0.0, 1.0), 1.0);
}
