#version 330 core
in vec2 v_texCoord; out vec4 fragColor;
uniform sampler2D u_currentTexture; uniform vec2 u_resolution;
uniform float amplitude; uniform float frequency;
void main() {
    vec2 uv = v_texCoord;
    vec2 p = (uv * u_resolution) - 0.5 * u_resolution;
    float maxR = length(0.5 * u_resolution);
    float dist = length(p);
    float wave = sin((dist / max(maxR, 1.0)) * frequency * 6.2831853);
    vec2 offset = vec2(wave * amplitude, wave * amplitude * 0.5) / u_resolution;
    fragColor = texture(u_currentTexture, clamp(uv + offset, 0.0, 1.0));
}
