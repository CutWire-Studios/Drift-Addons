#version 330 core
in vec2 v_texCoord; out vec4 fragColor;
uniform sampler2D u_currentTexture; uniform vec2 u_resolution;
uniform float strength; uniform float radius;

void main() {
    vec4 src = texture(u_currentTexture, v_texCoord);
    float s = clamp(strength, 0.0, 1.0);
    if (s <= 1e-5) {
        fragColor = src;
        return;
    }

    int r = int(clamp(floor(radius + 0.5), 1.0, 8.0));
    vec2 px = 1.0 / u_resolution;
    vec3 mean = vec3(0.0);
    vec3 m2 = vec3(0.0);
    float count = 0.0;

    for (int y = -8; y <= 8; ++y) {
        for (int x = -8; x <= 8; ++x) {
            if (abs(x) > r || abs(y) > r)
                continue;
            vec3 c = texture(u_currentTexture, v_texCoord + vec2(float(x), float(y)) * px).rgb;
            mean += c;
            m2 += c * c;
            count += 1.0;
        }
    }
    mean /= count;
    vec3 var = max(m2 / count - mean * mean, vec3(0.0));
    float lum = dot(mean, vec3(0.2126, 0.7152, 0.0722));
    vec3 flat = mean / max(lum, 1e-4) * dot(src.rgb, vec3(0.2126, 0.7152, 0.0722));
    float w = 1.0 / (1.0 + dot(var, vec3(1.0)));
    vec3 painted = mix(mean, flat, w);
    fragColor = vec4(mix(src.rgb, painted, s), src.a);
}
