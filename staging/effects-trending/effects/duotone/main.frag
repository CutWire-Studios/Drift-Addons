#version 330 core
in vec2 v_texCoord; out vec4 fragColor;
uniform sampler2D u_currentTexture;
uniform float strength; uniform vec3 shadowColor; uniform vec3 highlightColor; uniform float contrast;

void main() {
    vec4 src = texture(u_currentTexture, v_texCoord);
    float s = clamp(strength, 0.0, 1.0);
    if (s <= 1e-5) {
        fragColor = src;
        return;
    }

    float lum = dot(src.rgb, vec3(0.2126, 0.7152, 0.0722));
    float c = mix(lum, smoothstep(0.0, 1.0, lum), clamp(contrast, 0.0, 1.0) * 2.0);
    vec3 duo = mix(shadowColor, highlightColor, c);
    fragColor = vec4(mix(src.rgb, duo, s), src.a);
}
