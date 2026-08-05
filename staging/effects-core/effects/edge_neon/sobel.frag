#version 330 core
in vec2 v_texCoord; out vec4 fragColor;
uniform sampler2D u_currentTexture; uniform vec2 u_resolution; uniform float threshold;
float lum(vec3 c){ return dot(c, vec3(0.299,0.587,0.114)); }
void main() {
    vec2 px = 1.0 / u_resolution;
    float tl = lum(texture(u_currentTexture, v_texCoord + px*vec2(-1, 1)).rgb);
    float t  = lum(texture(u_currentTexture, v_texCoord + px*vec2( 0, 1)).rgb);
    float tr = lum(texture(u_currentTexture, v_texCoord + px*vec2( 1, 1)).rgb);
    float l  = lum(texture(u_currentTexture, v_texCoord + px*vec2(-1, 0)).rgb);
    float r  = lum(texture(u_currentTexture, v_texCoord + px*vec2( 1, 0)).rgb);
    float bl = lum(texture(u_currentTexture, v_texCoord + px*vec2(-1,-1)).rgb);
    float b  = lum(texture(u_currentTexture, v_texCoord + px*vec2( 0,-1)).rgb);
    float br = lum(texture(u_currentTexture, v_texCoord + px*vec2( 1,-1)).rgb);
    float gx = -tl + tr - 2.0*l + 2.0*r - bl + br;
    float gy = -tl - 2.0*t - tr + bl + 2.0*b + br;
    float mag = length(vec2(gx, gy));
    // Soft edge mask; threshold in [0,1] maps to a gentle cutoff.
    float edge = smoothstep(threshold * 0.5, threshold * 0.5 + 0.35, mag);
    fragColor = vec4(vec3(edge), 1.0);
}
