#version 330 core
in vec2 v_texCoord; out vec4 fragColor;
uniform sampler2D u_currentTexture; uniform float u_time;
uniform float intensity; uniform float frequency; uniform float hue; uniform float flash;

vec3 hsv2rgb(vec3 c) {
    vec3 p = abs(fract(c.xxx + vec3(1.0, 2.0 / 3.0, 1.0 / 3.0)) * 6.0 - 3.0);
    return c.z * mix(vec3(1.0), clamp(p - 1.0, 0.0, 1.0), c.y);
}

float hash11(float p) { return fract(sin(p * 127.1) * 43758.5453); }

void main() {
    vec4 src = texture(u_currentTexture, v_texCoord);
    float amt = clamp(intensity, 0.0, 1.0);
    if (amt <= 1e-5) {
        fragColor = src;
        return;
    }

    float sky = smoothstep(0.35, 1.0, 1.0 - v_texCoord.y);
    float t = u_time * mix(0.4, 2.5, clamp(frequency, 0.0, 1.0));
    float strike = step(0.992 - clamp(frequency, 0.0, 1.0) * 0.02,
                        hash11(floor(t * 3.0) + floor(v_texCoord.x * 40.0)));
    float bolt = exp(-abs(v_texCoord.x - 0.5 - sin(v_texCoord.y * 12.0 + t) * 0.08) * 120.0)
                 * smoothstep(0.2, 0.95, v_texCoord.y);
    float lit = max(strike * bolt, flash * 0.35 * sky);

    vec3 boltColor = mix(vec3(0.85, 0.92, 1.0), hsv2rgb(vec3(fract(hue), 0.7, 1.0)), 0.35);
    vec3 add = boltColor * lit * sky * amt;
    vec3 outc = clamp(src.rgb + add, 0.0, 1.0);
    fragColor = vec4(outc, src.a);
}
