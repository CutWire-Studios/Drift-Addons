#version 330 core
in vec2 v_texCoord; out vec4 fragColor;
uniform sampler2D u_currentTexture; uniform vec2 u_resolution;
uniform float strength; uniform float dotSize; uniform float levels; uniform float angle;

void main() {
    vec4 src = texture(u_currentTexture, v_texCoord);
    float s = clamp(strength, 0.0, 1.0);
    if (s <= 1e-5) {
        fragColor = src;
        return;
    }

    float lum = dot(src.rgb, vec3(0.2126, 0.7152, 0.0722));
    int lv = int(clamp(floor(levels + 0.5), 2.0, 8.0));
    float poster = floor(lum * float(lv)) / float(lv - 1);

    float cell = clamp(dotSize, 2.0, 16.0);
    float rot = angle * 3.14159265;
    mat2 R = mat2(cos(rot), -sin(rot), sin(rot), cos(rot));
    vec2 pix = (v_texCoord * u_resolution - u_resolution * 0.5) * R + u_resolution * 0.5;
    vec2 cellUv = mod(pix, cell) / cell - 0.5;
    float d = length(cellUv);
    float dotMask = smoothstep(0.5, 0.35, d * (1.1 - poster * 0.5));

    vec3 ink = vec3(poster * dotMask);
    vec3 outc = mix(src.rgb, ink, s);
    fragColor = vec4(clamp(outc, 0.0, 1.0), src.a);
}
