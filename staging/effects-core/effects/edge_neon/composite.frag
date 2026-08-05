#version 330 core
in vec2 v_texCoord; out vec4 fragColor;
uniform sampler2D u_currentTexture; // blurred mask
uniform sampler2D u_texture1;       // original
uniform float intensity; uniform vec3 color; uniform float radius;
void main() {
    float amt = clamp(intensity, 0.0, 2.0);
    vec4 src = texture(u_texture1, v_texCoord);
    if (amt <= 1e-5) {
        fragColor = src;
        return;
    }
    float glow = texture(u_currentTexture, v_texCoord).r * amt;
    fragColor = vec4(clamp(src.rgb + color * glow, 0.0, 1.0), src.a);
}
