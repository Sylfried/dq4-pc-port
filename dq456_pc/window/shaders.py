"""Drawing programs (GLSL) of the window."""


VERTEX = '''#version 330 core
in vec3 position; in vec2 tex_coords; in vec4 colors;
uniform mat4 mvp;
out vec2 g_uv; out vec4 g_col;
void main() { gl_Position = mvp * vec4(position, 1.0); g_uv = tex_coords; g_col = colors; }'''

# Each triangle's uv box (min u, min v, max u, max v), the same for its three vertices: the sharp sampling of FRAG never reads a texel beyond the polygon's own edges. A polygon
# whose edge lies on a texel border (the bed's sheet: two halves mirrored, texel row 0 on the middle line) otherwise blended the texel outside it (the texture's opposite edge,
# through Repeat) over one screen pixel: a thin dark line in the middle of every bed.
GEOMETRY = '''#version 330 core
layout(triangles) in; layout(triangle_strip, max_vertices = 3) out;
in vec2 g_uv[]; in vec4 g_col[];
centroid out vec2 v_uv; out vec4 v_col; flat out vec4 v_box;
void main() {
    vec4 box = vec4(min(min(g_uv[0], g_uv[1]), g_uv[2]), max(max(g_uv[0], g_uv[1]), g_uv[2]));
    for (int i = 0; i < 3; i++) { gl_Position = gl_in[i].gl_Position; v_uv = g_uv[i]; v_col = g_col[i]; v_box = box; EmitVertex(); }
    EndPrimitive(); }'''

FRAG = '''#version 330 core
centroid in vec2 v_uv; in vec4 v_col; flat in vec4 v_box; out vec4 fragColor;
uniform sampler2D tex; uniform float cutoff; uniform vec2 tsize; uniform vec2 tshift; uniform float crisp; uniform float amul; uniform float a2c; uniform vec3 tint; uniform float sepia; uniform vec2 hue;      // tint: packet 33 (scenery only), 1, 1, 1 = neutral; sepia: packet 1 (town scenery only), 0 = original colors
const float TIE = 1e-3;
void main() {
    vec2 uv = v_uv; float lod = 0.0;
    if (crisp > 0.5) { vec2 p0 = uv * tsize; vec2 dx = dFdx(p0), dy = dFdy(p0); lod = max(0.0, 0.5 * log2(max(max(dot(dx, dx), dot(dy, dy)), 1e-8))); }      // mipmaps chosen on the original uv (the shifted uv jumps from one texel to the next)
    // tshift (texels, town and battle scenery only): their uv are texel CENTERS ((t + 0.5) / size, the DS data adapted for bilinear filtering); the crisp sampling works on t, the DS texel
    // coordinate, so that the edge of each polygon falls on a texel border: otherwise every polygon showed half a texel at its edges, thin lines at each seam of the ground
    // + TIE (1/1000 texel): a point exactly on a texel border belongs to the texel after it, as in the original (DS coordinate t -> uv (t + 0.5) / size, the CENTER of texel t). Polygons whose uv
    // does not vary (the inner faces of the cave rocks: v = 0.5 / 64 everywhere, the black bottom row of the texture) lie exactly on a border: without this the soft sampling blended the two
    // texels 50/50 over the whole polygon (with the opposite edge of the texture, through Repeat: brown instead of black) and the strict one could fall on either side
    // v_box: the polygon's own texels (DS coordinates tmin to tmax): the sample stays between the centers of its first and last texel (lo, hi), so that a border on the polygon's edge
    // is never blended with the texel beyond it (one texel wide or less: the texel after the border, as TIE)
    vec2 lo = v_box.xy * tsize - tshift + 0.5, hi = max(v_box.zw * tsize - tshift - 0.5, lo);
    if (crisp > 1.5) { uv = clamp(floor(uv * tsize - tshift + TIE) + 0.5, lo, hi) / tsize; }      // pixel perfect: strict nearest neighbor, no softening
    else if (crisp > 0.5) {   // pixel art: the pixels stay crisp, only the border between two pixels is softened
        vec2 p = uv * tsize - tshift + TIE; vec2 b = floor(p + 0.5); vec2 w = max(fwidth(p), vec2(1e-4));       // b = nearest texel border: the texel center stays pure, only a one-screen-pixel band around the border is blended
        uv = clamp(b + clamp((p - b) / w, -0.5, 0.5), lo, hi) / tsize;
    }
    vec4 c = (crisp > 0.5 ? textureLod(tex, uv, lod) : texture(tex, uv)) * clamp(v_col, 0.0, 1.0);
    vec3 m = c.rgb * tint;
    if (sepia > 0.5) m = vec3(dot(vec3(0.299, 0.587, 0.114), m)) + vec3(0.109375, -0.0546875, 0.0);      // Custom/fld_*_sepia (flashbacks, cmd_map_effect_sepia): gray (0.299; 0.587; 0.114) of texture x vertex color x _Color, plus (0.109375; -0.0546875; 0), alpha unchanged
    if (hue.x > 1.5) m = m * (1.0 - hue.y) + vec3(dot(m, vec3(0.3333))) * hue.y;      // DQ VI Custom/CharaHueGray (_Hue = hue.y, _UnHue = 1 - hue.y): a petrified character
    else if (hue.x > 0.5) m = m * (1.0 - hue.y) + vec3(dot(m, vec3(0.299, 0.587, 0.114))) * hue.y + vec3(-0.219062507, 0.0443671867, 0.346093744);      // DQ VI Custom/CharaHueIce: a frozen character
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
