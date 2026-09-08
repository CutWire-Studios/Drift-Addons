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

// --- upstream: Revolve_Left.glsl ---
// Author: bread
// License: MIT
// gl-transitions v1 compatible

uniform float p_center_x;
uniform float p_center_y;
#define center vec2(p_center_x, p_center_y)
uniform float direction;
uniform float maxRotation;
uniform float peakZoom;
uniform float swirl;
uniform float barrel;
uniform float motionBlur;
uniform float switchStart;
uniform float switchEnd;
uniform float shadow;

float sat(float x) {
  return clamp(x, 0.0, 1.0);
}

float ease(float x) {
  x = sat(x);
  return x * x * (3.0 - 2.0 * x);
}

float revolveEnvelope(float t) {
  float rise = ease((t - 0.10) / 0.33);
  float fall = 1.0 - ease((t - 0.43) / 0.29);
  return rise * fall;
}

vec2 rotate2(vec2 p, float a) {
  float s = sin(a);
  float c = cos(a);
  return vec2(c * p.x - s * p.y, s * p.x + c * p.y);
}

vec2 warpUv(vec2 uv, float t) {
  float e = revolveEnvelope(t);

  vec2 p = uv - center;
  p.x *= ratio;

  float r = length(p);
  float edgeSpin = maxRotation * e;
  float coreSpin = swirl * e * pow(1.0 - sat(r / 0.96), 1.55);
  float visibleAngle = direction * (edgeSpin + coreSpin);

  p = rotate2(p, -visibleAngle);

  float sc = 1.0 + (peakZoom - 1.0) * pow(e, 0.85);
  p /= sc;

  float rr = length(p);
  p *= 1.0 + barrel * e * rr * rr * 2.8;

  p.x /= ratio;
  return clamp(p + center, vec2(0.001), vec2(0.999));
}

vec4 sampleRevolve(vec2 uv, float t) {
  vec2 p = warpUv(uv, t);
  float reveal = smoothstep(switchStart, switchEnd, t);
  return mix(getFromColor(p), getToColor(p), reveal);
}

vec4 transition(vec2 uv) {
  if (progress <= 0.0) return getFromColor(uv);
  if (progress >= 1.0) return getToColor(uv);

  float e = revolveEnvelope(progress);
  float span = 0.060 * motionBlur * e;

  vec4 color = vec4(0.0);
  float total = 0.0;

  for (int i = -8; i <= 8; i++) {
    float x = float(i) / 8.0;
    float w = 1.0 - abs(x);
    w = w * w + 0.01;

    float t = sat(progress + x * span);
    color += sampleRevolve(uv, t) * w;
    total += w;
  }

  color /= total;

  vec2 q = uv - vec2(0.5);
  q.x *= ratio;
  float vignette = 1.0 - shadow * e * smoothstep(0.35, 0.95, length(q));
  color.rgb *= vignette;

  return color;
}

void main() {
    progress = u_progress;
    ratio = u_resolution.x / max(u_resolution.y, 1.0);
    fragColor = transition(vec2(v_texCoord.x, 1.0 - v_texCoord.y));
}
