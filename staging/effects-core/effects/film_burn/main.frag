#version 330 core
in vec2 v_texCoord; out vec4 fragColor;
uniform sampler2D u_currentTexture; uniform vec2 u_resolution; uniform float u_timeUs;
uniform float intensity; uniform float warmth; uniform float flicker; uniform float seed; uniform float position;

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
    vec4 src = texture(u_currentTexture, v_texCoord);
    float mode = position;
    if (mode > 3.5) {
        uint hp = blockGlitchHash(seed, u_timeUs, 2, 4);
        mode = float(hp % 4u);
    }
    uint hf = blockGlitchHash(seed, u_timeUs, 5, 9);
    float flickerMod = 1.0 - flicker + flicker * hash01(hf);
    vec3 leakColor = vec3(1.0, (100.0 + warmth * 155.0) / 255.0, (15.0 + warmth * 120.0) / 255.0);
    float nx = v_texCoord.x;
    float ny = v_texCoord.y;
    float gradient = 0.0;
    vec2 blobC = vec2(0.5);
    if (mode < 0.5) { gradient = pow(1.0 - nx, 1.7); blobC = vec2(0.05, 0.5); }
    else if (mode < 1.5) { gradient = pow(nx, 1.7); blobC = vec2(0.95, 0.5); }
    else if (mode < 2.5) { gradient = pow(1.0 - ny, 1.7); blobC = vec2(0.5, 0.05); }
    else { gradient = pow(ny, 1.7); blobC = vec2(0.5, 0.95); }
    float blob = max(0.0, 1.0 - distance(v_texCoord, blobC) / 0.75);
    ivec2 pix = ivec2(v_texCoord * u_resolution);
    uint hn = blockGlitchHash(seed, u_timeUs, pix.x, pix.y);
    float n = 0.65 + 0.35 * float(hn & 0xFFu) / 255.0;
    float leak = clamp(max(gradient, blob * 0.85) * n * flickerMod * intensity, 0.0, 1.0);
    fragColor = vec4(clamp(src.rgb + leakColor * leak, 0.0, 1.0), src.a);
}
