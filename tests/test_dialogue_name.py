"""Speaker name in the game's dialogue box (MenuMessage, command 4 of port 1), without a window or an engine:

1. protocol: `[4, 0]` = no name; `[4, 1]` announces the name, which the NEXT PACKET of the port carries (one integer per character); the name is cleared when the window hides (SetVisible(false));
   the other commands (type, cursor, scrolling) keep working, and neither they nor the other ports are taken for the name;
2. `MessageWindow.select_language(typ, y, feed, who)`: the name is shown only on the field window (type 0); the frame becomes frameData 191 (tab) and a "who" text appears (m_who: top-center anchor,
   size 10, local position (-104.5; 4; dy - 104)); without a name, or in battle (types 1 to 3), the rendering stays EXACTLY as before (frame 192, no "who" node);
3. the dimensions that position the window (extent, bottom) do not change with the tab (the Yes/No and the scale keep their place);
4. (if the interface cache exists: DQ_UI_CACHE, otherwise /tmp/uicache4) the REAL frames: 191 = 192 + a 246 x 32 tab that sticks out upward.

  python3 tests/test_dialogue_name.py        (Linux without a display: pyglet in "headless" mode)
"""
import os, sys, types, unittest

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), '..'))
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import _paths
import pyglet
if sys.platform.startswith('linux') and not os.environ.get('DISPLAY'): pyglet.options['headless'] = True; pyglet.options['shadow_window'] = False
from dq4_pc.menus import ui_menu as UM
from dq4_pc.core import engine as ENGINE

CACHE = _paths.ui_cache('/tmp/uicache4')


def chars(s): return [ord(c) for c in s]


def fake_border(z_top):
    """Minimal frame: a 452 x 126 rectangle (x -223..229, z -251..-125); with tab: + a rectangle x -223..23, z -125..z_top."""
    vt = [[-223.0, -251.0], [229.0, -251.0], [229.0, -125.0], [-223.0, -125.0]]; tri_indices = [0, 1, 2, 0, 2, 3]
    if z_top > -125.0: vt += [[-223.0, -125.0], [23.0, -125.0], [23.0, z_top], [-223.0, z_top]]; tri_indices += [4, 5, 6, 4, 6, 7]
    return dict(vtx=vt, uv=[[0.0, 0.0]] * len(vt), tri=tri_indices)


def fake_ml(with_borders=True):
    base = fake_border(-125.0)
    t0 = dict(win=[0.0, 10.0, 86.0], canvas=dict(vtx=[[-217.0, 4.0, -140.0], [217.0, 4.0, -140.0], [217.0, 4.0, -240.5], [-217.0, 4.0, -240.5]], uv=[[0, 0], [1, 0], [1, 1], [0, 1]], tris=[0, 1, 2, 0, 2, 3]),
              feed_local=[0.0, 8.0, -235.0], frame_mesh=dict(vtx=base['vtx'], uv=base['uv'], tris=base['tri']))
    t1 = dict(t0, win=[-225.0, 10.0, -362.0])
    msg = dict(types=[t0, t1, dict(t1), dict(t1)], feed=dict(vtx=[[0.0, 0.0], [1.0, 0.0], [1.0, 1.0]], uv=[[0, 0]] * 3, tris=[0, 1, 2], mats=[{'sheet': 0, 'part': 1}]), frame_mats=[{'sheet': 0, 'part': 4}])
    borders = [None] * 191 + [fake_border(-93.0), base] if with_borders else []
    return types.SimpleNamespace(message=msg, borders=borders, hdr={'lang': {'dy': 20.0, 'hiro': 1.0}})


class TestProtocol(unittest.TestCase):
    def ui(self): return ENGINE.Interface()

    def test_without_name(self):
        ui = self.ui(); ui.apply([(1, [4, 0])]); self.assertEqual((ui.msg['speaker'], ui.msg['speaker_pending']), ('', False))

    def test_name_in_next_packet(self):
        ui = self.ui(); ui.apply([(1, [4, 1]), (1, chars('Roi Bastien') + [0, 0])])
        self.assertEqual((ui.msg['speaker'], ui.msg['speaker_pending']), ('Roi Bastien', False))

    def test_name_in_two_different_frames(self):
        ui = self.ui(); ui.apply([(1, [4, 1])]); self.assertTrue(ui.msg['speaker_pending']); ui.apply([(1, chars('Angus'))]); self.assertEqual(ui.msg['speaker'], 'Angus')

    def test_name_is_not_taken_for_command(self):
        """The name packet starts with a character (here 1 = "cursor", 2 = "type"...): it must only be read as text."""
        ui = self.ui(); ui.msg['type'] = 0; ui.apply([(1, [4, 1]), (1, [1, 1, 2, 3])])
        self.assertEqual((ui.msg['type'], ui.msg['feed'], ui.msg['speaker']), (0, False, '\x01\x01\x02\x03'))
        ui.apply([(1, [1, 1])]); self.assertTrue(ui.msg['feed'])                  # the next packet is a command again

    def test_next_name_replaces_previous(self):
        ui = self.ui(); ui.apply([(1, [4, 1]), (1, chars('Roi Bastien')), (1, [4, 1]), (1, chars('Angus'))]); self.assertEqual(ui.msg['speaker'], 'Angus')

    def test_no_name_erases_previous(self):
        ui = self.ui(); ui.apply([(1, [4, 1]), (1, chars('Angus')), (1, [4, 0])]); self.assertEqual(ui.msg['speaker'], '')

    def test_other_commands_unchanged(self):
        ui = self.ui(); ui.apply([(1, [0, 2]), (1, [1, 1]), (1, [3, 40])])
        self.assertEqual((ui.msg['type'], ui.msg['feed'], ui.msg['y'], ui.msg['speaker']), (2, True, 40, ''))

    def test_other_ports_give_no_name(self):
        ui = self.ui(); ui.apply([(14, [4, 1]), (14, chars('Angus'))]); self.assertEqual((ui.msg['speaker'], ui.msg['speaker_pending']), ('', False))


class TestWindow(unittest.TestCase):
    def win(self, **kw): return UM.MessageWindow(fake_ml(**kw))

    def test_without_name_as_before(self):
        f = self.win(); f.select_language(0, 0, False, '')
        self.assertEqual(sorted(f.N), ['canvas', 'cursor', 'frame'])
        self.assertEqual(len(f.N['frame']['vtx']), 4); self.assertFalse(f.with_name)

    def test_with_name_tab_and_text(self):
        f = self.win(); f.select_language(0, 0, False, 'Roi Bastien')
        self.assertEqual(len(f.N['frame']['vtx']), 8); self.assertTrue(f.with_name)
        q = f.N['speaker']; self.assertEqual(q['text']['text'], 'Roi Bastien')
        self.assertEqual((q['text']['anchor'], q['text']['alignment'], q['text']['characterSize']), (1, 1, 10.0))
        self.assertEqual(q['pos'], [-104.5, 14.0, 86.0 - 104.0 + 20.0])

    def test_only_the_field_window(self):
        for typ in (1, 2, 3, 4):
            f = self.win(); f.select_language(typ, 0, False, 'Angus'); self.assertNotIn('speaker', f.N, typ); self.assertFalse(f.with_name); self.assertEqual(f.who, '')

    def test_name_that_comes_and_goes(self):
        f = self.win(); f.select_language(0, 0, False, ''); f.select_language(0, 0, False, 'Angus'); self.assertIn('speaker', f.N); f.select_language(0, 0, False, ''); self.assertNotIn('speaker', f.N); self.assertEqual(len(f.N['frame']['vtx']), 4)

    def test_change_name_without_rebuilding(self):
        f = self.win(); f.select_language(0, 0, False, 'Angus'); n = f.N; f.select_language(0, 0, False, 'Roi Bastien'); self.assertIs(f.N, n); self.assertEqual(f.N['speaker']['text']['text'], 'Roi Bastien')

    def test_sides_unchanged(self):
        a = self.win(); a.select_language(0, 0, False, ''); b = self.win(); b.select_language(0, 0, False, 'Angus')
        self.assertEqual((a.extent(), a.bottom()), (b.extent(), b.bottom())); self.assertEqual(a.extent(), (86.0 - 251.0, 86.0 - 125.0))
        self.assertEqual(a.extent_x(), b.extent_x())

    def test_scroll_and_cursor_kept_with_name(self):
        f = self.win(); f.select_language(0, 100, True, 'Angus'); self.assertTrue(f.N['cursor']['act']); self.assertAlmostEqual(f.N['canvas']['uv'][0][1], 100 / 512.0)
        f.select_language(0, 100, False, ''); self.assertFalse(f.N['cursor']['act']); self.assertAlmostEqual(f.N['canvas']['uv'][0][1], 100 / 512.0)

    def test_without_border_191_no_name(self):
        f = self.win(with_borders=False); f.select_language(0, 0, False, 'Angus'); self.assertNotIn('speaker', f.N); self.assertEqual(len(f.N['frame']['vtx']), 4)

    def test_name_is_drawn_like_menu_text(self):
        """Render._items must find the text (a mesh without vertices + a text) and draw nothing else for this node."""
        f = self.win(); f.select_language(0, 0, False, 'Angus'); items = UM.Render._items(types.SimpleNamespace(), f)
        self.assertEqual(sorted(g for _, _, g, _ in items), ['m', 'm', 't'])            # frame + canvas + text (the end-of-page cursor is hidden)
        self.assertEqual([x[1]['text']['text'] for _, _, g, x in items if g == 't'], ['Angus'])

    def test_editor_preview_without_name(self):
        f = self.win(); self.assertEqual(f.who, ''); self.assertNotIn('speaker', f.N)


class TestRealBorders(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        l, c = os.path.join(CACHE, 'ui_layout.json'), os.path.join(CACHE, 'ui_frameData.bin')
        if not (os.path.exists(l) and os.path.exists(c)): raise unittest.SkipTest('cache d\'interface absent : ' + CACHE)
        cls.ml = UM.PageLayout(l, c)

    def test_191_is_192_plus_a_tab(self):
        a, b = self.ml.borders[191], self.ml.borders[192]
        za, zb = [v[1] for v in a['vtx']], [v[1] for v in b['vtx']]
        self.assertEqual((min(za), max(za)), (-251.0, -93.0)); self.assertEqual((min(zb), max(zb)), (-251.0, -125.0))
        xs = [v[0] for v in a['vtx'] if v[1] > -125.0]; self.assertEqual((min(xs), max(xs)), (-223.0, 23.0))             # tab: 246 wide, 32 high
        self.assertEqual((min(v[0] for v in a['vtx']), max(v[0] for v in a['vtx'])), (min(v[0] for v in b['vtx']), max(v[0] for v in b['vtx'])))      # same frame width

    def test_layout_terrain_border_is_192(self):
        t0 = self.ml.message['types'][0]['frame_mesh']; b = self.ml.borders[192]
        self.assertEqual(sorted(map(tuple, t0['vtx'])), sorted(tuple(v) for v in b['vtx']))

    def test_set_with_the_real_borders(self):
        f = UM.MessageWindow(self.ml); f.select_language(0, 0, False, ''); e0 = f.extent(); f.select_language(0, 0, False, 'Roi Bastien')
        self.assertEqual(len(f.N['frame']['vtx']), len(self.ml.borders[191]['vtx'])); self.assertEqual(f.extent(), e0)
        z = [f.N['frame']['pos'][2] + v[1] for v in f.N['frame']['vtx']]; self.assertEqual(max(z) - e0[1], 32.0)          # the tab sticks out 32 above the frame


if __name__ == '__main__':
    unittest.main(verbosity=1)
