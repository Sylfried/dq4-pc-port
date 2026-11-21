"""DQ V's opening credits on black: the title's map, loaded in advance (Game._preload_first_scene), is not drawn under them.

  python3 tests/test_opening_credits_scenery.py

During the credits the engine is in its town part with no map of its own (state.game_map None): the preloaded scenery had no camera for them and showed as
vertical streaks behind the text. FieldMixin._paint_scenery draws nothing then; with a map it goes on as before.
"""
import os, sys, types, unittest
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), '..'))
from dq456_pc.core import engine as ENGINE
try:
    import pyglet
    pyglet.options['shadow_window'] = False
    from dq456_pc.window.field import FieldMixin
except Exception:          # (pyglet, numpy, unicorn...: the import alone is enough)
    FieldMixin = None


@unittest.skipIf(FieldMixin is None, 'window not importable here')
class CreditsOnBlack(unittest.TestCase):
    def window(self, part, game_map):
        return types.SimpleNamespace(engine=types.SimpleNamespace(state=types.SimpleNamespace(part=part, game_map=game_map)))

    def test_town_part_without_a_map_draws_nothing(self):
        self.assertIsNone(FieldMixin._paint_scenery(self.window(ENGINE.PART_TOWN, None)))

    def test_with_a_map_it_goes_on(self):
        with self.assertRaises(AttributeError): FieldMixin._paint_scenery(self.window(ENGINE.PART_TOWN, 'ev17'))          # (the bare window has nothing to draw with)


if __name__ == '__main__':
    unittest.main()
