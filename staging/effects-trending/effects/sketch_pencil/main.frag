#version 330 core
in vec2 v_texCoord; out vec4 fragColor;
uniform sampler2D u_currentTexture; uniform vec2 u_resolution;
uniform float strength; uniform float detail; uniform float contrast;

float lum(vec3 c) { return dot(c, vec3(0.2126, 0.7152, 0.0722)); }

void main() {
    vec4 src = texture(u_currentTexture, v_texCoord);
    float s = clamp(strength, 0.0, 1.0);
    if (s <= 1e-5) {
        fragColor = src;
        return;
    }

    vec2 px = 1.0 / u_resolution;
    float r = mix(1.0, 3.0, clamp(detail, 0.0, 1.0));
    vec3 c = src.rgb;
    vec3 blur = vec3(0.0);
    float n = 0.0;
    for (int x = -2; x <= 2; ++x) {
        for (int y = -2; y <= 2; ++y) {
            blur += texture(u_currentTexture, v_texCoord + vec2(float(x), float(y)) * px * r).rgb;
            n += 1.0;
        }
    }
    blur /= n;
    float dodge = clamp(1.0 - lum(blur), 0.0, 1.0);

    float tl = lum(texture(u_currentTexture, v_texCoord + vec2(-px.x, -px.y) * 2.0).rgb);
    float tr = lum(texture(u_currentTexture, v_texCoord + vec2(px.x, -px.y) * 2.0).rgb);
    float bl = lum(texture(u_currentTexture, v_texCoord + vec2(-px.x, px.y) * 2.0).rgb);
    float br = lum(texture(u_currentTexture, v_texCoord + vec2(px.x, px.y) * 2.0).rgb);
    float edge = abs(tl - br) + abs(tr - bl);

    float ink = clamp(dodge + edge * mix(1.0, 3.0, contrast), 0.0, 1.0);
    vec3 paper = vec3(0.95);
    vec3 sketch = mix(paper, vec3(0.08), 1.0 - ink);
    fragColor = vec4(mix(src.rgb, sketch, s), src.a);
}
