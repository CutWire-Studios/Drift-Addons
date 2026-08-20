#version 330 core
in vec2 v_texCoord; out vec4 fragColor;
uniform sampler2D u_currentTexture; uniform vec2 u_resolution;
uniform float strength; uniform float invert; uniform float threshold;
void main() {
    vec2 px = 1.0 / u_resolution;
    float tl = dot(texture(u_currentTexture, v_texCoord + px * vec2(-1, -1)).rgb, vec3(0.299, 0.587, 0.114));
    float t  = dot(texture(u_currentTexture, v_texCoord + px * vec2( 0, -1)).rgb, vec3(0.299, 0.587, 0.114));
    float tr = dot(texture(u_currentTexture, v_texCoord + px * vec2( 1, -1)).rgb, vec3(0.299, 0.587, 0.114));
    float l  = dot(texture(u_currentTexture, v_texCoord + px * vec2(-1,  0)).rgb, vec3(0.299, 0.587, 0.114));
    float r  = dot(texture(u_currentTexture, v_texCoord + px * vec2( 1,  0)).rgb, vec3(0.299, 0.587, 0.114));
    float bl = dot(texture(u_currentTexture, v_texCoord + px * vec2(-1,  1)).rgb, vec3(0.299, 0.587, 0.114));
    float b  = dot(texture(u_currentTexture, v_texCoord + px * vec2( 0,  1)).rgb, vec3(0.299, 0.587, 0.114));
    float br = dot(texture(u_currentTexture, v_texCoord + px * vec2( 1,  1)).rgb, vec3(0.299, 0.587, 0.114));
    float gx = -tl - 2.0*l - bl + tr + 2.0*r + br;
    float gy = -tl - 2.0*t - tr + bl + 2.0*b + br;
    float e = length(vec2(gx, gy)) * strength;
    e = smoothstep(threshold, threshold + 0.15, e);
    if (invert > 0.5) e = 1.0 - e;
    float a = texture(u_currentTexture, v_texCoord).a;
    fragColor = vec4(vec3(e), a);
}
