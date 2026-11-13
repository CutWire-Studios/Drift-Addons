#version 330 core
in vec2 v_texCoord; out vec4 fragColor;
uniform sampler2D u_currentTexture;
uniform float echoes; uniform float spacing; uniform float decay;

void main() {
    vec4 src = texture(u_currentTexture, v_texCoord);
    vec4 r = vec4(src.rgb * src.a, src.a);
    float w = 1.0;
    for (int i = 1; i <= 8; ++i) {
        if (float(i) > echoes)
            break;
        w *= decay;
        vec4 e = historyFrame(float(i) * spacing, v_texCoord);
        r = max(r, vec4(e.rgb * e.a, e.a) * w);
    }
    fragColor = vec4(r.rgb / max(r.a, 0.0001), r.a);
}
