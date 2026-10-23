#version 330 core
in vec2 v_texCoord; out vec4 fragColor;
uniform sampler2D u_currentTexture; // jump-flood offsets to the nearest boundary texel
uniform sampler2D u_texture1;       // the clip
uniform sampler2D u_texture2;       // the shape's bounding box, from bounds.frag
uniform vec2 u_resolution;
uniform float u_time;
#define SRC u_texture1

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

uniform vec4 color;
uniform float corners;
uniform float softness;
uniform float hideContent;

uniform float fillType;
uniform vec4 color2;
uniform float gradientAngle;
uniform float gradientSpeed;

uniform float dashed;
uniform float dashLength;
uniform float dashGap;
uniform float roundCaps;
uniform float dashSpeed;

uniform vec4 color3;

uniform float wobbleScale;
uniform float widthJitter;
uniform float boil;

uniform float innerEdge;
uniform float innerDepth;
uniform float innerScale;
uniform float outerEdge;
uniform float outerDepth;
uniform float outerScale;
uniform float edgeSeed;
uniform vec4 rimColor;
uniform float rimWidth;
uniform vec3 burnColor;
uniform vec4 emberColor;

uniform vec4 shadowColor;
uniform float shadowAngle;
uniform float innerShadow;
uniform vec4 innerShadowColor;
uniform float innerShadowAngle;
uniform float innerShadowDistance;
uniform float innerShadowBlur;
uniform float innerShadowSpread;

uniform vec4 glowColor;
uniform float glowIntensity;
uniform float innerGlow;
uniform vec4 innerGlowColor;
uniform float innerGlowSize;
uniform float innerGlowIntensity;

bool unpack(vec4 c, out vec2 off)
{
    vec3 b = floor(c.rgb * 255.0 + 0.5);
    float hi = floor(b.g / 16.0);
    vec2 v = vec2(b.r * 16.0 + hi, (b.g - hi * 16.0) * 256.0 + b.b);
    off = v - 2048.0;
    return v.x > 0.0;
}

float hash11(float p)
{
    p = fract(p * 0.1031);
    p *= p + 33.33;
    p *= p + p;
    return fract(p);
}

float hash21(vec2 p)
{
    vec3 p3 = fract(vec3(p.xyx) * 0.1031);
    p3 += dot(p3, p3.yzx + 33.33);
    return fract((p3.x + p3.y) * p3.z);
}

float vnoise(vec2 p)
{
    vec2 i = floor(p);
    vec2 f = fract(p);
    vec2 u = f * f * (3.0 - 2.0 * f);
    return mix(mix(hash21(i), hash21(i + vec2(1.0, 0.0)), u.x),
               mix(hash21(i + vec2(0.0, 1.0)), hash21(i + vec2(1.0)), u.x), u.y);
}

// Value noise along the outline that repeats every n cells, so it closes up seamlessly.
float pnoise(float u, float n, float salt)
{
    float i = floor(u);
    float f = fract(u);
    float a = hash11(mod(i, n) + salt * 101.0 + edgeSeed * 7.31);
    float b = hash11(mod(i + 1.0, n) + salt * 101.0 + edgeSeed * 7.31);
    return mix(a, b, f * f * (3.0 - 2.0 * f));
}

float pfbm(float u, float n, float salt)
{
    float v = 0.0;
    float amp = 0.5;
    for (int o = 0; o < 4; ++o) {
        v += amp * pnoise(u, n, salt + float(o));
        u *= 2.0;
        n *= 2.0;
        amp *= 0.5;
    }
    return v / 0.9375;
}

// Antialiased step: 1 where x > 0. fwidth keeps steep edge profiles (zigzag, perforations) crisp.
float aa(float x, float soft)
{
    float w = max(soft, 0.5 * fwidth(x));
    return smoothstep(-w, w, x);
}

vec2 boilOffset()
{
    float frame = boil > 0.0 ? floor(u_time * boil) : 0.0;
    return vec2(frame * 17.13 + edgeSeed * 3.7, frame * -9.71);
}

// Distance travelled along the shape's bounding box to the point where the ray from the box's
// centre through b meets it. Exact for rectangles (images, video, frames) and close enough for
// stickers; it gives dashes and edge textures a coordinate along the outline. P is the perimeter.
float perimeterParam(vec2 b, float sc, out float P)
{
    vec4 bounds = texelFetch(u_texture2, ivec2(0), 0);
    vec2 c = u_resolution * 0.5;
    vec2 hs = u_resolution * sc * 0.5;
    if (bounds.z > bounds.x) {
        c = (bounds.xy + bounds.zw) * 0.5 * u_resolution;
        hs = (bounds.zw - bounds.xy) * 0.5 * u_resolution;
    }
    hs = max(hs, vec2(1.0));
    vec2 dir = b - c;
    P = 4.0 * (hs.x + hs.y);
    if (abs(dir.x) * hs.y >= abs(dir.y) * hs.x) {
        float y = dir.y * hs.x / max(abs(dir.x), 1e-4);
        return dir.x >= 0.0 ? 2.0 * hs.x + (y + hs.y) : 4.0 * hs.x + 2.0 * hs.y + (hs.y - y);
    }
    float x = dir.x * hs.y / max(abs(dir.y), 1e-4);
    return dir.y < 0.0 ? x + hs.x : 2.0 * hs.x + 2.0 * hs.y + (hs.x - x);
}

float metric(vec2 v)
{
    v = abs(v);
    if (corners < 0.5)
        return length(v);
    if (corners < 1.5)
        return max(v.x, v.y);
    return max(max(v.x, v.y), (v.x + v.y) * 0.70710678);
}

// Signed distance to the shape's edge at q, in px: negative inside. s/P locate the nearest edge
// point along the outline.
float field(vec2 q, float sc, float k, out float s, out float P)
{
    ivec2 size = ivec2(u_resolution);
    ivec2 ip = clamp(ivec2(floor(q)), ivec2(0), size - 1);
    vec2 o;
    bool ok = unpack(texelFetch(u_currentTexture, ip, 0), o);
    bool inside = insideAt(q, sc);
    s = 0.0;
    P = 1.0;
    if (!ok)
        return inside ? -1e4 : 1e4;
    vec2 b = vec2(ip) + 0.5 + o;
    s = perimeterParam(b, sc, P);
    float dist = metric(b - q);
    float d = inside ? -(dist + 0.5) : dist - 0.5;
    if (wobble > 0.0)
        d += wobble * k * (vnoise(q / (max(wobbleScale, 1.0) * k) + boilOffset()) * 2.0 - 1.0);
    return d;
}

// How far a point lies inside the material (content or stroke) once an edge texture has cut it.
// n is the untextured distance inward from the edge; s/P place the point along the outline.
float edgeMaterial(float style, float n, float s, float P, float depth, float scale, float salt)
{
    if (style < 0.5 || depth <= 0.0)
        return n;
    float N = max(1.0, floor(P / max(scale, 1.0) + 0.5));
    float u = s / P * N;
    float x = fract(u);
    if (style < 1.5) // torn paper: ragged fbm with fine fibres
        return n - depth * clamp(0.85 * pfbm(u, N, salt) + 0.15 * pnoise(u * 8.0, N * 8.0, salt + 9.0), 0.0, 1.0);
    if (style < 2.5) // burnt: broad, uneven bites
        return n - depth * pfbm(u * 0.5, N * 0.5, salt + 20.0);
    if (style < 3.5) { // stamp: round perforations centred on the edge
        float hole = length(vec2((x - 0.5) * P / N, n)) - min(depth * 0.5, 0.45 * P / N);
        return min(n, hole);
    }
    if (style < 4.5) // pinking-shear zigzag
        return n - depth * abs(x * 2.0 - 1.0);
    if (style < 5.5) { // scallops
        float xx = x * 2.0 - 1.0;
        return n - depth * (1.0 - sqrt(max(1.0 - xx * xx, 0.0)));
    }
    if (style < 6.5) // tape torn on a dispenser: uneven serration
        return n - depth * abs(x * 2.0 - 1.0) * (0.45 + 0.55 * hash11(mod(floor(u), N) + salt * 13.0 + edgeSeed));
    if (style < 7.5) // wavy
        return n - depth * (0.5 - 0.5 * cos(6.2831853 * x));
    // rough: fine grain
    return n - depth * (0.5 * pnoise(u * 2.0, N * 2.0, salt + 30.0) + 0.5 * pnoise(u * 7.0, N * 7.0, salt + 31.0));
}

vec3 edgeShading(vec3 rgb, float m, float style, float s, float depth, float k)
{
    if (style < 0.5)
        return rgb;
    if (rimWidth > 0.0) {
        float rw = rimWidth * k;
        if (style < 1.5) // torn paper shows a fibrous white core of uneven width
            rw *= 0.45 + 0.55 * vnoise(vec2(s / (2.5 * k), 1.3 + edgeSeed));
        rgb = mix(rgb, rimColor.rgb, rimColor.a * (1.0 - smoothstep(rw - 0.75, rw + 0.75, m)));
    }
    if (style > 1.5 && style < 2.5) {
        float n = vnoise(vec2(s, m) / (6.0 * k) + edgeSeed);
        float charW = max(depth * 0.75, 2.0 * k);
        rgb = mix(rgb, burnColor, 0.92 * (1.0 - smoothstep(0.0, charW * (0.6 + 0.8 * n), m)));
        float ember = 1.0 - smoothstep(0.0, 2.5 * k * (0.5 + n), m);
        rgb = mix(rgb, emberColor.rgb, ember * emberColor.a * (0.5 + 0.5 * n));
    }
    return rgb;
}

vec3 hsv2rgb(vec3 c)
{
    vec3 p = abs(fract(c.xxx + vec3(1.0, 2.0 / 3.0, 1.0 / 3.0)) * 6.0 - 3.0);
    return c.z * mix(vec3(1.0), clamp(p - 1.0, 0.0, 1.0), c.y);
}

vec4 strokeFill(vec2 px, float s, float P)
{
    if (fillType < 0.5)
        return color;
    float along = s / P;
    if (fillType > 3.5)
        return vec4(hsv2rgb(vec3(fract(along - gradientSpeed * u_time), 0.85, 1.0)), color.a);
    if (fillType > 2.5)
        return mix(color, color2, 0.5 - 0.5 * cos(6.2831853 * (along - gradientSpeed * u_time)));
    vec2 h = u_resolution * 0.5;
    float t;
    if (fillType < 1.5) {
        float a = radians(gradientAngle);
        vec2 dir = vec2(cos(a), sin(a));
        t = dot(px - h, dir) / max(dot(abs(dir), h), 1.0) * 0.5 + 0.5;
    } else {
        t = length((px - h) / h) / 1.4142136;
    }
    // Triangle wave: equals t at rest, and scrolls back and forth without a seam when animated.
    t = 1.0 - abs(fract((t + gradientSpeed * u_time) * 0.5) * 2.0 - 1.0);
    return mix(color, color2, t);
}

vec2 dirOf(float degrees)
{
    float a = radians(degrees);
    return vec2(cos(a), sin(a));
}

float band(float d, float lo, float hi, float soft) { return aa(d - lo, soft) * aa(hi - d, soft); }

void over(inout vec4 acc, vec3 rgb, float a)
{
    a = clamp(a, 0.0, 1.0);
    acc = vec4(rgb * a, a) + acc * (1.0 - a);
}

void main()
{
    float k = unitPx();
    float sc = contentScale();
    vec2 px = gl_FragCoord.xy;
    float soft = softness * k;

    vec2 uv = contentUv(px, sc);
    bool inBox = inContent(uv);
    vec4 src = inBox ? texture(SRC, uv) : vec4(0.0);
    float contentA = inBox ? src.a * maskAt(uv) : 0.0;
    if (source > 1.5)
        contentA *= frameCoverage(px, sc);

    float s;
    float P;
    float d = field(px, sc, k, s, P);

    // Stroke bands, in px outward from the edge.
    bool hasStroke1 = width > 0.0;
    float w1 = width * k * (1.0 - widthJitter * vnoise(vec2(s / (max(wobbleScale, 1.0) * k), 3.7) + boilOffset()));
    float o1 = offset * k;
    float lo1 = strokePosition < 0.5 ? o1 : strokePosition < 1.5 ? o1 - w1 * 0.5 : -o1 - w1;
    float hi1 = strokePosition < 0.5 ? o1 + w1 : strokePosition < 1.5 ? o1 + w1 * 0.5 : -o1;
    bool hasStroke2 = outline2 > 0.5 && width2 > 0.0;
    float lo2 = (hasStroke1 ? max(hi1, 0.0) : 0.0) + offset2 * k;
    float hi2 = lo2 + width2 * k;
    float silh = hasStroke2 ? hi2 : hasStroke1 ? max(hi1, 0.0) : 0.0;

    // Edge textures. Inner cuts into the content; outer cuts the outermost stroke.
    float innerM = edgeMaterial(innerEdge, -d, s, P, innerDepth * k, innerScale * k, 1.0);
    float outerM = edgeMaterial(outerEdge, silh - d, s, P, outerDepth * k, outerScale * k, 2.0);
    float outerCut = aa(outerM, soft);
    float contentCut = aa(innerM, soft);
    if (!hasStroke1 && !hasStroke2)
        contentCut *= outerCut;
    bool showContent = hideContent < 0.5;

    // Stroke 1. Outside and touching the shape, it runs on under the content, which closes the
    // seam on soft edges and fills whatever an inner edge texture tears out.
    bool under = strokePosition < 0.5;
    float c1 = 0.0;
    if (hasStroke1) {
        bool fillUnder = under && showContent && offset <= 0.0 && dashed < 0.5;
        c1 = fillUnder ? aa(hi1 - d, soft) : band(d, lo1, hi1, soft);
        if (dashed > 0.5) {
            float period = (dashLength + dashGap) * k;
            float N = max(1.0, floor(P / period + 0.5));
            float stretch = P / (N * period);
            float pd = period * stretch;
            float halfL = dashLength * k * stretch * 0.5;
            float m = mod(s - dashSpeed * k * u_time, pd);
            float along = min(abs(m - halfL), abs(m - pd - halfL));
            if (roundCaps > 0.5) {
                float r = max((hi1 - lo1) * 0.5, 0.0);
                float caps = length(vec2(max(along - max(halfL - r, 0.0), 0.0), d - (hi1 + lo1) * 0.5)) - r;
                c1 = aa(-caps, soft);
            } else {
                c1 *= aa(halfL - along, soft);
            }
        }
        if (!hasStroke2)
            c1 *= outerCut;
    }
    float c2 = hasStroke2 ? band(d, lo2, hi2, soft) * outerCut : 0.0;

    vec4 acc = vec4(0.0);

    if (shadow > 0.5) {
        float ss;
        float sp;
        float ds = field(px - dirOf(shadowAngle) * shadowDistance * k, sc, k, ss, sp);
        float bw = max(shadowBlur * k, 0.5);
        float cov;
        if (showContent) {
            cov = 1.0 - smoothstep(-bw, bw, ds - silh - shadowSpread * k);
        } else {
            float grow = shadowSpread * k;
            cov = max(hasStroke1 ? band(ds, lo1 - grow, hi1 + grow, bw) : 0.0,
                      hasStroke2 ? band(ds, lo2 - grow, hi2 + grow, bw) : 0.0);
        }
        over(acc, shadowColor.rgb, cov * shadowColor.a);
    }

    if (glow > 0.5) {
        float g = 1.0 - clamp(-outerM / max(glowSize * k, 1.0), 0.0, 1.0);
        over(acc, glowColor.rgb, g * g * glowIntensity * glowColor.a);
    }

    if (hasStroke2)
        over(acc, edgeShading(color3.rgb, outerM, outerEdge, s, outerDepth * k, k), c2 * color3.a);

    vec4 fill1 = strokeFill(px, s, P);
    vec3 rgb1 = hasStroke2 ? fill1.rgb : edgeShading(fill1.rgb, outerM, outerEdge, s, outerDepth * k, k);
    if (hasStroke1 && under)
        over(acc, rgb1, c1 * fill1.a);

    if (showContent) {
        float a = contentA * contentCut;
        vec3 rgb = edgeShading(src.rgb, innerM, innerEdge, s, innerDepth * k, k);
        if (!hasStroke1 && !hasStroke2)
            rgb = edgeShading(rgb, outerM, outerEdge, s, outerDepth * k, k);
        over(acc, rgb, a);

        if (innerShadow > 0.5) {
            float is;
            float ip;
            float di = field(px - dirOf(innerShadowAngle) * innerShadowDistance * k, sc, k, is, ip);
            float bi = max(innerShadowBlur * k, 0.5);
            float amt = smoothstep(-bi, bi, di + innerShadowSpread * k);
            over(acc, innerShadowColor.rgb, amt * innerShadowColor.a * a);
        }
        if (innerGlow > 0.5) {
            float g = 1.0 - clamp(innerM / max(innerGlowSize * k, 1.0), 0.0, 1.0);
            over(acc, innerGlowColor.rgb, g * g * innerGlowIntensity * innerGlowColor.a * a);
        }
    }

    if (hasStroke1 && !under)
        over(acc, rgb1, c1 * fill1.a);

    // Layer targets are straight alpha.
    fragColor = acc.a > 1e-5 ? vec4(acc.rgb / acc.a, acc.a) : vec4(0.0);
}
