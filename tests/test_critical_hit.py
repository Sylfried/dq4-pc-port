"""Critical hit ("kaishin") effect on the enemies: what the engine asks of the viewer.

Real engine (Unicorn), slot 4, one weak monster (Encount + 0x34 / 0x44). The critical is forced on the hero by setting `BaseAction::kaishinFlag_` (LIB + 0x25c6ed) on exit from
`BaseAction::checkActorKaishin` (0x1a81dc) when the actor is on our side (`[acteur + 8]` = 0; 1 = monsters, which roll for it: `rand(0x20) == 0`). Findings:
  - a SECOND effect model (5344, slot 3) is loaded at the same instant as the hit effect (5303, slot 2), 17 frames; the viewer draws it like any battle model;
  - sound effect 407 (`SE0407.akb`, present in the data) is requested, plus a 0 (no file: no effect);
  - the damage number is 2.5 to 3 times larger (8 -> 26, 11 -> 27 measured) and the text "Coup critique !" is added;
  - NO packet 34 (`cmd_screen_effect`), no message shake, no flash: screen effects 3, 5 and 6 have nothing to do with criticals.

    DQ_APK=<patched APKs folder> DQ_SAVES=<saves folder> python3 tests/test_critical_hit.py"""
import os, sys, struct, tempfile, unittest

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), '..'))
from dq456_pc.core import engine as ENGINE

APK, SAVES = os.environ.get('DQ_APK'), os.environ.get('DQ_SAVES')
MONSTER = 3


class Sound(unittest.TestCase):
    def test_sfx_0_is_not_searched_but_407_is(self):
        from dq456_pc import sound as SOUND
        s = object.__new__(SOUND.Sound); seen = []
        s._get = lambda name_str, callback: seen.append(name_str)
        s.play_sfx(0); s.play_sfx(407)
        self.assertEqual(seen, ['SE0407'])


@unittest.skipUnless(APK and SAVES, 'real engine: DQ_APK=<folder of the patched APKs> DQ_SAVES=<folder of the saves>')
class RealEngine(unittest.TestCase):
    @staticmethod
    def first_hit(critical):
        """-> dict(models, sounds, types, damage) seen up to the hero's first damage number on the monster."""
        import unicorn
        eng = ENGINE.Engine(APK, SAVES, tempfile.mkdtemp(prefix='sv_crit_'))
        for _ in range(3): eng.step(0, 0)
        eng.load_save(4)
        for i in range(100): eng.step(0, 0x10 if i % 10 == 0 else 0)
        if eng.state.part != ENGINE.PART_FIELD:
            eng.start_field()
            for i in range(120): eng.step(0, 0)
        c = eng.core; L = c.LIB_BASE; eng.impose_scroll_mode(0)                  # automatic messages
        enc = c.call(eng.E('_ZN7Encount12getSingletonEv'), label='enc')

        def monster(uc, addr, sz, ud):
            for j in range(4):
                c.mem_w(enc + 0x34 + 4 * j, struct.pack('<I', MONSTER if j == 0 else 0)); c.mem_w(enc + 0x44 + 4 * j, struct.pack('<I', 1 if j == 0 else 0))
        a = c.export('_ZN10BattleRoot12setupMonsterEv'); c.uc.hook_add(unicorn.UC_HOOK_CODE, monster, None, a, a)
        if critical:
            def force(uc, addr, sz, ud):
                x20 = uc.reg_read(c.XREG[20]) & 0xffffffffffff
                if struct.unpack('<I', bytes(c.mem(x20 + 8, 4)))[0] == 0: c.mem_w(L + 0x25c6ed, b'\x01')
            c.uc.hook_add(unicorn.UC_HOOK_CODE, force, None, L + 0x1a81dc, L + 0x1a81dc)
        c.uc.ctl_flush_tb()
        c.call(eng.E('_ZN7Encount12forceEncountEv'), enc, label='force')
        for i in range(900):
            eng.step([0x4, 0x8][(i // 20) % 2], 0)
            if eng.state.part == ENGINE.PART_BATTLE: break
        r = dict(models=set(), sons=set(), types=set(), damage=None); rel = None; att = 0
        for i in range(1500):
            if rel is not None: eng.send_menu(rel, 1, -1, 0); rel = None
            port = eng.active_menu()
            if port is not None and not eng.msg_visible:
                att += 1
                if att % 4 == 0: eng.send_menu(port, 1, -1, 0x10); rel = port
            pkt = eng.step(0, 0)
            for t, a, f in pkt:
                r['types'].add(t)
                if t == 21 and len(a) >= 2 and a[1] >= 0: r['models'].add(a[1])
                if t == 35 and a: r['sons'].add(a[0])
            if eng.ui.damage and r['damage'] is None: r['damage'] = [d[2] for d in eng.ui.damage]
            eng.ui.damage = []
            if r['damage'] is not None: break
        return r

    def test_critical_requests_second_effect_model_and_sfx_no_screen_effect(self):
        normal, critical = self.first_hit(False), self.first_hit(True)
        self.assertIsNotNone(normal['damage']); self.assertIsNotNone(critical['damage'])
        self.assertIn(5303, normal['models']); self.assertNotIn(5344, normal['models'])
        self.assertIn(5303, critical['models']); self.assertIn(5344, critical['models'])
        self.assertNotIn(407, normal['sons']); self.assertIn(407, critical['sons'])
        self.assertNotIn(34, critical['types'])                          # no screen effect (cmd_screen_effect): flash, shake...
        self.assertGreater(max(critical['damage']), 1.5 * max(normal['damage']))


if __name__ == '__main__': unittest.main()
