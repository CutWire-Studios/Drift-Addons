#version 330 core
in vec2 v_texCoord; out vec4 fragColor;
uniform sampler2D u_currentTexture;
uniform float decay; uniform float blend;

void main() {
    vec4 src = texture(u_currentTexture, v_texCoord);
    vec4 prev = texture(u_prevOutput, v_texCoord);
    vec4 sp = vec4(src.rgb * src.a, src.a);
    vec4 pp = vec4(prev.rgb * prev.a, prev.a);
    vec4 r;
    if (blend > 1.5)
        r = vec4(mix(sp.rgb, pp.rgb, decay * pp.a), max(sp.a, pp.a * decay));
    else if (blend > 0.5)
        r = min(sp + pp * decay, 1.0);
    else
        r = max(sp, pp * decay);
    fragColor = vec4(r.rgb / max(r.a, 0.0001), r.a);
}
