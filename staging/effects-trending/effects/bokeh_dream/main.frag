#version 330 core
in vec2 v_texCoord; out vec4 fragColor;
uniform sampler2D u_currentTexture; uniform vec2 u_resolution;
uniform float intensity; uniform float radius; uniform float threshold; uniform float softness;

const int kSamples = 16;

void main() {
    vec4 src = texture(u_currentTexture, v_texCoord);
    if (intensity <= 1e-5) {
        fragColor = src;
        return;
    }

    float r = clamp(radius, 1.0, 24.0);
    vec2 px = 1.0 / u_resolution;
    vec3 acc = vec3(0.0);
    float wsum = 0.0;

    for (int i = 0; i < kSamples; ++i) {
        float ang = 6.2831853 * (float(i) / float(kSamples));
        float ring = float((i % 4) + 1) / 4.0;
        vec2 off = vec2(cos(ang), sin(ang)) * r * ring * px;
        vec3 s = texture(u_currentTexture, clamp(v_texCoord + off, 0.0, 1.0)).rgb;
        float lum = dot(s, vec3(0.2126, 0.7152, 0.0722));
        float w = smoothstep(threshold, threshold + mix(0.05, 0.35, softness), lum);
        w *= 1.0 - ring * 0.15;
        acc += s * w;
        wsum += w;
    }

    vec3 bokeh = acc / max(wsum, 1e-4);
    vec3 outc = mix(src.rgb, bokeh, clamp(intensity, 0.0, 1.0));
    fragColor = vec4(clamp(outc, 0.0, 1.0), src.a);
}
