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

// --- upstream: Slides.glsl ---
// Author: Mark Craig
// mrmcsoftware on github and youtube ( http://www.youtube.com/MrMcSoftware )
// License: MIT

// Slides Transition by Mark Craig (Copyright © 2022)

uniform float p_type;
#define type int(p_type)
uniform float p_In;
#define In (p_In > 0.5)

// type: slide to/from which edge, which corner, or center
// In: if true slide new image in, otherwise slide old image out

#define rad2 rad / 2.0

vec4 transition(vec2 uv)
{
vec2 uv0 = uv;
float rad = In ? progress : 1.0 - progress;
float xc1, yc1;
// I used if/else instead of switch in case it's an old GPU
if (type == 0) { xc1 = .5 - rad2; yc1 = 0.0; }
else if (type == 1) { xc1 = 1.0 - rad; yc1 = .5 - rad2; }
else if (type == 2) { xc1 = .5 - rad2; yc1 = 1.0 - rad; }
else if (type == 3) { xc1 = 0.0; yc1 = .5 - rad2; }
else if (type == 4) { xc1 = 1.0 - rad; yc1 = 0.0; }
else if (type == 5) { xc1 = 1.0 - rad; yc1 = 1.0 - rad; }
else if (type == 6) { xc1 = 0.0; yc1 = 1.0 - rad; }
else if (type == 7) { xc1 = 0.0; yc1 = 0.0; }
else if (type == 8) { xc1 = .5 - rad2; yc1 = .5 - rad2; }
uv.y = 1.0 - uv.y;
vec2 uv2;
if ((uv.x >= xc1) && (uv.x <= xc1 + rad) && (uv.y >= yc1) && (uv.y <= yc1 + rad))
	{
	uv2 = vec2((uv.x - xc1) / rad, 1.0 - (uv.y - yc1) / rad);
	return(In ? getToColor(uv2) : getFromColor(uv2));
	}
return(In ? getFromColor(uv0) : getToColor(uv0));
}

void main() {
    progress = u_progress;
    ratio = u_resolution.x / max(u_resolution.y, 1.0);
    fragColor = transition(vec2(v_texCoord.x, 1.0 - v_texCoord.y));
}
