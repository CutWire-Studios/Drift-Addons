#version 330 core
in vec2 v_texCoord; out vec4 fragColor;
uniform sampler2D u_currentTexture; uniform vec2 u_resolution;
uniform float u_faceValid;
uniform float u_faceMouthX; uniform float u_faceMouthY;
uniform float u_faceMouthLeftX; uniform float u_faceMouthLeftY;
uniform float u_faceMouthRightX; uniform float u_faceMouthRightY;
uniform float u_faceAngle;
uniform float widen; uniform float heighten; uniform float radius;

vec2 toLocal(vec2 uv, float aspect) { return vec2(uv.x, uv.y * aspect); }
vec2 fromLocal(vec2 q, float aspect) { return vec2(q.x, q.y / aspect); }
vec2 rot(vec2 p, float a) { float c = cos(a), s = sin(a); return vec2(p.x * c - p.y * s, p.x * s + p.y * c); }

void main() {
    if (u_faceValid < 0.5) { fragColor = texture(u_currentTexture, v_texCoord); return; }
    float aspect = u_resolution.y / u_resolution.x;
    vec2 q = toLocal(v_texCoord, aspect);
    vec2 c = toLocal(vec2(u_faceMouthX, u_faceMouthY), aspect);
    vec2 ml = toLocal(vec2(u_faceMouthLeftX, u_faceMouthLeftY), aspect);
    vec2 mr = toLocal(vec2(u_faceMouthRightX, u_faceMouthRightY), aspect);

    float r = max(length(mr - ml) * radius, 1e-5);
    vec2 d = q - c;
    float t = length(d) / r;
    if (t >= 1.0) { fragColor = texture(u_currentTexture, v_texCoord); return; }

    // Scale along the mouth's own axes, so a tilted head widens across the lips rather than
    // across the screen. Inverse scale, because this samples the source.
    float falloff = 1.0 - smoothstep(0.0, 1.0, t);
    vec2 p = rot(d, -u_faceAngle);
    p.x /= mix(1.0, 1.0 + widen, falloff);
    p.y /= mix(1.0, 1.0 + heighten, falloff);
    fragColor = texture(u_currentTexture, clamp(fromLocal(rot(p, u_faceAngle) + c, aspect), 0.0, 1.0));
}
