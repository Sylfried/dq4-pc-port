"""Engine heap allocator: blocks returned by `free` are reused.

Before, `Core.malloc` only advanced a pointer and `h_free` returned nothing. Measured on real battles: the engine **does free
96 to 101%** of what a battle allocates, and the memory actually live peaks at 1.8 MB. The 256 MB heap was therefore filling up
for nothing (about 1.34 MB per battle, i.e. ~183 battles before the engine stopped) and each savestate cost more and more,
its size and duration following the pointer: 0.62 s at 200 MB against 0.016 s at 2 MB.

The pool is deliberately simple: **by exact size**, with no splitting or merging, so two blocks can never overlap.
What this test guards:

  1. a returned block is reused, and the heap pointer does not advance;
  2. the reused block is **zeroed**: with the old allocator every allocation fell into fresh memory, hence zero, and the engine
     may have relied on it (`calloc` does nothing more than `malloc`);
  3. sizes do not mix, and sizes are rounded to 16 bytes as before;
  4. `free` on an unknown or already returned pointer breaks nothing and never returns the same block twice;
  5. loading a savestate moves the pointer back: the pool forgets everything that lived above it, otherwise the engine
     would reallocate through the pointer blocks still in the pool;
  6. `heap_used` stays the highest reached (it is what the memory alert watches), `heap_live` says what is alive.

    python3 tests/test_heap_reuse.py
"""
import os, sys, unittest

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, '..'))
from dq4_pc.core import emu_core

BORROWED = ('malloc', 'free', 'heap_rewind', 'heap_used', 'heap_live')


class FakeHeap:
    """The heap alone, without Unicorn: `mem_w` records what is written."""
    HEAP_BASE, HEAP_SIZE = emu_core.Core.HEAP_BASE, emu_core.Core.HEAP_SIZE

    def __init__(self):
        self.heap_ptr = self.HEAP_BASE; self.heap_blocks = {}; self.heap_free = {}; self.heap_scratch = {}; self.ram = {}

    def mem_w(self, p, data): self.ram[p] = bytes(data)


for _n in BORROWED: setattr(FakeHeap, _n, emu_core.Core.__dict__[_n])


class Reuse(unittest.TestCase):
    def setUp(self): self.h = FakeHeap()

    def test_a_freed_block_comes_back(self):
        p = self.h.malloc(512); top = self.h.heap_ptr
        self.h.free(p)
        self.assertEqual(self.h.malloc(512), p, 'the same block is reused')
        self.assertEqual(self.h.heap_ptr, top, 'the heap pointer did not move')

    def test_reused_block_is_zeroed(self):
        p = self.h.malloc(512); self.h.free(p); self.h.ram.clear()
        self.h.malloc(512)
        self.assertEqual(self.h.ram.get(p), bytes(512), 'the reused block is zeroed')

    def test_a_fresh_block_is_not_rewritten(self):
        self.h.malloc(512)
        self.assertEqual(self.h.ram, {}, 'a new block is already zero: nothing to write')

    def test_sizes_do_not_mix(self):
        a = self.h.malloc(512); self.h.free(a)
        b = self.h.malloc(1024)
        self.assertNotEqual(b, a); self.assertEqual(self.h.malloc(512), a)

    def test_sizes_are_rounded_to_16(self):
        p = self.h.malloc(1); self.assertEqual(self.h.heap_ptr - p, 16)
        self.h.free(p)
        self.assertEqual(self.h.malloc(9), p, 'a 9-byte request takes the 16-byte block')

    def test_zero_bytes_still_gives_a_block(self):
        q = self.h.malloc(0); self.assertEqual(self.h.heap_ptr - q, 16)

    def test_free_of_an_unknown_pointer_does_nothing(self):
        before = dict(self.h.heap_blocks)
        self.h.free(0x12345678); self.h.free(self.h.HEAP_BASE)
        self.assertEqual(self.h.heap_blocks, before); self.assertEqual(self.h.heap_free, {})

    def test_double_free_hands_the_block_out_only_once(self):
        p = self.h.malloc(256); self.h.free(p); self.h.free(p)
        self.assertEqual(self.h.malloc(256), p)
        self.assertNotEqual(self.h.malloc(256), p, 'the same block cannot be given twice')

    def test_two_live_blocks_never_overlap(self):
        taken = []
        for _ in range(200): taken.append(self.h.malloc(1024))
        for p in taken[::2]: self.h.free(p)
        again = [self.h.malloc(1024) for _ in range(100)]
        live = taken[1::2] + again
        self.assertEqual(len(set(live)), len(live), 'no overlap')

    def test_loading_a_state_forgets_what_lived_above(self):
        low = self.h.malloc(512)
        mark = self.h.heap_ptr
        high = self.h.malloc(512); self.h.free(high)                      # a freed block, above the savestate point
        self.assertIn(512, self.h.heap_free)
        self.h.heap_rewind(mark)
        self.assertEqual(self.h.heap_free.get(512, []), [], 'the reserve forgets the blocks above the pointer')
        self.assertIn(low, self.h.heap_blocks, 'ce qui vivait en dessous reste')
        self.assertEqual(self.h.malloc(512), high, 'the pointer reallocates the space, which is indeed free')

    def test_used_is_the_high_water_mark_and_live_is_what_is_held(self):
        a = self.h.malloc(1024); self.h.malloc(512)
        self.assertEqual(self.h.heap_used(), 1536); self.assertEqual(self.h.heap_live(), 1536)
        self.h.free(a)
        self.assertEqual(self.h.heap_used(), 1536, 'the memory alert follows the highest point reached')
        self.assertEqual(self.h.heap_live(), 512)

    def test_the_heap_is_still_bounded(self):
        self.h.heap_ptr = self.h.HEAP_BASE + self.h.HEAP_SIZE - 16
        self.h.malloc(16)
        with self.assertRaises(MemoryError): self.h.malloc(16)

    def test_free_then_the_wall_is_pushed_back(self):
        """The player's scenario: the same sequence allocated and freed in a loop no longer makes the heap grow."""
        self.h.heap_ptr = self.h.HEAP_BASE
        for _ in range(500):
            ps = [self.h.malloc(1024) for _ in range(20)] + [self.h.malloc(512) for _ in range(20)]
            for p in ps: self.h.free(p)
        self.assertEqual(self.h.heap_used(), 20 * 1024 + 20 * 512, 'the heap levels off at the live peak, not at the sum of the allocations')


class WiredUp(unittest.TestCase):
    def test_engine_free_calls_go_to_the_reserve(self):
        """The engine's three `free`s (C and C++) go through the pool, and `calloc` through `malloc` (hence zeroed)."""
        import inspect
        for name_str in ('h_free', 'h__ZdaPv'):
            self.assertIn('self.free(p)', inspect.getsource(getattr(emu_core.Core, name_str)), name_str)
        self.assertIs(emu_core.Core.h__ZdlPv, emu_core.Core.h__ZdaPv)
        self.assertIn('self.malloc(', inspect.getsource(emu_core.Core.h_calloc))

    def test_loading_a_state_rewinds_the_reserve(self):
        import inspect
        from dq4_pc.persistence import savestates as SS
        self.assertIn('heap_rewind', inspect.getsource(SS.apply))


if __name__ == '__main__':
    unittest.main(verbosity=2)
