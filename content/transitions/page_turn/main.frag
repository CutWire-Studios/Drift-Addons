#version 330 core
in vec2 v_texCoord;
out vec4 fragColor;

uniform sampler2D u_currentTexture;
uniform sampler2D u_fromTexture;
uniform sampler2D u_toTexture;
uniform vec2 u_resolution;
uniform float u_progress;

float hash11(float p) {
    p = fract(p * 0.1031);
    p *= p + 33.33;
    p *= p + p;
    return fract(p);
}

float hash21(vec2 p) {
    vec3 p3 = fract(vec3(p.xyx) * 0.1031);
    p3 += dot(p3, p3.yzx + 33.33);
    return fract((p3.x + p3.y) * p3.z);
}

vec2 hash22(vec2 p) {
    vec3 p3 = fract(vec3(p.xyx) * vec3(0.1031, 0.1030, 0.0973));
    p3 += dot(p3, p3.yzx + 33.33);
    return fract((p3.xx + p3.yz) * p3.zy);
}

float valueNoise(vec2 p) {
    vec2 i = floor(p);
    vec2 f = fract(p);
    f = f * f * (3.0 - 2.0 * f);
    float a = hash21(i);
    float b = hash21(i + vec2(1.0, 0.0));
    float c = hash21(i + vec2(0.0, 1.0));
    float d = hash21(i + vec2(1.0, 1.0));
    return mix(mix(a, b, f.x), mix(c, d, f.x), f.y);
}

float fbm(vec2 p) {
    float v = 0.0;
    float amp = 0.5;
    for (int i = 0; i < 5; ++i) {
        v += amp * valueNoise(p);
        p *= 2.02;
        amp *= 0.5;
    }
    return v;
}

vec4 over(vec4 top, vec4 bot) {
    float oa = top.a + bot.a * (1.0 - top.a);
    if (oa <= 0.0001) return vec4(0.0);
    vec3 rgb = (top.rgb * top.a + bot.rgb * bot.a * (1.0 - top.a)) / oa;
    return vec4(rgb, oa);
}

float aspectRatio() { return u_resolution.x / max(u_resolution.y, 1.0); }


uniform float curl; uniform float shadow; uniform float angle;

void main() {
    vec2 uv = v_texCoord;
    float aspect = aspectRatio();
    // Progressive peel from the right edge with a cylindrical curl.
    float p = clamp(u_progress, 0.0, 1.0);
    float edge = 1.0 - p * (1.0 + curl * 0.35);
    float x = uv.x + (uv.y - 0.5) * angle * 0.25;
    float d = x - edge;

    if (d < 0.0) {
        // Still on the outgoing page
        float sh = smoothstep(0.0, 0.25, -d) * shadow * p;
        vec4 from = texture(u_fromTexture, uv);
        from.rgb *= 1.0 - sh * 0.55;
        fragColor = over(from, texture(u_toTexture, uv));
        return;
    }

    float R = mix(0.18, 0.55, curl);
    if (d < 3.14159265 * R) {
        float theta = d / R;
        float mapped = edge - sin(theta) * R;
        float z = (1.0 - cos(theta)) * R;
        vec2 suv = vec2(mapped, uv.y);
        // Back-face of the turning page (slightly darkened mirror of from)
        if (theta > 1.5707963) {
            float backX = edge - sin(3.14159265 - theta) * R;
            suv.x = backX;
            vec4 page = texture(u_fromTexture, clamp(vec2(2.0 * edge - suv.x, suv.y), 0.0, 1.0));
            page.rgb *= 0.55;
            float sh = shadow * smoothstep(0.0, 0.4, z);
            vec4 under = texture(u_toTexture, uv);
            under.rgb *= 1.0 - sh * 0.7;
            fragColor = over(page, under);
            return;
        }
        vec4 page = texture(u_fromTexture, clamp(suv, 0.0, 1.0));
        float sh = shadow * smoothstep(0.0, 0.35, z);
        vec4 under = texture(u_toTexture, uv);
        under.rgb *= 1.0 - sh * 0.65;
        fragColor = over(page, under);
        return;
    }

    fragColor = texture(u_toTexture, uv);
}
