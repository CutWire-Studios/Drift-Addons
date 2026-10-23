#version 330 core
in vec2 v_texCoord;
out vec4 fragColor;
uniform sampler2D u_currentTexture;
uniform float u_blurRadius;
uniform vec2 u_resolution;

// Per-pixel hash that turns residual stepping into fine grain.
float ign(vec2 p) {
    return fract(52.9829189 * fract(dot(p, vec2(0.06711056, 0.00583715))));
}

// Input is already premultiplied by blur_h, so tap it as-is and un-premultiply on output.
void main() {
    if (u_blurRadius < 0.5) {
        vec4 c = texture(u_currentTexture, v_texCoord);
        fragColor = vec4(c.rgb / max(c.a, 1e-4), c.a);
        return;
    }

    // 1.6x the radius matches the spread of the old 5-tap kernel, so the slider keeps its strength.
    float sigma = u_blurRadius * 1.6;
    float reach = 3.0 * sigma;
    // Each fetch is a bilinear pair of texels, so 64 fetches per side cover 128 texels. Beyond that
    // the taps spread out and jitter hides the steps.
    float step = max(1.0, reach / 128.0);
    float jitter = step > 2.0 ? (ign(gl_FragCoord.xy) - 0.5) * step : 0.0;
    float inv2s2 = 0.5 / (sigma * sigma);
    int n = int(min(ceil(reach / (2.0 * step)), 64.0));
    vec2 dir = vec2(0.0, 1.0 / u_resolution.y);

    vec4 result = texture(u_currentTexture, v_texCoord);
    float wsum = 1.0;
    for (int i = 1; i <= 64; ++i) {
        if (i > n)
            break;
        float a = (2.0 * float(i) - 1.0) * step;
        float b = 2.0 * float(i) * step;
        float wa = exp(-a * a * inv2s2);
        float wb = exp(-b * b * inv2s2);
        float w = wa + wb;
        float x = (a * wa + b * wb) / w + jitter;
        result += (texture(u_currentTexture, v_texCoord + dir * x) + texture(u_currentTexture, v_texCoord - dir * x)) * w;
        wsum += 2.0 * w;
    }
    result /= wsum;

    fragColor = vec4(result.rgb / max(result.a, 1e-4), result.a);
}
