#version 330 core
in vec2 v_texCoord;
out vec4 fragColor;

uniform sampler2D u_currentTexture;
uniform sampler2D audio;
uniform float bars;
uniform vec4 color;
uniform float gap;
uniform float heightScale;
uniform float mirror;

void main() {
    vec4 src = texture(u_currentTexture, v_texCoord);
    float n = floor(clamp(bars, 8.0, 128.0));
    float slot = v_texCoord.x * n;
    float level = texture(audio, vec2((floor(slot) + 0.5) / n, 0.25)).r * heightScale;
    float inBar = step(gap * 0.5, fract(slot)) * step(fract(slot), 1.0 - gap * 0.5);
    float up = mirror > 0.5 ? step(abs(v_texCoord.y - 0.5), level * 0.5) : step(1.0 - v_texCoord.y, level);
    float a = color.a * inBar * up;
    fragColor = vec4(color.rgb * a + src.rgb * src.a * (1.0 - a), a + src.a * (1.0 - a));
}
