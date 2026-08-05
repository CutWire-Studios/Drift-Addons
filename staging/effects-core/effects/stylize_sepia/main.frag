#version 330 core
in vec2 v_texCoord; out vec4 fragColor;
uniform sampler2D u_currentTexture;
void main() {
    vec4 c = texture(u_currentTexture, v_texCoord);
    mat3 m = mat3(0.393,0.349,0.272, 0.769,0.686,0.534, 0.189,0.168,0.131);
    fragColor = vec4(clamp(m * c.rgb, 0.0, 1.0), c.a);
}
