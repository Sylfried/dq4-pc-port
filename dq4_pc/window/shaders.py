"""Drawing programs (GLSL) of the window."""


VERTEX = '''#version 330 core
in vec3 position; in vec2 tex_coords; in vec4 colors;
uniform mat4 mvp;
centroid out vec2 v_uv; out vec4 v_col;
void main() { gl_Position = mvp * vec4(position, 1.0); v_uv = tex_coords; v_col = colors; }'''

FRAG = '''#version 330 core
centroid in vec2 v_uv; in vec4 v_col; out vec4 fragColor;
uniform sampler2D tex; uniform float cutoff; uniform vec2 tsize; uniform float crisp; uniform float amul; uniform float a2c; uniform vec3 tint; uniform float sepia;      // tint: packet 33 (scenery only), 1, 1, 1 = neutral; sepia: packet 1 (town scenery only), 0 = original colors
void main() {
    vec2 uv = v_uv; float lod = 0.0;
    if (crisp > 0.5) { vec2 p0 = uv * tsize; vec2 dx = dFdx(p0), dy = dFdy(p0); lod = max(0.0, 0.5 * log2(max(max(dot(dx, dx), dot(dy, dy)), 1e-8))); }      // mipmaps chosen on the original uv (the shifted uv jumps from one texel to the next)
    if (crisp > 1.5) { uv = (floor(uv * tsize) + 0.5) / tsize; }      // pixel perfect: strict nearest neighbor, no softening
    else if (crisp > 0.5) {   // pixel art: the pixels stay crisp, only the border between two pixels is softened
        vec2 p = uv * tsize; vec2 b = floor(p + 0.5); vec2 w = max(fwidth(p), vec2(1e-4));       // b = nearest texel border: the texel center stays pure, only a one-screen-pixel band around the border is blended
        uv = (b + clamp((p - b) / w, -0.5, 0.5)) / tsize;
    }
    vec4 c = (crisp > 0.5 ? textureLod(tex, uv, lod) : texture(tex, uv)) * clamp(v_col, 0.0, 1.0);
    vec3 m = c.rgb * tint;
    if (sepia > 0.5) m = vec3(dot(vec3(0.299, 0.587, 0.114), m)) + vec3(0.109375, -0.0546875, 0.0);      // Custom/fld_*_sepia (flashbacks, cmd_map_effect_sepia): gray (0.299; 0.587; 0.114) of texture x vertex color x _Color, plus (0.109375; -0.0546875; 0), alpha unchanged
    c.rgb = clamp(m, 0.0, 1.0);      // texture x vertex color x _Color (fld_*.frag): _Color = _OrgColor (white, original alpha: FldObject.save_org_color) x tint of packet 33, which can exceed 1 (1.25 in red): saturation on write, like the frame buffer
    if (a2c > 0.5) { c.a = clamp((c.a - cutoff) / max(fwidth(c.a), 1e-4) + 0.5, 0.0, 1.0); if (c.a <= 0.0) discard; }      // cut-out scenery (flowers, foliage, grilles): the silhouette becomes a coverage of 0 to 4 samples (MSAA), not a hard edge that sparkles
    else if (c.a < cutoff) discard;
    c.a *= amul; fragColor = c; }'''

VERTEX_EFFECT = '''#version 330 core
in vec2 position; in vec2 tex_coords; in vec4 colors;
out vec2 v_uv; out vec4 v_col;
void main() { gl_Position = vec4(position, 0.0, 1.0); v_uv = tex_coords; v_col = colors; }'''

FRAG_EFFECT = '''#version 330 core
in vec2 v_uv; in vec4 v_col; out vec4 fragColor;
uniform sampler2D tex; uniform float lum; uniform float blur;
void main() { vec3 c = texture(tex, v_uv, blur).rgb; fragColor = vec4(c * v_col.rgb * lum, v_col.a * lum); }'''

BLUR_EFFECT = 1.0              # Capture.SetBlur(true) during the effect: the capture is softened (mipmap bias)

# Town background: the game's `BackColor` = a full-screen quadrilateral (vertices (1, 1), (-1, 1), (-1, -1), (1, -1) written AS IS in clip space:
# "BackColor" shader, `gl_Position = in_POSITION0`, `SV_Target0 = vs_COLOR0`, Background queue, ZTest Always, ZWrite Off, no blending) whose two top vertices have
# the packet 8 "top" color and the two bottom ones the "bottom" color (BackColor.SetColor(top, bottom, 0), RVA 0xCC43F8): a linear vertical gradient over the full
# height of the frame, behind everything else.
VERTEX_GRADIENT = '''#version 330 core
in vec2 position; uniform vec3 top; uniform vec3 bottom; out vec3 v_col;
void main() { gl_Position = vec4(position, 0.0, 1.0); v_col = mix(bottom, top, position.y * 0.5 + 0.5); }'''

FRAG_GRADIENT = '''#version 330 core
in vec3 v_col; out vec4 fragColor;
void main() { fragColor = vec4(v_col, 1.0); }'''

# Windows wider than 16:9: beyond the 16:9 base (the phone's portrait area turned on its side), the town and dungeon picture fades into the map's own background
# (the BackColor gradient, or its clear color), so the edge of a finite plane (water, lava, floor) laid on that background is never cut by a hard line. `inner` = half width of the
# base in clip space (base aspect / window aspect); full background at the edge of the window.
VERTEX_SIDES = '''#version 330 core
in vec2 position; uniform vec3 top; uniform vec3 bottom; out vec3 v_col; out float v_x;
void main() { gl_Position = vec4(position, 0.0, 1.0); v_col = mix(bottom, top, position.y * 0.5 + 0.5); v_x = position.x; }'''

FRAG_SIDES = '''#version 330 core
in vec3 v_col; in float v_x; uniform float inner; out vec4 fragColor;
void main() { float k = clamp((abs(v_x) - inner) / max(1.0 - inner, 1e-4), 0.0, 1.0); fragColor = vec4(v_col, k * k * (3.0 - 2.0 * k)); }'''
