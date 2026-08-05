#version 330 core
in vec2 v_texCoord; out vec4 fragColor;
uniform sampler2D u_currentTexture; uniform vec2 u_resolution;
uniform float strength; uniform float angle; uniform float blend;
void main() {
    vec2 px = 1.0 / u_resolution;
    float rad = radians(angle);
    vec2 dir = vec2(cos(rad), sin(rad)) * px;
    vec3 a = texture(u_currentTexture, clamp(v_texCoord - dir, 0.0, 1.0)).rgb;
    vec3 b = texture(u_currentTexture, clamp(v_texCoord + dir, 0.0, 1.0)).rgb;
    vec3 emb = (b - a) * strength + 0.5;
    vec3 src = texture(u_currentTexture, v_texCoord).rgb;
    fragColor = vec4(mix(src, emb, clamp(blend, 0.0, 1.0)), texture(u_currentTexture, v_texCoord).a);
}
