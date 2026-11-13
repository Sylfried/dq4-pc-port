"""Test of the inactive lines of the Pause menu ("Display" page: a line inactive in full screen, "Resolution"; "Save states" page: empty slots) and of the "Modifiers" label (categories Difficulty, Modifier, Cheats).

    python3 tests/test_inactive_lines.py

A line that cannot be modified in the current state (`off`) is grayed out entirely (label, value, arrow, ↺ button, checkbox), never chosen (the golden cursor and the keyboard skip it), never hovered (no
highlight), never clicked or confirmed; no more red note text under the values. The test covers all the line types of all the pages: it marks each line, one by one, as inactive (PauseMarked)
and verifies that no action reaches it (keyboard, click, hover, wheel, drag, input, drop-down list). The menu is driven with a fake "game"; drawing is done in a hidden pyglet window (EGL without a screen):
hover is checked on the pixels (the inactive line does not change when the pointer hovers over it, an active one does).
"""
import copy, os, sys, types, unittest

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), '..'))
import _paths          # (test helper: finding the source code in the subfolders of dq4_pc)
import pyglet
if sys.platform.startswith('linux') and not os.environ.get('DISPLAY'): pyglet.options['headless'] = True; pyglet.options['shadow_window'] = False
import numpy as np
from dq4_pc.persistence import settings as RG
from dq4_pc.menus import pause as PA

K = pyglet.window.key
LEFT = 1
PAGES = ('root', 'display', 'sound', 'controls', 'changes', 'states', 'quit', 'interface')
DRAWN_PAGES = tuple(p for p in PAGES if p != 'interface')          # (the "Interface" page draws the game preview: the fake game has none)
CACHE = os.environ.get('DQ_UI_CACHE', '/inexistant')                    # (optional: the game's interface cache for the font and the icons; without it, system fonts and a fallback plate)


class FakeGame:
    """What the Pause menu asks of the window; `full` can change at any time (the lines are recomputed every frame)."""
    mode = 4; zoom = 1.0

    def __init__(self, full=False):
        self.reg = RG.Settings(None); self.full = full; self.res = (1280, 720); self.calls = []; self.lbl = {}
        self.width, self.height = 1280, 720; self.args = types.SimpleNamespace(cache=CACHE); self.mouse = None
        self.post = types.SimpleNamespace(max_msaa=None); self.sound = types.SimpleNamespace(active=True, listening=False, listen=lambda b: None, tick=lambda: None)

    is_fullscreen = property(lambda self: self.full)
    def set_full_screen(self, v): self.full = bool(v); self.calls.append(('plein', bool(v)))
    def resolutions(self): return [(1280, 720), (1920, 1080), (2560, 1440)]
    def current_resolution(self): return self.res
    def set_resolution(self, v): self.res = tuple(v); self.calls.append(('res', tuple(v)))
    def set_mode(self, v): self.calls.append(('mode', v))
    def set_distance(self, v): self.calls.append(('distance', v))
    def set_sound(self, yes): self.calls.append(('sound', yes))
    def apply_mix(self): self.calls.append('mixage')
    def preview_sound(self, category): self.calls.append(('apercu', category))
    def set_fade(self, v): self.calls.append(('fondu', v))
    def apply_text(self): self.calls.append('texte')
    def apply_game(self): self.calls.append('jeu')
    def set_battle_speed(self, v): self.calls.append(('battle', v))
    def window_names(self): return {}
    def state_info(self, n): return None
    def pause_game(self, yes): pass
    def quit_game(self): self.calls.append('quit')
    def back_to_title(self): self.calls.append('titre')

    def _lbl(self, text, size_value, color=(255, 255, 255, 255), fonts=()):
        k = (text, round(size_value, 1), color, fonts)
        if k not in self.lbl: self.lbl[k] = pyglet.text.Label(text, font_size=size_value, color=color, anchor_x='left', anchor_y='baseline')
        return self.lbl[k]


class PauseMarked(PA.Pause):
    """Pause menu in which some lines (labels in `inactive`, on all pages) are marked inactive: lets each line type be exercised."""
    inactive = ()

    def _entries(self):
        e = super()._entries()
        for x in e:
            if x['t'] != 'sep' and x.get('l') in self.inactive: x['off'] = True
        return e


def menu(page, full=False, klass=PA.Pause, **attrs):
    J = FakeGame(full); p = klass(J); p.opened = True; p.stack = [page]
    for k, v in attrs.items(): setattr(p, k, v)
    return J, p


def state(J, p):
    """Everything an action on a line could change."""
    return repr((copy.deepcopy(J.reg.v), list(J.calls), list(p.stack), p.capture, p.entry, p.open_dropdown, p.popup, p.dragging, J.full, J.res, p.state_action))


def labels(e): return [x.get('l') for x in e]


_win = []
def window():
    """Hidden pyglet window (a single one for the whole test); None if the graphics context is missing here."""
    if not _win:
        try:
            import pyglet.window
            _win.append(pyglet.window.Window(width=1280, height=720, visible=False))
        except Exception as ex: _win.append(ex)
    if isinstance(_win[0], Exception): raise unittest.SkipTest('no graphics context here (%r)' % (_win[0],))
    return _win[0]


def render_texture(p):
    """Draws the menu then returns the image (RGBA array, origin at bottom left)."""
    w = window(); w.switch_to(); w.clear(); p.draw_all()
    im = pyglet.image.get_buffer_manager().get_color_buffer().get_image_data()
    return np.frombuffer(im.get_data('RGBA', im.width * 4), np.uint8).reshape(im.height, im.width, 4).copy()


def crop(img, z, margin=2): return img[int(z[1]) + margin:int(z[3]) - margin, int(z[0]) + margin:int(z[2]) - margin]


def zone_of(p, idx):
    """Area (x0, y0, x1, y1) of line idx in the last frame: (area, active?)."""
    for z in p.zones:
        if z[4] == idx: return z[:4], True
    for z in p.zones_off:
        if z[4] == idx: return z[:4], False
    return None, None


class PauseFullScreenLine(PA.Pause):
    """The Affichage page without "Resolution" has no line that depends on the full screen any more: "Brightness" is made inactive in full screen here, as "Resolution" was."""
    def _entries(self):
        e = super()._entries()
        for x in e:
            if x.get('l') == 'settings.brightness': x['off'] = self.J.is_fullscreen; x['hint'] = 'No effect in full screen (test)'
        return e


class DisplayPage(unittest.TestCase):
    """A line inactive in full screen. "Brightness", the line right after "Fullscreen" now, plays its part here
    (PauseFullScreenLine) so that the mechanism stays tested on the real page."""
    def lines(self, full):
        J, p = menu('display', full, klass=PauseFullScreenLine); e = p._entries(); return J, p, e, {x['l']: i for i, x in enumerate(e)}

    def test_line_states(self):
        for full in (False, True):
            J, p, e, n = self.lines(full)
            self.assertEqual(p._inactive(e[n['settings.brightness']]), full, full); self.assertNotIn('settings.resolution', n)
            self.assertFalse(p._inactive(e[n['settings.fullscreen']])); self.assertFalse(p._inactive(e[n['settings.sharpness']])); self.assertFalse(p._inactive(e[n['settings.interface']]))

    def test_no_more_red_note_text(self):
        for full in (False, True):
            J, p, e, n = self.lines(full)
            for x in e: self.assertNotIn('note', x, x.get('l'))
        with open(PA.__file__, encoding='utf-8') as f: src = f.read()
        self.assertNotIn("entry['note']", src); self.assertNotIn('note=', src); self.assertNotIn('dec = ', src)                    # (no more `note` parameter, no more space reserved under the value; still in red: the error message at the foot of the frame and the editor's "Hidden", which are not notes under the values)

    def test_navigation_skips_inactive_lines(self):
        J, p, e, n = self.lines(False); p.selected['display'] = n['settings.fullscreen']                      # window: nothing is skipped
        p.key_press(K.S); self.assertEqual(p.selected['display'], n['settings.brightness'])
        p.key_press(K.W); self.assertEqual(p.selected['display'], n['settings.fullscreen'])
        J, p, e, n = self.lines(True); p.selected['display'] = n['settings.fullscreen']                       # full screen: "Brightness" is skipped
        p.key_press(K.S); self.assertEqual(p.selected['display'], n['settings.contrast'])
        p.key_press(K.W); self.assertEqual(p.selected['display'], n['settings.fullscreen'])
        p.key_press(K.W); self.assertEqual(p.selected['display'], n['settings.language'])                           # ("Language" is the first line of the page)
        p.key_press(K.W); self.assertEqual(p.selected['display'], n['settings.interface'])                        # (the list wraps around, restarting from the end: the Interface button, last)
        p.key_press(K.S); self.assertEqual(p.selected['display'], n['settings.language'])
        p.key_press(K.S); self.assertEqual(p.selected['display'], n['settings.fullscreen'])

    def test_wheel_skips_inactive_lines(self):
        J, p, e, n = self.lines(True); p.selected['display'] = n['settings.fullscreen']
        p.wheel(1); self.assertEqual(p.selected['display'], n['settings.contrast'])                            # (wheel up = next line)

    def test_keyboard_without_effect_on_inactive_line(self):
        for full, lib in ((True, 'settings.brightness'),):
            J, p, e, n = self.lines(full); p.selected['display'] = n[lib]; before = state(J, p)
            for t in (K.RETURN, K.SPACE, K.LEFT, K.RIGHT, K.DELETE, K.HOME): p.key_press(t); p.selected['display'] = n[lib]
            self.assertEqual(state(J, p), before, (full, lib)); self.assertIsNone(p._current())

    def test_active_line_always_adjustable(self):
        J, p, e, n = self.lines(False); p.selected['display'] = n['settings.brightness']; p.key_press(K.RIGHT)          # window: the line can be set
        self.assertAlmostEqual(J.reg['brightness'], 1.1)

    def test_state_recomputed_each_frame(self):
        """A line grayed out because another value makes it ineffective becomes active again as soon as that value changes (and vice versa)."""
        J, p = menu('display', False, klass=PauseFullScreenLine); n = {x['l']: i for i, x in enumerate(p._entries())}
        self.assertFalse(p._inactive(p._entries()[n['settings.brightness']]))
        p.selected['display'] = n['settings.fullscreen']; p.key_press(K.RETURN)                                          # Enter on the switch: full screen
        self.assertTrue(J.full); self.assertTrue(p._inactive(p._entries()[n['settings.brightness']]))              # ... "Brightness" is grayed out right away
        p.key_press(K.RETURN); self.assertFalse(J.full); self.assertFalse(p._inactive(p._entries()[n['settings.brightness']]))      # ... and turns back on when returning to window mode

    def test_selection_leaves_line_that_became_inactive(self):
        J, p = menu('display', False, klass=PauseFullScreenLine); n = {x['l']: i for i, x in enumerate(p._entries())}; window()
        p.selected['display'] = n['settings.brightness']; render_texture(p); self.assertEqual(p.selected['display'], n['settings.brightness'])
        J.full = True; render_texture(p); self.assertEqual(p.selected['display'], n['settings.contrast'])                      # F11 while "Brightness" is selected: the cursor moves to the next active line
        J.full = False; render_texture(p); self.assertEqual(p.selected['display'], n['settings.contrast'])                    # (back in window mode: the line turns back on, the cursor stays where it is)

    def test_click_hover_and_tooltip(self):
        J, p = menu('display', True, klass=PauseFullScreenLine); n = {x['l']: i for i, x in enumerate(p._entries())}; window(); render_texture(p)
        for lib in ('settings.brightness',):
            z, active = zone_of(p, n[lib]); self.assertFalse(active, lib)
            for f in (0.05, 0.3, 0.5, 0.7, 0.95):                                                          # (label, value, arrow, ↺ button: anywhere in the cell)
                x, y = z[0] + f * (z[2] - z[0]), (z[1] + z[3]) / 2; before = state(J, p); selected = p.selected['display']
                p.hovered(x, y); self.assertTrue(p.mouse_mode); self.assertEqual(p.selected['display'], selected, 'survol')
                p.click(x, y, LEFT); self.assertEqual(state(J, p), before, 'clic'); self.assertEqual(p.selected['display'], selected)
                p.release(x, y, LEFT)
            self.assertTrue(p._line_helptext(p._entries()[n[lib]]), lib)                                      # (it keeps its help: it says why)
        self.assertNotIn('settings.enter', p._line_helptext(p._entries()[n['settings.brightness']]))                           # (but no more "Enter or click: open the list" hint)
        z, active = zone_of(p, n['settings.sharpness']); self.assertTrue(active)                                      # an active line, on the other hand, responds
        p.hovered((z[0] + z[2]) / 2, (z[1] + z[3]) / 2); self.assertEqual(p.selected['display'], n['settings.sharpness'])

    def test_pixels_no_highlight_on_hover(self):
        """The inactive line is identical with or without the pointer over it; an active line changes (test control)."""
        J, p = menu('display', True, klass=PauseFullScreenLine); n = {x['l']: i for i, x in enumerate(p._entries())}; window(); far = (5.0, 5.0)
        p.mouse_mode = True; p.mouse_pos = far; render_texture(p); background = render_texture(p)
        for lib, change in (('settings.brightness', False), ('settings.sharpness', True), ('settings.contrast', True)):
            z, active = zone_of(p, n[lib]); self.assertEqual(active, change, lib)
            p.mouse_pos = ((z[0] + z[2]) / 2, (z[1] + z[3]) / 2); p.tt = None; above = render_texture(p); p.mouse_pos = far; p.tt = None
            equal = np.array_equal(crop(background, z), crop(above, z))
            self.assertEqual(equal, not change, '%s : %s' % (lib, 'identique' if equal else 'different'))
        p.mouse_pos = far

    def test_whole_cell_grayed(self):
        """The plate of an inactive line is darker than that of an active line, and its text is gray (not white)."""
        J, p = menu('display', True, klass=PauseFullScreenLine); n = {x['l']: i for i, x in enumerate(p._entries())}; window(); p.mouse_mode = False; img = render_texture(p)
        zr, _ = zone_of(p, n['settings.brightness']); zn, _ = zone_of(p, n['settings.sharpness'])
        def lum(z): c = crop(img, z, 6).astype(float); return c[..., :3].mean(), c[..., :3].max()
        (m_r, max_r), (m_n, max_n) = lum(zr), lum(zn)
        self.assertLess(m_r, m_n); self.assertLess(max_r, 200); self.assertGreater(max_n, 240)             # (grayed out: no pure white; active: white text)


class AllTypes(unittest.TestCase):
    """Every line of every page, marked inactive in turn: no action reaches it, the cursor avoids it, it has no click area."""
    def lines_of(self, page):
        J, p = menu(page); return [x for x in p._entries() if x['t'] != 'sep']

    def test_no_action_reaches_inactive_line(self):
        seen = set()
        for page in PAGES:
            for line in self.lines_of(page):
                lib = line['l']; J, p = menu(page, klass=PauseMarked, inactive=(lib,)); e = p._entries(); idx = labels(e).index(lib); seen.add(line['t'])
                self.assertTrue(p._inactive(e[idx]), (page, lib)); self.assertFalse(p._active(e[idx]))
                p.selected[page] = idx; before = state(J, p)
                for t in (K.RETURN, K.SPACE, K.LEFT, K.RIGHT, K.DELETE, K.HOME):
                    p.selected[page] = idx; p.key_press(t); self.assertEqual(state(J, p), before, (page, lib, t)); self.assertIsNone(p._current())
                self.assertIsNone(p._current(), (page, lib))
                p.selected[page] = idx; p.entry = None
                for direction in (K.S, K.W) if any(p._active(x) for x in e) else ():                          # navigation: never onto the inactive line (if another line is active)
                    p.selected[page] = idx
                    for _ in range(len(e) + 2):
                        p.key_press(direction); self.assertNotEqual(p.selected[page], idx, (page, lib, direction))
        self.assertGreaterEqual(seen, {'act', 'choice', 'slider', 'key', 'slot'})                            # (all line types have been exercised)

    def test_drawing_click_hover_of_each_inactive_line(self):
        window(); seen = set()
        for page in DRAWN_PAGES:
            for line in self.lines_of(page):
                lib = line['l']; J, p = menu(page, klass=PauseMarked, inactive=(lib,)); e = p._entries(); idx = labels(e).index(lib); seen.add(line['t'])
                p.selected[page] = idx; render_texture(p)
                if any(p._active(x) for x in e): self.assertNotEqual(p.selected[page], idx, (page, lib, 'the cursor leaves the inactive line'))          # (single-line page: the cursor has nowhere to go)
                z, active = zone_of(p, idx)
                if z is None: continue                                                                      # (line outside the view of a scrolling list: nothing to click)
                self.assertFalse(active, (page, lib)); self.assertNotIn(idx, p.bars); self.assertNotIn(idx, p.zones_val); self.assertNotIn(idx, p.default_zones); self.assertNotIn(idx, p.zones_mute)
                self.assertFalse([k for k in p.zones_eff if k[0] == idx])
                for f in (0.05, 0.25, 0.5, 0.75, 0.95):
                    x, y = z[0] + f * (z[2] - z[0]), (z[1] + z[3]) / 2; before = state(J, p); selected = p.selected[page]
                    p.hovered(x, y); self.assertEqual(p.selected[page], selected, (page, lib, 'survol')); p.click(x, y, LEFT); self.assertEqual(state(J, p), before, (page, lib, f, 'clic'))
                    self.assertEqual(p.selected[page], selected); p.release(x, y, LEFT); p.drag_to(x, y); self.assertEqual(state(J, p), before, (page, lib, 'glisser'))
                    render_texture(p)
        self.assertGreaterEqual(seen, {'act', 'choice', 'slider', 'key', 'slot'})

    def test_page_without_any_active_line(self):
        """All lines inactive: no error and no action; the selection does not move, the cursor is not drawn."""
        window()
        for page in DRAWN_PAGES:
            J, p = menu(page); libs = tuple(x['l'] for x in p._entries() if x['t'] != 'sep')
            J, p = menu(page, klass=PauseMarked, inactive=libs); p.selected[page] = 2 if page == 'quit' else 0; selected = p.selected[page]; before = state(J, p)
            render_texture(p); self.assertEqual(p.selected[page], selected, page)
            for t in (K.S, K.W, K.LEFT, K.RIGHT, K.RETURN, K.SPACE, K.DELETE, K.HOME, K.PAGEDOWN): p.key_press(t)
            p.wheel(1); p.wheel(-1); self.assertEqual(p.selected[page], selected, page)
            for z in p.zones_off:
                x, y = (z[0] + z[2]) / 2, (z[1] + z[3]) / 2; p.hovered(x, y); p.click(x, y, LEFT); p.release(x, y, LEFT); p.drag_to(x, y)
            self.assertEqual(p.selected[page], selected, page); render_texture(p); self.assertIsNone(p._current())
            self.assertEqual(state(J, p), before, page)

    def test_an_active_line_stays_usable(self):
        """Marking the other lines does not interfere with the one that remains (test control)."""
        window(); J, p = menu('quit', klass=PauseMarked, inactive=('settings.yes',)); p.selected['quit'] = 2; render_texture(p)
        p.key_press(K.W); self.assertEqual(p.selected['quit'], 2)                                               # "Yes" is inactive: the cursor stays on "No"
        z, active = zone_of(p, 1); self.assertFalse(active)
        p.click((z[0] + z[2]) / 2, (z[1] + z[3]) / 2, LEFT); self.assertNotIn('quit', J.calls); self.assertEqual(p.stack, ['quit'])          # click on inactive "Yes": the application does not close
        z, active = zone_of(p, 2); self.assertTrue(active); p.click((z[0] + z[2]) / 2, (z[1] + z[3]) / 2, LEFT); self.assertFalse(p.opened)          # click on "No" (active): the menu closes


class ChangesDuringAction(unittest.TestCase):
    """A line that becomes inactive while being held (slider dragged, value typed, list open) is released without changing anything."""
    def test_slider_dragged_value_typed_list_opened(self):
        window(); J, p = menu('display', klass=PauseMarked); n = {x['l']: i for i, x in enumerate(p._entries())}; render_texture(p)
        z, _ = zone_of(p, n['settings.sharpness']); bx0, bx1 = p.bars[n['settings.sharpness']]
        p.click(bx0 + 0.8 * (bx1 - bx0), (z[1] + z[3]) / 2, LEFT); self.assertEqual(p.dragging, n['settings.sharpness']); self.assertAlmostEqual(J.reg['sharpness'], 0.8, 1)       # (active: the click sets the cursor)
        p.inactive = ('settings.sharpness',); p.drag_to(bx0 + 0.2 * (bx1 - bx0), (z[1] + z[3]) / 2); self.assertIsNone(p.dragging); self.assertAlmostEqual(J.reg['sharpness'], 0.8, 1)   # (became inactive while being held: released)
        p.inactive = (); p.entry = [n['settings.sharpness'], '5']; p.inactive = ('settings.sharpness',); render_texture(p); self.assertIsNone(p.entry)
        p.inactive = (); p.selected['display'] = n['settings.shader']; p.key_press(K.RETURN); self.assertIsNotNone(p.open_dropdown)                                  # list opened on "Shader"
        p.inactive = ('settings.shader',); render_texture(p); self.assertIsNone(p.open_dropdown)


class ChangesCaption(unittest.TestCase):
    def test_caption_everywhere(self):
        J, p = menu('root'); libs = labels(p._entries())
        self.assertIn('settings.modifiers', libs); self.assertNotIn('Modifications', libs); self.assertNotIn('settings.cheats', libs); self.assertEqual(libs.index('settings.modifiers'), libs.index('settings.controls') + 1)           # ("Cheats" is a category of the page, not a root line)
        e = next(x for x in p._entries() if x['l'] == 'settings.modifiers'); e['ok'](); self.assertEqual(p.screen_page, 'changes')
        self.assertEqual([x['l'] for x in p._entries()], ['settings.difficulty', 'settings.hp_mp_restored_level_up', 'settings.modifier', 'settings.cheats', 'settings.game_ending_talking_king_bastione', 'settings.ending_played_shortcut'])           # (trois categories)


if __name__ == '__main__':
    unittest.main(verbosity=1)
