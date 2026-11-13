#version 330 core
in vec2 v_texCoord; out vec4 fragColor;
uniform sampler2D u_currentTexture;
uniform float direction; uniform float frames;

void main() {
    float t = direction < 0.5 ? v_texCoord.x : v_texCoord.y;
    float age = floor(t * (frames - 1.0) + 0.5);
    if (age < 0.5) {
        fragColor = texture(u_currentTexture, v_texCoord);
        return;
    }
    fragColor = historyFrame(age, v_texCoord);
}
