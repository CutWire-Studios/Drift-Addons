#version 330 core
in vec2 v_texCoord;
out vec4 fragColor;

uniform sampler2D u_currentTexture;
uniform sampler2D u_texture1;
uniform vec2 u_resolution;
uniform float u_time;
uniform float swayRate;
uniform float spread;
uniform float cloneSize;
uniform float cloneTint;
uniform vec3 rightColor;
uniform vec3 leftColor;
uniform vec3 haloColor;
uniform float halo;
float pv_swayRate() { return swayRate; }
float pv_spread() { return spread; }
float pv_cloneSize() { return cloneSize; }
float pv_cloneTint() { return cloneTint; }
vec3 pv_rightColor() { return rightColor; }
vec3 pv_leftColor() { return leftColor; }
vec3 pv_haloColor() { return haloColor; }
float pv_halo() { return halo; }

float luma(vec4 c) { return dot(c.rgb, vec3(0.2126, 0.7152, 0.0722)); }

mat2 rot2(float a) {
    float c = cos(a);
    float s = sin(a);
    return mat2(c, s, -s, c);
}

vec4 n_nleol4m_image(vec2 uv) {
    return texture(u_currentTexture, uv);
}

vec4 n_nz5dq22_image(vec2 uv) {
    return texture(u_texture1, uv);
}

float n_nf0tscp_r(vec2 uv) {
    return n_nz5dq22_image(uv).r;
}

vec4 n_nignwke_image(vec2 uv) {
    return mix(vec4(0.0, 0.0, 0.0, 1.0), vec4(pv_haloColor(), 1.0), clamp(n_nf0tscp_r(uv), 0.0, 1.0));
}

vec4 n_n0t3zyw_image(vec2 uv) {
    vec4 b = n_nleol4m_image(uv);
    vec4 l = n_nignwke_image(uv);
    vec3 rgb = 1.0 - (1.0 - b.rgb) * (1.0 - l.rgb);
    return vec4(mix(b.rgb, rgb, clamp(pv_halo() * l.a, 0.0, 1.0)), b.a);
}

float n_nqp3tmi_value(vec2 uv) {
    float x = u_time * pv_swayRate() + 0.0;
    return mix(0.8, 1.0, 0.5 - 0.5 * cos(x * 6.2832));
}

float n_na39xdb_value(vec2 uv) {
    return pv_spread() * n_nqp3tmi_value(uv);
}

vec2 n_nabqrz0_p(vec2 uv) {
    return vec2(n_na39xdb_value(uv), 0.0);
}

vec2 n_nps6dz9_p(vec2 uv) {
    return n_nabqrz0_p(uv) * -1.0;
}

vec2 n_nn2rwsf_p(vec2 uv) {
    mat2 M = mat2(pv_cloneSize(), 0.0, 0.0, pv_cloneSize());
    float det = determinant(M);
    M = mat2(M[1][1], -M[0][1], -M[1][0], M[0][0]) / (abs(det) < 1e-6 ? 1e-6 : det);
    float asp = u_resolution.x / max(u_resolution.y, 1.0);
    vec2 o = vec2(0.5, 1.0);
    vec2 q = (uv - o) * vec2(asp, 1.0);
    return (M * q) / vec2(asp, 1.0) + o + n_nps6dz9_p(uv);
}

vec4 n_ntf6fv4_image(vec2 uv) {
    vec2 p = n_nn2rwsf_p(uv);
    if (p.x < 0.0 || p.x > 1.0 || p.y < 0.0 || p.y > 1.0) return vec4(0.0);
    return n_nleol4m_image(p);
}

vec4 n_n1j4ubz_image(vec2 uv) {
    vec4 col = n_ntf6fv4_image(uv);
    vec3 tinted = luma(col) * vec4(pv_rightColor(), 1.0).rgb * 1.6;
    return vec4(mix(col.rgb, clamp(tinted, 0.0, 1.0), pv_cloneTint()), col.a);
}

float n_nb1gobt_mask(vec2 uv) {
    return driftMask(uv);
}

vec4 n_nimu810_image(vec2 uv) {
    vec2 p = n_nn2rwsf_p(uv);
    if (p.x < 0.0 || p.x > 1.0 || p.y < 0.0 || p.y > 1.0) return vec4(0.0);
    return vec4(vec3(n_nb1gobt_mask(p)), 1.0);
}

float n_n3x9fqe_r(vec2 uv) {
    return n_nimu810_image(uv).r;
}

vec4 n_ngwdv0z_image(vec2 uv) {
    return mix(n_n0t3zyw_image(uv), n_n1j4ubz_image(uv), clamp(n_n3x9fqe_r(uv), 0.0, 1.0));
}

vec2 n_nhad8ks_p(vec2 uv) {
    mat2 M = mat2(pv_cloneSize(), 0.0, 0.0, pv_cloneSize());
    float det = determinant(M);
    M = mat2(M[1][1], -M[0][1], -M[1][0], M[0][0]) / (abs(det) < 1e-6 ? 1e-6 : det);
    float asp = u_resolution.x / max(u_resolution.y, 1.0);
    vec2 o = vec2(0.5, 1.0);
    vec2 q = (uv - o) * vec2(asp, 1.0);
    return (M * q) / vec2(asp, 1.0) + o + n_nabqrz0_p(uv);
}

vec4 n_ni0kt27_image(vec2 uv) {
    vec2 p = n_nhad8ks_p(uv);
    if (p.x < 0.0 || p.x > 1.0 || p.y < 0.0 || p.y > 1.0) return vec4(0.0);
    return n_nleol4m_image(p);
}

vec4 n_nycw0qv_image(vec2 uv) {
    vec4 col = n_ni0kt27_image(uv);
    vec3 tinted = luma(col) * vec4(pv_leftColor(), 1.0).rgb * 1.6;
    return vec4(mix(col.rgb, clamp(tinted, 0.0, 1.0), pv_cloneTint()), col.a);
}

vec4 n_nu0rtcg_image(vec2 uv) {
    vec2 p = n_nhad8ks_p(uv);
    if (p.x < 0.0 || p.x > 1.0 || p.y < 0.0 || p.y > 1.0) return vec4(0.0);
    return vec4(vec3(n_nb1gobt_mask(p)), 1.0);
}

float n_nesq3ia_r(vec2 uv) {
    return n_nu0rtcg_image(uv).r;
}

vec4 n_nk6jpau_image(vec2 uv) {
    return mix(n_ngwdv0z_image(uv), n_nycw0qv_image(uv), clamp(n_nesq3ia_r(uv), 0.0, 1.0));
}

vec4 n_nht65fs_image(vec2 uv) {
    return mix(n_nk6jpau_image(uv), n_nleol4m_image(uv), clamp(n_nb1gobt_mask(uv), 0.0, 1.0));
}

void main() {
    fragColor = n_nht65fs_image(v_texCoord);
}
