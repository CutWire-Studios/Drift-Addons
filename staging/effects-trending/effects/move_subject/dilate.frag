#version 330 core
in vec2 v_texCoord;
out vec4 fragColor;

uniform sampler2D u_currentTexture;
uniform vec2 u_resolution;

void main() {
    vec2 uv = v_texCoord;
    vec2 t = 1.0 / u_resolution;
    float px = max(6.0, 0.03 * u_resolution.y);
    float d = driftMask(uv);
    for (int r = 1; r <= 4; ++r) {
        float rad = px * float(r) / 4.0;
        float wt = r == 1 ? 1.0 : (r == 2 ? 0.9 : (r == 3 ? 0.65 : 0.35));
        for (int i = 0; i < 12; ++i) {
            float a = float(i) * 0.5235988;
            d = max(d, driftMask(uv + vec2(cos(a), sin(a)) * t * rad) * wt);
        }
    }
    fragColor = vec4(smoothstep(0.1, 0.9, d), 0.0, 0.0, 1.0);
}
