"""The transfer targets (Make_TargetCharaList, type 5): the "Bag" row after a row was hidden.

The engine hides an unused row of the list with an "active" code (SetItemCode(row, 0)) but fills the bag's row without ever sending its code (SetCharaButtonInfo). In the game,
the next activation of the window (MenuPortItem.NoticeReceive: first command after a stop, `m_objectActive` false) shows every part again (SetActive(true)). The port kept the row
hidden: "Bag" was missing from the transfer targets after a transfer from the bag, or after loading a savestate taken then (the user's save 3, state 1).
  1. the window (ui_menu.Window.reactivate) shows the rows again, the codes that follow hide what they must;
  2. the interface (engine.Interface) calls it at the first command after a stop and keeps the codes received since, so that a savestate's replay ends in the same state;
  3. Manager.replay: a stopped window keeps its codes (its next activation shows the rows again), an active one is shown again then gets the codes received since.

    python3 tests/test_target_rows.py            (DQ_UI_CACHE=<interface cache>)"""
import os, sys, unittest

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import _text_render as TR
UM = TR.UM
from dq456_pc.core import engine as ENGINE

CACHE = TR.CACHE
ROWS = (1551, 1661, 1771)          # the three buttons of type 5 (parts 1 to 3: codes 0 to 2)


class Log:
    def __init__(self): self.calls = []
    def __getattr__(self, name): return lambda *a: self.calls.append((name,) + a)


class Interface(unittest.TestCase):
    def feed(self, ui, *msgs): ui.apply([(6, list(m)) for m in msgs])

    def test_first_command_after_a_stop(self):
        ui = ENGINE.Interface(); ui.obs = Log()
        ui.apply([(0, [6, 1, 1, 5])])                                   # (port 6 created, type 5)
        self.feed(ui, [1, 1, 1, 1], [12, 1, 0], [12, 2, 0]); self.assertIn(('reactivate', 6), ui.obs.calls)
        self.assertEqual(ui.f[6]['since_act'], {1: 0, 2: 0})
        self.feed(ui, [7]); ui.obs.calls.clear()
        self.feed(ui, [1, 1, 1, 1], [12, 0, 1], [12, 2, 0])
        self.assertEqual(ui.obs.calls[0], ('reactivate', 6)); self.assertEqual(ui.f[6]['since_act'], {0: 1, 2: 0})
        self.assertEqual(ui.f[6]['indicators'], {1: 0, 2: 0, 0: 1})     # (every code still known: the title's counts, the replay of a stopped window)
        ui.obs.calls.clear(); self.feed(ui, [5]); self.assertNotIn(('reactivate', 6), ui.obs.calls)          # (already active: nothing)


@unittest.skipUnless(os.path.exists(os.path.join(CACHE, 'ui_layout.json')), 'no interface cache (DQ_UI_CACHE)')
class RealLayout(unittest.TestCase):
    @classmethod
    def setUpClass(cls): cls.ml = UM.PageLayout(os.path.join(CACHE, 'ui_layout.json'))

    def acts(self, w): return [w.N[n]['act'] for n in ROWS]

    def test_rows_shown_again(self):
        w = UM.Window(self.ml, 5)
        w.code(1, 0); w.code(2, 0); self.assertEqual(self.acts(w), [True, False, False])          # (transfer from the bag: Ragnar alone)
        w.reactivate(); w.code(0, 1); w.code(2, 0); self.assertEqual(self.acts(w), [True, True, False])          # (transfer from Ragnar: Ragnar, then the bag's row, filled without a code)

    def test_live_and_replayed(self):
        m = UM.Manager(self.ml); ui = ENGINE.Interface(); ui.obs = m
        ui.apply([(0, [6, 1, 1, 5])])
        ui.apply([(6, [1, 1, 1, 1]), (6, [12, 0, 1]), (6, [12, 1, 0]), (6, [12, 2, 0]), (6, [7])])
        self.assertEqual(self.acts(m.f[6]), [True, False, False])
        ui.apply([(6, [1, 1, 1, 1]), (6, [12, 0, 1]), (6, [12, 2, 0])])
        self.assertEqual(self.acts(m.f[6]), [True, True, False], 'the bag row is back')
        m2 = UM.Manager(self.ml); m2.replay(ui); self.assertEqual(self.acts(m2.f[6]), [True, True, False], 'a savestate taken with the list open')
        ui.apply([(6, [7])]); m3 = UM.Manager(self.ml); m3.replay(ui)
        ui.obs = m3; ui.apply([(6, [1, 1, 1, 1]), (6, [12, 0, 1]), (6, [12, 2, 0])])
        self.assertEqual(self.acts(m3.f[6]), [True, True, False], 'a savestate taken with the list closed, then the list opened')


if __name__ == '__main__':
    unittest.main(verbosity=1)
