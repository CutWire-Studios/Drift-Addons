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

// --- upstream: powerKaleido.glsl ---
// Name: Power Kaleido
// Author: Boundless
// License: MIT

uniform float scale;
uniform float z;
uniform float speed;

// Hoisted: these initialisers read uniforms, which GLSL 330 does not
// allow at global scope. Assigned at the top of transition() instead.
float dist;

#define PI 3.14159265358979
const float rad = 120.; // change this value to get different mirror effects
const float deg = rad / 180. * PI;
vec2 refl(vec2 p,vec2 o,vec2 n)
{
	return 2.0*o+2.0*n*dot(p-o,n)-p;
}

vec2 rot(vec2 p, vec2 o, float a)
{
    float s = sin(a);
    float c = cos(a);
	return o + mat2(c, -s, s, c) * (p - o);
}

vec4 mainImage(vec2 uv)
{
  vec2 uv0 = uv;
	uv -= 0.5;
  uv.x *= ratio;
  uv *= z;
  uv = rot(uv, vec2(0.0), progress*speed);
  // uv.x = fract(uv.x/l/3.0)*l*3.0;
	float theta = progress*6.+PI/.5;
	for(int iter = 0; iter < 10; iter++) {
    for(float i = 0.; i < 2. * PI; i+=deg) {
	    float ts = sign(asin(cos(i))) == 1.0 ? 1.0 : 0.0;
      if(((ts == 1.0) && (uv.y-dist*cos(i) > tan(i)*(uv.x+dist*+sin(i)))) || ((ts == 0.0) && (uv.y-dist*cos(i) < tan(i)*(uv.x+dist*+sin(i))))) {
        uv = refl(vec2(uv.x+sin(i)*dist*2.,uv.y-cos(i)*dist*2.), vec2(0.,0.), vec2(cos(i),sin(i)));
      }
    }
  }
  uv += 0.5;
  uv = rot(uv, vec2(0.5), progress*-speed);
  uv -= 0.5;
  uv.x /= ratio;
  uv += 0.5;
  uv = 2.*abs(uv/2.-floor(uv/2.+0.5));
  vec2 uvMix = mix(uv,uv0,cos(progress*PI*2.)/2.+0.5);
  vec4 color = mix(getFromColor(uvMix),getToColor(uvMix),cos((progress-1.)*PI)/2.+0.5);
	return color;
    
}
vec4 transition (vec2 uv) {
    dist = scale / 10.;
  vec4 color = mainImage(uv);
  return color;
}

void main() {
    progress = u_progress;
    ratio = u_resolution.x / max(u_resolution.y, 1.0);
    fragColor = transition(vec2(v_texCoord.x, 1.0 - v_texCoord.y));
}
