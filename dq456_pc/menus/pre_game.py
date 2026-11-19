"""What the game's Unity layer does BEFORE the game starts: entry logos, the title's "Touchez l'ecran", resources.

Everything comes from the original code (Boot, TapToStart, ApplicationQuit... of libil2cpp.so, re-read instruction by instruction: values and addresses in docs/engine-patches.md,
section "Before the game"). This module depends neither on the engine nor on OpenGL apart from drawing the images (pyglet.sprite)."""
import os
import pyglet
from dq456_pc import games as GM
from dq456_pc.language import N_

# cache files -> (archive, Unity object type, resource name)
RESOURCES = {
    'ap_sqex.png': ('base', 'Texture2D', 'sqex'),                      # SQUARE ENIX logo (Boot.m_logoTexture[1])
    'ap_arte.png': ('base', 'Texture2D', 'arte_logo720_240'),          # ArtePiazza logo (Boot.m_logoTexture[2])
    'ap_taptostart.png': ('pack', 'Texture2D', 'taptostart'),         # "Touchez l'ecran" (Resources/Title/TapToStart)
    'ap_copyright.png': ('pack', 'Texture2D', 'Retro%d_copyright'),   # title copyright line (DQ IV: Resources/Title/Retro4_copyright; DQ V / VI: boot/Retro5_copyright, boot/Retro6_copyright)
    'ap_licence.txt': ('pack', 'TextAsset', 'License_list_A'),         # text of the License screen (Android variant)
    'ap_hyodai1.png': ('pack', 'Texture2D', 'hyodai1'),               # chapter title banner (Menu/map/hyodai1, 256 x 128, Make_Chapter)
    'ap_encyclopedia.png': ('pack', 'Texture2D', 'encyclopedia'),     # the bestiary's parchment (Menu/map/encyclopedia, 256 x 256, Make_MonsterEncyclopedia; window/backdrop.py)
}
ONLY = {'ap_hyodai1.png': ('dq4',)}                                     # resources that only some games have (DQ V / VI have no chapters)


def resources():
    """RESOURCES of the running game."""
    g = GM.profile().key
    return {n: r for n, r in RESOURCES.items() if g in ONLY.get(n, (g,))}


# ---- Boot.Logo (MoveNext 0xCC5618): constants of the Boot class
LOGO_FADE_IN, LOGO_HOLD, LOGO_FADE_OUT = 1.0, 3.0, 1.0          # c_fadeTime, c_waitTime, c_fadeTime (real seconds: Time.deltaTime)
LOGO_SIDE = 450.0                                                  # the logo quad is a square of 450 units (720 x 720 texture), centered, in the 450 x 800 interface

# ---- TapToStart (interface class of port 12, type 73): constants from the dump
TT_ACC, TT_WAIT = 0.025, 20                                         # c_acc, c_cwait (frames)
TT_L, TT_H, TT_BOTTOM = 223.04001, 41.48, 228.0                       # c_width, c_height; center 228 units BELOW the screen center
CP_ACC = 0.0625                                                    # c_copyrightAcc
# c_firstWait, c_copyrightFirstWait, c_copyrightSecondWait of each game (frames; DQ V / VI: the copyright never fades out again)
TT_WAITS = {'dq4': (720, 690, 2508), 'dq5': (799, 767, 999999), 'dq6': (810, 760, 999999)}
TITLE_TOUCH_TYPE = 73                                              # Make_TitleTouch: port 12 in DQ IV / V, port 13 in DQ VI (port 12 holds its type 113 there)
CP_L, CP_H, CP_TOP = 450.0, 40.0005, 25.0003                      # c_copyrightWidth / Height; center 25 units above the bottom edge


# ---- Title logo: DELIBERATE DEVIATION from the APK: the logo and the subtitle are enlarged
# The logo is an engine mesh (packets 21 / 22, map `ev01`): model 8901 = "DRAGON QUEST" + "IV" + "TM" + subtitle, model 8900 = the animated
# glint on the logo; both at the same position (0, 1, 0), vertices in the panel's local coordinates (x toward the camera's right, mirrored from Unity, y up), x
# from -4.549 to 4.549 for "DRAGON QUEST".
LOGO_MODELS = (8900, 8901)
LOGO_SCALE = 1.5                     # desired enlargement factor (1 = the APK)
LOGO_HALF_WIDTH = 4.549              # local half-width of "DRAGON QUEST" (read from the vertices of packet 22)
LOGO_Y_FIXED = 0.70                     # local y coordinate of the point that does not move: the logo grows around this point (which keeps it above "Touchez l'ecran" and below the top of the screen; see notes)
LOGO_WIDTH_MARGIN = 0.96              # the enlarged logo never exceeds 96% of the window width (very narrow window); it never becomes smaller than the APK's


# DQ VI's logo (model 8901 too, but in the orthographic layer: 249 units wide at (0, 8)) is smaller in its APK than DQ IV's, and DQ IV's is enlarged here: at 16:9 "DRAGON QUEST" took 28.3 % of the
# window's width against 46.9 %. DELIBERATE DEVIATION, asked for: enlarged around its own position so that its "DRAGON QUEST" is as wide as DQ IV's (600 / 362 px at 1280 x 720; the two projections follow
# the window's shape the same way, so the two stay equal), within the same margin of the window's width. DQ V's logo (its tall "V" and ring: about DQ IV's height already) stays the APK's.
ORTHO_LOGO_SCALE = {'dq6': 1.66}


def ortho_logo(loc, half_width, game, desired=None, margin=LOGO_WIDTH_MARGIN):
    """Local vertices (n, 3) of a title logo of the orthographic layer, enlarged around its own position (local origin) by its game's factor (ORTHO_LOGO_SCALE; `desired`: another factor), reduced
    so that it keeps within `margin` of the window's width. `half_width`: half the window's width in the layer's units. The same array when the game has no factor."""
    import numpy as np
    k = ORTHO_LOGO_SCALE.get(game) if desired is None else desired
    if not k or k == 1.0 or len(loc) == 0: return loc
    width = (float(np.max(loc[:, 0])) - float(np.min(loc[:, 0]))) / (2.0 * half_width) if half_width > 0 else 0.0
    k = logo_factor(width, k, margin)
    out = np.array(loc, np.float32, copy=True); out[:, :2] *= k
    return out


def logo_factor(original_width, desired=LOGO_SCALE, margin=LOGO_WIDTH_MARGIN):
    """Enlargement factor of the logo: `desired`, reduced (down to 1) so that the enlarged logo fits within `margin` of the window width. `original_width` = width of the APK's logo
    as a fraction of the window width (0 to 1)."""
    if original_width <= 0.0: return max(1.0, desired)             # width cannot be measured: the desired factor is applied as is
    return max(1.0, min(desired, margin / original_width))


def upscale_logo(loc, factor, y_fixed=LOGO_Y_FIXED):
    """Local vertices (n, 3: x, y, depth) of the logo enlarged by `factor` around the panel's point (0, y_fixed): x and y change, the depth (drawing order of the panel's layers: glint in front of the logo, etc.)
    stays the engine's. Returns a new array."""
    import numpy as np
    output = np.array(loc, np.float32, copy=True)
    output[:, 0] *= factor
    output[:, 1] = y_fixed + factor * (output[:, 1] - y_fixed)
    return output


def prepare(apk_folder, cache, log=print):
    """Extracts from the APKs (only once) the images and text specific to the pre-game. -> True if everything is in the cache. Without UnityPy or without an APK: False (the game does without)."""
    res = resources(); dest = {n: os.path.join(cache, n) for n in res}
    missing = [n for n, p in dest.items() if not os.path.exists(p)]
    if not missing: return True
    try:
        import UnityPy, zipfile
        os.makedirs(cache, exist_ok=True)
        log('Reading the title images (once)...')
        archives = {}
        for lookup_key in {res[n][0] for n in missing}:
            if lookup_key == 'base': archives[lookup_key] = UnityPy.load(os.path.join(apk_folder, 'base.apk'))
            else: archives[lookup_key] = UnityPy.load(zipfile.ZipFile(os.path.join(apk_folder, 'split_UnityDataAssetPack.apk')).read('assets/bin/Data/datapack.unity3d'))
        for file_name in missing:
            lookup_key, kind, name_str = res[file_name]
            if '%d' in name_str: name_str = name_str % int(GM.profile().key[2:])
            for o in archives[lookup_key].objects:
                if o.type.name != kind: continue
                d = o.read()
                if d.m_Name != name_str: continue
                if kind == 'Texture2D': d.image.convert('RGBA').save(dest[file_name])
                else:
                    raw = d.m_Script; open(dest[file_name], 'wb').write(raw.encode('utf-8', 'surrogateescape') if isinstance(raw, str) else bytes(raw))
                break
        return all(os.path.exists(p) for p in dest.values())
    except Exception as ex:
        log('Title images unavailable: %r' % (ex,)); return False


def paths(cache):
    """Cache paths -> dict short name -> path (only those that exist)."""
    return {n[3:].rsplit('.', 1)[0]: os.path.join(cache, n) for n in resources() if os.path.exists(os.path.join(cache, n))}


class Logos:
    """Boot.Logo: one logo after the other, on a black background. Fade-in (1 s), hold (3 s), fade-out (1 s). A touch during the fade-in skips the hold,
    during the hold it starts the fade-out right away. French / English: SQUARE ENIX then ArtePiazza (the Japanese warning is shown only in language 0)."""
    def __init__(self, files):
        self.entries = [files[n] for n in ('sqex', 'arte') if n in files]
        self.i = 0; self.phase = 0; self.t = 0.0; self.alpha = 0.0; self.skip = False; self.sprites = {}
    @property
    def finished(self): return self.i >= len(self.entries)
    @property
    def ok(self): return bool(self.entries)

    def touch(self):
        """A press (click, key): skips the hold of the current logo."""
        if self.finished: return
        if self.phase == 0: self.skip = True
        elif self.phase == 1: self.phase = 2; self.t = 0.0

    def do_update(self, dt):
        """Advances by dt real seconds."""
        if self.finished: return
        self.t += dt
        if self.phase == 0:
            self.alpha = min(1.0, self.t / LOGO_FADE_IN)
            if self.t >= LOGO_FADE_IN:
                self.alpha = 1.0; self.t = 0.0; self.phase = 2 if self.skip else 1; self.skip = False
        elif self.phase == 1:
            if self.t >= LOGO_HOLD: self.phase = 2; self.t = 0.0
        else:
            self.alpha = max(0.0, 1.0 - self.t / LOGO_FADE_OUT)
            if self.t >= LOGO_FADE_OUT: self.i += 1; self.phase = 0; self.t = 0.0; self.alpha = 0.0; self.skip = False

    def draw_all(self, width_px, height_px):
        """Square of 450 units (window height = 800 units) at the center of the screen, alpha blending."""
        if self.finished: return
        import pyglet
        sp = self.sprites.get(self.i)
        if sp is None:
            img = pyglet.image.load(self.entries[self.i]); sp = self.sprites[self.i] = pyglet.sprite.Sprite(img)
        side = LOGO_SIDE * height_px / 800.0
        sp.update(x=(width_px - side) / 2, y=(height_px - side) / 2, scale_x=side / sp.image.width, scale_y=side / sp.image.height)
        sp.opacity = int(round(255 * self.alpha)); sp.draw()


class TitleTouch:
    """TapToStart (window type 73): blinking "Touchez l'ecran" and copyright line. Counts game frames (30 Hz).
    Without the engine's CountReset message (code 0), the first display only happens after c_firstWait frames (TT_WAITS); with it, it starts right away and the copyright stays fully opaque."""
    def __init__(self, image0, files):
        self.first_wait, self.cp_first, self.cp_second = TT_WAITS.get(GM.profile().key, TT_WAITS['dq4'])
        self.begin = image0; self.acc = TT_ACC; self.alpha = 0.0; self.first = True; self.waiting = self.first_wait
        self.alpha_c = 0.0; self.state_c = 0; self.sprites = {}; self.files = files

    def reset(self):
        """TapToStart.CountReset: the engine announces the end of the first phase of the title."""
        if self.first: self.waiting = 0
        self.state_c = 5; self.alpha_c = 1.0

    def do_update(self, image):
        """One game frame (TapToStart.Update, once per rendered frame)."""
        f = image - self.begin
        if f >= self.waiting:
            self.first = False; self.alpha += self.acc
            if self.alpha > 1.0 or self.alpha < 0.0:
                self.waiting = f + TT_WAIT; self.alpha = 1.0 if self.acc > 0 else 0.0; self.acc = -self.acc
        c = self.state_c
        if c == 0 and f >= self.cp_first: self.state_c = 1
        elif c == 1:
            self.alpha_c = min(1.0, self.alpha_c + CP_ACC)
            if self.alpha_c >= 1.0: self.state_c = 2
        elif c == 2 and f >= self.cp_second: self.state_c = 3
        elif c == 3:
            self.alpha_c = max(0.0, self.alpha_c - CP_ACC)
            if self.alpha_c <= 0.0: self.state_c = 4

    def draw_all(self, cx, cy, ui_scale, height_px):
        """(cx, cy, ui_scale) = reference frame of the interface column (see Game._ui_reference); height_px = window height."""
        import pyglet
        for name_str, alpha, w, h, x, y in (('taptostart', self.alpha, TT_L, TT_H, cx, cy - TT_BOTTOM * ui_scale), ('copyright', self.alpha_c, CP_L, CP_H, cx, CP_TOP * ui_scale)):
            if alpha <= 0.001 or name_str not in self.files: continue
            sp = self.sprites.get(name_str)
            if sp is None: sp = self.sprites[name_str] = pyglet.sprite.Sprite(pyglet.image.load(self.files[name_str]))
            sp.update(x=x - w * ui_scale / 2, y=y - h * ui_scale / 2, scale_x=w * ui_scale / sp.image.width, scale_y=h * ui_scale / sp.image.height)
            sp.opacity = int(round(255 * min(1.0, alpha))); sp.draw()


# ---- "License" screen (type 80, Make_License / LicensePolicy / LicenseNobu)
PRIVACY_URL = 'https://square-enix-games.com/en_US/documents/privacy'       # LicensePolicy.OnMouseUpAsButton: language != 0 (Japanese opens https://www.jp.square-enix.com/privacy/)
LICENSE_BORDER = (-215.0, -345.0, 215.0, 330.0)
LICENSE_TEXT = (-198.0, -262.0, 186.0, 272.0)                  # text area (x0, y0, x1, y1), interface units
LICENSE_POLICY = (-198.0, -334.0, 90.0, -284.0)              # "Privacy Policy" button
LICENSE_BACK = (136.0, -337.0, 198.0, -285.0)
LICENSE_TITLE_Y = 302.0
LICENSE_TITLE = N_('menus.license')                    # (drawn by Pause._label, which translates it; "Privacy Policy" is the game's text)


# Text added at the top of the License screen (in English, like the original list): what the port is and what it uses ({name}, {library}: the running game, games.py). The original list (TextAsset
# Menu/License_list_A) follows, unchanged.
PROJECT_LICENSE = (
    "<color=orange>{name} PC port (unofficial)</color>\n"
    "--------------------------------------------------\n"
    "This is an unofficial, non-commercial fan project. It is not affiliated with, endorsed by or sponsored by SQUARE ENIX CO., LTD., ArtePiazza or any other rights holder. DRAGON QUEST is a trademark of SQUARE ENIX CO., LTD.\n"
    "\n"
    "This program contains no game content. It runs the original game engine ({library}) and reads the game data from the Android version of {name} that you own (the APK files and the save files on your own computer). Nothing from the game is copied, modified or distributed by this program, and your original files are never changed.\n"
    "\n"
    "The French text comes from an unofficial French translation patch that the user applied to those APK files.\n"
    "\n"
    "How it works: the original ARM64 game engine runs unmodified inside a CPU emulator (Unicorn). The Unity layer of the Android game (display, menus, input and sound) is re-implemented in Python (pyglet), following the behavior of the original game code. The 16:9 display, the mouse and keyboard controls, the on-screen buttons, the settings menu, the instant save states and the save export / import tool are additions of this port.\n"
    "\n"
    "Your save files, save states and settings stay on your computer (in the \"data\" folder of this project). This program does not send any data over the Internet; only the launcher downloads the components listed below, once, the first time it runs. The \"Privacy Policy\" button opens the publisher's web page in your browser.\n"
    "\n"
    "<color=orange>Components used by this port</color>\n"
    "--------------------------------------------------\n"
    "The Python packages below are downloaded by the launcher from the Python Package Index; none of them is distributed with this program.\n"
    "\n"
    "Python - PSF License - python.org\n"
    "Unicorn Engine (CPU emulator) - GNU GPL v2 - unicorn-engine.org\n"
    "pyglet (window, graphics, input) - BSD 3-Clause License - pyglet.org\n"
    "NumPy - BSD 3-Clause License - numpy.org\n"
    "Pillow (images) - MIT-CMU License - python-pillow.org\n"
    "UnityPy (reading the game data) - MIT License - github.com/K0lb3/UnityPy\n"
    "Capstone (reading the menu layout from the game code, once) - BSD License - capstone-engine.org\n"
    "SoundFile (music) - BSD 3-Clause License; its libsndfile library - LGPL 2.1 - github.com/bastibe/python-soundfile\n"
    "\n"
    "Key and gamepad button pictures of the Controls menu: \"Input Prompts\" by Kenney - CC0 1.0 (public domain) - kenney.nl (included with this program, in dq456_pc/assets/input_prompts)\n"
    "\n"
    "<color=orange>Original game notices</color>\n"
    "--------------------------------------------------\n"
    "The notices below are those of the original Android game. They are kept unchanged.\n"
    "\n\n")


class License:
    """License text (TextAsset Menu/License_list_A) in a scrolling window, with the <color=orange> titles in orange. The exact positions of the original window were not recovered
    (they depend on the screen's aspect ratio): layout drawn here, scrolling with the wheel, the arrow keys, PageUp/PageDown, or by dragging the bar."""
    def __init__(self, path):
        import re
        self.layout_cache = None; self.zones = []; self.topmost = 0.0; self.dragging = None; self.bar_zone = None; self.hovered = None; self.geom = None
        game = GM.profile()
        txt = PROJECT_LICENSE.replace('{name}', game.name).replace('{library}', game.library.rsplit('/', 1)[-1]) + (open(path, 'rb').read().decode('utf-8', 'replace').replace('\r\n', '\n').replace('\ufeff', '') if path else '')
        self.plan = []; out = []; n = 0; orange = False
        for m in re.split(r'(<color=orange>|</color>)', txt):
            if m == '<color=orange>': orange = True
            elif m == '</color>': orange = False
            elif m: self.plan.append((n, n + len(m), orange)); out.append(m); n += len(m)
        self.text = ''.join(out)

    def _layout(self, J, ui_scale):
        """pyglet TextLayout of the window (recreated if the scale changes)."""
        lookup_key = round(ui_scale, 3)
        if self.layout_cache is not None and self.layout_cache[0] == lookup_key: return self.layout_cache[1]
        P = J.pause; P._label('x', 10)                                                                     # (registers the game font)
        size_value = 11.0 * ui_scale * 0.75; wid = int((LICENSE_TEXT[2] - LICENSE_TEXT[0]) * ui_scale); topmost = int((LICENSE_TEXT[3] - LICENSE_TEXT[1]) * ui_scale)
        fonts = tuple(P._pol or ()) + ('Consolas', 'DejaVu Sans Mono', 'Courier New')
        doc = pyglet.text.document.FormattedDocument(self.text)
        doc.set_style(0, len(self.text), dict(font_name=fonts, font_size=size_value, color=(235, 235, 235, 255)))
        for a, b, o in self.plan:
            if o: doc.set_style(a, b, dict(color=(255, 160, 40, 255)))
        lay = pyglet.text.layout.ScrollableTextLayout(doc, width=wid, height=topmost, multiline=True)
        self.layout_cache = (lookup_key, lay); return lay

    def maximum(self):
        lay = self.layout_cache[1] if self.layout_cache else None
        return max(0.0, lay.content_height - lay.height) if lay else 0.0

    def scroll_by(self, delta):
        self.topmost = min(self.maximum(), max(0.0, self.topmost + delta))

    def on_bar(self, x, y):
        zb = self.bar_zone
        return zb is not None and self.maximum() > 0 and zb[0] <= x <= zb[2] and zb[1] <= y <= zb[3]

    def drag_to(self, y):
        """The scrollbar thumb follows the pointer (LicenseNobu: thumb position -> proportion of the text); y in pixels (pyglet, upward)."""
        if self.geom is None: return
        by0, bh, th = self.geom; free = bh - th
        if free <= 0: return
        self.topmost = min(1.0, max(0.0, (by0 + bh - th / 2 - y) / free)) * self.maximum()

    def draw_all(self, J, cx, cy, ui_scale):
        pg = pyglet; from pyglet import gl as g
        P = J.pause; k = ui_scale * 800.0 / 900.0
        ui_scale = min(ui_scale, 0.97 * J.height / (LICENSE_BORDER[3] - LICENSE_BORDER[1])); k = ui_scale * 800.0 / 900.0
        U = lambda x, y: (cx + x * ui_scale, cy + y * ui_scale)
        g.glDisable(g.GL_DEPTH_TEST); g.glEnable(g.GL_BLEND); g.glBlendFunc(g.GL_SRC_ALPHA, g.GL_ONE_MINUS_SRC_ALPHA)
        x0, y0 = U(LICENSE_BORDER[0], LICENSE_BORDER[1]); x1, y1 = U(LICENSE_BORDER[2], LICENSE_BORDER[3]); P._border(x0, y0, x1 - x0, y1 - y0, k)
        P._restore_blend()
        label = P._label(LICENSE_TITLE, 24 * ui_scale * 0.75); label.x = cx - label.content_width / 2; label.y = cy + LICENSE_TITLE_Y * ui_scale - 9 * ui_scale; label.draw()
        lay = self._layout(J, ui_scale); self.topmost = min(self.topmost, self.maximum())
        tx, ty = U(LICENSE_TEXT[0], LICENSE_TEXT[1]); lay.x = int(tx); lay.y = int(ty); lay.view_y = -int(self.topmost); lay.draw()
        # scrollbar
        bx0, by0 = U(LICENSE_TEXT[2] + 4, LICENSE_TEXT[1]); bw, bh = 8 * ui_scale, (LICENSE_TEXT[3] - LICENSE_TEXT[1]) * ui_scale; m = self.maximum()
        pg.shapes.Rectangle(bx0, by0, bw, bh, color=(34, 36, 42)).draw()
        if m > 0:
            th = max(26 * ui_scale, bh * lay.height / lay.content_height); hau = by0 + bh - th - (bh - th) * (self.topmost / m)
            P._plate(bx0 - 1, hau, bw + 2, th, k * 0.6, self.dragging is not None); self.geom = (by0, bh, th)
        self.bar_zone = (bx0 - 4, by0, bx0 + bw + 4, by0 + bh)
        px0, py0 = U(LICENSE_POLICY[0], LICENSE_POLICY[1]); px1, py1 = U(LICENSE_POLICY[2], LICENSE_POLICY[3])
        P._plate(px0, py0, px1 - px0, py1 - py0, k, self.hovered == 'politique'); P._restore_blend()          # (hover: darkened plate, no yellow outline)
        e2 = P._label('Privacy Policy', 16 * ui_scale * 0.75); e2.x = (px0 + px1) / 2 - e2.content_width / 2; e2.y = (py0 + py1) / 2 - 5 * ui_scale; e2.draw()
        rx0, ry0 = U(LICENSE_BACK[0], LICENSE_BACK[1]); rx1, ry1 = U(LICENSE_BACK[2], LICENSE_BACK[3])
        P._back_button(rx0, ry0, rx1 - rx0, ry1 - ry0, self.hovered == 'retour')
        self.zones = [(px0, py0, px1, py1, 'politique'), (rx0, ry0, rx1, ry1, 'retour')]

    def zone(self, x, y):
        for a, b, c, d, name_str in self.zones:
            if a <= x <= c and b <= y <= d: return name_str
        return None
