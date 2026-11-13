#version 330 core
in vec2 v_texCoord;
out vec4 fragColor;

uniform sampler2D u_currentTexture;
uniform vec2 u_resolution;

void main() {
    vec2 uv = v_texCoord;
    vec2 h = 0.5 / u_resolution;
    vec3 sum = vec3(0.0);
    float wsum = 0.0;
    for (int i = 0; i < 4; ++i) {
        vec2 o = vec2((i & 1) == 0 ? -h.x : h.x, (i & 2) == 0 ? -h.y : h.y);
        vec4 s = texture(u_currentTexture, uv + o);
        sum += s.rgb * s.a;
        wsum += s.a;
    }
    fragColor = vec4(wsum > 1e-4 ? sum / wsum : vec3(0.0), clamp(wsum * 0.5, 0.0, 1.0));
}
