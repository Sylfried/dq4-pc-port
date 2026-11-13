"""Engine heap alert: the heap is never freed and is 256 MB; the window logs it in the error log at 200 MB then at 240 MB (no more on-screen message).

1. `Core.heap_used`: allocated bytes (heap_ptr - HEAP_BASE); thresholds of 200 and 240 MB below the heap size;
2. `Game._watch_heap`: nothing below 200 MB; one log line at 200 MB, another at 240 MB, each ONCE, and no on-screen message (the fake game has no `toast`); a heap that drops back (loading a state) re-arms the alerts;
   a direct jump past 240 MB gives a single line; no savestate is written (it would keep the heap full).

  python3 tests/test_heap_alert.py
"""
import os, sys, types, unittest

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), '..'))
from dq4_pc import language as _LANGUAGE; _LANGUAGE.select_language('fr')          # (these tests expect the French texts, whatever the computer's language)
from dq4_pc.core import emu_core as EC

try:
    import pyglet
    pyglet.options['shadow_window'] = False
    from dq4_pc.window import game as WND
except Exception as ex:          # window/game.py needs pyglet, numpy, unicorn... (the import alone is enough)
    WND = None; ERROR_WND = ex

ENGINE = 1 << 20


def fake_core_heap(mb_used):
    return types.SimpleNamespace(HEAP_BASE=EC.Core.HEAP_BASE, HEAP_SIZE=EC.Core.HEAP_SIZE, heap_ptr=EC.Core.HEAP_BASE + int(mb_used * ENGINE), HEAP_ALERT=EC.Core.HEAP_ALERT, HEAP_CRITICAL=EC.Core.HEAP_CRITICAL,
                                 heap_used=lambda: None)


def core(mb_used):
    c = fake_core_heap(mb_used); c.heap_used = types.MethodType(EC.Core.heap_used, c); return c


class Thresholds(unittest.TestCase):
    def test_heap_used(self):
        self.assertEqual(core(0).heap_used(), 0); self.assertEqual(core(13).heap_used(), 13 * ENGINE)

    def test_thresholds(self):
        self.assertEqual(EC.Core.HEAP_ALERT, 200 * ENGINE); self.assertEqual(EC.Core.HEAP_CRITICAL, 240 * ENGINE)
        self.assertLess(EC.Core.HEAP_ALERT, EC.Core.HEAP_CRITICAL); self.assertLess(EC.Core.HEAP_CRITICAL, EC.Core.HEAP_SIZE); self.assertEqual(EC.Core.HEAP_SIZE, 256 * ENGINE)


@unittest.skipIf(WND is None, 'fenetre/jeu.py non importable ici')
class Alert(unittest.TestCase):
    def setUp(self):
        self.logfile = []
        self.j = types.SimpleNamespace(_heap_level=0)
        self.j._watch_heap = types.MethodType(WND.Game._watch_heap, self.j)
        self.old = WND.note_error; WND.note_error = lambda t: self.logfile.append(t)

    def tearDown(self): WND.note_error = self.old

    def test_nothing_below_200_mb(self):
        for u in (0, 14, 150, 199.9): self.j._watch_heap(core(u))
        self.assertEqual(self.logfile, [])

    def test_one_message_per_tier(self):
        for u in (100, 200, 205, 230, 239.9): self.j._watch_heap(core(u))
        self.assertEqual(len(self.logfile), 1); self.assertIn('200 MB of 256 MB', self.logfile[0]); self.assertIn('at 78 %', self.logfile[0])
        for u in (240, 245, 255): self.j._watch_heap(core(u))
        self.assertEqual(len(self.logfile), 2); self.assertIn('at 94 %', self.logfile[1])

    def test_direct_jump_beyond_240(self):
        self.j._watch_heap(core(250)); self.assertEqual(len(self.logfile), 1); self.assertIn('at 98 %', self.logfile[0])
        self.j._watch_heap(core(252)); self.assertEqual(len(self.logfile), 1)

    def test_heap_dropping_back_rearms(self):
        self.j._watch_heap(core(210)); self.j._watch_heap(core(12)); self.j._watch_heap(core(12)); self.assertEqual(len(self.logfile), 1)             # (loaded state: 12 MB heap)
        self.j._watch_heap(core(210)); self.assertEqual(len(self.logfile), 2)
        self.j._watch_heap(core(245)); self.j._watch_heap(core(215)); self.assertEqual(len(self.logfile), 3)                                       # 94% then back to 84%: no new alert (the low threshold has already been passed)
        self.j._watch_heap(core(215)); self.assertEqual(len(self.logfile), 3)


if __name__ == '__main__':
    unittest.main()
