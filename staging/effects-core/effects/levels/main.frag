#version 330 core
in vec2 v_texCoord; out vec4 fragColor;
uniform sampler2D u_currentTexture;
uniform float inBlack; uniform float inWhite; uniform float gamma;
uniform float outBlack; uniform float outWhite;
void main() {
    vec4 c = texture(u_currentTexture, v_texCoord);
    float ib = inBlack;
    float iw = max(inWhite, ib + 1e-4);
    vec3 x = clamp((c.rgb - ib) / (iw - ib), 0.0, 1.0);
    x = pow(x, vec3(1.0 / max(gamma, 1e-4)));
    fragColor = vec4(mix(vec3(outBlack), vec3(outWhite), x), c.a);
}
