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

// --- upstream: GlitchDisplace.glsl ---
// Author: Matt DesLauriers
// License: MIT

float random(vec2 co)
{
    float a = 12.9898;
    float b = 78.233;
    float c = 43758.5453;
    float dt= dot(co.xy ,vec2(a,b));
    float sn= mod(dt,3.14);
    return fract(sin(sn) * c);
}
float voronoi( in vec2 x ) {
    vec2 p = floor( x );
    vec2 f = fract( x );
    float res = 8.0;
    for( float j=-1.; j<=1.; j++ )
    for( float i=-1.; i<=1.; i++ ) {
        vec2  b = vec2( i, j );
        vec2  r = b - f + random( p + b );
        float d = dot( r, r );
        res = min( res, d );
    }
    return sqrt( res );
}

vec2 displace(vec4 tex, vec2 texCoord, float dotDepth, float textureDepth, float strength) {
    float b = voronoi(.003 * texCoord + 2.0);
    float g = voronoi(0.2 * texCoord);
    float r = voronoi(texCoord - 1.0);
    vec4 dt = tex * 1.0;
    vec4 dis = dt * dotDepth + 1.0 - tex * textureDepth;

    dis.x = dis.x - 1.0 + textureDepth*dotDepth;
    dis.y = dis.y - 1.0 + textureDepth*dotDepth;
    dis.x *= strength;
    dis.y *= strength;
    vec2 res_uv = texCoord ;
    res_uv.x = res_uv.x + dis.x - 0.0;
    res_uv.y = res_uv.y + dis.y;
    return res_uv;
}

float ease1(float t) {
  return t == 0.0 || t == 1.0
    ? t
    : t < 0.5
      ? +0.5 * pow(2.0, (20.0 * t) - 10.0)
      : -0.5 * pow(2.0, 10.0 - (t * 20.0)) + 1.0;
}
float ease2(float t) {
  return t == 1.0 ? t : 1.0 - pow(2.0, -10.0 * t);
}



vec4 transition(vec2 uv) {
  vec2 p = uv.xy / vec2(1.0).xy;
  vec4 color1 = getFromColor(p);
  vec4 color2 = getToColor(p);
  vec2 disp = displace(color1, p, 0.33, 0.7, 1.0-ease1(progress));
  vec2 disp2 = displace(color2, p, 0.33, 0.5, ease2(progress));
  vec4 dColor1 = getToColor(disp);
  vec4 dColor2 = getFromColor(disp2);
  float val = ease1(progress);
  vec3 gray = vec3(dot(min(dColor2, dColor1).rgb, vec3(0.299, 0.587, 0.114)));
  dColor2 = vec4(gray, 1.0);
  dColor2 *= 2.0;
  color1 = mix(color1, dColor2, smoothstep(0.0, 0.5, progress));
  color2 = mix(color2, dColor1, smoothstep(1.0, 0.5, progress));
  return mix(color1, color2, val);
  //gl_FragColor = mix(gl_FragColor, dColor, smoothstep(0.0, 0.5, progress));

   //gl_FragColor = mix(texture(from, p), texture(to, p), progress);
}

void main() {
    progress = u_progress;
    ratio = u_resolution.x / max(u_resolution.y, 1.0);
    fragColor = transition(vec2(v_texCoord.x, 1.0 - v_texCoord.y));
}
