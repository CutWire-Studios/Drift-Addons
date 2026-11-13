#version 330 core
in vec2 v_texCoord;
out vec4 fragColor;

uniform sampler2D u_currentTexture;
uniform vec2 u_resolution;

void main() {
    vec2 blocks = max(vec2(1.0), floor(u_resolution / 64.0 + 0.5));
    vec2 id = floor(v_texCoord * blocks);
    float count = 0.0;
    float sx = 0.0;
    float sy = 0.0;
    float minX = 1.0;
    float maxX = 0.0;
    float maxY = 0.0;
    for (int j = 0; j < 32; ++j) {
        for (int i = 0; i < 32; ++i) {
            vec2 rel = (vec2(float(i), float(j)) + 0.5) / 32.0;
            if (driftMask((id + rel) / blocks) > 0.5) {
                count += 1.0;
                sx += rel.x;
                sy += rel.y;
                minX = min(minX, rel.x);
                maxX = max(maxX, rel.x);
                maxY = max(maxY, rel.y);
            }
        }
    }
    if (count < 3.0) {
        fragColor = vec4(0.0);
        return;
    }
    float m = max(count / 1024.0, 1.0 / 255.0);
    float cx = sx / count;
    float cy = sy / count;
    fragColor = vec4(minX, maxX, 0.0, 1.0);
}
