#version 330 core
in vec2 v_texCoord; out vec4 fragColor;
uniform sampler2D u_currentTexture; // bright mask (rgb = highlight colour, a = mask)
uniform sampler2D u_texture1;       // original
uniform vec2 u_resolution; uniform float u_time;
uniform float intensity; uniform float density; uniform float size;
uniform float twinkleSpeed; uniform float points; uniform float colorize;

float hash21(vec2 p) { return fract(sin(dot(p, vec2(127.1, 311.7))) * 43758.5453123); }

void main() {
    vec4 src = texture(u_texture1, v_texCoord);
    if (intensity <= 1e-5) {
        fragColor = src;
        return;
    }

    // One candidate star per cell, jittered inside it: a uniform grid would read as a screen door.
    float cell = mix(140.0, 34.0, clamp(density, 0.0, 1.0));
    float radius = cell * mix(0.35, 1.1, clamp(size, 0.0, 1.0));
    float thick = max(radius * 0.045, 0.75);
    int lines = int(clamp(floor(points * 0.5), 2.0, 4.0));

    vec2 pix = v_texCoord * u_resolution;
    vec2 base = floor(pix / cell);
    vec3 glow = vec3(0.0);

    // 3x3 because a star's arms reach past its own cell.
    for (int dy = -1; dy <= 1; ++dy) {
        for (int dx = -1; dx <= 1; ++dx) {
            vec2 cellId = base + vec2(float(dx), float(dy));
            float h1 = hash21(cellId);
            float h2 = hash21(cellId + vec2(17.3, 5.9));
            float h3 = hash21(cellId + vec2(41.7, 23.1));
            vec2 center = (cellId + vec2(h1, h2)) * cell;
            vec2 uv = center / u_resolution;
            if (uv.x < 0.0 || uv.x > 1.0 || uv.y < 0.0 || uv.y > 1.0)
                continue;
            vec4 b = texture(u_currentTexture, uv);
            if (b.a <= 0.01)
                continue;

            float phase = h3 * 6.2831853;
            float tw = max(sin(u_time * twinkleSpeed * 3.0 + phase), 0.0);
            tw = tw * tw * tw; // most of the cycle dark, brief pop — reads as a glint, not a pulse
            if (tw <= 0.001)
                continue;

            vec2 d = pix - center;
            float r = radius * (0.6 + 0.4 * h1);
            float rot = phase * 0.25;
            float star = 0.0;
            for (int i = 0; i < 4; ++i) {
                if (i >= lines)
                    break;
                float a = rot + float(i) * 3.14159265 / float(lines);
                float ca = cos(a);
                float sa = sin(a);
                vec2 q = vec2(d.x * ca + d.y * sa, -d.x * sa + d.y * ca);
                star += max(1.0 - abs(q.y) / thick, 0.0)
                        * pow(max(1.0 - abs(q.x) / r, 0.0), 1.6);
            }
            star += pow(max(1.0 - length(d) / (thick * 3.0), 0.0), 2.0) * 1.5;

            vec3 tint = b.rgb / max(max(b.r, max(b.g, b.b)), 1e-4);
            tint = mix(vec3(1.0), tint, clamp(colorize, 0.0, 1.0));
            glow += tint * star * tw * b.a;
        }
    }

    glow = clamp(glow * intensity * 1.4, 0.0, 1.0);
    vec3 outc = 1.0 - (1.0 - clamp(src.rgb, 0.0, 1.0)) * (1.0 - glow);
    fragColor = vec4(outc, src.a);
}
