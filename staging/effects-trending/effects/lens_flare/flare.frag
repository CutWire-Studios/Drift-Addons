#version 330 core
in vec2 v_texCoord; out vec4 fragColor;
uniform sampler2D u_currentTexture; // bright pass
uniform sampler2D u_texture1;       // original
uniform vec2 u_resolution;
uniform float intensity; uniform float centerX; uniform float centerY;
uniform float streak; uniform float ghosts; uniform float hue;

vec3 hsv2rgb(vec3 c) {
    vec3 p = abs(fract(c.xxx + vec3(1.0, 2.0 / 3.0, 1.0 / 3.0)) * 6.0 - 3.0);
    return c.z * mix(vec3(1.0), clamp(p - 1.0, 0.0, 1.0), c.y);
}

// Ghosts land on the line through the flare centre, on both sides and at several scales.
const float kGhostScale[4] = float[4](-0.4, -0.85, 0.55, 1.6);
const float kGhostWeight[4] = float[4](0.9, 0.5, 0.6, 0.3);

void main() {
    vec4 src = texture(u_texture1, v_texCoord);
    if (intensity <= 1e-5) {
        fragColor = src;
        return;
    }

    vec3 tint = hsv2rgb(vec3(fract(hue), 0.6, 1.0));

    // Anamorphic streak: a long horizontal gather of the bright pass. Horizontal only —
    // that asymmetry is what makes it read as a lens artifact rather than a glow.
    float lenPx = mix(40.0, 520.0, clamp(streak, 0.0, 1.0));
    vec3 acc = vec3(0.0);
    float wsum = 0.0;
    for (int s = -32; s <= 32; ++s) {
        float t = float(s) / 32.0;
        float w = 1.0 - abs(t);
        w = w * w;
        vec2 uv = v_texCoord + vec2(t * lenPx / u_resolution.x, 0.0);
        acc += texture(u_currentTexture, clamp(uv, 0.0, 1.0)).rgb * w;
        wsum += w;
    }
    vec3 flare = acc / max(wsum, 1e-4) * tint * 1.6;

    vec2 c = vec2(centerX, centerY);
    int ghostCount = int(clamp(floor(ghosts + 0.5), 0.0, 4.0));
    for (int i = 0; i < 4; ++i) {
        if (i >= ghostCount)
            break;
        vec2 guv = (v_texCoord - c) * kGhostScale[i] + c;
        // Clamped sampling would smear an edge texel across the whole ghost; drop it instead.
        if (guv.x < 0.0 || guv.x > 1.0 || guv.y < 0.0 || guv.y > 1.0)
            continue;
        vec3 g = texture(u_currentTexture, guv).rgb;
        vec3 gtint = hsv2rgb(vec3(fract(hue + float(i) * 0.11), 0.55, 1.0));
        // Fade with distance from the flare axis so ghosts sit as discs, not a wash.
        float fall = 1.0 - smoothstep(0.0, 0.9, distance(v_texCoord, c));
        flare += g * gtint * kGhostWeight[i] * fall;
    }

    flare = clamp(flare * intensity, 0.0, 1.0);
    vec3 outc = 1.0 - (1.0 - clamp(src.rgb, 0.0, 1.0)) * (1.0 - flare);
    fragColor = vec4(outc, src.a);
}
