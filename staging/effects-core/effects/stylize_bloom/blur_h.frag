#version 330 core
in vec2 v_texCoord; out vec4 fragColor;
uniform sampler2D u_currentTexture; uniform vec2 u_resolution; uniform float blurRadius;
void main() {
    float r = max(blurRadius, 0.0);
    vec2 off = vec2(1.0 / u_resolution.x, 0.0);
    vec4 result = texture(u_currentTexture, v_texCoord) * 0.2270270270;
    result += texture(u_currentTexture, v_texCoord + off * r * 1.3846153846) * 0.3162162162;
    result += texture(u_currentTexture, v_texCoord - off * r * 1.3846153846) * 0.3162162162;
    result += texture(u_currentTexture, v_texCoord + off * r * 3.2307692308) * 0.0702702703;
    result += texture(u_currentTexture, v_texCoord - off * r * 3.2307692308) * 0.0702702703;
    fragColor = result;
}
