#version 330 core
in vec2 v_texCoord; out vec4 fragColor;
uniform sampler2D u_currentTexture; uniform float u_time;
uniform float intensity; uniform float hue; uniform float angle;
uniform float speed; uniform float softness; uniform float flicker;

vec3 hsv2rgb(vec3 c) {
    vec3 p = abs(fract(c.xxx + vec3(1.0, 2.0 / 3.0, 1.0 / 3.0)) * 6.0 - 3.0);
    return c.z * mix(vec3(1.0), clamp(p - 1.0, 0.0, 1.0), c.y);
}

void main() {
    vec4 src = texture(u_currentTexture, v_texCoord);
    if (intensity <= 1e-5) {
        fragColor = src;
        return;
    }

    vec2 p = v_texCoord - 0.5;
    float a = angle * 6.2831853;
    float axis = p.x * cos(a) + p.y * sin(a);

    // The leak sweeps past rather than sitting still; travel runs off both edges so the
    // wrap at fract() == 0 happens off-frame instead of as a visible jump.
    float travel = fract(u_time * speed * 0.15);
    float pos = mix(-0.9, 0.9, travel);
    float soft = max(softness, 0.02);

    float band = exp(-pow((axis - pos) / soft, 2.0));
    float band2 = exp(-pow((axis - pos - 0.18) / (soft * 0.4), 2.0)) * 0.6;

    // Real leaks come off a lamp with mains ripple, not a steady source.
    float flick = 1.0 - flicker * 0.5 * (0.5 + 0.5 * sin(u_time * 37.0));

    vec3 leak = hsv2rgb(vec3(fract(hue), 0.75, 1.0));
    vec3 add = leak * (band + band2) * intensity * flick;
    add = clamp(add, 0.0, 1.0);

    vec3 outc = 1.0 - (1.0 - clamp(src.rgb, 0.0, 1.0)) * (1.0 - add);
    fragColor = vec4(outc, src.a);
}
