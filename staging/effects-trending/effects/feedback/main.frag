#version 330 core
in vec2 v_texCoord; out vec4 fragColor;
uniform sampler2D u_currentTexture;
uniform vec2 u_resolution;
uniform float zoom; uniform float rotation; uniform float offsetX; uniform float offsetY;
uniform float decay; uniform float mixAmount;

// u_prevOutput is this effect's result one frame ago; it is transparent on the first frame and
// after a seek, which leaves the live picture alone.
void main() {
    vec4 src = texture(u_currentTexture, v_texCoord);
    vec2 asp = vec2(u_resolution.x / u_resolution.y, 1.0);
    vec2 p = (v_texCoord - 0.5) * asp;
    float a = radians(rotation);
    float cs = cos(a);
    float sn = sin(a);
    p = mat2(cs, sn, -sn, cs) * p / zoom;
    p = p / asp + 0.5 - vec2(offsetX, offsetY);
    float inside = step(0.0, p.x) * step(p.x, 1.0) * step(0.0, p.y) * step(p.y, 1.0);
    vec4 fb = texture(u_prevOutput, p);
    vec4 fp = vec4(fb.rgb * fb.a, fb.a) * (decay * inside);
    vec4 r = max(vec4(src.rgb * src.a, src.a), fp);
    fragColor = mix(src, vec4(r.rgb / max(r.a, 0.0001), r.a), mixAmount);
}
