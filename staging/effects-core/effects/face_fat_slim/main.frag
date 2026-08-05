#version 330 core
in vec2 v_texCoord; out vec4 fragColor;
uniform sampler2D u_currentTexture; uniform vec2 u_resolution;
uniform float u_faceValid;
uniform float u_faceCenterX; uniform float u_faceCenterY;
uniform float u_faceRx; uniform float u_faceRy; uniform float u_faceAngle;
uniform float width; uniform float height; uniform float coverage;

vec2 toLocal(vec2 uv, float aspect) { return vec2(uv.x, uv.y * aspect); }
vec2 fromLocal(vec2 q, float aspect) { return vec2(q.x, q.y / aspect); }
vec2 rot(vec2 p, float a) { float c = cos(a), s = sin(a); return vec2(p.x * c - p.y * s, p.x * s + p.y * c); }

void main() {
    if (u_faceValid < 0.5) { fragColor = texture(u_currentTexture, v_texCoord); return; }
    float aspect = u_resolution.y / u_resolution.x;
    vec2 q = toLocal(v_texCoord, aspect);
    vec2 c = toLocal(vec2(u_faceCenterX, u_faceCenterY), aspect);
    vec2 axes = max(vec2(u_faceRx, u_faceRy) * coverage, vec2(1e-5));

    vec2 p = rot(q - c, -u_faceAngle);
    float t = length(p / axes);
    if (t >= 1.0) { fragColor = texture(u_currentTexture, v_texCoord); return; }

    // Full strength at the centre easing to none at the oval edge, so the jaw stretches but the
    // background behind the head stays put.
    float falloff = 1.0 - smoothstep(0.0, 1.0, t);
    p.x /= mix(1.0, 1.0 + width, falloff);
    p.y /= mix(1.0, 1.0 + height, falloff);
    fragColor = texture(u_currentTexture, clamp(fromLocal(rot(p, u_faceAngle) + c, aspect), 0.0, 1.0));
}
