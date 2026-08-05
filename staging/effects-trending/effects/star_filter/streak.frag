#version 330 core
in vec2 v_texCoord; out vec4 fragColor;
uniform sampler2D u_currentTexture; // bright pass
uniform sampler2D u_texture1;       // original
uniform vec2 u_resolution;
uniform float intensity; uniform float spikeLength; uniform float points;
uniform float rotation; uniform float rainbow;

vec3 hsv2rgb(vec3 c) {
    vec3 p = abs(fract(c.xxx + vec3(1.0, 2.0 / 3.0, 1.0 / 3.0)) * 6.0 - 3.0);
    return c.z * mix(vec3(1.0), clamp(p - 1.0, 0.0, 1.0), c.y);
}

const int kSteps = 24;

void main() {
    vec4 src = texture(u_texture1, v_texCoord);
    if (intensity <= 1e-5) {
        fragColor = src;
        return;
    }

    // A cross-screen filter smears each highlight outward along fixed axes, so this is a
    // directional gather over the bright pass rather than a drawn sprite.
    int arms = int(clamp(floor(points + 0.5), 2.0, 6.0));
    float lenPx = mix(20.0, 320.0, clamp(spikeLength, 0.0, 1.0));
    float rot = rotation * 6.2831853;

    vec3 acc = vec3(0.0);
    float wsum = 0.0;
    for (int a = 0; a < 6; ++a) {
        if (a >= arms)
            break;
        float ang = rot + float(a) * 6.2831853 / float(arms);
        vec2 dir = vec2(cos(ang), sin(ang));
        for (int s = 1; s <= kSteps; ++s) {
            float t = float(s) / float(kSteps);
            float w = (1.0 - t) * (1.0 - t);
            vec2 uv = v_texCoord + dir * (t * lenPx) / u_resolution;
            vec3 c = texture(u_currentTexture, clamp(uv, 0.0, 1.0)).rgb;
            // Real diffraction spikes disperse along their length; hue ramps with distance.
            vec3 tint = mix(vec3(1.0), hsv2rgb(vec3(fract(t * 0.8 + float(a) * 0.13), 0.8, 1.0)),
                            clamp(rainbow, 0.0, 1.0));
            acc += c * tint * w;
            wsum += w;
        }
    }

    vec3 streak = acc / max(wsum, 1e-4) * float(arms) * intensity;
    streak = clamp(streak, 0.0, 1.0);
    vec3 outc = 1.0 - (1.0 - clamp(src.rgb, 0.0, 1.0)) * (1.0 - streak);
    fragColor = vec4(outc, src.a);
}
