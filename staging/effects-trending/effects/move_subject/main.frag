#version 330 core
in vec2 v_texCoord;
out vec4 fragColor;

uniform sampler2D u_currentTexture;
uniform sampler2D u_texture1;
uniform sampler2D u_texture2;
uniform sampler2D u_texture3;
uniform sampler2D u_texture4;
uniform vec2 u_resolution;
uniform float u_time;
uniform float offsetX;
uniform float offsetY;
uniform float rotation;
uniform float scale;
uniform float squash;
uniform float shadow;
uniform float shake;
uniform float background;

float unpack16(vec2 v) { return v.x + v.y / 255.0; }

float wob(float t, float k) {
    return (sin(t * 1.3 + k) + 0.6 * sin(t * 2.71 + k * 2.3) + 0.35 * sin(t * 5.13 + k * 0.7)) / 1.95;
}

vec4 fill(vec2 uv) {
    vec2 sz = vec2(textureSize(u_texture2, 0));
    vec2 p = uv * sz - 0.5;
    vec2 f = fract(p);
    ivec2 i0 = ivec2(floor(p));
    ivec2 hi = ivec2(sz) - 1;
    vec4 acc = vec4(0.0);
    for (int k = 0; k < 4; ++k) {
        ivec2 o = ivec2(k & 1, k >> 1);
        vec4 s = texelFetch(u_texture2, clamp(i0 + o, ivec2(0), hi), 0);
        float w = ((k & 1) == 0 ? 1.0 - f.x : f.x) * ((k >> 1) == 0 ? 1.0 - f.y : f.y);
        acc += vec4(s.rgb * s.a, s.a) * w;
    }
    return vec4(acc.a > 1e-5 ? acc.rgb / acc.a : vec3(0.0), acc.a);
}

void main() {
    vec2 uv = v_texCoord;
    vec4 src = texture(u_currentTexture, uv);
    vec4 geo = texelFetch(u_texture4, ivec2(0), 0);
    if (geo.a < 0.5) {
        fragColor = src;
        return;
    }
    float asp = u_resolution.x / max(u_resolution.y, 1.0);
    vec2 A = vec2(asp, 1.0);
    vec4 pv = texelFetch(u_texture3, ivec2(0), 0);
    vec2 pivotUv = vec2(unpack16(pv.rg), unpack16(pv.ba));

    float sq = 1.0 + squash;
    vec2 sc = max(scale, 1e-3) * vec2(sq, 1.0 / sq);
    float th = radians(rotation);
    float c = cos(th);
    float s = sin(th);
    vec2 q = (uv - pivotUv - vec2(offsetX, offsetY)) * A;
    vec2 local = vec2(c * q.x + s * q.y, -s * q.x + c * q.y) / sc;
    vec2 sUv = pivotUv + local / A;
    float inside = step(0.0, sUv.x) * step(sUv.x, 1.0) * step(0.0, sUv.y) * step(sUv.y, 1.0);
    float sa = driftMask(sUv) * inside;
    vec3 sCol = texture(u_currentTexture, sUv).rgb;

    vec3 bg = vec3(0.0);
    float ba = 0.0;
    int mode = int(background + 0.5);
    if (mode != 2) {
        float t = u_time * 9.0;
        vec2 sh = shake * 0.03 * vec2(wob(t, 0.0), wob(t, 4.1));
        vec2 bUv = (uv - 0.5) / (1.0 + 0.065 * shake) + 0.5 + sh;
        vec4 b = texture(u_currentTexture, bUv);
        bg = b.rgb;
        ba = b.a;
        if (mode == 1) {
            float hole = texture(u_texture1, bUv).r;
            vec4 f = fill(bUv);
            bg = mix(bg, f.rgb, hole * smoothstep(0.0, 0.02, f.a));
        }
    }

    float lift = max(0.0, -offsetY);
    float k = 1.0 / (1.0 + 4.0 * lift);
    vec2 feet = geo.rg;
    float rx = max(0.55 * geo.b * asp * k, 1e-4);
    float ry = rx * 0.22;
    vec2 d = (uv - feet) * A - vec2(0.0, -0.2 * ry);
    float e = length(d / vec2(rx, ry));
    float shA = shadow * k * (1.0 - smoothstep(0.2, 1.0, e));

    vec3 pc = bg * ba;
    float a = ba;
    pc *= 1.0 - shA;
    a = shA + a * (1.0 - shA);
    pc = sCol * sa + pc * (1.0 - sa);
    a = sa + a * (1.0 - sa);
    fragColor = vec4(a > 1e-5 ? pc / a : vec3(0.0), a);
}
