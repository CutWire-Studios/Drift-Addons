#version 330 core
in vec2 v_texCoord; out vec4 fragColor;
uniform sampler2D u_currentTexture;
uniform float rr; uniform float rg; uniform float rb;
uniform float gr; uniform float gg; uniform float gb;
uniform float br; uniform float bg; uniform float bb;
void main() {
    vec4 c = texture(u_currentTexture, v_texCoord);
    mat3 m = mat3(rr, gr, br, rg, gg, bg, rb, gb, bb);
    fragColor = vec4(clamp(m * c.rgb, 0.0, 1.0), c.a);
}
