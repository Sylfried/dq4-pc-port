"""Test of the two windows of the Pause menu, like the System menu of Dragon Quest VII: the root on the left, the page opened from it on the right.

    python3 tests/test_pause_two_panels.py

While the root is chosen, its window is alone, on the left: nothing is shown on its right before a page is opened (Enter, right or a click). The page is then used
on the right while the root stays on the left, its line lit; a click on another root line opens that page instead; Esc goes back to the root. The right pages all take the
width of the widest, their tops aligned with the root's. A menu opened on a page, the history and the interface editor stay one window; a screen too narrow for both (16:10, 4:3) draws them smaller, down to 75 %, and narrower still: one window.
The menu is driven with the fake "game" of test_inactive_lines, drawn in a hidden pyglet window.
"""
import os, sys, unittest

HERE = os.path.dirname(os.path.abspath(__file__)); sys.path.insert(0, HERE); sys.path.insert(0, os.path.join(HERE, '..'))
import _paths          # (test helper: finding the source code in the subfolders of dq456_pc)
import test_inactive_lines as TI
from dq456_pc.menus import pause as PA
from dq456_pc.menus import name_entry as NE

K = TI.K; LEFT = TI.LEFT


def root_menu(**attrs):
    J, p = TI.menu('root', **attrs); p.dims = {}; p.left_zones = []; p.page_rect = None; return J, p


def line_of(p, page):
    return next(i for i, x in enumerate(p._entries_root()) if x.get('page') == page)


def centre(z): return ((z[0] + z[2]) / 2, (z[1] + z[3]) / 2)


def opened(page, **attrs):
    J, p = root_menu(**attrs); p.selected['root'] = line_of(p, page); TI.render_texture(p); p._validate(); TI.render_texture(p); return J, p


class TwoPanels(unittest.TestCase):
    def test_nothing_on_the_right_before_a_click(self):
        J, p = root_menu()
        for page in PA.Pause.SIDE_PAGES:
            p.selected['root'] = line_of(p, page); TI.render_texture(p)
            self.assertIsNone(p.page_rect, page); self.assertEqual(p.screen_page, 'root'); self.assertEqual(p.left_zones, [])
            self.assertEqual({z[4] for z in p.zones}, {i for i, x in enumerate(p._entries_root()) if not p._inactive(x)}, page)          # (the zones are those of the root)
        p.mouse_mode = True; img = TI.render_texture(p); xl, xr, top, wl, wr, kk, hf = p._two_panels(J.width, J.height, max(0.75, J.height / 900.0))
        inside = img[int(top - hf + PA.HELP_H * kk + 10):int(top - 30), int(xr + 30):int(xr + wr - 30)]
        self.assertLess(inside[..., :3].max(), 60)                                                                                 # (the right frame is there, empty: no title, no line)
        self.assertGreater(img[int(top - hf / 2), int(xr):int(xr + 8)][..., :3].max(), 150)                                       # (its border)

    def test_help_zone(self):
        """At the bottom of the right frame, the help of the chosen line (no pop-up): the root's line (nothing for "Resume", which has none), then the open page's line."""
        J, p = root_menu(); k = max(0.75, J.height / 900.0)
        def zone(img):
            xl, xr, top, wl, wr, kk, hf = p._two_panels(J.width, J.height, k)
            return img[int(top - hf + 8):int(top - hf + PA.HELP_H * kk - 12), int(xr + 30):int(xr + wr - 30)][..., :3].max()
        p.selected['root'] = 0; self.assertLess(zone(TI.render_texture(p)), 60)
        p.selected['root'] = next(i for i, x in enumerate(p._entries_root()) if x['l'] == 'settings.quit_game'); self.assertGreater(zone(TI.render_texture(p)), 120)
        J, p = opened('difficulty'); p.selected['difficulty'] = 2; self.assertGreater(zone(TI.render_texture(p)), 120)

    def test_same_frame_content_at_the_top(self):
        """The right frame keeps the same size for every page, the history included; a short page has its lines at the top, under its title."""
        frames = {page: opened(page)[1].page_rect for page in PA.Pause.SIDE_PAGES + ('history',)}
        self.assertEqual(len({tuple(round(v, 3) for v in f) for f in frames.values()}), 1, frames)
        J, p = opened('cheats'); f = p.page_rect; z = p.zones[0]
        self.assertLess(f[3] - z[3], 120); self.assertGreater(z[1] - f[1], 300)                                                   # (one line: right under the title, the frame empty below)

    def test_page_on_the_right_once_opened(self):
        for page in PA.Pause.SIDE_PAGES:
            J, p = opened(page); self.assertEqual(p.stack, ['root', page]); self.assertIsNotNone(p.page_rect, page)
            self.assertGreater(p.page_rect[0], max(z[2] for z in p.left_zones), page)                                             # (the page is on the right of the root)

    def test_right_pages_same_width_tops_aligned(self):
        frames = {page: opened(page)[1].page_rect for page in PA.Pause.SIDE_PAGES}
        self.assertEqual(len({(round(f[0], 3), round(f[2], 3), round(f[3], 3)) for f in frames.values()}), 1, frames)

    def test_enter_right_esc(self):
        for key in (K.RETURN, K.RIGHT):
            J, p = root_menu(); p.selected['root'] = line_of(p, 'sound'); TI.render_texture(p)
            p.key_press(key); self.assertEqual(p.stack, ['root', 'sound'], key); TI.render_texture(p)
            self.assertTrue(p.left_zones); self.assertGreater(min(z[0] for z in p.zones), max(z[2] for z in p.left_zones))          # (the page is used on the right, the root stays on the left)
            p.key_press(K.BACKSPACE); self.assertFalse(p.opened)                                               # (Backspace from a page beside the root: the menu closes, never the root alone)
            J, p = root_menu(); p.selected['root'] = line_of(p, 'sound'); p.key_press(key); p.key_press(K.ESCAPE); self.assertFalse(p.opened)          # (Esc: the whole menu closes, from a page too)
        J, p = root_menu(); p.selected['root'] = 0; p.key_press(K.RIGHT); self.assertEqual(p.stack, ['root']); self.assertTrue(p.opened)          # ("Resume": right does nothing)

    def test_previous_next_page_keys(self):
        """Q / R (L / R): previous / next line of the root, its page opening on the right; a line without a page (Resume, Return to title...) is only chosen; it loops."""
        J, p = root_menu(); p.selected['root'] = line_of(p, 'sound'); p.key_press(K.RETURN); TI.render_texture(p)
        L, R = J.reg.codes('L')[0], J.reg.codes('R')[0]                                                  # (the previous / next page keys: Q / R on a QWERTY keyboard)
        p.key_press(R); self.assertEqual(p.stack, ['root', 'controls'])
        p.key_press(L); p.key_press(L); self.assertEqual(p.stack, ['root', 'display'])
        p.key_press(L); self.assertEqual(p.stack, ['root']); self.assertEqual(p._entries_root()[p.selected['root']]['l'], 'settings.resume'); self.assertTrue(p.opened)
        p.key_press(L); self.assertEqual(p.stack, ['root']); self.assertEqual(p._entries_root()[p.selected['root']]['l'], 'settings.quit_game')          # (loops: the last line)

    def test_click_on_the_root_opens_its_page(self):
        J, p = root_menu(); TI.render_texture(p)
        z = next(z for z in p.zones if z[4] == line_of(p, 'display')); p.click(*centre(z), LEFT); self.assertEqual(p.stack, ['root', 'display'])

    def test_click_on_the_root_while_a_page_is_open(self):
        J, p = opened('display')
        z = next(z for z in p.left_zones if z[4] == line_of(p, 'sound')); p.click(*centre(z), LEFT)
        self.assertEqual(p.stack, ['root', 'sound']); self.assertEqual(p.selected['root'], line_of(p, 'sound'))
        TI.render_texture(p); z = next(z for z in p.left_zones if z[4] == line_of(p, 'sound')); p.click(*centre(z), LEFT); self.assertEqual(p.stack, ['root', 'sound'])          # (its own line: nothing)
        TI.render_texture(p); z = next(z for z in p.left_zones if z[4] == 0); p.click(*centre(z), LEFT); self.assertFalse(p.opened)          # ("Resume" closes the menu)

    def test_one_window(self):
        J, p = TI.menu('display'); p.dims = {}; p.left_zones = []; p.page_rect = None; TI.render_texture(p); self.assertEqual(p.left_zones, []); self.assertIsNone(p.page_rect)          # (a menu opened on a page)
        J, p = root_menu(); J.width, J.height = 700, 720; p.selected['root'] = line_of(p, 'display'); p._validate(); TI.render_texture(p); self.assertIsNone(p.page_rect); self.assertEqual(p.left_zones, [])          # (too narrow for both, even smaller)

    def test_16_10_and_4_3_screens(self):
        """Too narrow at full size (16:10, 4:3): the two windows are drawn smaller, inside the screen."""
        for w, h in ((1920, 1200), (1600, 1200), (1280, 720)):
            J, p = root_menu(); J.width, J.height = w, h; k = max(0.75, h / 900.0)
            p.selected['root'] = line_of(p, 'display'); p._validate(); TI.render_texture(p)
            self.assertIsNotNone(p.page_rect, (w, h)); self.assertGreaterEqual(min(z[0] for z in p.left_zones), 0); self.assertLessEqual(p.page_rect[2], w - 12 * k * 0.75, (w, h))
            kk = p.dims[(w, h, PA.LG.current_language())][0]; self.assertGreaterEqual(kk, 0.75 * k); self.assertLessEqual(kk, k)
            if (w, h) == (1280, 720): self.assertEqual(kk, k)          # (16:9: full size)


class WarmUp(unittest.TestCase):
    def test_first_openings_build_no_label(self):
        """warm_up (called before the first game frame) builds the text labels of the first Esc and of the new-game panel, its name page included: opening them later builds
        none (each one cost about a millisecond: the first opening stalled for half a second). It draws nothing on the screen and leaves the menu as it was."""
        w = TI.window(); w.switch_to(); w.clear()
        J = TI.FakeGame(); p = PA.Pause(J); J.pause = p; J.last_device = 'keyboard'; J.name_entry = NE.NameEntry(J)
        stack, selected = p.stack, p.selected
        p.warm_up()
        im = TI.pyglet.image.get_buffer_manager().get_color_buffer().get_image_data()
        self.assertEqual(max(im.get_data('RGBA', im.width * 4)[::4]), 0)                              # (nothing drawn: the empty scissor box)
        self.assertFalse(p.opened); self.assertIs(p.stack, stack); self.assertIs(p.selected, selected); self.assertNotIn('new_game', p.__dict__); self.assertFalse(p.new_game)
        self.assertGreater(len(J.lbl), 200)
        n = len(J.lbl)
        for side, new_game in (('display', False), (None, True)):
            p.open_menu(side=side, new_game=new_game); TI.render_texture(p)
            if new_game: p._open_root_page('name'); TI.render_texture(p)
            p.shutdown()
        self.assertEqual(list(J.lbl)[n:], [])

if __name__ == '__main__':
    unittest.main()
