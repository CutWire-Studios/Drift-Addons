#version 330 core
in vec2 v_texCoord;
out vec4 fragColor;
uniform sampler2D u_currentTexture;
uniform sampler2D u_texture1;
uniform float intensity;
uniform float streakLength;
uniform float cool;

void main() {
    vec4 src = texture(u_currentTexture, v_texCoord);
    vec3 streak = texture(u_texture1, v_texCoord).rgb;
    // Each pass keeps unit weight, so a small light spread over the streak loses brightness in
    // proportion to its reach: gain it back, then saturate so wide bright areas don't blow out.
    float reach = max(streakLength, 0.005) * float(textureSize(u_texture1, 0).x);
    vec3 s = streak * reach * 0.12 * intensity;
    s = vec3(1.0) - exp(-s);
    vec3 tint = mix(vec3(1.0, 0.62, 0.32), vec3(0.38, 0.62, 1.0), cool);
    float l = dot(s, vec3(0.2126, 0.7152, 0.0722));
    vec3 coloured = mix(s * tint, vec3(l), smoothstep(0.6, 1.0, l) * 0.5);
    fragColor = vec4(clamp(src.rgb + coloured * 1.5, 0.0, 1.0), src.a);
}
