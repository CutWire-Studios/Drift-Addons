#version 330 core
in vec2 v_texCoord; out vec4 fragColor;
uniform sampler2D u_currentTexture; uniform vec2 u_resolution; uniform float u_timeUs;
uniform float intensity; uniform float grain; uniform float scratches; uniform float weave; uniform float flicker;

uint hashMix(uint v) {
    v ^= v >> 16u; v *= 0x7feb352du; v ^= v >> 15u; v *= 0x846ca68bu; v ^= v >> 16u; return v;
}
float hash01(uint h) { return float(h & 0xFFFFu) / 65535.0; }

void main() {
    vec4 src = texture(u_currentTexture, v_texCoord);
    float amt = clamp(intensity, 0.0, 1.0);
    if (amt <= 1e-5) {
        fragColor = src;
        return;
    }

    uint frame = uint(u_timeUs / 33333.0);
    float flick = 1.0 - flicker * (hash01(hashMix(frame * 17u)) * 0.5);
    vec2 uv = v_texCoord;
    float wob = weave * 0.01;
    uv.x += sin(float(frame) * 0.31) * wob;
    uv.y += cos(float(frame) * 0.27) * wob;
    vec3 c = texture(u_currentTexture, clamp(uv, 0.0, 1.0)).rgb * flick;

    ivec2 pix = ivec2(v_texCoord * u_resolution);
    uint hg = hashMix(frame ^ uint(pix.x) * 374761393u ^ uint(pix.y) * 668265263u);
    c += (hash01(hg) * 2.0 - 1.0) * grain * 0.08;

    float scratchLine = hash01(hashMix(frame * 41u + uint(pix.x / 3)));
    if (scratches > 0.01 && scratchLine > 1.0 - scratches * 0.02)
        c *= 0.85;

    uint hd = hashMix(frame * 97u + uint(pix.y * 13 + pix.x));
    if (hash01(hd) > 0.998 - scratches * 0.003)
        c = mix(c, vec3(0.9), 0.6);

    vec3 warm = mix(src.rgb, c, amt);
    fragColor = vec4(clamp(warm, 0.0, 1.0), src.a);
}
