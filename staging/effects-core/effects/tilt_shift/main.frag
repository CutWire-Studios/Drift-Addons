#version 330 core
in vec2 v_texCoord; out vec4 fragColor;
uniform sampler2D u_currentTexture; uniform vec2 u_resolution;
uniform float blur; uniform float focus; uniform float range;
uniform float softness; uniform float samples;
void main() {
    float dist = abs(v_texCoord.y - focus);
    float m = smoothstep(range, range + softness, dist);
    float amt = m * blur;
    if (amt <= 1e-5) { fragColor = texture(u_currentTexture, v_texCoord); return; }
    vec2 px = 1.0 / u_resolution;
    int n = int(clamp(floor(samples + 0.5), 4.0, 20.0));
    vec3 acc = vec3(0.0);
    float wsum = 0.0;
    float rad = amt * 12.0;
    for (int i = 0; i < 20; ++i) {
        if (i >= n) break;
        float t = (float(i) / float(n - 1) - 0.5) * 2.0;
        float w = exp(-t * t * 2.0);
        acc += texture(u_currentTexture, clamp(v_texCoord + vec2(0.0, px.y * rad * t), 0.0, 1.0)).rgb * w;
        wsum += w;
    }
    // mild horizontal pass contribution
    for (int i = 0; i < 20; ++i) {
        if (i >= n) break;
        float t = (float(i) / float(n - 1) - 0.5) * 2.0;
        float w = exp(-t * t * 2.0) * 0.65;
        acc += texture(u_currentTexture, clamp(v_texCoord + vec2(px.x * rad * t * 0.6, 0.0), 0.0, 1.0)).rgb * w;
        wsum += w;
    }
    fragColor = vec4(acc / max(wsum, 1e-4), texture(u_currentTexture, v_texCoord).a);
}
