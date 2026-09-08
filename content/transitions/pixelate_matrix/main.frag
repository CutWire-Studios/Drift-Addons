#version 330 core
in vec2 v_texCoord;
out vec4 fragColor;

uniform sampler2D u_fromTexture;
uniform sampler2D u_toTexture;
uniform vec2 u_resolution;
uniform float u_progress;

// Real mutable globals rather than #defines: StereoViewer takes `float ratio` as a function
// parameter and undulatingBurnOut declares a local of that name, both of which a macro would
// turn into a syntax error. Globals let them shadow legally.
float progress;
float ratio;

// Upstream works in WebGL's bottom-left uv space; v_texCoord.y == 0 is the top of a Drift frame.
// The flip here and the one in main() are a single round trip, not a double negation.
// The clamp makes the CLAMP_TO_EDGE behaviour upstream assumes explicit rather than inherited
// from sampler state -- about two dozen shaders sample outside [0,1] unguarded.
vec4 getFromColor(vec2 uv) {
    uv = clamp(uv, 0.0, 1.0);
    return texture(u_fromTexture, vec2(uv.x, 1.0 - uv.y));
}

vec4 getToColor(vec2 uv) {
    uv = clamp(uv, 0.0, 1.0);
    return texture(u_toTexture, vec2(uv.x, 1.0 - uv.y));
}

// --- upstream: pixelize.glsl ---
// Author: gre
// License: MIT
// forked from https://gist.github.com/benraziel/c528607361d90a072e98

// minimum number of squares (when the effect is at its higher level)

uniform float p_squaresMin_x;
uniform float p_squaresMin_y;
#define squaresMin ivec2(int(p_squaresMin_x), int(p_squaresMin_y))
uniform float p_steps;
#define steps int(p_steps)

// Hoisted: these initialisers read uniforms, which GLSL 330 does not
// allow at global scope. Assigned at the top of transition() instead.
float d;
float dist;
vec2 squareSize;

// zero disable the stepping


vec4 transition(vec2 uv) {
    d = min(progress, 1.0 - progress);
    dist = steps>0 ? ceil(d * float(steps)) / float(steps) : d;
    squareSize = 2.0 * dist / vec2(squaresMin);
  vec2 p = dist>0.0 ? (floor(uv / squareSize) + 0.5) * squareSize : uv;
  return mix(getFromColor(p), getToColor(p), progress);
}

void main() {
    progress = u_progress;
    ratio = u_resolution.x / max(u_resolution.y, 1.0);
    fragColor = transition(vec2(v_texCoord.x, 1.0 - v_texCoord.y));
}
