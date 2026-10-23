#version 330 core
in vec2 v_texCoord;
out vec4 fragColor;

uniform sampler2D u_currentTexture;
uniform sampler2D audio;
uniform vec2 u_resolution;
uniform vec4 color;
uniform float thickness;
uniform float amplitude;

float curve(float x) {
    return 0.5 + (texture(audio, vec2(clamp(x, 0.0, 1.0), 0.75)).r - 0.5) * amplitude;
}

void main() {
    vec4 src = texture(u_currentTexture, v_texCoord);
    float px = 1.0 / u_resolution.x;
    float yc = curve(v_texCoord.x);
    // The line spans the curve over one pixel either side, so steep parts stay connected.
    float lo = min(min(curve(v_texCoord.x - px), curve(v_texCoord.x + px)), yc) - thickness * 0.5;
    float hi = max(max(curve(v_texCoord.x - px), curve(v_texCoord.x + px)), yc) + thickness * 0.5;
    float aa = 1.0 / u_resolution.y;
    float a = color.a * smoothstep(lo - aa, lo + aa, v_texCoord.y) * (1.0 - smoothstep(hi - aa, hi + aa, v_texCoord.y));
    fragColor = vec4(color.rgb * a + src.rgb * src.a * (1.0 - a), a + src.a * (1.0 - a));
}
