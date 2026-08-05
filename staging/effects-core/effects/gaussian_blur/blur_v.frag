#version 330 core
in vec2 v_texCoord;
out vec4 fragColor;
uniform sampler2D u_currentTexture;
uniform float u_blurRadius;
uniform vec2 u_resolution;

// Input is already premultiplied by blur_h, so tap it as-is and un-premultiply on output.
void main() {
    vec2 tex_offset = vec2(0.0, 1.0 / u_resolution.y);
    vec4 result = texture(u_currentTexture, v_texCoord) * 0.2270270270;

    result += texture(u_currentTexture, v_texCoord + tex_offset * u_blurRadius * 1.3846153846) * 0.3162162162;
    result += texture(u_currentTexture, v_texCoord - tex_offset * u_blurRadius * 1.3846153846) * 0.3162162162;
    result += texture(u_currentTexture, v_texCoord + tex_offset * u_blurRadius * 3.2307692308) * 0.0702702703;
    result += texture(u_currentTexture, v_texCoord - tex_offset * u_blurRadius * 3.2307692308) * 0.0702702703;

    fragColor = vec4(result.rgb / max(result.a, 1e-4), result.a);
}
