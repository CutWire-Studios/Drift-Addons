#version 330 core
in vec2 v_texCoord;
out vec4 fragColor;
uniform sampler2D u_currentTexture;
uniform float streakLength;

// Kawase-style cascade: passes step 1, 4, 16, 64 units over 11 taps, together an exponential falloff
// reaching streakLength. Steps grow by 4 while the previous pass already spans 5 units each side,
// so there are no gaps between copies.
void main() {
    float texW = float(textureSize(u_currentTexture, 0).x);
    float unit = max(streakLength, 0.005) * texW / 425.0;
    float b = 64.0;
    vec3 acc = vec3(0.0);
    float wsum = 0.0;
    for (int s = -5; s <= 5; ++s) {
        float w = exp(-3.0 * abs(float(s)) * b / 425.0 * 2.0);
        float x = v_texCoord.x + float(s) * b * unit / texW;
        acc += texture(u_currentTexture, vec2(clamp(x, 0.0, 1.0), v_texCoord.y)).rgb * w;
        wsum += w;
    }
    fragColor = vec4(acc / wsum, 1.0);
}
