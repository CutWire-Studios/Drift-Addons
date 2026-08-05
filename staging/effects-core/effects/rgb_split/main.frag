#version 330 core
in vec2 v_texCoord; out vec4 fragColor;
uniform sampler2D u_currentTexture; uniform vec2 u_resolution; uniform float u_time;
uniform float amount; uniform float angle; uniform float animated; uniform float speed;
void main() {
    float a = radians(angle + (animated > 0.5 ? u_time * speed * 60.0 : 0.0));
    vec2 delta = vec2(cos(a), sin(a)) * amount / u_resolution;
    float r = texture(u_currentTexture, clamp(v_texCoord + delta, 0.0, 1.0)).r;
    vec4 g = texture(u_currentTexture, v_texCoord);
    float b = texture(u_currentTexture, clamp(v_texCoord - delta, 0.0, 1.0)).b;
    fragColor = vec4(r, g.g, b, g.a);
}
