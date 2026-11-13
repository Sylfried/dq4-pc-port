""""Yes" / "No" stacked at the top right of the dialogue box, as on the DS (one on top of the other, right edges aligned),
without a window or the engine:

  1. `Window` of type 1 (Make_YesNo): the "No" plate moves under "Yes" (same column, one unit between the two), with its text; its frame panel follows it; the vertical extent grows by one panel, the horizontal extent
     is that of a single column; the touch areas are stacked ("Yes" on top); another layout (not two plates) is left untouched;
  2. `visible_edges`: the VISIBLE edge of a frame mesh cell (the columns and rows of the sheet whose opacity exceeds the threshold), not the edge of the mesh cell;
  3. `_yesno_on_message` / `_ui_yesno`: the stack places its VISIBLE bottom edge `YESNO_BOX_SPACING` above the visible top edge of the box, and its visible right edge on that of the box, at all player scales;
  4. (if the interface cache exists: DQ_UI_CACHE, otherwise /tmp/uicache4) the REAL layout: (-10 ; 87) on a column from -134.5 to -0.5; keyboard and click unchanged (up = "Yes", down = "No").

    python3 tests/test_stacked_yes_no.py        (only pyglet is needed; without pyglet the tests are skipped)
"""
import ast, os, sys, types, unittest

ROOT = os.path.join(os.path.dirname(os.path.abspath(__file__)), '..')
sys.path.insert(0, ROOT)
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import _paths
os.environ.setdefault('PYGLET_HEADLESS', '1')
CACHE = _paths.ui_cache('/tmp/uicache4')

try:
    import numpy as np
    from dq4_pc.menus import ui_menu as UM
    from dq4_pc.window import constants as K
    from dq4_pc.window.menu_display import MenusMixin
    IMPORT_ERROR = None
except Exception as ex:                                       # (CI: neither pyglet nor a window)
    UM = K = MenusMixin = np = None; IMPORT_ERROR = ex


def yes_no_template(plate_spacing=1.0):
    """Minimal layout of Make_YesNo (same structure as the game export): frame (z 87) of two 134 x 48 panels (x -134.5..-0.5 and 0.5..134.5, one cell each), two plates (x -67.5 and 67.5, z 62.5) and their texts."""
    def quad(x0, x1, z0, z1): return [[x0, z1], [x1, z1], [x1, z0], [x0, z0]]
    mat = lambda sheet, part: [dict(sheet=sheet, part=part, color=None, shader='parts', offset=None)]
    border = dict(id=1, par=None, pos=[0.0, 10.0, 87.0], act=True, mats=mat(0, 4), mesh=dict(vtx=quad(-134.5, -0.5, -48.0, 0.0) + quad(0.5, 134.5, -48.0, 0.0), uv=[[0, 0]] * 8, sub={'0': [0, 1, 3, 3, 1, 2, 4, 5, 7, 7, 5, 6]}))
    def plate(i, x, button):
        return dict(id=i, par=1, pos=[x, 14.0, 62.5], act=True, mats=mat(1, 7), mesh=dict(vtx=quad(-61.0, 61.0, 2.0, 18.0), uv=[[0, 0]] * 4, sub={'0': [0, 1, 3, 3, 1, 2]}), parts=dict(buttonId=button, gamepad=1))
    def text(i, parent_idx, x): return dict(id=i, par=parent_idx, pos=[x, 20.0, 83.5], act=True, mats=[dict(sheet='font', part=None, color=[1, 1, 1, 1], shader='font', offset=None)], text=dict(font='font', alignment=1, anchor=4, lineSpacing=0.8, characterSize=10.5, text=None))
    nodes = [border, plate(2, -67.5, 0), text(3, 2, -67.5), plate(4, 67.5, 1), text(5, 4, 67.5)]
    for n in nodes[1:]:
        if 'parts' not in n: n['parts'] = {}
    t = dict(name='Make_YesNo()', nodes=nodes, parts=[], params=[], codes=[], builds=[])
    return types.SimpleNamespace(types={'1': t}, borders=[], hdr={})


@unittest.skipIf(UM is None, 'ui_menu non importable ici (%r)' % (IMPORT_ERROR,))
class Stacking(unittest.TestCase):
    def wnd(self): return UM.Window(yes_no_template(), 1)

    def test_no_under_yes(self):
        wnd = self.wnd(); yes, no = wnd.N[2], wnd.N[4]
        self.assertEqual(no['pos'][0], yes['pos'][0])                                        # same column
        self.assertEqual(yes['pos'][2], 62.5)                                                 # "Yes" has not moved
        self.assertAlmostEqual(yes['pos'][2] - no['pos'][2], 48.0 + UM.Window.YES_NO_SPACING)       # one panel (48) + one unit
        self.assertEqual((wnd.N[5]['pos'][0], wnd.N[5]['pos'][2]), (wnd.N[3]['pos'][0], wnd.N[3]['pos'][2] - 49.0))      # the text of "No" followed its plate

    def test_border_follows_plates(self):
        wnd = self.wnd(); v = wnd.N[1]['vtx']
        left, right = v[:4], v[4:]
        self.assertEqual((min(p[0] for p in right), max(p[0] for p in right)), (min(p[0] for p in left), max(p[0] for p in left)))      # same column
        self.assertAlmostEqual(max(p[1] for p in left) - min(p[1] for p in right), 48.0 + 48.0 + 1.0)                                      # "No" just under "Yes", one unit between the panels

    def test_extents(self):
        wnd = self.wnd()
        self.assertEqual(wnd.extent(), (87.0 - 48.0 - 49.0, 87.0))                              # (-10 ; 87): two panels one on top of the other
        self.assertEqual(wnd.extent_x(), (-134.5, -0.5))                                        # a single column, the left one

    def test_stacked_touch_zones(self):
        wnd = self.wnd(); z = {b[0]: b for b in wnd.buttons()}
        self.assertEqual(set(z), {0, 1})
        self.assertEqual((z[0][2], z[0][4]), (z[1][2], z[1][4]))                                # same left and right edges
        self.assertGreater(z[0][3], z[1][5])                                                    # "Yes" (0) entirely above "No" (1)

    def test_other_layout_intact(self):
        ml = yes_no_template(); ml.types['1']['nodes'] = [n for n in ml.types['1']['nodes'] if n['id'] not in (4, 5)]      # a single plate: nothing to stack
        wnd = UM.Window(ml, 1); self.assertEqual(wnd.N[2]['pos'], [-67.5, 14.0, 62.5]); self.assertEqual(wnd.extent(), (39.0, 87.0))
        ml = yes_no_template(); ml.types['1']['name'] = 'Make_Autre()'; wnd = UM.Window(ml, 1)                                    # another window type
        self.assertEqual((wnd.N[4]['pos'], wnd.extent()), ([67.5, 14.0, 62.5], (39.0, 87.0)))

    def test_gap_equals_one_visible_unit(self):
        self.assertEqual(K.YESNO_BOX_SPACING, 1.0); self.assertEqual(UM.Window.YES_NO_SPACING, 1.0)


@unittest.skipIf(UM is None, 'ui_menu non importable ici (%r)' % (IMPORT_ERROR,))
class VisibleEdges(unittest.TestCase):
    """10 x 6 unit cell on a 16 x 8 pixel sheet (the cell covers columns 0 to 15, rows 0 to 3: u from 0 to 1, v from 0 to -0.5)."""
    QUAD = ([[0.0, 0.0], [10.0, 0.0], [10.0, -6.0], [0.0, -6.0]], [[0.0, 0.0], [1.0, 0.0], [1.0, -0.5], [0.0, -0.5]], [0, 1, 3, 3, 1, 2])

    def alpha(self):
        a = np.zeros((8, 16), np.uint8); a[1:4, 2:14] = 255                                     # drawing: columns 2 to 13, rows 1 to 3
        a[0, :] = 100; a[:, 1] = 100                                                            # below the threshold: does not count
        return a

    def test_drawing_edge_not_mesh_edge(self):
        x0, x1, z0, z1 = UM.visible_edges(*self.QUAD, self.alpha())
        self.assertAlmostEqual(x0, 10 * 2 / 16.0); self.assertAlmostEqual(x1, 10 * 14 / 16.0)          # 1.25 and 8.75
        self.assertAlmostEqual(z1, -6 * 1 / 4.0); self.assertAlmostEqual(z0, -6 * 4 / 4.0)             # row 1 of 4 from the top; bottom of row 3 = bottom of the cell

    def test_threshold(self):
        r = UM.visible_edges(*self.QUAD, self.alpha(), threshold=50)                               # with a low threshold row 0 (opacity 100, across the full width) counts: edges of the whole cell
        self.assertAlmostEqual(r[0], 0.0); self.assertAlmostEqual(r[1], 10.0); self.assertAlmostEqual(r[3], 0.0)

    def test_nothing_visible(self):
        self.assertIsNone(UM.visible_edges(*self.QUAD, np.zeros((8, 16), np.uint8)))

    def test_several_cells(self):
        """Two cells side by side: the edges are those of the whole."""
        vtx = [[0.0, 0.0], [5.0, 0.0], [5.0, -6.0], [0.0, -6.0], [5.0, 0.0], [10.0, 0.0], [10.0, -6.0], [5.0, -6.0]]
        uv = [[0.0, 0.0], [0.5, 0.0], [0.5, -0.5], [0.0, -0.5], [0.5, 0.0], [1.0, 0.0], [1.0, -0.5], [0.5, -0.5]]
        r = UM.visible_edges(vtx, uv, [0, 1, 3, 3, 1, 2, 4, 5, 7, 7, 5, 6], self.alpha())
        self.assertAlmostEqual(r[0], 1.25); self.assertAlmostEqual(r[1], 8.75)


class FakeBorder:
    """Window that only knows how to give its visible extent (x0, x1, z0, z1)."""
    def __init__(self, v): self.v = v
    def visible_extent(self): return self.v


@unittest.skipIf(MenusMixin is None, 'fenetre non importable ici (%r)' % (IMPORT_ERROR,))
class Pose(unittest.TestCase):
    MSG = (-223.0 + 6.0, 229.0 - 6.0, -165.0, -43.5)              # dialogue box: visible edges
    STACK = (-134.5, -0.5, -10.0, 87.0)                            # "Yes" / "No" stack: visible edges of its original layout

    def pose(self, msg=None, stack=None): return MenusMixin._yesno_on_message(None, FakeBorder(msg or self.MSG), FakeBorder(stack or self.STACK))

    def test_bottom_edge_of_stack_on_top_edge_of_box(self):
        dz, (bm, bp) = self.pose()
        self.assertAlmostEqual(self.STACK[2] + dz, self.MSG[3] + K.YESNO_BOX_SPACING)              # bottom of the (shifted) stack = top of the box + 1
        self.assertEqual((bm, bp), (self.MSG[1], self.STACK[1]))

    def test_missing_measure(self):
        self.assertIsNone(MenusMixin._yesno_on_message(None, None, FakeBorder(self.STACK)))
        self.assertIsNone(MenusMixin._yesno_on_message(None, FakeBorder(self.MSG), FakeBorder(None)))

    def test_right_edge_aligned_at_any_scale(self):
        """Whatever size the player has set (v[0]), the right edge of the stack is that of the box (as long as the player does not shift it); the bottom edge too, around its foot."""
        game = types.SimpleNamespace(width=1280, height=720); dz, edges = self.pose()
        base = (640.0, 300.0, 0.9)                                                          # (center x, bottom y, scale) of the box
        for scale_factor in (0.5, 1.0, 1.3, 2.0):
            cx, cy, s2 = MenusMixin._ui_yesno(game, base, dz, self.STACK[2], (scale_factor, 0.0, 0.0), edges)
            self.assertAlmostEqual(cx + self.STACK[1] * s2, base[0] + self.MSG[1] * base[2], places=6)         # right edges
            self.assertAlmostEqual(cy + self.STACK[2] * s2, base[1] + (dz + self.STACK[2]) * base[2], places=6)  # bottom edge: does not move with the size

    def test_relative_position_setting(self):
        game = types.SimpleNamespace(width=1000, height=500); dz, edges = self.pose(); base = (500.0, 200.0, 1.0)
        a = MenusMixin._ui_yesno(game, base, dz, self.STACK[2], (1.0, 0.0, 0.0), edges); b = MenusMixin._ui_yesno(game, base, dz, self.STACK[2], (1.0, 0.1, -0.2), edges)
        self.assertAlmostEqual(b[0] - a[0], 100.0); self.assertAlmostEqual(b[1] - a[1], -100.0)

    def test_without_edges_nothing_changes(self):
        """Without a measurement (edges = None) the stack keeps its old placement: x = box center + offset."""
        game = types.SimpleNamespace(width=1000, height=500)
        self.assertEqual(MenusMixin._ui_yesno(game, (500.0, 200.0, 1.0), 0.0, 0.0, (1.0, 0.0, 0.0))[0], 500.0)


class Code(unittest.TestCase):
    """Without pyglet: the placement is wired in at the places that matter (drawing, click areas, editor preview)."""
    def source(self, *path):
        with open(os.path.join(ROOT, *path), encoding='utf-8') as f: return f.read()

    def test_yes_no_border_stacks_on_creation(self):
        tree = ast.parse(self.source('dq4_pc', 'menus', 'ui_menu.py'))
        init = [n for c in ast.walk(tree) if isinstance(c, ast.ClassDef) and c.name == 'Window' for n in c.body if isinstance(n, ast.FunctionDef) and n.name == '__init__'][0]
        calls = [n.func.attr for n in ast.walk(init) if isinstance(n, ast.Call) and isinstance(n.func, ast.Attribute)]
        self.assertIn('_push_yes_no', calls)

    def test_drawing_click_and_preview_use_same_pose(self):
        src = self.source('dq4_pc', 'window', 'menu_display.py')
        self.assertGreaterEqual(src.count('_yesno_on_message('), 3)                       # definition + drawing + editor preview
        self.assertIn("ui_edges", src); self.assertIn("self.ui_tf[p] = (t2[0], t2[1] - D * t2[2], t2[2])", src)      # click areas = drawing coordinate frame


@unittest.skipIf(UM is None, 'ui_menu non importable ici (%r)' % (IMPORT_ERROR,))
class RealPageLayout(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        l = os.path.join(CACHE, 'ui_layout.json')
        if not os.path.exists(l): raise unittest.SkipTest("cache d'interface absent : " + CACHE)
        cls.ml = UM.PageLayout(l, os.path.join(CACHE, 'ui_frameData.bin'))

    def test_real_window_stack(self):
        wnd = UM.Window(self.ml, 1); self.assertEqual(wnd.t['name'][:11], 'Make_YesNo(')
        e = wnd.extent(); self.assertAlmostEqual(e[0], -10.0); self.assertAlmostEqual(e[1], 87.0)
        x = wnd.extent_x(); self.assertAlmostEqual(x[0], -134.5); self.assertAlmostEqual(x[1], -0.5)

    def test_yes_above_no(self):
        z = {b[0]: b for b in UM.Window(self.ml, 1).buttons()}
        self.assertEqual(set(z), {0, 1}); self.assertGreater(z[0][3], z[1][5]); self.assertEqual((z[0][2], z[0][4]), (z[1][2], z[1][4]))


if __name__ == '__main__':
    unittest.main(verbosity=1)
