#version 330 core
in vec2 v_texCoord; out vec4 fragColor;
uniform sampler2D u_currentTexture; uniform vec2 u_resolution;
uniform float u_faceValid;
uniform float u_faceNoseX; uniform float u_faceNoseY;
uniform float u_faceRx; uniform float u_faceRy;
uniform float twist; uniform float coverage;

vec2 toLocal(vec2 uv, float aspect) { return vec2(uv.x, uv.y * aspect); }
vec2 fromLocal(vec2 q, float aspect) { return vec2(q.x, q.y / aspect); }
vec2 rot(vec2 p, float a) { float c = cos(a), s = sin(a); return vec2(p.x * c - p.y * s, p.x * s + p.y * c); }

void main() {
    if (u_faceValid < 0.5) { fragColor = texture(u_currentTexture, v_texCoord); return; }
    float aspect = u_resolution.y / u_resolution.x;
    vec2 q = toLocal(v_texCoord, aspect);
    vec2 c = toLocal(vec2(u_faceNoseX, u_faceNoseY), aspect);

    float r = max(max(u_faceRx, u_faceRy) * coverage, 1e-5);
    vec2 d = q - c;
    float t = length(d) / r;
    if (t >= 1.0) { fragColor = texture(u_currentTexture, v_texCoord); return; }

    // Twist hardest at the nose and unwind to nothing at the edge, so the swirl stays on the face.
    float angle = twist * (1.0 - smoothstep(0.0, 1.0, t));
    fragColor = texture(u_currentTexture, clamp(fromLocal(rot(d, angle) + c, aspect), 0.0, 1.0));
}
