#version 330 core
in vec2 v_texCoord; out vec4 fragColor;
uniform sampler2D u_currentTexture; uniform vec2 u_resolution;
uniform float u_faceValid; uniform float u_faceHasContours; uniform float u_faceRx;
uniform float amount;

// Horizontal half of a separable edge-aware blur.
//
// A separable Gaussian is not edge-preserving and a true bilateral is not separable; this is the
// usual compromise every shipping beauty filter makes, weighting each tap by how close its
// luminance is to the centre so strong edges do not bleed. It is good enough here specifically
// because the composite pass masks out the eyes, brows and lips, which is where the approximation's
// artefacts would otherwise show. A guided filter would be better and needs several more passes.
//
// Both blur buffers run at half resolution: skin blur is low-frequency by definition, and the
// bilinear upsample in the composite costs nothing.
void main() {
    // The blur runs over the whole frame — masking happens at composite time, because a masked
    // blur would pull unblurred pixels in from outside the face and ring the boundary.
    float radius = max(u_faceRx * mix(0.035, 0.11, amount), 1e-5);
    float step = radius / 4.0;
    vec3 centre = texture(u_currentTexture, v_texCoord).rgb;
    float cl = dot(centre, vec3(0.2126, 0.7152, 0.0722));

    vec3 sum = vec3(0.0);
    float wsum = 0.0;
    for (int i = -4; i <= 4; i++) {
        vec2 uv = v_texCoord + vec2(float(i) * step, 0.0);
        vec3 s = texture(u_currentTexture, clamp(uv, 0.0, 1.0)).rgb;
        float sl = dot(s, vec3(0.2126, 0.7152, 0.0722));
        float spatial = exp(-float(i * i) / 8.0);
        float range = exp(-(sl - cl) * (sl - cl) / 0.012);
        float w = spatial * range;
        sum += s * w;
        wsum += w;
    }
    fragColor = vec4(sum / max(wsum, 1e-5), 1.0);
}
