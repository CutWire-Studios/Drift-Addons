#version 330 core
in vec2 v_texCoord; out vec4 fragColor;
uniform sampler2D u_currentTexture;
uniform vec2 u_resolution;
#define SRC u_currentTexture

// Runs as a single texel: the shape's bounding box, from a 64x64 sample grid, as (min, max) in uv.
// Dashes and edge textures measure along the outline by casting rays from its centre, so a sticker
// that sits off-centre in its clip still gets evenly spaced dashes.

// ---- shared with composite.frag (packages cannot #include) ----
uniform float source;
uniform float threshold;
uniform float width;
uniform float strokePosition;
uniform float offset;
uniform float frameRadius;
uniform float fitInside;
uniform float outline2;
uniform float width2;
uniform float offset2;
uniform float wobble;
uniform float glow;
uniform float glowSize;
uniform float shadow;
uniform float shadowDistance;
uniform float shadowBlur;
uniform float shadowSpread;

// Sizes are authored against a 1080-pixel short side, so they track the clip, not its pixel count.
float unitPx() { return min(u_resolution.x, u_resolution.y) / 1080.0; }

// Outer edge of the first stroke, in authored units, measured outward from the shape.
float stroke1Hi()
{
    if (width <= 0.0)
        return 0.0;
    float hi = strokePosition < 0.5 ? offset + width : strokePosition < 1.5 ? offset + width * 0.5 : -offset;
    return max(hi, 0.0);
}

float silhouette()
{
    float e = stroke1Hi();
    if (outline2 > 0.5 && width2 > 0.0)
        e += offset2 + width2;
    return e;
}

// How far the content is scaled down so everything drawn outside it still lands in the clip.
float contentScale()
{
    float s = silhouette();
    float e = s + wobble;
    if (glow > 0.5)
        e = max(e, s + glowSize);
    if (shadow > 0.5)
        e = max(e, s + shadowSpread + shadowBlur + shadowDistance);
    if (fitInside < 0.5 || e <= 0.0)
        return 1.0;
    float pad = e * unitPx() + 1.0;
    vec2 fit = (u_resolution - 2.0 * pad) / u_resolution;
    return clamp(min(fit.x, fit.y), 0.05, 1.0);
}

vec2 contentUv(vec2 px, float sc) { return (px / u_resolution - 0.5) / sc + 0.5; }

bool inContent(vec2 uv) { return all(greaterThanEqual(uv, vec2(0.0))) && all(lessThanEqual(uv, vec2(1.0))); }

float frameCoverage(vec2 px, float sc)
{
    vec2 hs = u_resolution * sc * 0.5;
    float r = min(frameRadius * unitPx(), min(hs.x, hs.y));
    vec2 q = abs(px - u_resolution * 0.5) - hs + r;
    float dist = length(max(q, 0.0)) + min(max(q.x, q.y), 0.0) - r;
    return clamp(0.5 - dist, 0.0, 1.0);
}

float maskAt(vec2 uv) { return u_hasClipMask > 0.5 ? driftMask(uv) : 1.0; }

float shapeAt(vec2 px, float sc)
{
    vec2 uv = contentUv(px, sc);
    if (!inContent(uv))
        return 0.0;
    if (source > 1.5)
        return frameCoverage(px, sc);
    vec4 c = texture(SRC, uv);
    float a = c.a * maskAt(uv);
    return source > 0.5 ? a * dot(c.rgb, vec3(0.2126, 0.7152, 0.0722)) : a;
}

bool insideAt(vec2 px, float sc)
{
    return shapeAt(px, sc) >= (source > 1.5 ? 0.5 : max(threshold, 0.002));
}
// ---- end shared ----

void main()
{
    float sc = contentScale();
    vec2 lo = vec2(1.0);
    vec2 hi = vec2(0.0);
    for (int j = 0; j < 64; ++j) {
        for (int i = 0; i < 64; ++i) {
            vec2 uv = (vec2(float(i), float(j)) + 0.5) / 64.0;
            if (insideAt(uv * u_resolution, sc)) {
                lo = min(lo, uv);
                hi = max(hi, uv);
            }
        }
    }
    // Widen by half a cell so the box reaches the edge between samples.
    fragColor = hi.x >= lo.x ? vec4(clamp(lo - 0.5 / 64.0, 0.0, 1.0), clamp(hi + 0.5 / 64.0, 0.0, 1.0)) : vec4(0.0);
}
