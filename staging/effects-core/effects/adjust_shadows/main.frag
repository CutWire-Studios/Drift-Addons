#version 330 core
in vec2 v_texCoord; out vec4 fragColor;
uniform sampler2D u_currentTexture; uniform float shadows;
void main() {
    vec4 c = texture(u_currentTexture, v_texCoord);
    float l = dot(c.rgb, vec3(0.299, 0.587, 0.114));
    float w = (1.0 - smoothstep(0.0, 0.55, l)) * smoothstep(0.0, 0.10, l);
    vec3 room = shadows >= 0.0 ? (1.0 - c.rgb) * 0.5 : c.rgb * 0.7;
    fragColor = vec4(clamp(c.rgb + shadows * w * room, 0.0, 1.0), c.a);
}
