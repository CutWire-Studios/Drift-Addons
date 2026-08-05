#version 330 core
in vec2 v_texCoord; out vec4 fragColor;
uniform sampler2D u_currentTexture; uniform vec2 u_resolution;
uniform float noise; uniform float chroma; uniform float saturation; uniform float u_time;
float rand(vec2 p){ return fract(sin(dot(p, vec2(12.9898,78.233))) * 43758.5453); }
void main() {
    vec2 px = 1.0 / u_resolution;
    float n = (rand(v_texCoord * u_resolution + u_time) - 0.5) * (noise / 255.0) * 2.0;
    float shift = chroma * px.x;
    float r = texture(u_currentTexture, v_texCoord + vec2(shift, 0.0)).r;
    float g = texture(u_currentTexture, v_texCoord).g;
    float b = texture(u_currentTexture, v_texCoord - vec2(shift, 0.0)).b;
    vec3 c = vec3(r,g,b) + n;
    c = (c - 0.5) * 1.08 + 0.5;
    c = pow(max(c, 0.0), vec3(1.0/1.12));
    float l = dot(c, vec3(0.299,0.587,0.114));
    c = mix(vec3(l), c, saturation);
    fragColor = vec4(clamp(c, 0.0, 1.0), 1.0);
}
