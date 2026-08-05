#version 330 core
in vec2 v_texCoord; out vec4 fragColor;
uniform sampler2D u_currentTexture; // bright
uniform sampler2D u_texture1;       // original
uniform float intensity; uniform float rayLength; uniform float centerX;
uniform float centerY; uniform float samples;
void main() {
    vec4 src = texture(u_texture1, v_texCoord);
    vec2 c = vec2(centerX, centerY);
    vec2 d = v_texCoord - c;
    int n = int(clamp(floor(samples + 0.5), 6.0, 32.0));
    vec3 acc = vec3(0.0);
    float wsum = 0.0;
    for (int i = 0; i < 32; ++i) {
        if (i >= n) break;
        float t = float(i) / float(n - 1);
        float w = 1.0 - t;
        vec2 uv = clamp(c + d * (1.0 - t * rayLength), 0.0, 1.0);
        acc += texture(u_currentTexture, uv).rgb * w;
        wsum += w;
    }
    vec3 rays = acc / max(wsum, 1e-4);
    fragColor = vec4(src.rgb + rays * intensity, src.a);
}
