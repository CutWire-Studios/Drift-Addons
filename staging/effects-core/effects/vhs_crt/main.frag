#version 330 core
in vec2 v_texCoord; out vec4 fragColor;
uniform sampler2D u_currentTexture; uniform vec2 u_resolution; uniform float u_time; uniform float u_timeUs;
uniform float scanlines; uniform float noise; uniform float colorBleed;
uniform float distortion; uniform float vignette; uniform float desaturation;

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
    if (scanlines + noise + colorBleed + distortion + vignette + desaturation <= 1e-5) {
        fragColor = texture(u_currentTexture, v_texCoord);
        return;
    }
    vec2 res = u_resolution;
    float y = v_texCoord.y * res.y;
    float timePhase = u_time * 3.0;
    float rowWave = sin((y / res.y) * 24.0 + timePhase) * (distortion * 14.0);
    float baseX = clamp(v_texCoord.x * res.x + rowWave, 0.0, res.x - 1.0);
    float r = texture(u_currentTexture, vec2(clamp(baseX + colorBleed, 0.0, res.x-1.0), y) / res).r;
    float g = texture(u_currentTexture, vec2(baseX, y) / res).g;
    float b = texture(u_currentTexture, vec2(clamp(baseX - colorBleed, 0.0, res.x-1.0), y) / res).b;
    vec3 col = vec3(r,g,b);
    float lum = dot(col, vec3(0.299,0.587,0.114));
    col = mix(col, vec3(lum), desaturation);
    if ((int(y) & 1) == 0) col *= (1.0 - scanlines * 0.55);
    vec2 p = v_texCoord * 2.0 - 1.0;
    float vig = clamp(1.0 - vignette * dot(p,p) * 0.85, 0.0, 1.0);
    col *= vig;
    ivec2 pix = ivec2(v_texCoord * res);
    uint h = blockGlitchHash(1.0, u_timeUs, pix.x, pix.y);
    float n = float(h & 0xFFu) / 127.5 - 1.0;
    float amp = noise * 42.0 / 255.0;
    col += vec3(n*amp, n*amp*0.92, n*amp*0.85);
    fragColor = vec4(clamp(col, 0.0, 1.0), 1.0);
}
