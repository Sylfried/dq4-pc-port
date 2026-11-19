"""End of the battle start cascade (Capture.BattleEffect, the three games): Unity ends it with Fade.SetFadeOutBlack(0): the screen is black at once and the fade in progress is over.
DQ V / VI start a 125-frame fade to black with the cascade (FieldCommandEncount::exec: UnitySetFade(0x107d)) and change to the battle part only once that fade is over (GamePartManager::Exec waits for
bit 0 of Global.Flag): without this end, the screen stayed black 68 frames after the cascade instead of 2.
A fight started by a script (DQ V / VI bosses, Encount::forceEventBrew) changes to the battle part at once and gives its fade-in during the cascade: no black at its end then.

    python3 tests/test_battle_cascade_end.py
"""
import os, sys, unittest

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), '..'))
from dq456_pc.core import engine as ENGINE


def engine():
    e = ENGINE.Engine.__new__(ENGINE.Engine); e.state = ENGINE.State(); e.flag_calls = []
    e._effect_flag = e.flag_calls.append
    return e


class CascadeEnd(unittest.TestCase):
    def test_long_fade_cut_at_the_end(self):
        e = engine(); s = e.state
        s.apply([(9, [0x1000 | 125], [])], lambda: '')                 # the engine's fade to black, 125 frames (DQ V / VI)
        e._start_battle_effect(0)
        for _ in range(ENGINE.BATTLE_EFFECT_FRAMES - 1):
            e._battle_effect(); s.tick_fade()
        self.assertIsNotNone(s.effect); self.assertTrue(s.fade_in_progress())
        e._battle_effect()
        self.assertIsNone(s.effect); self.assertEqual(e.flag_calls, [True, False])
        self.assertFalse(s.fade_in_progress(), 'the fade is over: the engine changes to the battle part')
        self.assertEqual((s.fade['a'], s.fade['end'], s.fade['col']), (1.0, 1.0, (0.0, 0.0, 0.0)), 'black at once')

    def test_battle_fade_in_after(self):
        e = engine(); s = e.state
        e._start_battle_effect(0)
        for _ in range(ENGINE.BATTLE_EFFECT_FRAMES): e._battle_effect()
        s.apply([(9, [30], [])], lambda: '')                            # the battle's arrival: fade-in in 30 frames, from black
        self.assertEqual((s.fade['a'], s.fade['n']), (1.0, 30))


    def test_script_fight_fade_in_during_the_cascade(self):
        e = engine(); s = e.state
        s.apply([(9, [0x1000 | 100], [])], lambda: '')                 # Global::startBattle's fade to black
        e._start_battle_effect(0)
        e._battle_effect(); s.tick_fade(); e._battle_effect(); s.tick_fade()
        s.part = ENGINE.PART_BATTLE
        s.apply([(9, [30], [])], lambda: '')                            # the battle part's fade-in, two frames later, during the cascade
        for _ in range(ENGINE.BATTLE_EFFECT_FRAMES): e._battle_effect(); s.tick_fade()
        self.assertIsNone(s.effect)
        self.assertEqual((s.fade['a'], s.fade['end']), (0.0, 0.0), 'the battle stays visible')


if __name__ == '__main__':
    unittest.main(verbosity=2)
