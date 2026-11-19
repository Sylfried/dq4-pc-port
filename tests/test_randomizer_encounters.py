"""Randomizer, encounters and bosses (dq456_pc/randomizer/encounters.py and Engine._encounter_rando_hooks):

  1. the plan, a fixed function of the seed: "Random encounters" Shuffled replaces each monster everywhere by the same other monster (a permutation of every monster, sea and land
     mixed), Random builds each battle's groups at random among every monster; "Bosses in random encounters" makes a random encounter a boss now and then;
  2. the bosses (with or without Safety): shuffled / random / two per fight, the companions kept;
  3. the seed and the Randomizer page: each setting of the code has its line; the codes of versions 3 and 4 read as the current settings;
  4. DQ V / VI: their tables read from their files (leveldata), the fights their scripts start, their bosses (the monsters the bestiary leaves out), the fights the story needs lost kept;
  5. the real engine (DQ_APK, DQ_SAVES): the game's zones and boss fights read from its tables; Encount::brew called as a random encounter gives the plan's monsters (the game then fits
     them on the screen), called as a story battle (forceBrew) it is not touched, nor a game without the randomizer; a boss fight gets the plan's boss (without Safety only).

    python3 tests/test_randomizer_encounters.py
"""
import collections, os, struct, sys, tempfile, unittest

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), '..'))
from dq456_pc.randomizer import encounters as EN
from dq456_pc.randomizer import seed as SD

APK, SAVES = os.environ.get('DQ_APK'), os.environ.get('DQ_SAVES')
N = EN.NONE


def catalog():
    """Zones 0, 1 at sea, 2 to 7 on land; monsters 1 to 4 at sea only, 10 to 28 on land, 5 in both."""
    rows = [(N,) * 12] * 10
    rows[0] = (1, 2, 5) + (N,) * 9; rows[1] = (3, 4, 1) + (N,) * 9
    for z in range(2, 8): rows[z] = tuple(10 + (z - 2) * 3 + k for k in range(4)) + ((5,) if z == 2 else (N,)) + (N,) * 7
    return EN.Catalog(rows, {0, 1}, set(range(2, 8)))


class Plan(unittest.TestCase):
    def setUp(self): self.cat = catalog()

    def test_catalog(self):
        self.assertEqual(self.cat.family, {0: 'sea', 1: 'sea', **{z: 'land' for z in range(2, 8)}})
        self.assertEqual(self.cat.monsters['sea'], [1, 2, 3, 4, 5]); self.assertIn(5, self.cat.monsters['land']); self.assertEqual(len(self.cat.all), 5 + 19)

    def test_unchanged(self):
        self.assertIsNone(EN.plan(self.cat, 7, EN.UNCHANGED))

    def test_shuffled(self):
        p = EN.plan(self.cat, 3, EN.SHUFFLED); seen = {}
        for z, m in p['monster_map'].items():
            for a, b in m.items(): self.assertEqual(seen.setdefault(a, b), b)                                      # (the same replacement everywhere)
        self.assertEqual(sorted(seen), self.cat.all); self.assertEqual(sorted(seen.values()), self.cat.all)
        self.assertTrue(any(seen[m] not in (1, 2, 3, 4, 5) for m in (1, 2, 3, 4)))                                   # (sea and land mixed)
        self.assertEqual(p, EN.plan(self.cat, 3, EN.SHUFFLED))                                                     # (same seed, same plan)
        g = EN.groups_for(p, 3, [(13, 2), (15, 1), (0, 0), (0, 0)], 0); m = p['monster_map'][3]
        self.assertEqual(g, [(m[13], 2), (m[15], 1), (0, 0), (0, 0)])
        self.assertEqual(EN.groups_for(p, 99, [(13, 2)], 0), [(13, 2)])                                          # (a zone outside the random encounters)

    def test_random(self):
        p = EN.plan(self.cat, 5, EN.RANDOM); sizes = set(); at_sea = set(); totals = collections.Counter()
        for s in range(4000):
            g = EN.groups_for(p, 0, [(1, 1), (0, 0), (0, 0), (0, 0)], s); self.assertEqual(len(g), 4)
            full = [x for x in g if x[1]]; sizes.add(len(full)); self.assertEqual(g[len(full):], [(0, 0)] * (4 - len(full)))
            self.assertTrue(all(m in self.cat.all and n >= 1 for m, n in full)); at_sea |= {m for m, _n in full}; totals[sum(n for _m, n in full)] += 1
        self.assertEqual(sizes, {1, 2, 3, 4}); self.assertEqual(at_sea, set(self.cat.all))                         # (any monster, at sea too)
        self.assertEqual(set(totals), set(range(1, EN.FREE_TOTAL + 1))); self.assertTrue(all(400 < k < 600 for k in totals.values()), totals)      # (the number of monsters too: 1 to 8, as likely)
        self.assertEqual(EN.groups_for(p, 3, [(13, 1)], 1234), EN.groups_for(p, 3, [(13, 1)], 1234))                # (same random state, same battle)

    def test_single_enemy(self):
        """"One enemy only": a random encounter is a single monster, any of them; only with "Random" (shuffled or unchanged: the setting does nothing)."""
        p = EN.plan(self.cat, 5, EN.RANDOM, single_enemy=1); seen = set()
        for s in range(400):
            g = EN.groups_for(p, 0, [(1, 1), (0, 0), (0, 0), (0, 0)], s); self.assertEqual(g[0][1], 1); self.assertEqual(g[1:], [(0, 0)] * 3); seen.add(g[0][0])
        self.assertEqual(seen, set(self.cat.all))
        self.assertFalse(EN.plan(self.cat, 5, EN.SHUFFLED, single_enemy=1)['single']); self.assertIsNone(EN.plan(self.cat, 5, EN.UNCHANGED, single_enemy=1))


def boss_catalog():
    """catalog() with three boss fights: rows 157 (boss 200 and a companion 10), 180 and 181 (the same boss 201, special party 40), 185 (boss 202 x 2 to 3)."""
    rows = [(N,) * 14] * 256; base = catalog()
    for z, slots in base.zones.items(): rows[z] = tuple(slots) + (N, N)
    specials = {17: [(200, 1, 1), (10, 1, 1), (N, 0, 0), (N, 0, 0)], 40: [(201, 1, 1), (N, 0, 0), (N, 0, 0), (N, 0, 0)], 44: [(202, 2, 3), (N, 0, 0), (N, 0, 0), (N, 0, 0)]}
    return EN.Catalog(rows, {0, 1}, set(range(2, 8)), specials, {157: 17, 180: 40, 181: 40, 185: 44})


class Bosses(unittest.TestCase):
    def setUp(self): self.cat = boss_catalog()

    def test_catalog(self):
        self.assertEqual(self.cat.bosses, {157: (17, [(200, 1, 1)], [(10, 1, 1)]), 180: (40, [(201, 1, 1)], []), 181: (40, [(201, 1, 1)], []), 185: (44, [(202, 2, 3)], [])})
        self.assertEqual(EN._boss_parts(self.cat), [[(200, 1, 1)], [(201, 1, 1)], [(202, 2, 3)]])

    def test_safety_does_not_matter(self):
        o = SD.parse(SD.new_code({'safety': 0, 'bosses': EN.SHUFFLED_BOSSES}, 9))['options']; self.assertEqual((o['safety'], o['bosses']), (0, EN.SHUFFLED_BOSSES))

    def test_shuffled(self):
        seen = set()
        for number in range(40):
            m = EN.plan(self.cat, number, EN.UNCHANGED, EN.SHUFFLED_BOSSES)['boss_map']
            bosses = [m[157][0][0], m[180][0][0], m[185][0][0]]
            self.assertEqual(sorted(bosses), [200, 201, 202]); self.assertEqual(m[180], m[181])                   # (a permutation; one boss, one replacement)
            self.assertEqual(m[157][1:], [(10, 1, 1)]); seen.add(tuple(bosses))                                     # (the companions stay)
        self.assertGreater(len(seen), 3)

    def test_random_and_two(self):
        for number in range(40):
            m = EN.plan(self.cat, number, EN.UNCHANGED, EN.RANDOM_BOSSES, 0, 1)['boss_map']
            g = m[157]; self.assertEqual(len(g), 3); self.assertIn(g[0][0], (200, 201, 202)); self.assertIn(g[1][0], (200, 201, 202)); self.assertNotEqual(g[0], g[1])
            self.assertEqual(g[2], (10, 1, 1))                                                                     # (its companion)

    def test_groups_of_a_fight(self):
        p = EN.plan(self.cat, 3, EN.UNCHANGED, EN.SHUFFLED_BOSSES)
        for state in range(30):
            g = EN.boss_groups(p, 185, state); self.assertEqual(len(g), 4)
            full = [x for x in g if x[1]]; self.assertTrue(full); self.assertEqual(EN.boss_groups(p, 185, state), g)
        self.assertIsNone(EN.boss_groups(p, 169, 0))                                                                    # (not a boss fight: unchanged)

    def test_boss_encounters(self):
        for _ in (1,):
            p = EN.plan(self.cat, 3, EN.UNCHANGED, 0, 1)
            out = [EN.groups_for(p, 3, [(13, 1), (0, 0), (0, 0), (0, 0)], s) for s in range(3000)]
            bosses = [g for g in out if g[0][0] in (200, 201, 202)]
            self.assertTrue(0.01 < len(bosses) / len(out) < 0.06, len(bosses)); self.assertTrue(all(g[1:] == [(0, 0)] * 3 for g in bosses if g[0][0] != 202))
            self.assertEqual(p['boss_map'], {})
        p = EN.plan(self.cat, 3, EN.RANDOM, 0, 1, single_enemy=1)                                                      # (one enemy only: a boss comes alone, once)
        bosses = [g for g in (EN.groups_for(p, 3, [(13, 1)], s) for s in range(3000)) if g[0][0] in (200, 201, 202)]
        self.assertTrue(bosses); self.assertTrue(all(g == [(g[0][0], 1)] + [(0, 0)] * 3 for g in bosses))


class SeedAndPage(unittest.TestCase):
    def test_codes(self):
        self.assertIsNone(EN.plan_for_code(None, object()))
        self.assertIsNone(EN.plan_for_code(SD.new_code({'items': 2}, 5), object()))                              # (encounters unchanged: no plan, nothing read)
        v2 = SD._text([2, 1, 2] + [0] * SD.RANDOM_DIGITS); self.assertIsNone(EN.plan_for_code(v2, object()))

    def test_older_codes(self):
        """Versions 3 and 4: 'zones' / 'groups' read as 'encounters' (random: free groups or random zones; shuffled: the other changes); 'boss_companions' and 'terrain' dropped."""
        def v4(zones, groups, comp=0):
            o = dict(safety=1, items=0, zones=zones, groups=groups, terrain=0, bosses=1, boss_encounters=1, boss_companions=comp, two_bosses=1)
            x = 0
            for k, n in SD.OPTIONS[4]: x = x * n + o[k]
            d = SD._option_digits(4); return SD._text([4] + [(x >> (5 * (d - 1 - i))) & 31 for i in range(d)] + [0] * SD.RANDOM_DIGITS)
        for (zones, groups), want in (((0, 0), 0), ((1, 0), 1), ((2, 0), 1), ((3, 0), 2), ((0, 1), 1), ((0, 2), 2), ((2, 2), 2)):
            o = SD.parse(v4(zones, groups, 1))['options']
            self.assertEqual(o['encounters'], want, (zones, groups)); self.assertEqual((o['bosses'], o['boss_encounters'], o['two_bosses']), (1, 1, 1))
            self.assertFalse({'zones', 'groups', 'boss_companions', 'terrain'} & set(o))

    def test_page_lines(self):
        src = open(os.path.join(os.path.dirname(os.path.abspath(__file__)), '..', 'dq456_pc', 'menus', 'pause.py'), encoding='utf-8').read()
        for k, _n in SD.OPTIONS[SD.VERSION]: self.assertIn("('%s', 'settings." % k, src)
        from dq456_pc.texts.fr import settings as FR
        from dq456_pc.texts.en import settings as EN_T
        for key in ('encounters_setting', 'encounters_random_hint', 'single_enemy_setting', 'loot_setting', 'boss_encounters_setting', 'two_bosses_setting', 'round_button_new_seed'):
            self.assertIn('settings.' + key, FR.TEXTS); self.assertIn('settings.' + key, EN_T.TEXTS)
        for gone in ('zones_setting', 'groups_setting', 'boss_companions_setting', 'new_seed', 'terrain_setting'): self.assertNotIn('settings.' + gone, FR.TEXTS)


@unittest.skipUnless(APK and SAVES, 'real engine: DQ_APK and DQ_SAVES')
class RealEngine(unittest.TestCase):
    ZONE = 78

    @classmethod
    def setUpClass(cls):
        from dq456_pc.core import engine as ENGINE
        cls.E = ENGINE; cls.sv = tempfile.mkdtemp(prefix='rz_enc_')
        eng = cls.eng = ENGINE.Engine(APK, SAVES, cls.sv)
        cls.code = None; eng.encounters_plan = lambda uid: EN.plan_for_code(cls.code, eng.core)
        cls.ok = eng.load_save(4)
        for _ in range(60): eng.step(0, 0)
        c = cls.c = eng.core; cls.enc = c.call(c.export('_ZN7Encount12getSingletonEv')); cls.brew = c.export('_ZN7Encount4brewEv')
        cls.cat = EN.Catalog.from_core(c)

    def setUp(self):
        if not self.ok: self.skipTest('save 4 not loaded')
        self.assertEqual([m for m in self.eng.missing_hooks if 'randomizer' in m], [])
        self.eng.random_brews.add(self.c.RET)

    def tearDown(self):
        self.eng.random_brews.discard(self.c.RET); type(self).code = None; self.eng.forget_items_plan()

    def draw(self, code, random_encounter=True):
        if code != self.code: type(self).code = code; self.eng.forget_items_plan()
        if not random_encounter: self.eng.random_brews.discard(self.c.RET)
        self.eng.last_brew = None
        self.c.mem_w(self.enc + 8, struct.pack('<i', self.ZONE)); self.assertEqual(self.c.call(self.brew, self.enc, label='brew') & 0xffffffff, 1)
        ms = struct.unpack('<4I', self.c.mem(self.enc + 0x34, 16)); ns = struct.unpack('<4I', self.c.mem(self.enc + 0x44, 16))
        return [m for m, n in zip(ms, ns) if n]

    def test_catalog(self):
        self.assertEqual((len(self.cat.zones), len(self.cat.all)), (111, 191))
        self.assertEqual(sorted(z for z, f in self.cat.family.items() if f == 'sea'), [0, 1, 2, 3])
        self.assertIn(self.ZONE, self.cat.zones); self.assertEqual(len(self.cat.bosses), len(EN.BOSS_ROWS))

    def test_untouched_without_randomizer(self):
        own = set(self.cat.zones[self.ZONE])
        for _ in range(10): self.assertTrue(set(self.draw(None)) <= own)
        self.assertIsNone(self.eng.last_brew)

    def test_shuffled(self):
        code = SD.new_code({'encounters': EN.SHUFFLED}, number=4242); p = EN.plan_for_code(code, self.c)
        allowed = set(p['monster_map'][self.ZONE].values())
        for _ in range(10):
            got = self.draw(code); self.assertTrue(got and set(got) <= allowed, (got, allowed))
            zone, old, new = self.eng.last_brew; self.assertEqual(zone, self.ZONE)
            self.assertEqual(got, [m for m, n in new if n][:len(got)])                                          # (the game may take some off to fit the screen, never adds)

    def test_random(self):
        code = SD.new_code({'encounters': EN.RANDOM}, number=77); seen = set()
        for _ in range(20): got = self.draw(code); self.assertTrue(got and set(got) <= set(self.cat.all), got); seen |= set(got)
        self.assertGreater(len(seen), 8)
        one = SD.new_code({'encounters': EN.RANDOM, 'single_enemy': 1}, number=77)
        for _ in range(10): got = self.draw(one); self.assertEqual(len(got), 1, got); self.assertEqual(self.eng.last_brew[2][0][1], 1)          # (one monster)

    def test_story_battle_untouched(self):
        code = SD.new_code({'encounters': EN.RANDOM, 'safety': 1, 'bosses': EN.SHUFFLED_BOSSES}, number=4242); own = set(self.cat.zones[self.ZONE])
        for _ in range(10): self.assertTrue(set(self.draw(code, random_encounter=False)) <= own)
        self.assertIsNone(self.eng.last_brew)

    def test_boss_fight(self):
        """A boss fight (row 185, the final one) started as by a script (forceBrew's return address): the plan's boss; the same row without the plan, or a story fight (169, lost in
        advance): as in the game; with Safety too."""
        code = SD.new_code({'safety': 1, 'bosses': EN.SHUFFLED_BOSSES}, number=99); p = EN.plan_for_code(code, self.c); self.assertTrue(p['boss_map'])
        self.eng.random_brews.discard(self.c.RET); self.eng.forced_brews.add(self.c.RET)
        try:
            want = {m for m, _lo, _hi in p['boss_map'][185]}
            for _ in range(5):
                type(self).ZONE = 185; got = self.draw(code, random_encounter=False)
                self.assertTrue(got and set(got) <= want, (got, want)); self.assertEqual(self.eng.last_brew[0], 185)
            self.assertEqual(set(self.draw(None, random_encounter=False)), {174})                                    # (no randomizer: Psaro)
            type(self).ZONE = 169; self.assertEqual(set(self.draw(code, random_encounter=False)), {171})             # (the fight lost in advance: unchanged)
            code = SD.new_code({'safety': 0, 'bosses': EN.SHUFFLED_BOSSES}, number=99); type(self).ZONE = 185
            self.assertTrue(set(self.draw(code, random_encounter=False)) <= want)                                     # (Safety does not change the bosses)
        finally: self.eng.forced_brews.discard(self.c.RET); type(self).ZONE = 78


def excel(rows, size):
    return struct.pack('<5I', 0, len(rows), size, 0, 0) + b''.join(r.ljust(size, b'\0') for r in rows)


class FilesV2(unittest.TestCase):
    """DQ V / VI: zones, specials and boss rows from their leveldata and their scripts' fight commands; a boss is a monster the bestiary leaves out (9 and 10 here)."""
    def files(self, key, ops):
        data = [bytes(28)] * 8
        data[1] = bytes(2) + bytes([3, 4, 0, 0, 0, 0, 0, 0, 0, 0, 0])                    # zone 1: monsters 3, 4
        data[2] = bytes(2) + bytes([5]) + bytes(9) + bytes([0])                          # zone 2: monster 5
        data[5] = bytes(0xc) + bytes([1])                                                 # row 5: special 1, a boss (9) and two 3
        data[6] = bytes(0xc) + bytes([2])                                                 # row 6: special 2, only monsters of the bestiary (not a boss)
        data[7] = bytes(0xc) + bytes([1])                                                 # row 7: kept by the story
        spec = [bytes(8), bytes([9, 3, 0, 0, 1 | 6 << 3, 0]), bytes([4, 6, 0, 0, 3 | 1 << 3, 0])]
        cmd = lambda op, row: struct.pack('<HBB4i', op, 1, 0, 0, row, 0, 0)                   # (the row at + 8)
        sys.path.insert(0, os.path.dirname(os.path.abspath(__file__))); import test_randomizer_items as TI
        script = TI.script([cmd(op, r) for op, r in ((ops[0], 5), (ops[1], 6), (ops[2], 7), (ops[0], 1))])
        book = [struct.pack('<H', m) for m in (0, 3, 4, 5, 6)]                         # (6: in the bestiary, met in no zone)
        files = {'assets/leveldata/%sds_encount_data.dat' % key: excel(data, 28), 'assets/leveldata/%sds_encount_special.dat' % key: excel(spec, 8),
                 'assets/leveldata/%sds_book_data.dat' % key: excel(book, 4), 'assets/leveldata/%sds_monster.dat' % key: excel([b''] * 11, 4), 'assets/script/a.e': script}
        return files

    def test_tables(self):
        for key in ('dq5', 'dq6'):
            G = EN.V2[key]; files = self.files(key, G['ops'])
            old = G['keep']; G['keep'] = (7,)
            try:
                cat = EN.Catalog.from_files(files.__getitem__, ['assets/script/a.e'], key)
            finally: G['keep'] = old
            self.assertEqual(sorted(cat.zones), [1, 2]); self.assertEqual(cat.zones[1][:3], [3, 4, N]); self.assertEqual(cat.all, [3, 4, 5])
            self.assertEqual(sorted(cat.bosses), [5])
            sp, boss, comp = cat.bosses[5]; self.assertEqual((sp, boss, comp), (1, [(9, 1, 1)], [(3, 2, 4)]))

    def test_level_table(self):
        self.assertEqual(EN.level_table(excel([b'ab', b'cd'], 4)), [b'ab\0\0', b'cd\0\0'])


@unittest.skipUnless(os.environ.get('DQ_APK_DQ5') or os.environ.get('DQ_APK_DQ6'), 'real game files: DQ_APK_DQ5 / DQ_APK_DQ6')
class RealFilesV2(unittest.TestCase):
    """(real data) the counts read on 17/11: zones, monsters, boss fights (the same with the bestiary's rule as with "a monster met in no zone")."""
    def test_counts(self):
        import zipfile
        for key, zones, mons, bosses in (('dq5', 86, 191, 22), ('dq6', 112, 193, 35)):
            pack = os.path.join(os.environ.get('DQ_APK_' + key.upper(), ''), 'split_UnityDataAssetPack.apk')
            if not os.path.isfile(pack): continue
            z = zipfile.ZipFile(pack); names = [n for n in z.namelist() if n.startswith('assets/script/')]
            cat = EN.Catalog.from_files(z.read, names, key)
            self.assertEqual((len(cat.zones), len(cat.all), len(cat.bosses)), (zones, mons, bosses), key)
            for r in EN.V2[key]['keep']: self.assertNotIn(r, cat.bosses)
            book = {struct.unpack_from('<H', r, 0)[0] for r in EN.level_table(z.read('assets/leveldata/%sds_book_data.dat' % key))}
            for _sp, boss, _comp in cat.bosses.values(): self.assertFalse({m for m, _lo, _hi in boss} & book, key)          # (no boss in the bestiary)
            p = EN.plan(cat, 4242, EN.SHUFFLED, EN.SHUFFLED_BOSSES)
            self.assertEqual(set(p['boss_map']), set(cat.bosses))


if __name__ == '__main__': unittest.main(verbosity=1)
