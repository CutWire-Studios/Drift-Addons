#version 330 core
in vec2 v_texCoord;
out vec4 fragColor;
uniform sampler2D u_currentTexture;
uniform float u_blurRadius;
uniform vec2 u_resolution;

// Taps are accumulated premultiplied. Straight-alpha blurring drags the RGB of transparent pixels
// (which is black) into the result, haloing anything with an alpha edge — text and masked layers
// above all. Opaque video is unaffected, since a == 1 there.
vec4 tap(vec2 uv) {
    vec4 c = texture(u_currentTexture, uv);
    c.rgb *= c.a;
    return c;
}

// Per-pixel hash that turns residual stepping into fine grain.
float ign(vec2 p) {
    return fract(52.9829189 * fract(dot(p, vec2(0.06711056, 0.00583715))));
}

void main() {
    if (u_blurRadius < 0.5) {
        fragColor = tap(v_texCoord);
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
    vec2 dir = vec2(1.0 / u_resolution.x, 0.0);

    vec4 result = tap(v_texCoord);
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
        result += (tap(v_texCoord + dir * x) + tap(v_texCoord - dir * x)) * w;
        wsum += 2.0 * w;
    }

    // Handed to the vertical pass still premultiplied; it un-premultiplies on the way out.
    fragColor = result / wsum;
}
