#version 330 core
in vec2 v_texCoord; out vec4 fragColor;
uniform sampler2D u_currentTexture;
uniform float flash; uniform float tint;

void main() {
    vec4 src = texture(u_currentTexture, v_texCoord);
    float f = clamp(flash, 0.0, 1.0);
    if (f <= 1e-5) {
        fragColor = src;
        return;
    }
    vec3 lift = mix(vec3(1.0), vec3(1.0, 0.95, 0.85), clamp(tint, 0.0, 1.0));
    vec3 outc = mix(src.rgb, lift, f);
    outc = clamp(outc + vec3(f * 0.35), 0.0, 1.0);
    fragColor = vec4(outc, src.a);
}
