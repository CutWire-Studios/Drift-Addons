#version 330 core
in vec2 v_texCoord; out vec4 fragColor;
uniform sampler2D u_currentTexture; uniform vec2 u_resolution;
uniform float u_faceValid; uniform float u_faceHasContours;
uniform vec2 u_faceEyeLeft[16];
uniform vec2 u_faceEyeRight[16];
uniform vec3 shade; uniform float thickness; uniform float wing; uniform float opacity;

vec2 toLocal(vec2 uv, float aspect) { return vec2(uv.x, uv.y * aspect); }

float sdSegment(vec2 p, vec2 a, vec2 b) {
    vec2 e = b - a, w = p - a;
    return length(w - e * clamp(dot(w, e) / max(dot(e, e), 1e-12), 0.0, 1.0));
}

// Signed distance to the closed eye ring, negative inside (Inigo Quilez). Unlike the other makeup
// packages this takes the array as a parameter rather than through a macro: the liner needs the
// ring's inside test *and* its upper arc together, so one function per eye is simpler than two.
float sdRing(vec2 p, vec2 ring[16]) {
    vec2 d0 = p - ring[0];
    float d = dot(d0, d0);
    float s = 1.0;
    for (int i = 0, j = 15; i < 16; j = i, i++) {
        vec2 e = ring[j] - ring[i];
        vec2 w = p - ring[i];
        vec2 b = w - e * clamp(dot(w, e) / dot(e, e), 0.0, 1.0);
        d = min(d, dot(b, b));
        bvec3 c = bvec3(p.y >= ring[i].y, p.y < ring[j].y, e.x * w.y > e.y * w.x);
        if (all(c) || all(not(c))) s = -s;
    }
    return s * sqrt(d);
}

// Coverage for one eye. The ring is wound inner-corner-first along the upper lid, so indices 0..8
// are the lash line and the parameter along it runs 0 at the inner corner to 1 at the outer — the
// direction liner is meant to thicken in.
float liner(vec2 p, vec2 ring[16], float eyeWidth) {
    float best = 1e9;
    float bestT = 0.0;
    for (int i = 0; i < 8; i++) {
        float d = sdSegment(p, ring[i], ring[i + 1]);
        if (d < best) { best = d; bestT = float(i) / 7.0; }
    }

    float halfWidth = max(eyeWidth * thickness * 0.07 * mix(0.45, 1.0, bestT), 1e-5);
    float feather = halfWidth * 0.6;
    float line = 1.0 - smoothstep(halfWidth - feather, halfWidth + feather, best);

    // Fade out over the eyeball. Liner straddles the lash line, so this only suppresses the part
    // that has crossed well inside the lid rather than clipping it flat at the boundary.
    line *= 1.0 - smoothstep(-halfWidth * 1.5, -halfWidth * 0.2, sdRing(p, ring));

    if (wing > 0.0) {
        // Continue the last lash-line segment past the outer corner, tapering to a point.
        vec2 tip = ring[8];
        vec2 dir = normalize(tip - ring[6]);
        float len = eyeWidth * wing * 0.30;
        vec2 endPoint = tip + dir * len;
        float along = clamp(dot(p - tip, dir) / max(len, 1e-9), 0.0, 1.0);
        float taper = max(halfWidth * (1.0 - along), 1e-5);
        float w = 1.0 - smoothstep(taper * 0.4, taper, sdSegment(p, tip, endPoint));
        line = max(line, w);
    }
    return clamp(line, 0.0, 1.0);
}

void main() {
    vec4 src = texture(u_currentTexture, v_texCoord);
    if (u_faceValid < 0.5 || u_faceHasContours < 0.5) { fragColor = src; return; }

    float aspect = u_resolution.y / u_resolution.x;
    vec2 p = toLocal(v_texCoord, aspect);

    // Index 0 is the inner corner and 8 the outer one, so this is the eye's own width — the scale
    // everything below is measured in, so the line looks the same at any distance from camera.
    float wl = length(u_faceEyeLeft[8] - u_faceEyeLeft[0]);
    float wr = length(u_faceEyeRight[8] - u_faceEyeRight[0]);

    float cover = max(liner(p, u_faceEyeLeft, wl), liner(p, u_faceEyeRight, wr));
    if (cover <= 0.0) { fragColor = src; return; }

    fragColor = vec4(mix(src.rgb, shade, cover * opacity), src.a);
}
