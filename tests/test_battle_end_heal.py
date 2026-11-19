"""Option "HP and MP restored at the end of a battle" (`battle_end_heal` setting, Engine.battle_heal, Engine._battle_end_heal): the original engine runs under Unicorn.

    DQ_APK=<folder of the patched APKs> DQ_SAVES=<folder of the saves> python3 tests/test_battle_end_heal.py

Without these two variables, the engine tests are skipped (only the setting is checked). The saves are only opened read-only: the engine writes to a temporary folder.
What is measured, with a real battle won (forced monster, the party at half HP and without MP, one member fallen before the battle):
  - option disabled: the party leaves the battle as the game leaves it (HP below the maximum, MP still 0: like the original);
  - option enabled: once the battle part has ended, every member still standing has all their HP and all their MP; the fallen member stays at 0 HP and keeps their MP;
  - a casino monster arena fight (Global + 0x1c = 1, still 1 when that battle part ends) heals nobody: the party only bet on it."""
import os, struct, sys, tempfile, unittest

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), '..'))
from dq456_pc.core import engine as ENGINE
from dq456_pc.persistence import settings as RG

APK, SAVES = os.environ.get('DQ_APK'), os.environ.get('DQ_SAVES')
OFF_HP, OFF_MP = 0x22, 0x26                                                  # in HaveStatus: HP, max HP, MP, max MP (u16 each, from + 0x22)
FALLEN_MP = 5


class Setting(unittest.TestCase):
    def test_disabled_by_default(self):
        self.assertIs(RG.DEFAULT['battle_end_heal'], False)
        self.assertIn('battle_end_heal', RG.SOUND_TEXT_BOOLEANS)             # a value that is not a boolean falls back to "disabled"
        self.assertIs(ENGINE.Engine.battle_heal, False)

    def test_constants(self):
        self.assertEqual((ENGINE.PARTY_MEMBERS, ENGINE.PARTY_SLOTS, ENGINE.PLAYER_STRIDE, ENGINE.PLAYER_HAVESTATUS, ENGINE.GLOBAL_STADIUM), (0x304, 13, 0x530, 0x58, 0x1c))


@unittest.skipUnless(APK and SAVES, 'real engine: DQ_APK=<folder of the patched APKs> DQ_SAVES=<folder of the saves>')
class RealEngine(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        import unicorn
        from dq456_pc.persistence import savestates as SS
        cls.SS = SS
        cls.eng = ENGINE.Engine(APK, SAVES, tempfile.mkdtemp(prefix='sv_heal_')); c = cls.c = cls.eng.core
        cls.eng.load_save(1)
        for _ in range(200): cls.eng.step(0, 0)
        cls.orig = c.export('_ZN6status9PartyData15originalPlayer_E'); cls.party = c.export('_ZN6status7g_PartyE')
        cls.members = [i for i in struct.unpack('<13I', c.mem(cls.party + 0x304, 13 * 4)) if i]
        enc = c.call(c.export('_ZN7Encount12getSingletonEv'), label='enc')
        def force(u, addr, sz, ud):                                                         # encounter: a single monster of group 3 (monster numbers at Encount + 0x34, counts at + 0x44)
            for j in range(4): c.mem_w(enc + 0x34 + 4 * j, struct.pack('<I', 3 if j == 0 else 0)); c.mem_w(enc + 0x44 + 4 * j, struct.pack('<I', 1 if j == 0 else 0))
        a = c.export('_ZN10BattleRoot12setupMonsterEv'); c.uc.hook_add(unicorn.UC_HOOK_CODE, force, None, a, a); c.uc.ctl_flush_tb()
        cls.snap = SS.snapshot(cls.eng)

    def setUp(self): self.SS.apply(self.eng, self.snap); self.eng.battle_heal = False; self.eng.level_heal = False

    def hs(self, i): return self.orig + ENGINE.PLAYER_STRIDE * i + ENGINE.PLAYER_HAVESTATUS

    def hp_mp(self, i): return struct.unpack_from('<4H', self.c.mem(self.hs(i) + OFF_HP, 8))          # (HP, max HP, MP, max MP)

    def place(self, i, hp, mp):
        self.c.mem_w(self.hs(i) + OFF_HP, struct.pack('<H', hp)); self.c.mem_w(self.hs(i) + OFF_MP, struct.pack('<H', mp))

    def prepare(self):
        """The party at half HP and without MP (nobody can heal during the battle), its last member fallen (0 HP, FALLEN_MP MP). -> (members standing, fallen member)."""
        self.assertGreaterEqual(len(self.members), 2, 'a save with at least two members')
        *standing, fallen = self.members
        for i in standing: self.place(i, max(1, self.hp_mp(i)[1] // 2), 0)
        self.place(fallen, 0, FALLEN_MP)
        return standing, fallen

    def battle(self):
        """A real battle, played to its end (the first command of each menu, messages turned). -> True when the battle part has ended."""
        eng, c = self.eng, self.c
        c.call(c.export('_ZN6Global11startBattleEv'), eng._global(), label='startBattle')
        n = 0
        while eng.state.part != ENGINE.PART_BATTLE and n < 1500: eng.step(0, 0); n += 1
        self.assertEqual(eng.state.part, ENGINE.PART_BATTLE, 'the battle starts')
        st = {'rel': None, 'pending': 0}
        for _ in range(6000):
            p = d = 0
            if st['rel'] is not None: eng.send_menu(st['rel'], 1, -1, 0); st['rel'] = None
            port = eng.active_menu()
            if port is not None and not eng.msg_visible:
                st['pending'] += 1
                if st['pending'] % 4 == 0: eng.send_menu(port, 1, -1, 0x10); st['rel'] = port
            elif eng.msg_visible and (eng.ui.msg.get('feed') or eng.message_state()[1] in (3, 5)):
                st['pending'] += 1
                if st['pending'] % 4 == 0: p = d = ENGINE.A
            else: st['pending'] = 0
            prev = eng.state.part; eng.step(p, d); eng.ui.damage = []
            if prev == ENGINE.PART_BATTLE and eng.state.part != ENGINE.PART_BATTLE: return True
        return False

    def test_disabled_like_the_game(self):
        standing, fallen = self.prepare()
        self.assertTrue(self.battle(), 'the battle ends')
        for i in standing:
            hp, hpm, mp, mpm = self.hp_mp(i)
            self.assertGreater(hp, 0); self.assertLess(hp, hpm, 'no healing'); self.assertEqual(mp, 0)
        self.assertEqual(self.hp_mp(fallen)[0], 0); self.assertEqual(self.hp_mp(fallen)[2], FALLEN_MP)

    def test_enabled_heals_the_members_standing(self):
        standing, fallen = self.prepare(); self.eng.battle_heal = True
        self.assertTrue(self.battle(), 'the battle ends')
        self.assertFalse([t for t in self.eng.missing_hooks if 'end of a battle' in t])
        for i in standing:
            hp, hpm, mp, mpm = self.hp_mp(i)
            self.assertEqual((hp, mp), (hpm, mpm), 'member %d: all their HP and MP' % i); self.assertGreater(hpm, 0)
        self.assertEqual(self.hp_mp(fallen)[0], 0, 'the fallen member stays fallen'); self.assertEqual(self.hp_mp(fallen)[2], FALLEN_MP, 'and keeps their MP')
        for _ in range(120): self.eng.step(0, 0)                                                  # (the map comes back: nothing undoes it)
        for i in standing: hp, hpm, mp, mpm = self.hp_mp(i); self.assertEqual((hp, mp), (hpm, mpm))

    def test_monster_arena_heals_nobody(self):
        """The guard alone (the arena's flag is established by playing an arena fight: Global + 0x1c = 1 from its start until its battle part has ended, 0 before)."""
        eng, c = self.eng, self.c
        standing, fallen = self.prepare(); flag = eng._global() + ENGINE.GLOBAL_STADIUM
        self.assertNotEqual(struct.unpack('<I', c.mem(flag, 4))[0], 1)
        c.mem_w(flag, struct.pack('<I', 1)); eng._battle_end_heal()
        for i in standing: hp, hpm, mp, mpm = self.hp_mp(i); self.assertLess(hp, hpm); self.assertEqual(mp, 0)
        c.mem_w(flag, struct.pack('<I', 0)); eng._battle_end_heal()
        for i in standing: hp, hpm, mp, mpm = self.hp_mp(i); self.assertEqual((hp, mp), (hpm, mpm))
        self.assertEqual(self.hp_mp(fallen)[0], 0)


if __name__ == '__main__':
    unittest.main()
