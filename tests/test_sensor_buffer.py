"""Viewer working buffers in the engine heap: they do not survive a loaded savestate.

The dialogue history (`core/history.py`) and the battle history (`battle/battle_history.py`) make the engine read a text
(`TextAPI::extractText`, `getName`) by passing it a buffer **allocated in its heap**. These buffers were kept in the sensors'
Python objects, which savestates do not know about: loading a state older than their allocation moved the heap
pointer back **below** the buffer, the engine reallocated the same area, and the sensor then overwrote an engine block, silently.

Reproduced on the real engine before the fix: buffer at 0x20243ea0, state loaded, the engine's next `malloc` -> **0x20243ea0**.

The buffers now go through `Core.scratch(nom, taille)`, and `Core.heap_rewind` forgets those that are no longer live.

    python3 tests/test_sensor_buffer.py                                   (unit tests)
    DQ_APK=... DQ_SAVES=... python3 tests/test_sensor_buffer.py           (+ the real engine)
"""
import os, sys, tempfile, unittest

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, '..'))
from dq456_pc.core import emu_core

APK, SAVES = os.environ.get('DQ_APK'), os.environ.get('DQ_SAVES')
BORROWED = ('malloc', 'free', 'heap_rewind', 'scratch')


class FakeHeap:
    HEAP_BASE, HEAP_SIZE = emu_core.Core.HEAP_BASE, emu_core.Core.HEAP_SIZE

    def __init__(self):
        self.heap_ptr = self.HEAP_BASE; self.heap_blocks = {}; self.heap_free = {}; self.heap_scratch = {}

    def mem_w(self, p, data): pass


for _n in BORROWED: setattr(FakeHeap, _n, emu_core.Core.__dict__[_n])


class Scratch(unittest.TestCase):
    def setUp(self): self.h = FakeHeap()

    def test_the_same_buffer_comes_back(self):
        a = self.h.scratch('history', 8192)
        self.assertEqual(self.h.scratch('history', 8192), a, 'garde d\'un appel a l\'autre')

    def test_two_names_two_buffers(self):
        self.assertNotEqual(self.h.scratch('a', 256), self.h.scratch('b', 256))

    def test_a_loaded_state_forgets_a_buffer_left_above(self):
        mark = self.h.heap_ptr
        self.h.scratch('history', 8192)
        self.h.heap_rewind(mark)                                           # state before the buffer was allocated
        self.assertNotIn('history', self.h.heap_scratch, 'the buffer is forgotten: it no longer lives')
        self.assertEqual(self.h.heap_scratch.get('history'), None)
        p = self.h.scratch('history', 8192)                             # the next one is a new allocation, recorded
        self.assertIn(p, self.h.heap_blocks)

    def test_a_buffer_below_the_state_is_kept(self):
        a = self.h.scratch('history', 8192)
        self.h.heap_rewind(self.h.heap_ptr)                                # later state: the buffer still lives
        self.assertEqual(self.h.scratch('history', 8192), a)

    def test_the_engine_never_gets_the_live_buffer(self):
        """The case: after a loaded savestate, what the engine allocates and what the sensor uses must be distinct."""
        mark = self.h.heap_ptr
        self.h.scratch('history', 8192)
        self.h.heap_rewind(mark)
        engine_block = self.h.malloc(8192)                                 # the engine reallocates the space
        self.assertNotEqual(self.h.scratch('history', 8192), engine_block)

    def test_both_sensors_go_through_scratch(self):
        import inspect
        from dq456_pc.core import history as HI
        from dq456_pc.battle import battle_history as HC
        for mod in (HI, HC):
            src = inspect.getsource(mod)
            self.assertIn("c.scratch(", src, mod.__name__)
            self.assertNotIn('c.malloc(8192)', src, mod.__name__); self.assertNotIn('c.malloc(256)', src, mod.__name__)


@unittest.skipUnless(APK and SAVES, 'real engine: DQ_APK=<folder of the patched APKs> DQ_SAVES=<folder of the saves>')
class RealEngine(unittest.TestCase):
    def test_buffer_and_engine_block_never_overlap_after_loading(self):
        from dq456_pc.core import engine as ENGINE
        from dq456_pc.persistence import savestates as SS
        m = ENGINE.Engine(APK, SAVES, tempfile.mkdtemp(prefix='sv_317_')); m.load_save(1)
        for _ in range(200): m.step(0, 0)
        c = m.core
        before = SS.snapshot(m)                                            # state taken before any text reading by the sensor
        buf = c.scratch('history', 8192)
        SS.apply(m, before)                                                # the heap pointer moves back below the buffer
        engine_block = c.malloc(8192)                                      # the engine reallocates the freed space
        self.assertEqual(engine_block, buf, 'the place of the buffer is given back to the engine')
        self.assertNotEqual(c.scratch('history', 8192), engine_block, 'the sensor takes another one: no more overlap')


if __name__ == '__main__':
    unittest.main(verbosity=2)
