#version 330 core
in vec2 v_texCoord; out vec4 fragColor;
uniform sampler2D u_currentTexture; uniform float temperature;
void main() {
    vec4 c = texture(u_currentTexture, v_texCoord);
    float t = (temperature - 6500.0) / 3500.0; // -1..~1
    vec3 warm = vec3(0.15, 0.05, -0.15) * t;
    fragColor = vec4(clamp(c.rgb + warm, 0.0, 1.0), c.a);
}
