#version 330 core
in vec2 v_texCoord;
out vec4 fragColor;

uniform sampler2D u_currentTexture;
uniform sampler2D u_texture1;

vec4 coarse(vec2 uv) {
    vec2 sz = vec2(textureSize(u_texture1, 0));
    vec2 p = uv * sz - 0.5;
    vec2 f = fract(p);
    ivec2 i0 = ivec2(floor(p));
    ivec2 hi = ivec2(sz) - 1;
    vec4 acc = vec4(0.0);
    for (int k = 0; k < 4; ++k) {
        ivec2 o = ivec2(k & 1, k >> 1);
        vec4 s = texelFetch(u_texture1, clamp(i0 + o, ivec2(0), hi), 0);
        float w = ((k & 1) == 0 ? 1.0 - f.x : f.x) * ((k >> 1) == 0 ? 1.0 - f.y : f.y);
        acc += vec4(s.rgb * s.a, s.a) * w;
    }
    return vec4(acc.a > 1e-5 ? acc.rgb / acc.a : vec3(0.0), acc.a);
}

void main() {
    vec2 uv = v_texCoord;
    vec4 fine = texture(u_currentTexture, uv);
    vec4 up = coarse(uv);
    float a = fine.a + (1.0 - fine.a) * up.a;
    vec3 p = fine.rgb * fine.a + (1.0 - fine.a) * up.a * up.rgb;
    fragColor = vec4(a > 1e-5 ? p / a : vec3(0.0), a);
}
