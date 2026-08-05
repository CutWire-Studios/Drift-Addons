#version 330 core
in vec2 v_texCoord; out vec4 fragColor;
uniform sampler2D u_currentTexture; uniform vec2 u_resolution;
uniform float u_faceValid;
uniform float u_faceCenterX; uniform float u_faceCenterY;
uniform float u_faceLeftEyeX; uniform float u_faceLeftEyeY;
uniform float u_faceRightEyeX; uniform float u_faceRightEyeY;
uniform float u_faceRx; uniform float u_faceRy; uniform float u_faceAngle;
uniform float stretch; uniform float narrow; uniform float coverage;

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

    // Everything above the eye line is the cranium; the face below it is left alone, which is
    // what separates an alien head from simply scaling the whole head.
    vec2 eyeMid = (toLocal(vec2(u_faceLeftEyeX, u_faceLeftEyeY), aspect)
                 + toLocal(vec2(u_faceRightEyeX, u_faceRightEyeY), aspect)) * 0.5;
    float eyeY = rot(eyeMid - c, -u_faceAngle).y;
    if (p.y > eyeY) { fragColor = texture(u_currentTexture, v_texCoord); return; }

    float reach = max(axes.y + eyeY, 1e-5);   // eyeY is negative: distance from eyes to crown
    float depth = clamp((eyeY - p.y) / reach, 0.0, 1.0);

    // Bounded across the head but not above it: the elongated skull has to reach past the crown,
    // while anything out to the sides is background and must stay where it is.
    float lateral = clamp(abs(p.x) / axes.x, 0.0, 1.0);
    float ease = smoothstep(0.0, 1.0, depth) * (1.0 - smoothstep(0.65, 1.0, lateral));

    p.y = eyeY - (eyeY - p.y) / mix(1.0, 1.0 + stretch, ease);
    p.x /= mix(1.0, 1.0 - narrow, ease);
    fragColor = texture(u_currentTexture, clamp(fromLocal(rot(p, u_faceAngle) + c, aspect), 0.0, 1.0));
}
