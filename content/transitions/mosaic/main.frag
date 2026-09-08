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

// --- upstream: Mosaic.glsl ---
// License: MIT
// Author: Xaychru
// ported by gre from https://gist.github.com/Xaychru/130bb7b7affedbda9df5

uniform float p_endx;
#define endx int(p_endx)
uniform float p_endy;
#define endy int(p_endy)

#define PI 3.14159265358979323
#define POW2(X) X*X
#define POW3(X) X*X*X

float Rand(vec2 v) {
  return fract(sin(dot(v.xy ,vec2(12.9898,78.233))) * 43758.5453);
}
vec2 Rotate(vec2 v, float a) {
  mat2 rm = mat2(cos(a), -sin(a),
                 sin(a), cos(a));
  return rm*v;
}
float CosInterpolation(float x) {
  return -cos(x*PI)/2.+.5;
}
vec4 transition(vec2 uv) {
  vec2 p = uv.xy / vec2(1.0).xy - .5;
  vec2 rp = p;
  float rpr = (progress*2.-1.);
  float z = -(rpr*rpr*2.) + 3.;
  float az = abs(z);
  rp *= az;
  rp += mix(vec2(.5, .5), vec2(float(endx) + .5, float(endy) + .5), POW2(CosInterpolation(progress)));
  vec2 mrp = mod(rp, 1.);
  vec2 crp = rp;
  bool onEnd = int(floor(crp.x))==endx&&int(floor(crp.y))==endy;
  if(!onEnd) {
    float ang = float(int(Rand(floor(crp))*4.))*.5*PI;
    mrp = vec2(.5) + Rotate(mrp-vec2(.5), ang);
  }
  if(onEnd || Rand(floor(crp))>.5) {
    return getToColor(mrp);
  } else {
    return getFromColor(mrp);
  }
}

void main() {
    progress = u_progress;
    ratio = u_resolution.x / max(u_resolution.y, 1.0);
    fragColor = transition(vec2(v_texCoord.x, 1.0 - v_texCoord.y));
}
