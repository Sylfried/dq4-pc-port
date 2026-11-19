"""Debug mode (dq456_pc/debug/service.py): pause, engine steps one at a time, speed factors, commands queued from another thread, the overlay's lines
(with a stand-in window and engine: the CI has neither a window nor the game).

    python3 tests/test_debug_service.py
"""
import os, sys, threading, unittest

HERE = os.path.dirname(os.path.abspath(__file__)); ROOT = os.path.join(HERE, '..')
sys.path.insert(0, ROOT)
import pyglet
pyglet.options['shadow_window'] = False
from dq456_pc.debug import service as DS
from dq456_pc.core import engine as ENGINE

K = pyglet.window.key


class Sound:
    paused = False
    def set_paused(self, on): self.paused = on


class Engine:
    def __init__(self): self.frames = 0; self.state = type('S', (), {'part': ENGINE.PART_TOWN, 'game_map': 'mbk1f1', 'fade': {'a': 1.0, 'end': 0.0, 'n': 12}, 'background_fade': None})(); self.ui = type('U', (), {'f': {}})(); self.msg_visible = False
    def step(self, held=0, decl=None): self.frames += 1; return []
    def send_menu(self, port, *args): pass
    def _send_messages(self, data): pass
    def flags(self): return 0x15
    def active_menu(self): return None


class Game:
    def __init__(self):
        self.engine = Engine(); self.sound = Sound(); self.n_loop = 0; self.t_loop = 1.0; self.acc = 0.5; self.alpha = 0.3; self.height = 720; self.map_name = None
    def _complete_savestate(self): return {}
    def _step(self): self.engine.step()


class DebugService(unittest.TestCase):
    def test_pause_and_steps(self):
        g = Game(); d = DS.DebugService(g)
        self.assertFalse(d.gate())                                           # running: the loop goes on as usual
        self.assertTrue(d.key(K.F3, 0)); self.assertTrue(d.paused); self.assertTrue(g.sound.paused)
        for _ in range(5): self.assertTrue(d.gate())
        self.assertEqual(g.engine.frames, 0)                                 # paused: no step
        d.key(K.F4, 0); d.gate(); d.gate(); self.assertEqual(g.engine.frames, 1)
        d.key(K.F4, K.MOD_SHIFT)
        for _ in range(DS.STEP_BURST + 3): d.gate()
        self.assertEqual(g.engine.frames, 1 + DS.STEP_BURST)
        d.key(K.F3, 0); self.assertFalse(d.paused); self.assertFalse(g.sound.paused); self.assertFalse(d.gate())

    def test_speeds(self):
        d = DS.DebugService(Game())
        self.assertEqual(d.factor(1.0), 1.0)
        d.key(K.F6, 0); self.assertEqual(d.speed, 2.0); self.assertEqual(d.factor(1.5), 3.0)
        for _ in range(10): d.key(K.F6, 0)
        self.assertEqual(d.speed, DS.SPEEDS[-1])
        d.key(K.F7, 0); self.assertEqual(d.speed, 1.0)
        for _ in range(10): d.key(K.F5, 0)
        self.assertEqual(d.speed, DS.SPEEDS[0])
        self.assertFalse(d.key(K.F1, 0)); self.assertFalse(d.key(K.A, 0))   # not debug keys: left to the game

    def test_engine_step_wrapped(self):
        g = Game(); d = DS.DebugService(g); seen = []
        d.after_step.append(seen.append)
        g.engine.step(1, 2); self.assertEqual(seen, [[]]); self.assertEqual(g.engine.frames, 1)

    def test_commands_from_another_thread(self):
        g = Game(); d = DS.DebugService(g); out = {}
        t = threading.Thread(target=lambda: out.setdefault('r', d.call(lambda: g.engine.frames + 41))); t.start()
        for _ in range(200):
            d.gate()
            if 'r' in out: break
            t.join(0.01)
        t.join(1.0); self.assertEqual(out.get('r'), 41)
        self.assertEqual(d.call(lambda: 7), 7)                               # on the window's thread: at once

    def test_overlay_lines(self):
        g = Game(); d = DS.DebugService(g); d.set_paused(True)
        lines = DS.overlay_lines(d.values())
        text = '\n'.join(lines)
        self.assertIn('mbk1f1', text); self.assertIn('0x15', text)
        self.assertEqual(DS.flag_names(0x15), 'fade lock +0x10')
        self.assertEqual(DS.flag_names(0), '-')
        self.assertIn('1.00 -> 0.00 (12)', text)


if __name__ == '__main__':
    unittest.main()
