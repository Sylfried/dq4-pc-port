"""the information lines (F1) are drawn last, over every interface.

Before, they were drawn with the scene: under the
screen buttons, the "Settings" menu (and blurred with the game behind it), the history, the toasts; and they were in the savestate thumbnails.
Source read as text (no display needed).
    python3 tests/test_info_on_top.py
"""
import os, unittest

HERE = os.path.dirname(os.path.abspath(__file__))
WINDOW = os.path.join(HERE, '..', 'dq456_pc', 'window')


def read(name): return open(os.path.join(WINDOW, name), encoding='utf-8').read()


class InfoOnTop(unittest.TestCase):
    def test_drawn_once_per_frame(self):
        total = sum(read(n).count('self._draw_helptext()') for n in os.listdir(WINDOW) if n.endswith('.py'))
        self.assertEqual(total, 1)

    def test_after_every_interface(self):
        src = read('game.py'); a = src.index('    def _draw(self):'); b = src.index('\n    def ', a + 10); body = src[a:b]
        last = body.index('self._draw_helptext()')
        for before in ('self._draw_scene()', 'self.hud.draw_all(', 'self.pause.draw_all()', 'self._clone_thumbnail()', 'self.toasts[0]', 'self.draw_replay_veil()'):
            self.assertLess(body.index(before), last, before)


if __name__ == '__main__':
    unittest.main(verbosity=2)
