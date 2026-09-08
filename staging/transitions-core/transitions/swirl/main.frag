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

// --- upstream: Swirl.glsl ---
// License: MIT
// Author: Sergey Kosarevsky
// ( http://www.linderdaum.com )
// ported by gre from https://gist.github.com/corporateshark/cacfedb8cca0f5ce3f7c

vec4 transition(vec2 UV)
{
	float Radius = 1.0;

	float T = progress;

	UV -= vec2( 0.5, 0.5 );

	float Dist = length(UV);

	if ( Dist < Radius )
	{
		float Percent = (Radius - Dist) / Radius;
		float A = ( T <= 0.5 ) ? mix( 0.0, 1.0, T/0.5 ) : mix( 1.0, 0.0, (T-0.5)/0.5 );
		float Theta = Percent * Percent * A * 8.0 * 3.14159;
		float S = sin( Theta );
		float C = cos( Theta );
		UV = vec2( dot(UV, vec2(C, -S)), dot(UV, vec2(S, C)) );
	}
	UV += vec2( 0.5, 0.5 );

	vec4 C0 = getFromColor(UV);
	vec4 C1 = getToColor(UV);

	return mix( C0, C1, T );
}

void main() {
    progress = u_progress;
    ratio = u_resolution.x / max(u_resolution.y, 1.0);
    fragColor = transition(vec2(v_texCoord.x, 1.0 - v_texCoord.y));
}
