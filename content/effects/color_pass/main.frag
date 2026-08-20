#version 330 core
in vec2 v_texCoord; out vec4 fragColor;
uniform sampler2D u_currentTexture;
uniform float hue; uniform float range; uniform float softness; uniform float desaturateRest;

vec3 rgb2hsv(vec3 c) {
    vec4 K = vec4(0.0, -1.0 / 3.0, 2.0 / 3.0, -1.0);
    vec4 p = mix(vec4(c.bg, K.wz), vec4(c.gb, K.xy), step(c.b, c.g));
    vec4 q = mix(vec4(p.xyw, c.r), vec4(c.r, p.yzx), step(p.x, c.r));
    float d = q.x - min(q.w, q.y);
    float e = 1.0e-10;
    return vec3(abs(q.z + (q.w - q.y) / (6.0 * d + e)), d / (q.x + e), q.x);
}

void main() {
    vec4 c = texture(u_currentTexture, v_texCoord);
    vec3 hsv = rgb2hsv(c.rgb);
    float dh = abs(hsv.x - hue);
    dh = min(dh, 1.0 - dh);
    float m = 1.0 - smoothstep(range, range + softness, dh);
    float lum = dot(c.rgb, vec3(0.2126, 0.7152, 0.0722));
    vec3 gray = vec3(lum);
    vec3 rest = mix(c.rgb, gray, clamp(desaturateRest, 0.0, 1.0));
    fragColor = vec4(mix(rest, c.rgb, m), c.a);
}
