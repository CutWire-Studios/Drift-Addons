#version 330 core
in vec2 v_texCoord; out vec4 fragColor;
uniform sampler2D u_currentTexture; // blurred bright
uniform sampler2D u_texture1;       // original
uniform float intensity;
uniform vec3 tint;
void main() {
    vec4 src = texture(u_texture1, v_texCoord);
    float amt = clamp(intensity, 0.0, 2.0);
    if (amt <= 1e-5) {
        fragColor = src;
        return;
    }
    vec3 glow = texture(u_currentTexture, v_texCoord).rgb * tint;
    // Premultiplied additive light: alpha rises to cover the glow, so rgb never exceeds a.
    vec3 rgb = clamp(src.rgb + glow * amt, 0.0, 1.0);
    fragColor = vec4(rgb, max(src.a, max(rgb.r, max(rgb.g, rgb.b))));
}
