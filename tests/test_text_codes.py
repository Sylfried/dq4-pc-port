"""The patch's "$" in the interface's texts: never drawn by the game, they mark where a word may be cut when it overflows its cell. The engine turns them into a hyphen and a line break, or removes them, only for the monster names it extracts (MenuItem::ExtractTextUTF16,
language 1); the spell names ("Méga$protection") reach the interface with them. `ui_menu.soft_hyphens`, applied by `Render._text`:
  1. a line that fits its room loses its "$"; one that does not is cut at the last "$" whose head fits with a hyphen, the rest on the next line;
  2. drawn in a button plate (dummy font): "Méga$protection" fits a wide plate as "Mégaprotection" and is cut "Méga-" / "protection" in a narrow one;
  3. the history (message font) does not draw it: the battle names keep it (battle_history), `HistoryView._line` removes it for the other fonts.

    python3 tests/test_text_codes.py
"""
import os, sys, unittest

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import _text_render as TR
UM = TR.UM

W = lambda t: 8.0 * len(t)                          # (8 units per character)


class SoftHyphens(unittest.TestCase):
    def test_removed_when_it_fits(self):
        self.assertEqual(UM.soft_hyphens(['Méga$protection'], W, 200.0), ['Mégaprotection'])
        self.assertEqual(UM.soft_hyphens(['Méga$protection'], W, None), ['Mégaprotection'])                      # (room unknown: removed)
        self.assertEqual(UM.soft_hyphens(['Gluant', 'Tornade'], W, 10.0), ['Gluant', 'Tornade'])              # (no "$": untouched, even too wide)

    def test_cut_with_a_hyphen_when_it_does_not(self):
        self.assertEqual(UM.soft_hyphens(['Méga$protection'], W, 90.0), ['Méga-', 'protection'])
        self.assertEqual(UM.soft_hyphens(['ab$cd$ef$gh'], W, 50.0), ['abcd-', 'efgh'])                       # (the last "$" whose head fits; the rest treated the same way)
        self.assertEqual(UM.soft_hyphens(['ab$cd$ef$gh'], W, 25.0), ['ab-', 'cd-', 'ef-', 'gh'])
        self.assertEqual(UM.soft_hyphens(['abcdef$g'], W, 20.0), ['abcdef-', 'g'])                            # (no head fits: the first "$")


class InAPlate(unittest.TestCase):
    def draw(self, plate_w, text='Méga$protection'):
        wnd = TR.make_window(35, [dict(pos=[0.0, 4.0, 0.0], anchor=4, alignment=1, cs=10.0)], plates=[dict(pos=[0.0, 0.0], w=plate_w, h=50.0)])
        wnd.param_str(0, 0, text); return [q.text for q in TR.draw(wnd, wnd.N[10], font=TR.FakeFont(advance=8))]

    def test_wide_plate(self):
        self.assertEqual(self.draw(200.0), ['Mégaprotection'])

    def test_narrow_plate(self):
        self.assertEqual(self.draw(100.0), ['Méga-', 'protection'])


class History(unittest.TestCase):
    def test_battle_names_keep_it(self):
        from dq456_pc.battle import battle_history as BH
        import inspect
        src = inspect.getsource(BH.BattleSensor._engine_text)
        self.assertNotIn("'$'", src.split('"""')[-1])                                   # (the code after the docstring: the "$" is not replaced)


if __name__ == '__main__':
    unittest.main(verbosity=1)
