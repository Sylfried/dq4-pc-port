"""Test: there is no small "Esc: menu    F1: info" reminder at the bottom left at startup.

python3 tests/test_without_startup_callback.py
"""
import inspect, os, sys, unittest

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, '..'))
import _paths          # (test helper: finding the source code in the subfolders of dq456_pc)
import pyglet
pyglet.options['shadow_window'] = False
from dq456_pc.window import game as F


class WithoutReminder(unittest.TestCase):
    def test_no_more_reminder_text(self):
        self.assertFalse(hasattr(F.Game, '_texte_conseil'))
        src = _paths.source('window.py')
        for pattern in ('startup_hint', 'settings.esc_menu_f1_info'): self.assertNotIn(pattern, src, pattern)

    def test_drawing_no_longer_waits_for_startup(self):
        self.assertNotIn('t_startup < 8.0', _paths.source('window.py'))                        # (t_startup remains: it is used for real-time measurements)


if __name__ == '__main__':
    unittest.main()
