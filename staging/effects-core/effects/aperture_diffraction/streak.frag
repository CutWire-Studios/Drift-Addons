#version 330 core
in vec2 v_texCoord; out vec4 fragColor;
uniform sampler2D u_currentTexture; // bright
uniform sampler2D u_texture1;       // original
uniform vec2 u_resolution;
uniform float intensity; uniform float bladeCount; uniform float spikeLength;
uniform float rotation; uniform float dispersion;
void main() {
    vec4 src = texture(u_texture1, v_texCoord);
    int blades = int(clamp(floor(bladeCount + 0.5), 4.0, 10.0));
    float baseAng = rotation * 3.14159265;
    vec2 px = 1.0 / u_resolution;
    vec3 spikes = vec3(0.0);
    for (int b = 0; b < 10; ++b) {
        if (b >= blades) break;
        float ang = baseAng + float(b) * 3.14159265 / float(blades);
        vec2 dir = vec2(cos(ang), sin(ang));
        for (int s = 1; s <= 18; ++s) {
            float t = float(s) / 18.0;
            float w = (1.0 - t) * (1.0 - t);
            vec2 o = dir * px * (t * spikeLength * 120.0);
            vec3 samp = texture(u_currentTexture, clamp(v_texCoord + o, 0.0, 1.0)).rgb;
            float hue = float(b) / float(blades) + t * dispersion * 0.35;
            vec3 tint = 0.65 + 0.35 * vec3(
                0.5 + 0.5 * cos(6.2831 * (hue + 0.0)),
                0.5 + 0.5 * cos(6.2831 * (hue + 0.33)),
                0.5 + 0.5 * cos(6.2831 * (hue + 0.67)));
            spikes += samp * w * mix(vec3(1.0), tint, dispersion);
        }
    }
    fragColor = vec4(src.rgb + spikes * intensity * 0.12, src.a);
}
