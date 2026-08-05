#version 330 core
in vec2 v_texCoord; out vec4 fragColor;
uniform sampler2D u_currentTexture; uniform vec2 u_resolution;
uniform float amount; uniform float radius; uniform float centerX; uniform float centerY;
void main() {
    float aspect = u_resolution.x / max(u_resolution.y, 1.0);
    vec2 c = vec2(centerX, centerY);
    vec2 d = (v_texCoord - c) * vec2(aspect, 1.0);
    float r = length(d);
    float R = max(radius, 1e-4);
    if (r >= R || abs(amount) < 1e-5) {
        fragColor = texture(u_currentTexture, v_texCoord);
        return;
    }
    float t = r / R;
    float bulge = mix(t, sin(t * 1.5707963), amount);
    vec2 nd = (r > 1e-6) ? d * (bulge / t) : d;
    vec2 src = c + vec2(nd.x / aspect, nd.y);
    fragColor = texture(u_currentTexture, clamp(src, 0.0, 1.0));
}
