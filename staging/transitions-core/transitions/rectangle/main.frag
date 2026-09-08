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

// --- upstream: Rectangle.glsl ---
// Author: martiniti
// License: MIT

uniform vec3 p_bgcolor;
uniform float p_bgcolor_a;
#define bgcolor vec4(p_bgcolor, p_bgcolor_a)

// Hoisted: these initialisers read uniforms, which GLSL 330 does not
// allow at global scope. Assigned at the top of transition() instead.
float s;

vec4 transition(vec2 p) {
    s = pow(2.0 * abs(progress - 0.5), 3.0);
  
   vec2 sq = p.xy / vec2(1.0).xy;
   
    // bottom-left
    vec2 bl = step(vec2(abs(1. - 2.*progress)), sq + .25);
    float dist = bl.x * bl.y;

    // top-right
    vec2 tr = step(vec2(abs(1. - 2.*progress)), 1.25-sq);
    dist *= 1. * tr.x * tr.y;
  
  return mix(
    progress < 0.5 ? getFromColor(p) : getToColor(p),
    bgcolor,
    step(s, dist)
  );
  
}

void main() {
    progress = u_progress;
    ratio = u_resolution.x / max(u_resolution.y, 1.0);
    fragColor = transition(vec2(v_texCoord.x, 1.0 - v_texCoord.y));
}
