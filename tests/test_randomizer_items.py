"""Randomizer, items (dq456_pc/randomizer/items.py and Engine._item_hooks):

  1. the game files, read without the game: a map's furniture table (chests, jars, barrels, shelves, wardrobes, sparkles: one container per "taken" flag; doors and special furniture left
     out) and a script's gifts (cmd_set_item / cmd_set_gold that give; the ones that take are not gifts);
  2. the plan, a fixed function of the seed: "Shuffled" deals the contents out again among every container of the game (the empty ones stay empty; a mimic only in a chest; a gold gift keeps
     its gold), "Random" draws each container's content (an item among every real item, the key items included, gold among the amounts of the game, a mini medal, nothing, a mimic in a
     chest only); "Safety": the key items stay where they are and the gifts do not change; "Monster drops" random: each drop the game rolls is drawn again among every item (Safety:
     a key item dropped stays);
  3. the real game files (DQ_APK): the containers and gifts found, the plans made from them;
  4. the real engine (DQ_APK, DQ_SAVES): the rows of a map's furniture table hold the plan's contents once the map is set up, the game reads them (TownFurnitureManager::checkCoffer: item,
     gold, mimic), the same after the map is set up again; a game without the randomizer is not touched; a gift's command is rewritten just before it runs and gives the plan's content;
     MonsterParty::checkDropItem keeps the drawn drop, at the game's rate.

    python3 tests/test_randomizer_items.py
"""
import collections, glob, os, struct, sys, tempfile, unittest

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), '..'))
from dq456_pc.randomizer import items as IT
from dq456_pc.randomizer import seed as SD

APK, SAVES = os.environ.get('DQ_APK'), os.environ.get('DQ_SAVES')


def stage(rows):
    """A map file whose furniture table has `rows`: (kind, item, gold, formation, monster, message, flag)."""
    head = bytearray(16); struct.pack_into('<4i', head, 0, 0x12345678, 16, 0, 0)
    table = bytearray(struct.pack('<I', IT.FURNITURE_MAGIC)) + bytearray(IT.ROW * max(1, len(rows)))
    for i, (kind, item, gold, form, mon, msg, flag) in enumerate(rows):
        o = 4 + i * IT.ROW; struct.pack_into('<7H', table, o + 6, item, gold, form, mon, msg, 0, flag); table[o + 0x14] = kind; table[o + 0x16] = len(rows)
    return bytes(head + table)


def script(commands):
    """A script file with one "execute" block of `commands` (bytes of each command)."""
    n = len(commands); offs = []; data = b''
    for c in commands: offs.append(len(data)); data += c
    block = bytearray(b'execute'.ljust(16, b'\x00')) + bytearray(0x30)
    struct.pack_into('<I', block, 0x14, 0x40); struct.pack_into('<5I', block, 0x24, n, 0, 0, 4 * n, len(data))
    return bytes(b'script'.ljust(16, b'\x00') + block + struct.pack('<%dI' % n, *offs) + data)


def item_cmd(item, count=1, mode=0): return struct.pack('<HBB3i', IT.OP_ITEM, 1, 0, item, count, mode)
def gold_cmd(amount, mode=0): return struct.pack('<HBB2i', IT.OP_GOLD, 1, 0, amount, mode)
def coin_cmd(amount, mode=0): return struct.pack('<HBB2i', IT.OP_COIN, 1, 0, amount, mode)


FILES = {'assets/map/aaa.stg': stage([(0, 0, 0, 0, 0, 0, 0),                     # a door: not a container
                                      (7, 5, 0, 0, 0, 0, 1), (7, 0, 100, 0, 0, 0, 2), (7, 0, 0, 72, 165, 0, 3), (7, 0, 0, 0, 0, 0, 4),       # chests: item, gold, mimic, empty
                                      (37, 132, 0, 0, 0, 0, 5), (39, 124, 0, 0, 0, 0, 6), (39, 0, 0, 0, 0, 0, 7),                            # a mini medal in a jar, the magic key, an empty barrel
                                      (7, 0, 0, 0, 0, 8180, 8)]),                                                                             # a special chest (message)
         'assets/map/bbb.stg': stage([(7, 61, 0, 0, 0, 0, 9), (44, 0, 30, 0, 0, 0, 10), (7, 5, 0, 0, 0, 0, 1)]),                           # (flag 1 again: the same chest)
         'assets/script/bbb.bin': script([item_cmd(17), item_cmd(17, 1, 1), gold_cmd(50), gold_cmd(50, 1), item_cmd(138), coin_cmd(500)])}          # a gift, a take, gold, a payment, a key item, tokens


def catalog(): return IT.Catalog(FILES.__getitem__, list(FILES))


class Files(unittest.TestCase):
    def test_containers(self):
        c = catalog()
        self.assertEqual(c.slots, {1: ('chest', ('item', 5)), 2: ('chest', ('gold', 100)), 3: ('chest', ('mimic', 72, 165)), 4: ('chest', ('empty',)), 5: ('other', ('item', 132)),
                                   6: ('other', ('item', 124)), 9: ('chest', ('item', 61)), 10: ('other', ('gold', 30))})          # (no door, no empty barrel, no special chest)
        self.assertEqual((c.golds, c.coins, c.mimics), ([30, 50, 100], [500, IT.BESTIARY_COINS], [(72, 165)]))

    def test_gifts(self):
        data = FILES['assets/script/bbb.bin']; g = catalog().gifts[IT.script_id(data)]
        cmds = {p: op for p, op, _r in IT.script_commands(data)}
        self.assertEqual(sorted(g.values()), [('coin gift', ('coins', 500), 1), ('gift', ('item', 17), 1), ('gift', ('item', 138), 1), ('gold gift', ('gold', 50), 1)])
        self.assertTrue(all(cmds[p] in (IT.OP_ITEM, IT.OP_GOLD, IT.OP_COIN) for p in g))

    def test_real_items(self):
        self.assertEqual(len(IT.ALL_ITEMS), 168); self.assertNotIn(158, IT.ALL_ITEMS); self.assertIn(171, IT.ALL_ITEMS)        # (the version for mobiles' items are real ones)
        self.assertTrue({124, 127, 138, 157, 33} <= IT.KEY_ITEMS); self.assertFalse({IT.MEDAL, 126, 130, 131} & IT.KEY_ITEMS)    # (keys, Ra's mirror, important items, Zenithian; not the consumables)


class Plans(unittest.TestCase):
    def test_unchanged_and_fixed(self):
        c = catalog(); self.assertIsNone(IT.plan(c, 1, IT.UNCHANGED, True))
        for mode in (IT.SHUFFLED, IT.RANDOM):
            self.assertEqual(IT.plan(c, 9, mode, True), IT.plan(c, 9, mode, True))                                      # (a fixed function of the seed)
        diff = {n for n in range(20) if IT.plan(c, n, IT.RANDOM, False) != IT.plan(c, 0, IT.RANDOM, False)}; self.assertGreater(len(diff), 10)

    def gift_slots(self, c, p):
        sid = IT.script_id(FILES['assets/script/bbb.bin']); kinds = {off: k for off, (k, _x, _n) in c.gifts[sid].items()}
        return {off: (kinds[off], x) for off, (x, _n, _room) in p['gifts'].get(sid, {}).items()}

    def test_shuffled(self):
        c = catalog()
        for n in range(30):
            for safety in (True, False):
                p = IT.plan(c, n, IT.SHUFFLED, safety); g = self.gift_slots(c, p)
                self.assertNotIn(4, p['furniture'])                                                                         # (the empty chest stays empty)
                if safety: self.assertNotIn(6, p['furniture']); self.assertEqual(sorted(k for k, _x in g.values()), ['coin gift', 'gold gift'])   # (Safety: the magic key stays, no item gift moves; gold and tokens do)
                else: self.assertIn(6, p['furniture']); self.assertEqual(len(g), 4)
                orig = [c.slots[f][1] for f in p['furniture']] + [x for (k, x, _n) in c.gifts[IT.script_id(FILES['assets/script/bbb.bin'])].values() if not (safety and k == 'gift')] + [('coins', IT.BESTIARY_COINS)]
                self.assertEqual(collections.Counter(list(p['furniture'].values()) + [x for _k, x in g.values()] + [p['bestiary']]), collections.Counter(orig))   # (the same contents, dealt out again)
                self.assertTrue(all(c.slots[f][0] == 'chest' for f, x in p['furniture'].items() if x[0] == 'mimic'))
                self.assertFalse([x for x in p['furniture'].values() if x[0] == 'coins'])                                    # (tokens only in a gift or the bestiary)
        self.assertTrue(any(x[0] == 'item' for n in range(30) for k, x in self.gift_slots(c, IT.plan(c, n, IT.SHUFFLED, False)).values() if k != 'gift'))     # (a gold or token gift can receive an item)
        self.assertTrue(any(IT.plan(c, n, IT.SHUFFLED, True)['bestiary'] != ('coins', IT.BESTIARY_COINS) for n in range(30)))

    def test_random(self):
        c = catalog(); seen = collections.Counter()
        for n in range(300):
            p = IT.plan(c, n, IT.RANDOM, True); g = self.gift_slots(c, p); seen['key'] += sum(x[0] == 'item' and x[1] in IT.KEY_ITEMS for x in list(p['furniture'].values()) + [x for _k, x in g.values()])
            self.assertNotIn(6, p['furniture']); self.assertIn(4, p['furniture'])                                         # (an empty chest draws too)
            self.assertEqual(sorted(k for k, _x in g.values()), ['coin gift', 'gold gift'])                                  # (Safety: gold and tokens draw, the item gifts do not)
            for f, x in p['furniture'].items():
                seen[x[0]] += 1
                if x[0] == 'mimic': self.assertEqual(c.slots[f][0], 'chest'); self.assertEqual(x[1:], (72, 165))
                if x[0] == 'item': self.assertIn(x[1], IT.ALL_ITEMS)
                if x[0] == 'gold': self.assertIn(x[1], c.golds)
                self.assertNotEqual(x[0], 'coins')
            for k, x in list(g.values()) + [('bestiary', p['bestiary'])]:
                self.assertNotEqual(x[0], 'mimic'); seen['gift ' + x[0]] += 1
                if x[0] == 'item': self.assertIn(x[1], IT.ALL_ITEMS)
                if x[0] == 'coins': self.assertIn(x[1], c.coins)
        self.assertTrue(all(seen[k] for k in ('item', 'gold', 'mimic', 'empty', 'gift item', 'gift gold', 'gift coins', 'gift empty', 'key')), seen)        # (a key item can be drawn, Safety on)
        self.assertNotIn(IT.MEDAL, IT.DRAWN_ITEMS); self.assertTrue(IT.KEY_ITEMS <= set(IT.DRAWN_ITEMS))

    def test_loot(self):
        self.assertEqual(IT.loot(None, 122, 127, 5), 127); self.assertEqual(IT.loot({'loot': None}, 122, 127, 5), 127)                  # (no plan, drops unchanged)
        free, safe = {'loot': {'number': 9, 'safety': False}}, {'loot': {'number': 9, 'safety': True}}
        self.assertEqual(IT.loot(free, 7, 0, 5), 0)                                                                         # (no drop: none drawn, the game's rate stays)
        self.assertEqual(IT.loot(safe, 122, 127, 5), 127); self.assertEqual(IT.loot(safe, 193, 142, 5), 142)                 # (Safety: Ra's mirror, the silent sphere stay)
        for p in (free, safe):
            got = [IT.loot(p, 30, 12, st) for st in range(400)]
            self.assertTrue(set(got) <= set(IT.DRAWN_ITEMS)); self.assertGreater(len(set(got)), 100)                        # (anything, drawn again at each drop)
            self.assertEqual(got, [IT.loot(p, 30, 12, st) for st in range(400)])                                            # (the same state: the same drop)
        self.assertNotEqual([IT.loot(free, 122, 127, st) for st in range(20)], [127] * 20)

    def test_writes(self):
        self.assertEqual([IT.row_values(x) for x in (('item', 7), ('gold', 30), ('mimic', 72, 165), ('empty',))], [(7, 0, 0, 0), (0, 30, 0, 0), (0, 0, 72, 165), (0, 0, 0, 0)])
        self.assertEqual(IT.gift_command(('item', 9), 2, 16), (IT.OP_ITEM, struct.pack('<3i', 9, 2, 0)))
        self.assertEqual(IT.gift_command(('gold', 40), 1, 16), (IT.OP_GOLD, struct.pack('<2i', 40, 0)))
        self.assertEqual(IT.gift_command(('empty',), 1, 12), (IT.OP_GOLD, struct.pack('<2i', 0, 0)))                        # (nothing: 0 gold)
        self.assertIsNone(IT.gift_command(('item', 9), 1, 12))                                                              # (an item does not fit in a gold gift's 12 bytes)
        self.assertEqual(IT.redirect(('item', 9), b'\x41\x00'), struct.pack('<HBB3i', IT.OP_ITEM, 0x41, 0, 9, 1, 0))        # (the cmd_set_item run instead, with the original's flags)
        self.assertEqual(IT.gift_command(('coins', 500), 1, 12), (IT.OP_COIN, struct.pack('<2i', 500, 0)))                  # (tokens fit in any gift)

    def test_plan_for_code(self):
        fs = types_fs(FILES)
        self.assertIsNone(IT.plan_for_code(None, fs)); self.assertIsNone(IT.plan_for_code('nope', fs)); self.assertIsNone(IT.plan_for_code(SD.new_code(number=3), fs))      # (Items unchanged)
        code = SD.new_code({'safety': 1, 'items': IT.RANDOM}, number=3)
        self.assertEqual(IT.plan_for_code(code, fs), dict(IT.plan(catalog(), 3, IT.RANDOM, False), loot=None)); self.assertIs(IT.plan_for_code(code, fs), IT.plan_for_code(code, fs))
        p = IT.plan_for_code(SD.new_code({'loot': IT.LOOT_RANDOM}, number=4), fs)                                           # (drops only: the containers and gifts untouched)
        self.assertEqual(p, {'furniture': {}, 'gifts': {}, 'bestiary': None, 'loot': {'number': 4, 'safety': True, 'game': 'dq4'}})
        self.assertEqual(IT.plan_for_code(SD.new_code({'safety': 1, 'items': IT.SHUFFLED, 'loot': IT.LOOT_RANDOM}, number=4), fs)['loot'], {'number': 4, 'safety': False, 'game': 'dq4'})


def stage_v2(rows):
    """DQ V / VI map file whose furniture table has `rows`: (kind, item, gold, mimic fight, message, flag)."""
    t = 0x14; data = bytearray(struct.pack('<2I', IT.V2_MAGIC, t)) + bytearray(12) + bytearray(IT.V2_ROW * max(1, len(rows)))
    for i, (kind, item, gold, form, msg, flag) in enumerate(rows):
        o = t + i * IT.V2_ROW; struct.pack_into('<I6H', data, o, msg, 100 + i, item, gold, form, 0, flag); data[o + 0x10] = kind; data[o + 0x11] = i + 1
    data[t + 0x12] = len(rows)
    return bytes(data)


def item_cmd_v2(op, item, count=1, mode=0): return struct.pack('<HBBi3i', op, 1, 0, 0, item, count, mode)
def gold_cmd_v2(op, amount, mode=0): return struct.pack('<HBB2i', op, 1, 0, amount, mode)          # (gold and tokens: from + 4, as in DQ IV)


class DragonQuestVandVI(unittest.TestCase):
    """DQ V / VI: their map files and furniture rows, their item gifts (4 bytes longer), their items; the people's gold and tokens keep their kind, only the amount changes."""
    def files(self, key):
        G = IT.game(key); op_item, op_gold, _op_coin = G['ops']; chest = G['chest']; key_item = min(G['keys'])
        return {'assets/map/a.stg': stage_v2([(0, 0, 0, 0, 0, 0), (chest, 5, 0, 0, 0, 1), (chest, 0, 30, 0, 0, 2), (chest, 0, 0, 178, 0, 3), (chest, 0, 0, 0, 0, 4),
                                              (51, 12, 0, 0, 0, 5), (0, 7, 0, 0, 0, 6), (28, 0, 0, 0, 0x18cd, 7), (chest, key_item, 0, 0, 0, 8)]),
                'assets/script/a.bin': script([item_cmd_v2(op_item, 17), item_cmd_v2(op_item, 17, 1, 1), gold_cmd_v2(op_gold, 50), item_cmd_v2(op_item, key_item)])}

    def test_rows_and_gifts(self):
        for key in ('dq5', 'dq6'):
            f = self.files(key); cat = IT.Catalog(f.__getitem__, list(f), key); chest = IT.game(key)['chest']
            self.assertEqual(IT.furniture_v2(f['assets/map/a.stg'])[3], (3, chest, 0, 0, 178, 178, 0, 3))
            self.assertEqual(cat.slots[1], ('chest', ('item', 5))); self.assertEqual(cat.slots[2], ('chest', ('gold', 30))); self.assertEqual(cat.slots[3], ('chest', ('mimic', 178, 178)))
            self.assertEqual(cat.slots[4], ('chest', ('empty',))); self.assertEqual(cat.slots[5], ('other', ('item', 12)))
            self.assertEqual(cat.slots[6], ('other', ('item', 7)))                                                       # (a twinkling spot of the floor)
            self.assertNotIn(7, cat.slots)                                                                               # (a message: special furniture)
            g = list(cat.gifts.values())[0]
            self.assertEqual(sorted(k for k, _c, _n in g.values()), ['gift', 'gift', 'gold gift'])                       # (the take is left out)
            self.assertEqual(cat.mimics, [(178, 178)]); self.assertEqual(cat.coins, [])

    def test_plans(self):
        for key in ('dq5', 'dq6'):
            f = self.files(key); cat = IT.Catalog(f.__getitem__, list(f), key); G = IT.game(key)
            for mode in (IT.SHUFFLED, IT.RANDOM):
                for safety in (True, False):
                    p = IT.plan(cat, 7, mode, safety)
                    self.assertEqual(p['bestiary'], None)
                    self.assertEqual(8 in p['furniture'], not safety)                                                    # (Safety: the key item stays)
                    for c in p['furniture'].values(): self.assertNotEqual(c[0], 'coins')
                    for g in p['gifts'].values():
                        for content, n, room in g.values():
                            self.assertNotEqual(content[0], 'coins')
                            if room == 12: self.assertEqual(content[0], 'gold')                                          # (a gold gift: gold, another amount)
                            else: self.assertEqual(room, 20)
                    if mode == IT.RANDOM:
                        for c in list(p['furniture'].values()) + [x[0] for g in p['gifts'].values() for x in g.values()]:
                            if c[0] == 'item': self.assertIn(c[1], G['drawn'])

    def test_commands_and_rows(self):
        G = IT.game('dq5')
        self.assertEqual(IT.gift_command(('item', 9), 2, 20, G['ops'], 8), (55, struct.pack('<3i', 9, 2, 0)))
        self.assertEqual(IT.gift_command(('gold', 40), 1, 20, G['ops'], 8), (56, struct.pack('<2i', 40, 0)))
        self.assertEqual(IT.row_values(('mimic', 178, 178), True), (0, 0, 178)); self.assertEqual(IT.row_values(('item', 5), True), (5, 0, 0))
        self.assertEqual(IT.loot({'loot': {'number': 1, 'safety': True, 'game': 'dq5'}}, 3, 193, 5), 193)                # (Safety: Ra's mirror stays)
        self.assertIn(IT.loot({'loot': {'number': 1, 'safety': False, 'game': 'dq6'}}, 3, 12, 5), IT.game('dq6')['drawn'])

    def test_items(self):
        for key, medal in (('dq5', 209), ('dq6', 237)):
            G = IT.game(key); self.assertEqual(G['medal'], medal); self.assertNotIn(medal, G['drawn']); self.assertIn(medal, G['items'])
            self.assertTrue(G['keys'] <= set(G['items'])); self.assertTrue(set(G['drawn']) <= set(G['items']))


class RealFilesV2(unittest.TestCase):
    """(real data, DQ_APK_DQ5 / DQ_APK_DQ6) every container and item gift of their files: the counts read on 17/11."""
    def test_counts(self):
        import zipfile
        for key, slots, gifts in (('dq5', 582, 70), ('dq6', 404, 81)):
            pack = os.path.join(os.environ.get('DQ_APK_' + key.upper(), ''), 'split_UnityDataAssetPack.apk')
            if not os.path.isfile(pack): continue
            z = zipfile.ZipFile(pack); names = [n for n in z.namelist() if n.startswith(('assets/map/', 'assets/script/'))]
            cat = IT.Catalog(z.read, names, key)
            self.assertEqual((len(cat.slots), sum(len(g) for g in cat.gifts.values())), (slots, gifts), key)
            for _k, c in cat.slots.values():
                if c[0] == 'item': self.assertIn(c[1], IT.game(key)['items'], key)


def types_fs(files):
    import types
    class Z:
        def __init__(self, n): self.n = n
        def read(self, n): return files[n]
    return types.SimpleNamespace(names={n: Z(n) for n in files})


@unittest.skipUnless(APK, 'real game files: DQ_APK')
class RealFiles(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        from dq456_pc.core import emu_core as EC
        fs = EC.ApkFs(sorted(glob.glob(os.path.join(APK, '*.apk')))); cls.cat = IT.Catalog.from_fs(fs); RealFiles.read = staticmethod(lambda n: fs.names[n].read(n))

    def test_found(self):
        c = self.cat; kinds = collections.Counter((k, x[0]) for k, x in c.slots.values())
        self.assertGreater(len(c.slots), 400); self.assertGreater(kinds[('chest', 'item')], 130); self.assertEqual(kinds[('chest', 'mimic')], 10); self.assertGreater(kinds[('other', 'gold')], 20)
        self.assertEqual(c.mimics, [(40, 164), (72, 165), (225, 166)])
        self.assertNotIn(201, c.slots)                                                                                      # (the Zenithian sword stuck in the ground: a scene's object, not a container)
        tdf5 = IT.script_id(RealFiles.read('assets/script/tdf5.bin')); self.assertIn(('gift', ('item', 33), 1), c.gifts[tdf5].values())      # (the scene gives it: a gift)
        gifts = collections.Counter(k for g in c.gifts.values() for k, _x, _n in g.values()); self.assertGreater(gifts['gift'], 40); self.assertGreater(gifts['gold gift'], 10); self.assertEqual(gifts['coin gift'], 5)
        self.assertEqual(c.coins, [100, 10000, IT.BESTIARY_COINS])

    def test_plans(self):
        for mode in (IT.SHUFFLED, IT.RANDOM):
            for safety in (True, False):
                p = IT.plan(self.cat, 2024, mode, safety)
                self.assertTrue(all(self.cat.slots[f][0] == 'chest' for f, x in p['furniture'].items() if x[0] == 'mimic'))
                kept = [f for f, (k, x) in self.cat.slots.items() if x[0] == 'item' and x[1] in IT.KEY_ITEMS]
                kinds = {(sid, off): k for sid, g in self.cat.gifts.items() for off, (k, _x, _n) in g.items()}
                given = {kinds[(sid, off)] for sid, g in p['gifts'].items() for off in g}
                if safety: self.assertFalse(set(kept) & set(p['furniture'])); self.assertEqual(given, {'gold gift', 'coin gift'})
                else: self.assertEqual(given, {'gift', 'gold gift', 'coin gift'})
                self.assertIsNotNone(p['bestiary'])


@unittest.skipUnless(APK and SAVES, 'real engine: DQ_APK and DQ_SAVES')
class RealEngine(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        from dq456_pc.core import engine as ENGINE
        cls.E = ENGINE; cls.sv = tempfile.mkdtemp(prefix='rz_items_')
        eng = cls.eng = ENGINE.Engine(APK, SAVES, cls.sv)
        cls.code = None; eng.items_plan = lambda uid: IT.plan_for_code(cls.code, eng.core.fs)
        cls.ok = eng.load_save(1)
        for _ in range(30): eng.step(0, 0)

    def setUp(self):
        if not self.ok: self.skipTest('save 1 not loaded')
        self.assertEqual([m for m in self.eng.missing_hooks if 'randomizer' in m], [])

    def town(self, name, code):
        type(self).code = code; self.eng.forget_items_plan(); self.eng.start_town(name)
        for _ in range(60): self.eng.step(0, 0)
        self.assertEqual(self.eng.state.game_map, name)
        c = self.eng.core; b = struct.unpack('<Q', c.mem(c.export(self.E.STAGE_SINGLETON), 8))[0]
        if not b or struct.unpack('<I', c.mem(b, 4))[0] != IT.FURNITURE_MAGIC: return None, []                                 # (a map without furniture)
        t = b + 4; n = c.mem(t + 0x16, 1)[0]
        return t, [struct.unpack_from('<8H', bytes(c.mem(t + i * IT.ROW, IT.ROW)), 4) + (c.mem(t + i * IT.ROW + 0x14, 1)[0],) for i in range(n)]          # (object, item, gold, formation, monster, message, door, flag, kind)

    def taken(self, flag):
        c = self.eng.core; return bool(c.mem(c.export('_ZN6status7g_StageE') + 0x15a + flag // 8, 1)[0] >> (flag % 8) & 1)

    def coffer(self, obj):
        c = self.eng.core; m = c.export('_ZN20TownFurnitureManager11m_singletonE')
        return c.call(c.export('_ZN20TownFurnitureManager11checkCofferEi'), m, obj, label='checkCoffer') & 0xffffffff

    def test_containers_of_a_map(self):
        code = SD.new_code({'safety': 1, 'items': IT.RANDOM}, number=777); p = IT.plan_for_code(code, self.eng.core.fs)
        orig = {r[7]: r for r in IT.furniture(self.eng.core.fs.open('map/cbf1.stg'))}
        _t, rows = self.town('cbf1', code); checked = 0; open_ = collections.Counter()
        for obj, item, gold, form, mon, msg, _door, flag, kind in rows:
            if flag not in p['furniture'] or not kind or msg: continue
            self.assertEqual((item, gold, form, mon), IT.row_values(p['furniture'][flag]), flag); checked += 1
            want = 1 if self.taken(flag) else {'item': 2, 'gold': 3, 'mimic': 4, 'empty': 1}[p['furniture'][flag][0]]                 # (already taken in this save: 1)
            self.assertEqual(self.coffer(obj), want, flag); open_[want] += 1                                                   # (the game reads the new contents)
        self.assertGreaterEqual(checked, 5); self.assertGreaterEqual(open_[2] + open_[3] + open_[4], 3, open_)                  # (some not taken yet in this save)
        _t, again = self.town('cbf1', code); self.assertEqual(again, rows)                                                      # (the map set up again: the same contents)
        _t, plain = self.town('cbf1', None)                                                                                     # (a game without the randomizer: the map's own contents)
        for obj, item, gold, form, mon, msg, _door, flag, kind in plain:
            if flag in orig: self.assertEqual((item, gold, form, mon), orig[flag][2:6], flag)

    def test_scene_objects_stay(self):
        """The Zenithian sword stuck in the ground (tdf5, kind 41) is left as it is: its scene gives the item (a gift, randomized without Safety); the World Tree's flower (kind 43) is a container."""
        code = SD.new_code({'safety': 1, 'items': IT.RANDOM}, number=4242); p = IT.plan_for_code(code, self.eng.core.fs)
        _t, rows = self.town('tdf5', code); by = {r[7]: r for r in rows}
        self.assertEqual((by[201][8], by[201][1]), (41, 33)); self.assertNotIn(201, p['furniture'])
        self.assertEqual(by[200][1:5], IT.row_values(p['furniture'][200]))

    def test_gifts_of_a_map(self):
        code = SD.new_code({'safety': 1, 'items': IT.SHUFFLED}, number=31337); p = IT.plan_for_code(code, self.eng.core.fs)
        self.town('dpout', code); c = self.eng.core
        S = self.E._adr_target(c, c.export(self.E.SCRIPT_SINGLETON[0]) + self.E.SCRIPT_SINGLETON[1])
        base, = struct.unpack('<Q', c.mem(S + 8, 8)); data = self.eng.core.fs.open('script/dpout.bin')
        gifts = p['gifts'][IT.script_id(data)]; party = c.export('_ZN6status7g_PartyE'); gold = lambda: struct.unpack('<I', c.mem(party + 0x2e0, 4))[0]
        self.assertGreaterEqual(len(gifts), 5)
        for off, (x, count, room) in sorted(gifts.items()):
            w = IT.gift_command(x, count, room)
            if w is None: continue                                                                                              # (a gold gift that gives an item: test_a_gold_gift_gives_an_item)
            g0 = gold(); c.call(c.export(self.E.COMMAND_FN[0]), base + off, label='CommandFunction')
            op, args = w; mem = bytes(c.mem(base + off, 4 + len(args)))
            self.assertEqual((struct.unpack_from('<H', mem)[0], mem[4:]), (op, args), hex(off))
            self.assertEqual(gold() - g0, x[1] if x[0] == 'gold' else 0, hex(off))


    def test_a_gold_gift_gives_an_item(self):
        """A gold gift that must give an item (its 12-byte command has no room for one): the game runs a cmd_set_item of the port instead, the original command stays as it is,
        its flags follow the run (already run: not run again; the script started again: run again), the gold does not change."""
        import unicorn
        c = self.eng.core; data = self.eng.core.fs.open('script/caf1.bin'); sid = IT.script_id(data); off = 0x950
        self.assertEqual(struct.unpack_from('<H', data, off)[0], IT.OP_GOLD); self.assertEqual(struct.unpack_from('<2i', data, off + 4), (100, 0))          # (caf1: a gift of 100 gold)
        code = next(k for k in (SD.new_code({'safety': 1, 'items': IT.RANDOM}, number=n) for n in range(1, 500))
                    if (lambda h: h and h[0][0] == 'item' and h[0][1] != IT.MEDAL)(IT.plan_for_code(k, c.fs)['gifts'].get(sid, {}).get(off)))
        item = IT.plan_for_code(code, c.fs)['gifts'][sid][off][0][1]
        self.town('caf1', code)
        S = self.E._adr_target(c, c.export(self.E.SCRIPT_SINGLETON[0]) + self.E.SCRIPT_SINGLETON[1]); x = struct.unpack('<Q', c.mem(S + 8, 8))[0] + off
        party = c.export('_ZN6status7g_PartyE'); gold = lambda: struct.unpack('<I', c.mem(party + 0x2e0, 4))[0]
        has = lambda i: c.call(c.export('_ZN6status11PartyStatus10isHaveItemEi'), party, i, label='isHaveItem') & 1
        calls = []; at = {c.export('_Z12cmd_set_itemP16CommandParameter'): 'item', c.export('_Z12cmd_set_goldP16CommandParameter'): 'gold'}
        hooks = [c.uc.hook_add(unicorn.UC_HOOK_CODE, lambda uc, a, s_, u: calls.append((at[a], struct.unpack('<i', c.mem(uc.reg_read(c.XREG[0]) + 4, 4))[0])), None, a, a) for a in at]
        try:
            original = bytes(c.mem(x, 12)); self.assertFalse(has(item)); g0 = gold(); run = lambda: c.call(c.export(self.E.COMMAND_FN[0]), x, label='CommandFunction')
            run(); self.assertEqual(calls, [('item', item)]); self.assertTrue(has(item)); self.assertEqual(gold(), g0)
            now = bytes(c.mem(x, 12)); self.assertEqual(now[:2] + now[4:], original[:2] + original[4:]); self.assertTrue(now[2] & 0x40)          # (the original as it was, marked as run)
            run(); self.assertEqual(len(calls), 1)                                                                              # (already run: not again)
            c.mem_w(x + 2, bytes([now[2] & ~0x40])); run(); self.assertEqual(calls, [('item', item)] * 2)                       # (the script started again: run again)
        finally:
            for h in hooks: c.uc.hook_del(h)


    def test_jingle_of_a_special_item(self):
        """An item the game finds with its jingle (item flag + 0x1d bit 4: key items, Zenithian equipment, mini medal...): a gift the plan turns into one plays BGM 48 (with the music
        resumed, as a chest does) after the step, unless the scene's own gift was already such an item; any other item: no jingle."""
        c = self.eng.core; e = self.eng
        self.assertTrue(all(e.special_item(i) for i in (33, 123, 132, 137))); self.assertFalse(any(e.special_item(i) for i in (1, 17, 21)))
        data = c.fs.open('script/caf1.bin'); sid = IT.script_id(data); off = 0x950                                              # (caf1: a gift of 100 gold)
        for special in (True, False):
            code = next(k for k in (SD.new_code({'safety': 1, 'items': IT.RANDOM}, number=n) for n in range(1, 3000))
                        if (lambda h: h and h[0][0] == 'item' and e.special_item(h[0][1]) == special)(IT.plan_for_code(k, c.fs)['gifts'].get(sid, {}).get(off)))
            self.town('caf1', code)
            S = self.E._adr_target(c, c.export(self.E.SCRIPT_SINGLETON[0]) + self.E.SCRIPT_SINGLETON[1]); x = struct.unpack('<Q', c.mem(S + 8, 8))[0] + off
            c.call(c.export(self.E.COMMAND_FN[0]), x, label='CommandFunction'); e.state.sounds = []; e.step(0, 0)
            self.assertEqual((37, 0x1000 | 48) in e.state.sounds, special, (special, e.state.sounds))


    def test_token_gifts_and_the_bestiary(self):
        """Tokens: a token gift of the scripts gives the plan's content (tokens, gold, an item through cmd_set_item, nothing); the bestiary's reward (300 000 tokens, in the game's code)
        gives the plan's tokens at once, or no token and, after the step, the plan's gold, item or mini medal. With Safety too: gold and tokens are not protected."""
        import unicorn
        c = self.eng.core; party = c.export('_ZN6status7g_PartyE'); u32 = lambda a: struct.unpack('<I', c.mem(a, 4))[0]
        coins, gold, medals = (lambda: u32(party + 0x2e8)), (lambda: u32(party + 0x2e0)), (lambda: u32(party + 0x2ec))
        has = lambda i: c.call(c.export('_ZN6status11PartyStatus10isHaveItemEi'), party, i, label='isHaveItem') & 1
        root = c.export('gMaterielMenu_PICTUREBOOK_ROOT'); f = c.export(self.E.BESTIARY_REWARD[0])
        force = c.uc.hook_add(unicorn.UC_HOOK_CODE, lambda uc, a, sz, u: uc.reg_write(c.XREG[0], 210), None, f + 0x2c, f + 0x2c)          # (the 210 monsters met: at its `cmp w0, #0xd2`)
        try:
            for want in ('coins', 'gold', 'item', 'medal', 'empty'):
                code = next(k for k in (SD.new_code({'safety': 0, 'items': IT.RANDOM}, number=n) for n in range(1, 3000))
                            if (lambda b: (b[0] if b[1:2] != (IT.MEDAL,) else 'medal') == want and not (want == 'item' and has(b[1])))(IT.plan_for_code(k, c.fs)['bestiary']))
                content = IT.plan_for_code(code, c.fs)['bestiary']; type(self).code = code; self.eng.forget_items_plan()
                c.call(c.export('_ZN6status11StoryStatus15setCompleteCoinEb'), c.export('_ZN6status7g_StoryE'), 0, label='setCompleteCoin')
                before = (coins(), gold(), medals())
                self.assertEqual(c.call(f, root, label='checkCompletePictureBook') & 1, 1, want)
                self.assertEqual(coins() - before[0], content[1] if want == 'coins' else 0, want)
                self.eng.step(0, 0)                                                                                             # (the rest is given after the step)
                self.assertEqual(gold() - before[1], content[1] if want == 'gold' else 0, want)
                self.assertEqual(medals() - before[2], 1 if want == 'medal' else 0, want)
                if want == 'item': self.assertTrue(has(content[1]))
        finally: c.uc.hook_del(force)
        data = c.fs.open('script/dfb1b.bin'); sid = IT.script_id(data); off = next(p_ for p_, op, _r in IT.script_commands(data) if op == IT.OP_COIN)
        code = next(k for k in (SD.new_code({'safety': 0, 'items': IT.SHUFFLED}, number=n) for n in range(1, 3000)) if IT.plan_for_code(k, c.fs)['gifts'][sid][off][0][0] == 'gold')
        x = IT.plan_for_code(code, c.fs)['gifts'][sid][off][0]; self.town('dfb1b', code)
        S = self.E._adr_target(c, c.export(self.E.SCRIPT_SINGLETON[0]) + self.E.SCRIPT_SINGLETON[1]); base = struct.unpack('<Q', c.mem(S + 8, 8))[0]
        before = (coins(), gold()); c.call(c.export(self.E.COMMAND_FN[0]), base + off, label='CommandFunction')
        self.assertEqual((coins() - before[0], gold() - before[1]), (0, x[1]))                                                  # (100 tokens given as gold instead)

    def test_monster_drops(self):
        """MonsterParty::checkDropItem on a fight's first monster (its slot written, its MonsterData's rate set to "always", then "never"): no randomizer, the game's drop; "Monster drops"
        random, any item, drawn again at each drop; Safety, Ra's mirror stays; no drop, none drawn."""
        c = self.eng.core; mp = c.export('_ZN6status9g_MonsterE'); md, = struct.unpack('<Q', c.mem(c.export('_ZN6status10excelParamE') + 0x80, 8))
        slot = mp + 8; row = lambda m: md + 0x3c * m
        saved = [(a, bytes(c.mem(a, n))) for a, n in ((slot + 0x4f8, 4), (slot + 0x10 + 0x424, 1), (row(122) + 0x1f, 1), (row(30) + 0x10, 2), (row(30) + 0x1f, 1), (mp + self.E.DROP_ITEM, 8))]
        def drop(m, code):
            type(self).code = code; self.eng.forget_items_plan(); self.eng.last_drop = None
            c.mem_w(slot + 0x4f8, struct.pack('<i', m)); c.mem_w(slot + 0x10 + 0x424, bytes([c.mem(slot + 0x10 + 0x424, 1)[0] & ~0x10 & 0xff]))      # (a monster there, not fled)
            c.call(c.export(self.E.DROP_CHECK[0]), mp, 0, label='checkDropItem')
            return struct.unpack('<2i', c.mem(mp + self.E.DROP_ITEM, 8))
        try:
            c.mem_w(row(122) + 0x1f, b'\0'); c.mem_w(row(30) + 0x10, struct.pack('<H', 12)); c.mem_w(row(30) + 0x1f, b'\0')       # (rate 1 in 1: always a drop)
            self.assertEqual(drop(122, None), (127, 122)); self.assertIsNone(self.eng.last_drop)                                     # (no randomizer: Ra's mirror)
            free, safe = SD.new_code({'safety': 1, 'loot': IT.LOOT_RANDOM}, number=8), SD.new_code({'safety': 0, 'loot': IT.LOOT_RANDOM}, number=8)
            got = [drop(122, free) for _ in range(12)]
            self.assertEqual({m for _i, m in got}, {122}); self.assertTrue({i for i, _m in got} <= set(IT.DRAWN_ITEMS)); self.assertGreater(len({i for i, _m in got}), 4)
            self.assertEqual(self.eng.last_drop[:2], (122, 127)); self.assertEqual(self.eng.last_drop[2], got[-1][0])
            self.assertEqual([drop(122, safe) for _ in range(3)], [(127, 122)] * 3)                                                # (Safety: a key item dropped stays)
            self.assertGreater(len({drop(30, safe)[0] for _ in range(12)}), 4)                                                     # (any other drop changes)
            c.mem_w(row(30) + 0x1f, b'\x08')                                                                                         # (rate "never")
            if struct.unpack('<i', c.mem(c.export('_ZN6status7g_StoryE') + 4, 4))[0] != 3: self.assertEqual(drop(30, free), (0, 30)); self.assertIsNone(self.eng.last_drop)     # (no drop: none drawn)
        finally:
            for a, b in saved: c.mem_w(a, b)

if __name__ == '__main__':
    unittest.main()
