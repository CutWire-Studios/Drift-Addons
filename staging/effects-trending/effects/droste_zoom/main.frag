#version 330 core
in vec2 v_texCoord; out vec4 fragColor;
uniform sampler2D u_currentTexture;
uniform float strength; uniform float centerX; uniform float centerY; uniform float turns; uniform float zoom;

const float PI = 3.14159265;

void main() {
    vec4 src = texture(u_currentTexture, v_texCoord);
    float s = clamp(strength, 0.0, 1.0);
    if (s <= 1e-5) {
        fragColor = src;
        return;
    }

    vec2 c = vec2(centerX, centerY);
    vec2 p = v_texCoord - c;
    float r = length(p) + 1e-5;
    float a = atan(p.y, p.x);
    float logR = log(r);
    float z = max(zoom, 0.5);
    float t = turns * 2.0 * PI;
    float newA = a + t * logR;
    float newR = exp(logR / z);
    vec2 uv = vec2(cos(newA), sin(newA)) * newR + c;
    vec3 warped = texture(u_currentTexture, clamp(uv, 0.0, 1.0)).rgb;
    fragColor = vec4(mix(src.rgb, warped, s), src.a);
}
