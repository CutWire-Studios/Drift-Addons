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

// --- upstream: Box.glsl ---
// Author: lql
// License: MIT

uniform float p_rectIn;
#define rectIn int(p_rectIn)
uniform float p_location;
#define location int(p_location)

// center:0, left_top:1, left_bottom:2, right_top:3, right_bottom:4

vec4 transition(vec2 uv) {
    float p = rectIn == 1 ? 1.0 - progress : progress;
    float x1, y1, x2, y2;

    // Determine rectangle coordinates based on location
    if (location == 0) {
        x1 = y1 = 0.5 * (1.0 - p);
        x2 = y2 = 1.0 - x1;
    } else {
        // Calculate the x and y coordinates based on the location
        x1 = (location == 1 || location == 2) ? 0.0 : 1.0 - p;
        y1 = (location == 1 || location == 3) ? 1.0 - p : 0.0;
        x2 = (location == 1 || location == 2) ? p : 1.0;
        y2 = (location == 1 || location == 3) ? 1.0 : p;
    }

    // Determine if the point is inside the rectangle
    float in_rect = step(x1, uv.x) * step(uv.x, x2) * step(y1, uv.y) * step(uv.y, y2);
    in_rect = rectIn == 1 ? 1.0 - in_rect : in_rect;

    // Mix colors based on the in_rect value
    return mix(getFromColor(uv), getToColor(uv), in_rect);
}

void main() {
    progress = u_progress;
    ratio = u_resolution.x / max(u_resolution.y, 1.0);
    fragColor = transition(vec2(v_texCoord.x, 1.0 - v_texCoord.y));
}
