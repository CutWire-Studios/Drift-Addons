#version 330 core
in vec2 v_texCoord; out vec4 fragColor;
uniform sampler2D u_currentTexture;
uniform float strength; uniform float teal; uniform float orange; uniform float contrast;

vec3 filmic(vec3 x) {
    return clamp((x * (2.51 * x + 0.03)) / (x * (2.43 * x + 0.59) + 0.14), 0.0, 1.0);
}

void main() {
    vec4 src = texture(u_currentTexture, v_texCoord);
    float s = clamp(strength, 0.0, 1.0);
    if (s <= 1e-5) {
        fragColor = src;
        return;
    }

    vec3 c = src.rgb;
    float lum = dot(c, vec3(0.2126, 0.7152, 0.0722));
    float sh = 1.0 - smoothstep(0.0, 0.55, lum);
    float hi = smoothstep(0.45, 1.0, lum);
    c = mix(c, c * vec3(0.85, 0.95, 1.05), sh * teal);
    c = mix(c, c * vec3(1.08, 0.98, 0.88), hi * orange);
    c = mix(vec3(0.5), c, 1.0 + contrast * 0.35);
    c = filmic(c);
    fragColor = vec4(mix(src.rgb, c, s), src.a);
}
