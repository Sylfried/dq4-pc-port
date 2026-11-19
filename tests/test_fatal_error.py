"""Window error barrier: when the engine dies, the game saves, logs and closes — it no longer vanishes without a trace.

Before, an error coming up from the engine (heap exhausted, hook error, timeout) went through `_loop` all the way to pyglet: the window closed,
`on_close` was not executed (settings, history and sound lost, along with the session history) and `window_errors.log` stayed empty,
whereas `launch_dq4.bat` sends the player there. What this test guards:

  1. an error in the loop does not leave it: it goes through `_fatal`;
  2. `_fatal` saves (settings, history, sound), writes the full trace and the context to the log, then closes the window;
  3. a save step that fails does not prevent the others, and the log says so;
  4. after a fatal error, no more steps and no more drawing (no cascade of errors), and `on_close` does not save a second time;
  5. the game marks `dead`: `main` returns a non-zero exit code, and the launcher keeps the console open.

    python3 tests/test_fatal_error.py
"""
import os, sys, tempfile, unittest

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, '..'))
import pyglet
if sys.platform.startswith('linux') and not os.environ.get('DISPLAY'): pyglet.options['headless'] = True; pyglet.options['shadow_window'] = False
from dq456_pc.window import game as G

BORROWED = ('_fatal', '_fatal_context', '_save_on_exit', '_guarded_loop', 'on_draw', 'on_close')


class Stub:
    """The bare minimum to exercise the barrier without opening a window or an engine."""
    _dying = False
    dead = False
    _ready = True
    n = 42
    n_loop = 1234

    def __init__(self, fail_on=()):
        self.done = []; self.fail_on = set(fail_on); self.closed = 0
        self.reg = self._part('settings'); self.history = self._part('history', True); self.sound = self._part('sound')
        self.engine = None

    def _part(self, name_str, arg=False):
        done, fail = self.done, self.fail_on
        class Part:
            def store(self, *a):
                if name_str in fail: raise OSError('disque plein (%s)' % name_str)
                done.append(name_str)
            shutdown = store
        return Part()

    def close(self): self.closed += 1
    def _loop(self, dt): raise RuntimeError("the engine stopped: heap exhausted")
    def _draw_frame(self): raise RuntimeError('dessin casse')


for _n in BORROWED: setattr(Stub, _n, G.Game.__dict__[_n])


class Barrier(unittest.TestCase):
    def setUp(self):
        self.log = os.path.join(tempfile.mkdtemp(prefix='jl_'), 'window_errors.log')
        self.old = os.environ.get('DQ_WINDOW_LOG'); os.environ['DQ_WINDOW_LOG'] = self.log
        Stub.dead = False

    def tearDown(self):
        if self.old is None: os.environ.pop('DQ_WINDOW_LOG', None)
        else: os.environ['DQ_WINDOW_LOG'] = self.old

    def text(self):
        with open(self.log, encoding='utf-8') as f: return f.read()

    def test_loop_error_does_not_escape(self):
        g = Stub()
        g._guarded_loop(0.033)                                                        # must raise NOTHING
        self.assertTrue(g._dying); self.assertTrue(Stub.dead); self.assertEqual(g.closed, 1)

    def test_saves_before_closing(self):
        g = Stub(); g._guarded_loop(0.033)
        self.assertEqual(sorted(g.done), ['history', 'settings', 'sound'])

    def test_log_has_trace_and_context(self):
        g = Stub(); g._guarded_loop(0.033)
        t = self.text()
        self.assertIn('the game stopped on an error in the game loop', t)
        self.assertIn('the engine stopped: heap exhausted', t)
        self.assertIn('Traceback', t)
        self.assertIn('frame 42', t); self.assertIn('loop 1234', t)
        self.assertIn('settings, history and sound saved', t)

    def test_a_failing_save_does_not_stop_the_others(self):
        g = Stub(fail_on=('settings',)); g._guarded_loop(0.033)
        self.assertEqual(sorted(g.done), ['history', 'sound'])                # the other two still happen
        self.assertIn('NOT saved: settings', self.text())
        self.assertEqual(g.closed, 1)

    def test_nothing_runs_after_the_error(self):
        g = Stub(); g._guarded_loop(0.033)
        before = self.text()
        g._guarded_loop(0.033); g.on_draw()                                           # no more steps or drawing: no cascade
        self.assertEqual(self.text(), before); self.assertEqual(g.closed, 1)

    def test_on_close_does_not_save_twice(self):
        g = Stub(); g._guarded_loop(0.033)
        done = list(g.done)
        try: g.on_close()
        except TypeError: pass                                                # Stub does not inherit from the pyglet window: super().on_close() stops there, after the part under test
        self.assertEqual(g.done, done)

    def test_drawing_error_is_caught_too(self):
        g = Stub(); g.on_draw()
        self.assertIn('the game stopped on an error in drawing a frame', self.text()); self.assertEqual(g.closed, 1)

    def test_log_is_written_even_without_engine(self):
        g = Stub(); g.engine = None; g._guarded_loop(0.033)
        self.assertTrue(os.path.exists(self.log))                             # _fatal_context does not raise when the engine does not exist


class ExitCode(unittest.TestCase):
    def test_main_returns_non_zero_when_dead(self):
        """`main` returns 1 when the game is dead: the launcher keeps the console open on a non-zero code."""
        src = open(os.path.join(HERE, '..', 'dq456_pc', 'main.py'), encoding='utf-8').read()
        self.assertIn("if getattr(game, 'dead', False):", src)
        self.assertIn('return 1', src)
        self.assertIn('sys.exit(main())', src)
        src = open(os.path.join(HERE, '..', 'dq456_pc', '__main__.py'), encoding='utf-8').read()
        self.assertIn('sys.exit(main())', src, '`python -m dq456_pc` runs __main__.py: without sys.exit the launcher always read exit code 0')


if __name__ == '__main__':
    unittest.main(verbosity=2)
