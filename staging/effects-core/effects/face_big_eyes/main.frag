#version 330 core
in vec2 v_texCoord; out vec4 fragColor;
uniform sampler2D u_currentTexture; uniform vec2 u_resolution;
uniform float u_faceValid;
uniform float u_faceLeftEyeX; uniform float u_faceLeftEyeY;
uniform float u_faceRightEyeX; uniform float u_faceRightEyeY;
uniform float u_faceEyeRadius;
uniform float amount; uniform float radius;

// Anchors arrive in uv, but lengths are width-normalized: uv with y scaled by the aspect, so a
// radius means the same thing along both axes. Work there, then convert back to sample.
vec2 toLocal(vec2 uv, float aspect) { return vec2(uv.x, uv.y * aspect); }
vec2 fromLocal(vec2 q, float aspect) { return vec2(q.x, q.y / aspect); }

// Radial magnify/pinch, faded out before the edge so the surrounding face is untouched.
//
// This runs backwards: q is the pixel being written and the result is where to read from. Sampling
// nearer the centre than the pixel sits (k > 1) is what magnifies, so positive strength raises the
// exponent — the reverse of what reading it as a forward warp suggests.
vec2 bulge(vec2 q, vec2 c, float r, float strength) {
    vec2 d = q - c;
    float dist = length(d);
    if (dist > r || dist < 1e-6) return q;
    float t = dist / r;
    float k = 1.0 + clamp(strength, -0.95, 0.95);
    float tw = pow(t, k);
    float blend = 1.0 - smoothstep(0.65, 1.0, t);
    return c + (d / dist) * mix(t, tw, blend) * r;
}

void main() {
    if (u_faceValid < 0.5) { fragColor = texture(u_currentTexture, v_texCoord); return; }
    float aspect = u_resolution.y / u_resolution.x;
    vec2 q = toLocal(v_texCoord, aspect);
    float r = max(u_faceEyeRadius * radius, 1e-5);
    q = bulge(q, toLocal(vec2(u_faceLeftEyeX, u_faceLeftEyeY), aspect), r, amount);
    q = bulge(q, toLocal(vec2(u_faceRightEyeX, u_faceRightEyeY), aspect), r, amount);
    fragColor = texture(u_currentTexture, clamp(fromLocal(q, aspect), 0.0, 1.0));
}
