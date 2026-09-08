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

// --- upstream: StaticFade.glsl ---
// Author: Ben Lucas
// License: MIT

uniform float n_noise_pixels;
uniform float static_luminosity;

float rnd (vec2 st) {
    return fract(sin(dot(st.xy,
                         vec2(10.5302340293,70.23492931)))*
        12345.5453123);
}

vec4 staticNoise (vec2 st, float offset, float luminosity) {
  float staticR = luminosity * rnd(st * vec2(offset * 2.0, offset * 3.0));
  float staticG = luminosity * rnd(st * vec2(offset * 3.0, offset * 5.0));
  float staticB = luminosity * rnd(st * vec2(offset * 5.0, offset * 7.0));
  return vec4(staticR, staticG, staticB, 1.0);
}

float staticIntensity(float t)
{
  float transitionProgress = abs(2.0*(t-0.5));
  float transformedThreshold =1.2*(1.0 - transitionProgress)-0.1;
  return min(1.0, transformedThreshold);
}
  
vec4 transition (vec2 uv) {

  float baseMix = step(0.5, progress);
  vec4 transitionMix = mix(
    getFromColor(uv),
    getToColor(uv),
    baseMix
  );
  
  vec2 uvStatic = floor(uv * n_noise_pixels)/n_noise_pixels;
  
  vec4 staticColor = staticNoise(uvStatic, progress, static_luminosity);

  float staticThresh = staticIntensity(progress);
  float staticMix = step(rnd(uvStatic), staticThresh);

  return mix(transitionMix, staticColor, staticMix);
}

void main() {
    progress = u_progress;
    ratio = u_resolution.x / max(u_resolution.y, 1.0);
    fragColor = transition(vec2(v_texCoord.x, 1.0 - v_texCoord.y));
}
