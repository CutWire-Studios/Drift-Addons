#version 330 core
in vec2 v_texCoord; out vec4 fragColor;
uniform sampler2D u_currentTexture; uniform vec2 u_resolution; uniform float u_time;
uniform float amplitude; uniform float frequency; uniform float speed;
uniform float centerX; uniform float centerY;
void main() {
    vec2 res = u_resolution;
    vec2 pos = v_texCoord * res;
    vec2 c = vec2(centerX, centerY) * (res - 1.0);
    vec2 d = pos - c;
    float dist = length(d);
    if (dist < 1e-3) { fragColor = texture(u_currentTexture, v_texCoord); return; }
    float maxR = max(length(c), 1.0);
    float phase = u_time * speed * 6.2831853;
    float wave = sin((dist / maxR) * frequency * 6.2831853 + phase);
    float scale = (wave * amplitude) / dist;
    vec2 src = clamp((d * scale + pos) / res, 0.0, 1.0);
    fragColor = texture(u_currentTexture, src);
}
