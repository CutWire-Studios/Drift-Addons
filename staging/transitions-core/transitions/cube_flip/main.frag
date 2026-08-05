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


uniform float perspective; uniform float direction;

void main() {
    vec2 uv = v_texCoord;
    float p = clamp(u_progress, 0.0, 1.0);
    int dir = int(clamp(floor(direction + 0.5), 0.0, 3.0));
    bool horizontal = (dir == 0 || dir == 1);
    bool reverse = (dir == 1 || dir == 3);

    float ang = p * 1.5707963;
    if (reverse) ang = -ang;
    float ca = cos(ang);
    float sa = sin(ang);
    float persp = mix(0.35, 1.2, perspective);

    vec2 q = uv * 2.0 - 1.0;
    float axis = horizontal ? q.x : q.y;
    float other = horizontal ? q.y : q.x;

    // Project rotating face
    float x1 = axis * ca;
    float z1 = axis * sa;
    float w = 1.0 + z1 * persp * 0.35;
    float xp = x1 / w;
    float yp = other / (1.0 + z1 * persp * 0.15);
    vec2 suv = horizontal ? vec2(xp, yp) : vec2(yp, xp);
    suv = suv * 0.5 + 0.5;

    bool useTo = (p > 0.5);
    // After halfway, sample the incoming face continuing the rotation
    if (useTo) {
        float ang2 = (p - 1.0) * 1.5707963;
        if (reverse) ang2 = -ang2;
        ca = cos(ang2); sa = sin(ang2);
        x1 = axis * ca;
        z1 = axis * sa;
        w = 1.0 + z1 * persp * 0.35;
        xp = x1 / w;
        yp = other / (1.0 + z1 * persp * 0.15);
        suv = horizontal ? vec2(xp, yp) : vec2(yp, xp);
        suv = suv * 0.5 + 0.5;
    }

    if (suv.x < 0.0 || suv.x > 1.0 || suv.y < 0.0 || suv.y > 1.0) {
        fragColor = vec4(0.0);
        return;
    }
    float shade = mix(1.0, 0.65, abs(sa) * 0.8);
    vec4 col = useTo ? texture(u_toTexture, suv) : texture(u_fromTexture, suv);
    col.rgb *= shade;
    fragColor = col;
}
