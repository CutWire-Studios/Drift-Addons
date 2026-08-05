#version 330 core
in vec2 v_texCoord; out vec4 fragColor;
uniform sampler2D u_currentTexture;
void main() { fragColor = texture(u_currentTexture, v_texCoord); }
