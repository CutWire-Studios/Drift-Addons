#version 330 core
in vec2 v_texCoord; out vec4 fragColor;
uniform sampler2D u_currentTexture; // blurred halation
uniform sampler2D u_texture1;       // original
uniform float intensity; uniform float grain; uniform float u_timeUs;

uint hashMix(uint v) {
    v ^= v >> 16u; v *= 0x7feb352du; v ^= v >> 15u; v *= 0x846ca68bu; v ^= v >> 16u; return v;
}
float filmGrain(vec2 uv, float timeUs) {
    uint h = hashMix(uint(timeUs * 0.001) ^ uint(uv.x * 1920.0) ^ uint(uv.y * 1080.0) * 374761393u);
    return float(h & 0xFFu) / 127.5 - 1.0;
}

void main() {
    vec4 src = texture(u_texture1, v_texCoord);
    float amt = clamp(intensity, 0.0, 2.0);
    if (amt <= 1e-5 && grain <= 1e-5) {
        fragColor = src;
        return;
    }
    vec3 glow = texture(u_currentTexture, v_texCoord).rgb;
    vec3 outc = clamp(src.rgb + glow * amt, 0.0, 1.0);
    if (grain > 1e-5)
        outc += filmGrain(v_texCoord, u_timeUs) * grain * 0.07;
    fragColor = vec4(clamp(outc, 0.0, 1.0), src.a);
}
