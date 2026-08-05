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

void main() {
    vec2 tex_offset = vec2(1.0 / u_resolution.x, 0.0);
    vec4 result = tap(v_texCoord) * 0.2270270270;

    result += tap(v_texCoord + tex_offset * u_blurRadius * 1.3846153846) * 0.3162162162;
    result += tap(v_texCoord - tex_offset * u_blurRadius * 1.3846153846) * 0.3162162162;
    result += tap(v_texCoord + tex_offset * u_blurRadius * 3.2307692308) * 0.0702702703;
    result += tap(v_texCoord - tex_offset * u_blurRadius * 3.2307692308) * 0.0702702703;

    // Handed to the vertical pass still premultiplied; it un-premultiplies on the way out.
    fragColor = result;
}
