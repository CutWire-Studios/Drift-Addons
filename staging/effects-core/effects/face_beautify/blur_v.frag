#version 330 core
in vec2 v_texCoord; out vec4 fragColor;
uniform sampler2D u_currentTexture; uniform vec2 u_resolution;
uniform float u_faceRx;
uniform float amount;

// Vertical half of the separable edge-aware blur. See blur_h.frag for the reasoning.
//
// The aspect correction matters here and not in the horizontal pass: the radius is measured in
// width-normalized units, so a vertical step of the same uv length covers a different number of
// pixels unless it is divided back out.
void main() {
    float aspect = u_resolution.y / u_resolution.x;
    float radius = max(u_faceRx * mix(0.035, 0.11, amount), 1e-5);
    float step = radius / 4.0 / max(aspect, 1e-5);
    vec3 centre = texture(u_currentTexture, v_texCoord).rgb;
    float cl = dot(centre, vec3(0.2126, 0.7152, 0.0722));

    vec3 sum = vec3(0.0);
    float wsum = 0.0;
    for (int i = -4; i <= 4; i++) {
        vec2 uv = v_texCoord + vec2(0.0, float(i) * step);
        vec3 s = texture(u_currentTexture, clamp(uv, 0.0, 1.0)).rgb;
        float sl = dot(s, vec3(0.2126, 0.7152, 0.0722));
        float spatial = exp(-float(i * i) / 8.0);
        float range = exp(-(sl - cl) * (sl - cl) / 0.012);
        float w = spatial * range;
        sum += s * w;
        wsum += w;
    }
    fragColor = vec4(sum / max(wsum, 1e-5), 1.0);
}
