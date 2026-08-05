#version 330 core
in vec2 v_texCoord; out vec4 fragColor;
uniform sampler2D u_currentTexture; // blurred
uniform sampler2D u_texture1;       // original
uniform vec2 u_resolution; uniform float blurRadius; uniform float intensity;
void main() {
    float r = max(blurRadius, 0.0);
    vec2 off = vec2(0.0, 1.0 / u_resolution.y);
    vec4 blur = texture(u_currentTexture, v_texCoord) * 0.2270270270;
    blur += texture(u_currentTexture, v_texCoord + off * r * 1.3846153846) * 0.3162162162;
    blur += texture(u_currentTexture, v_texCoord - off * r * 1.3846153846) * 0.3162162162;
    blur += texture(u_currentTexture, v_texCoord + off * r * 3.2307692308) * 0.0702702703;
    blur += texture(u_currentTexture, v_texCoord - off * r * 3.2307692308) * 0.0702702703;
    vec4 src = texture(u_texture1, v_texCoord);
    fragColor = vec4(clamp(src.rgb + blur.rgb * clamp(intensity, 0.0, 2.0), 0.0, 1.0), src.a);
}
