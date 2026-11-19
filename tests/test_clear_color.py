"""Test of the frame clear color: `Game._clear_color` never returns None.

The crash: a battle on a map **without a battle backdrop** (`cmd_fld_load` receives the name "0": no packet 8, no scenery color, no entry in the backgrounds list) left `background` as None,
and `gl.glClearColor(background[0], ...)` raised `TypeError: 'NoneType' object is not subscriptable` in the drawing loop — so the window crashed. The same value is used twice in the frame
(`glClearColor` then `post.begin(background)`): the guard is at the source, in the decision, not in front of every use.

    python3 tests/test_clear_color.py
No screen, no GL, no APK.
"""
import os, sys, types, unittest

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), '..'))
import pyglet
if sys.platform.startswith('linux') and not os.environ.get('DISPLAY'): pyglet.options['headless'] = True; pyglet.options['shadow_window'] = False
from dq456_pc.core import engine as ENGINE
from dq456_pc.window import game as F

LIST = (0.1, 0.2, 0.3)           # color read from the list of backgrounds (FETC of the loaded scenery)
SCENERY = (0.4, 0.5, 0.6)        # estimate made on the scenery pixels (field.py)
PACKET = (0.7, 0.8, 0.9)         # color sent by the engine (packet 8)


def game(listed=None, scenery=None):
    """A fake `self`: `_clear_color` only touches these three attributes (same approach as GLRender in test_gradient_background)."""
    return types.SimpleNamespace(backgrounds=types.SimpleNamespace(color=lambda name_str: listed), scenery_background=scenery, map_src='btl_xxx')


def state(part, background=(0.0, 0.0, 0.0)):
    return types.SimpleNamespace(part=part, background=background)


class ClearColor(unittest.TestCase):
    def setUp(self):
        self.estimate = os.environ.pop('DQ_ESTIMATED_BACKGROUND', None)

    def tearDown(self):
        if self.estimate is not None: os.environ['DQ_ESTIMATED_BACKGROUND'] = self.estimate

    def call(self, g, e): return F.Game._clear_color(g, e)

    def test_no_colour_at_all_gives_black(self):
        """battle on a map without a battle backdrop — this is the case that crashed the window."""
        self.assertEqual(self.call(game(), state(ENGINE.PART_BATTLE)), (0.0, 0.0, 0.0))

    def test_never_none_whatever_the_part(self):
        for part in (ENGINE.PART_TOWN, ENGINE.PART_BATTLE, ENGINE.PART_FIELD, ENGINE.PART_CASINO, ENGINE.PART_INITIAL):
            for listed, scenery in ((None, None), (None, SCENERY), (LIST, None)):
                c = self.call(game(listed, scenery), state(part))
                self.assertIsNotNone(c, 'partie %#x, liste %s, estimation %s' % (part, listed, scenery))
                self.assertEqual(len(c), 3)
                c[0], c[1], c[2]                                        # what glClearColor does: a None would raise here, as in the window

    def test_the_packet_wins(self):
        self.assertEqual(self.call(game(LIST, SCENERY), state(ENGINE.PART_BATTLE, PACKET)), PACKET)
        self.assertEqual(self.call(game(LIST, SCENERY), state(ENGINE.PART_FIELD, PACKET)), PACKET)

    def test_battle_falls_back_on_the_list_then_on_the_estimate(self):
        self.assertEqual(self.call(game(LIST, SCENERY), state(ENGINE.PART_BATTLE)), LIST, 'the list of backgrounds (FETC) first')
        self.assertEqual(self.call(game(None, SCENERY), state(ENGINE.PART_BATTLE)), SCENERY, 'list not ready yet: the estimate')

    def test_out_of_battle_no_fallback(self):
        """Outside battle, the battle scenery must not tint the screen: black, as before."""
        self.assertEqual(self.call(game(LIST, SCENERY), state(ENGINE.PART_FIELD)), (0.0, 0.0, 0.0))

    def test_estimate_forced(self):
        os.environ['DQ_ESTIMATED_BACKGROUND'] = '1'
        self.assertEqual(self.call(game(LIST, SCENERY), state(ENGINE.PART_BATTLE)), SCENERY, 'DQ_ESTIMATED_BACKGROUND=1: the old estimate, without the list')
        self.assertEqual(self.call(game(LIST, None), state(ENGINE.PART_BATTLE)), (0.0, 0.0, 0.0), 'and without an estimate: black, not None')


class Usage(unittest.TestCase):
    def test_the_frame_takes_its_colour_from_the_decision(self):
        """The guard is at the source: every use of `background` in the frame comes from `_clear_color`; none rereads `e.background` on its own."""
        import inspect
        body = inspect.getsource(F.Game._draw_scene)
        self.assertIn('background = self._clear_color(e)', body)
        self.assertNotIn('background = e.background', body)


if __name__ == '__main__':
    unittest.main(verbosity=2)
