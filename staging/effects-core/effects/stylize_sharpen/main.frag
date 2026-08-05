#version 330 core
in vec2 v_texCoord; out vec4 fragColor;
uniform sampler2D u_currentTexture; uniform vec2 u_resolution; uniform float luma_amount;
void main() {
    vec2 px = 1.0 / u_resolution;
    vec4 c = texture(u_currentTexture, v_texCoord);
    vec4 blur = (
        texture(u_currentTexture, v_texCoord + vec2(-px.x,0.0)) +
        texture(u_currentTexture, v_texCoord + vec2( px.x,0.0)) +
        texture(u_currentTexture, v_texCoord + vec2(0.0,-px.y)) +
        texture(u_currentTexture, v_texCoord + vec2(0.0, px.y))
    ) * 0.25;
    fragColor = vec4(clamp(c.rgb + (c.rgb - blur.rgb) * luma_amount, 0.0, 1.0), c.a);
}
