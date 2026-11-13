"""Chaining of a turn's animations at automatic speed: the damage amount appears sooner after a hit.

Real engine (engine frames, 30 per second): an attack hit on the world map (slot 4, forced encounter). "Battle speed" imposes OptionStatus.battleSpeed (g_Option + 5): 0 / 1 / 2 / 3 = wait of
12 / 22 / 32 / 42 frames between two messages; "Normal" / "Fast" / "Tres rapide" impose 0 (settings.CODE_SCROLL_AUTO), the old "Normal" imposed 2. Measurement: hit animation (model 5303) -> damage number;
the duration of the animation itself does not change.

    DQ_APK=<patched APK folder> DQ_SAVES=<saves folder> python3 tests/test_turn_chaining.py"""
import os, sys, tempfile, unittest

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), '..'))
from dq4_pc.core import engine as ENGINE
from dq4_pc.persistence import settings as RG

APK, SAVES = os.environ.get('DQ_APK'), os.environ.get('DQ_SAVES')


class Setting(unittest.TestCase):
    def test_automatic_speeds_impose_the_shortest_wait(self):
        self.assertEqual([RG.scroll_code(v) for v in RG.BATTLE_SPEEDS], [4, 0, 0, 0])      # "Manual": by hand (unchanged); "Normal", "Fast", "Tres rapide": 12 frames


@unittest.skipUnless(APK and SAVES, 'real engine: DQ_APK=<folder of the patched APKs> DQ_SAVES=<folder of the saves>')
class RealEngine(unittest.TestCase):
    @staticmethod
    def hit(code):
        """-> (frame of the confirmed command, frame of the effect model, frame of its removal, frame of the damage number) of the first hit of a battle."""
        eng = ENGINE.Engine(APK, SAVES, tempfile.mkdtemp(prefix='sv_tours_'))
        for _ in range(3): eng.step(0, 0)
        eng.load_save(4)
        for i in range(100): eng.step(0, 0x10 if i % 10 == 0 else 0)
        if eng.state.part != ENGINE.PART_FIELD:
            eng.start_field()
            for i in range(120): eng.step(0, 0)
        c = eng.core; eng.impose_scroll_mode(code)
        c.call(eng.E('_ZN7Encount12forceEncountEv'), c.call(eng.E('_ZN7Encount12getSingletonEv'), label='enc'), label='force')
        for i in range(900):
            eng.step([0x4, 0x8][(i // 20) % 2], 0)
            if eng.state.part == ENGINE.PART_BATTLE: break
        r = dict(menu=None, effect=None, end=None, count=None); was_seen = False; rel = None; att = 0
        for i in range(1500):
            if rel is not None: eng.send_menu(rel, 1, -1, 0); rel = None
            port = eng.active_menu()
            if port is not None and not eng.msg_visible:
                was_seen = True; att += 1
                if att % 4 == 0: eng.send_menu(port, 1, -1, 0x10); rel = port
            elif was_seen and r['menu'] is None: r['menu'] = eng.frames
            pkt = eng.step(0, 0)
            if r['menu'] is None and was_seen and port is None and not eng.msg_visible: r['menu'] = eng.frames
            for t, a, f in pkt:
                if t == 21 and len(a) >= 2 and a[1] == 5303 and r['effect'] is None: r['effect'] = eng.frames
                if t == 21 and len(a) >= 2 and a[1] == -1 and a[0] == 2 and r['effect'] is not None and r['end'] is None: r['end'] = eng.frames
            if eng.ui.damage and r['count'] is None: r['count'] = eng.frames
            eng.ui.damage = []
            if r['count'] is not None: break
        return r

    def test_damage_number_arrives_faster_animation_unchanged(self):
        before, after = self.hit(2), self.hit(0)
        for r in (before, after): self.assertTrue(all(v is not None for v in r.values()), r)
        self.assertEqual(before['end'] - before['effect'], after['end'] - after['effect'])                         # the hit animation keeps its game duration
        self.assertGreaterEqual(before['count'] - before['effect'], 22)                                          # (old "Normal": 23 frames, 0.77 s)
        self.assertLessEqual(after['count'] - after['effect'], 14)                                             # now 13 frames (0.43 s): right after the end of the animation
        self.assertLess(after['count'], before['count'])


if __name__ == '__main__':
    unittest.main()
