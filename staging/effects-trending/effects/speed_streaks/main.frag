#version 330 core
in vec2 v_texCoord;
out vec4 fragColor;
uniform sampler2D u_currentTexture;
uniform float strength;
uniform float chromatic;
uniform float centerX;
uniform float centerY;

void main() {
    vec4 original = texture(u_currentTexture, v_texCoord);
    float amount = clamp(strength, 0.0, 1.0);
    if (amount < 0.001) {
        fragColor = original;
        return;
    }
    vec2 direction = v_texCoord - vec2(centerX, centerY);
    vec3 accumulated = vec3(0.0);
    float sum = 0.0;
    // Per-pixel jitter turns the gaps between taps into fine grain instead of ghost copies.
    float jitter = fract(52.9829189 * fract(dot(gl_FragCoord.xy, vec2(0.06711056, 0.00583715))));
    for (int i = 0; i < 24; ++i) {
        float stepAmount = (float(i) + jitter) / 24.0;
        vec2 sampleUV = clamp(v_texCoord - direction * stepAmount * (0.32 * amount), 0.0, 1.0);
        float weight = 1.0 - stepAmount * 0.5;
        accumulated += texture(u_currentTexture, sampleUV).rgb * weight;
        sum += weight;
    }
    vec3 blurred = accumulated / max(sum, 0.001);
    vec2 fringe = direction * (0.018 * amount * chromatic);
    blurred.r = mix(blurred.r, texture(u_currentTexture, clamp(v_texCoord + fringe, 0.0, 1.0)).r, chromatic * 0.6);
    blurred.b = mix(blurred.b, texture(u_currentTexture, clamp(v_texCoord - fringe, 0.0, 1.0)).b, chromatic * 0.6);
    fragColor = vec4(mix(original.rgb, blurred, amount), original.a);
}
