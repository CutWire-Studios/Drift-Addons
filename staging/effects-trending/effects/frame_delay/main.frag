#version 330 core
in vec2 v_texCoord; out vec4 fragColor;
uniform sampler2D u_currentTexture;
uniform float delay;

// Until `delay` frames have been seen, historyFrame reads the oldest one recorded.
void main() {
    if (delay < 0.5) {
        fragColor = texture(u_currentTexture, v_texCoord);
        return;
    }
    fragColor = historyFrame(delay, v_texCoord);
}
