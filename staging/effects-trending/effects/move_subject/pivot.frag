#version 330 core
in vec2 v_texCoord;
out vec4 fragColor;

uniform sampler2D u_currentTexture;
uniform sampler2D u_texture1;
uniform float pivot;

vec2 pack16(float v) {
    v = clamp(v, 0.0, 0.9999);
    float hi = floor(v * 255.0) / 255.0;
    return vec2(hi, fract(v * 255.0));
}

void main() {
    ivec2 sz = textureSize(u_currentTexture, 0);
    float wsum = 0.0;
    vec2 c = vec2(0.0);
    float minX = 1.0;
    float maxX = 0.0;
    float maxY = 0.0;
    for (int y = 0; y < sz.y; ++y) {
        for (int x = 0; x < sz.x; ++x) {
            vec4 a = texelFetch(u_currentTexture, ivec2(x, y), 0);
            if (a.r <= 0.0)
                continue;
            vec4 b = texelFetch(u_texture1, ivec2(x, y), 0);
            vec2 id = vec2(float(x), float(y));
            vec2 sizeF = vec2(sz);
            c += a.r * (id + a.gb) / sizeF;
            wsum += a.r;
            minX = min(minX, (id.x + b.r) / sizeF.x);
            maxX = max(maxX, (id.x + b.g) / sizeF.x);
            maxY = max(maxY, (id.y + a.a) / sizeF.y);
        }
    }
    if (wsum <= 0.0) {
        fragColor = vec4(0.0);
        return;
    }
    vec2 p = pivot < 0.5 ? vec2(0.5 * (minX + maxX), maxY) : c / wsum;
    fragColor = vec4(pack16(p.x), pack16(p.y));
}
