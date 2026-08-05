#version 330 core
in vec2 v_texCoord; out vec4 fragColor;
uniform sampler2D u_currentTexture; uniform vec2 u_resolution;
uniform float u_faceValid;
uniform float u_faceCenterX; uniform float u_faceCenterY;
uniform float u_faceRx; uniform float u_faceRy; uniform float u_faceAngle;
uniform float amount; uniform float coverage;

vec2 toLocal(vec2 uv, float aspect) { return vec2(uv.x, uv.y * aspect); }
vec2 fromLocal(vec2 q, float aspect) { return vec2(q.x, q.y / aspect); }
vec2 rot(vec2 p, float a) { float c = cos(a), s = sin(a); return vec2(p.x * c - p.y * s, p.x * s + p.y * c); }

void main() {
    if (u_faceValid < 0.5) { fragColor = texture(u_currentTexture, v_texCoord); return; }
    float aspect = u_resolution.y / u_resolution.x;
    vec2 q = toLocal(v_texCoord, aspect);
    vec2 c = toLocal(vec2(u_faceCenterX, u_faceCenterY), aspect);

    // Into the face's own frame, where the oval is the unit circle: the warp then follows a
    // tilted head instead of smearing across it.
    vec2 p = rot(q - c, -u_faceAngle);
    vec2 e = p / max(vec2(u_faceRx, u_faceRy) * coverage, vec2(1e-5));
    float t = length(e);
    if (t >= 1.0 || t < 1e-6) { fragColor = texture(u_currentTexture, v_texCoord); return; }

    // Inverse map: sampling nearer the centre than the pixel sits (k > 1) is what magnifies.
    float k = 1.0 + clamp(amount, -0.95, 0.95);
    float blend = 1.0 - smoothstep(0.6, 1.0, t);
    float tf = mix(t, pow(t, k), blend);
    vec2 warped = rot(e * (tf / t) * (vec2(u_faceRx, u_faceRy) * coverage), u_faceAngle) + c;
    fragColor = texture(u_currentTexture, clamp(fromLocal(warped, aspect), 0.0, 1.0));
}
