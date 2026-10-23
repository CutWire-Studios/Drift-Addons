#version 330 core
in vec2 v_texCoord; out vec4 fragColor;
uniform sampler2D u_currentTexture; uniform vec2 u_resolution; uniform float blurRadius;
void main() {
    // Separable vertical box blur.
    // The radius is in pixels of a 1080-line frame, so a reduced-scale preview matches the export.
    // Past 30 taps the taps spread out instead of growing in number.
    float r = clamp(blurRadius, 1.0, 30.0) * u_resolution.y / 1080.0;
    float taps = clamp(ceil(r), 1.0, 30.0);
    vec2 px = vec2(0.0, 1.0 / u_resolution.y) * (r / taps);
    vec4 sum = vec4(0.0);
    float count = 0.0;
    for (int k = -30; k <= 30; ++k) {
        if (abs(float(k)) > taps) continue;
        sum += texture(u_currentTexture, v_texCoord + px * float(k));
        count += 1.0;
    }
    fragColor = sum / max(count, 1.0);
}
