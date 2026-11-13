#version 330 core
in vec2 v_texCoord;
out vec4 fragColor;
uniform sampler2D u_currentTexture;
uniform vec2 u_resolution;
uniform float u_time;
uniform float shake;
uniform float rate;
uniform float rgb;
uniform float zoom;

void main() {
    vec2 pixel = 1.0 / max(u_resolution, vec2(1.0));
    float beat = floor(u_time * max(rate, 1.0));
    vec2 displacement = vec2(sin(beat * 127.1 + 2.5), sin(beat * 311.7 + 0.2));
    displacement *= max(shake, 0.0) * pixel;
    float scale = 1.0 + max(zoom, 0.0);
    vec2 uv = (v_texCoord - vec2(0.5)) / scale + vec2(0.5) + displacement;
    uv = clamp(uv, 0.0, 1.0);
    vec4 original = texture(u_currentTexture, uv);
    vec2 shift = pixel * max(rgb, 0.0);
    vec3 color = vec3(texture(u_currentTexture, clamp(uv + shift, 0.0, 1.0)).r,
                      original.g,
                      texture(u_currentTexture, clamp(uv - shift, 0.0, 1.0)).b);
    fragColor = vec4(color, original.a);
}
