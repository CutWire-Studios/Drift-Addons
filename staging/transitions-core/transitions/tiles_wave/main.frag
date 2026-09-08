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

// --- upstream: TilesWave.glsl ---
// Author: numb3r23
// License: MIT
// Ported from https://gist.github.com/numb3r23/169781bb76f310e2bfde

uniform float p_tileCount_x;
uniform float p_tileCount_y;
#define tileCount ivec2(int(p_tileCount_x), int(p_tileCount_y))
uniform float p_flipX;
#define flipX (p_flipX > 0.5)
uniform float p_flipY;
#define flipY (p_flipY > 0.5)

vec4 transition(vec2 uv) {
  vec2 tileSize = 1.0 / vec2(tileCount);
  vec2 posInTile = fract(uv * vec2(tileCount));
  vec2 tileNum = floor(uv * vec2(tileCount));
  float countTiles = float(tileCount.x * tileCount.y);

  // Diagonal wave from bottom-left to top-right
  float offset = (tileNum.y + tileNum.x * float(tileCount.y)) / countTiles;
  float timeOffset = clamp((progress - offset) * countTiles, 0.0, 0.5);
  float sinTime = 1.0 - abs(cos(fract(timeOffset) * 3.1415926));

  vec2 texC = posInTile;

  if (sinTime <= 0.5) {
    if (flipX) {
      if (texC.x < sinTime || texC.x > 1.0 - sinTime)
        return getFromColor(uv);
      texC.x = texC.x < 0.5
        ? (texC.x - sinTime) * 0.5 / (0.5 - sinTime)
        : (texC.x - 0.5) * 0.5 / (0.5 - sinTime) + 0.5;
    }
    if (flipY) {
      if (texC.y < sinTime || texC.y > 1.0 - sinTime)
        return getFromColor(uv);
      texC.y = texC.y < 0.5
        ? (texC.y - sinTime) * 0.5 / (0.5 - sinTime)
        : (texC.y - 0.5) * 0.5 / (0.5 - sinTime) + 0.5;
    }
    vec2 globalUV = tileNum * tileSize + texC * tileSize;
    return getFromColor(globalUV);
  } else {
    if (flipX) {
      if (texC.x > sinTime || texC.x < 1.0 - sinTime)
        return getToColor(uv);
      texC.x = texC.x < 0.5
        ? (texC.x - sinTime) * 0.5 / (0.5 - sinTime)
        : (texC.x - 0.5) * 0.5 / (0.5 - sinTime) + 0.5;
      texC.x = 1.0 - texC.x;
    }
    if (flipY) {
      if (texC.y > sinTime || texC.y < 1.0 - sinTime)
        return getToColor(uv);
      texC.y = texC.y < 0.5
        ? (texC.y - sinTime) * 0.5 / (0.5 - sinTime)
        : (texC.y - 0.5) * 0.5 / (0.5 - sinTime) + 0.5;
      texC.y = 1.0 - texC.y;
    }
    vec2 globalUV = tileNum * tileSize + texC * tileSize;
    return getToColor(globalUV);
  }
}

void main() {
    progress = u_progress;
    ratio = u_resolution.x / max(u_resolution.y, 1.0);
    fragColor = transition(vec2(v_texCoord.x, 1.0 - v_texCoord.y));
}
