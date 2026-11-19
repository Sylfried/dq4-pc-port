"""Test of the battle results capture (dq456_pc/battle_history.py): defeated enemies, gold, experience.

Three levels:
- pure computation (Tracking, plate names, build_battle): no engine;
- glue (BattleSensor) on a FAKE engine (simulated memory and emulator: the hooks are triggered by hand): start / deaths / victory / end, breaks, abandonments, errors;
- OPTIONAL REAL engine: DQ_APK=<patched APKs folder> DQ_SAVES=<saves folder> (save 1: Ragnar and Doc in a town). Battles are forced in a throwaway engine (the encounter composition
  is written to Encount when BattleRoot::setupMonster is about to read it; Global::startBattle starts the battle); each dict is compared with the game TEXT ("reçoit N points d'expérience",
  "N pièces d'or") and with the party counters in memory (gold before / after, each member's experience before / after).

    python3 tests/test_battle_history.py
    DQ_APK=... DQ_SAVES=... python3 tests/test_battle_history.py        (about a minute)
"""
import os, re, struct, sys, tempfile, unittest

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, '..'))
sys.path.insert(0, HERE)
import _saves as SV
from dq456_pc import language as LG
LG.select_language('fr')          # (the expectations of this test are in French, whatever the language of the computer)
from dq456_pc.battle import battle_history as HC


# ---------------------------------------------------------------------------------------------------------------------------------- pure computation
class Plates(unittest.TestCase):
    def test_plate_name(self):
        self.assertEqual(HC.plate_name('Rat volant'), 'Rat volant')
        self.assertEqual(HC.plate_name('Gluant\n\n\t×3'), 'Gluant')
        self.assertEqual(HC.plate_name('  Chauve-sourat \r\n'), 'Chauve-sourat')
        for v in ('', '\n\t', None, 3, b'x'): self.assertIsNone(HC.plate_name(v), repr(v))

    def test_name_on_two_lines(self):
        """Long names are split over two lines by the game (the ";" and "$" in the texts): the full name is returned, the monster count (line starting with a tab) removed."""
        for raw_value, name_str in (('Armure \n\nerrante', 'Armure errante'), ('Gluant de \n\nmercure\n\n\t×2', 'Gluant de mercure'), ('Scara-\n\nsomniaque', 'Scara-somniaque'),
                          ('Typhon-\n\nphonphon\n\n\t×3', 'Typhon-phonphon'), ("Rejeton de \n\nl'enfer", "Rejeton de l'enfer"), ('Gluant\n\n×3', 'Gluant'), ('Gluant\n\n\t×3\n\n', 'Gluant')):
            self.assertEqual(HC.plate_name(raw_value), name_str, repr(raw_value))

    def test_names_in_group_order(self):
        groups = [(0, 3), (0, 3), (1, 20), (2, 0), (2, 0), (2, 0), (3, 5)]
        self.assertEqual(HC.group_names(groups, ['Londuleux\n\n\t×2', 'Rat volant', 'Gluant\n\n\t×3', 'Chauve-sourat']), {3: 'Londuleux', 20: 'Rat volant', 0: 'Gluant', 5: 'Chauve-sourat'})
        self.assertEqual(HC.group_names([(1, 7), (4, 9)], ['A', 'B']), {7: 'A', 9: 'B'})                       # (the group numbers are not necessarily 0, 1, 2...)

    def test_no_match_no_name(self):
        self.assertEqual(HC.group_names([(0, 3), (1, 20)], ['Londuleux']), {})                                  # fewer plates than groups
        self.assertEqual(HC.group_names([(0, 3)], ['Londuleux', 'Rat volant']), {})                              # more plates than groups
        self.assertEqual(HC.group_names([(0, 3), (1, 20)], ['Londuleux', None]), {})                             # a plate without a name
        self.assertEqual(HC.group_names([], []), {})


class PureTracking(unittest.TestCase):
    def test_one_monster_per_occupied_slot(self):
        s = HC.Tracking(); s.see([(0, 3), (1, 3), (2, 20)]); s.see([(0, 3), (1, 3), (2, 20)])
        self.assertEqual([m['num'] for m in s.monsters], [3, 3, 20])                                                  # reviewed at each frame: not recounted
        self.assertEqual(s.present_count(), 3)

    def test_appearance_order_and_grouping(self):
        s = HC.Tracking(); s.assign_names({3: 'Londuleux', 20: 'Rat volant'}); s.see([(0, 20), (1, 3), (2, 20)]); s.dead(1, 3); s.dead(0, 20)
        self.assertEqual(s.enemies(), [{'name': 'Rat volant', 'total': 2, 'defeated': 1, 'fled': 0, 'vanished': 0}, {'name': 'Londuleux', 'total': 1, 'defeated': 1, 'fled': 0, 'vanished': 0}])

    def test_slot_released_then_reoccupied_is_reinforcement(self):
        s = HC.Tracking(); s.assign_names({0: 'Gluant', 9: 'Roi des gluants'}); s.see([(0, 0), (1, 0)]); s.dead(0, 0)
        s.see([(0, 0), (1, 0)])                                                                                      # the defeated monster stays in its slot until the cleanup
        s.see([(1, 0)])                                                                                              # cleaned up
        s.see([(0, 9), (1, 0)])                                                                                      # a reinforcement arrives in the free slot
        self.assertEqual(s.enemies(), [{'name': 'Gluant', 'total': 2, 'defeated': 1, 'fled': 0, 'vanished': 0}, {'name': 'Roi des gluants', 'total': 1, 'defeated': 0, 'fled': 0, 'vanished': 0}])

    def test_number_change_in_slot(self):
        s = HC.Tracking(); s.see([(0, 0)]); s.see([(0, 5)])                                                            # transformation / replacement between two readings: new monster
        self.assertEqual([m['num'] for m in s.monsters], [0, 5])

    def test_death_of_never_seen_monster(self):
        s = HC.Tracking(); s.dead(4, 7)
        self.assertEqual(s.enemies(), [{'name': LG.tr(HC.UNKNOWN_NAME), 'total': 1, 'defeated': 1, 'fled': 0, 'vanished': 0}]); self.assertEqual(s.deaths, 1)

    def test_several_deaths_in_same_frame(self):
        s = HC.Tracking(); s.see([(0, 0), (1, 0), (2, 0)]); s.dead(0, 0); s.dead(1, 0); s.dead(2, 0)
        self.assertEqual(s.enemies(), [{'name': LG.tr(HC.UNKNOWN_NAME), 'total': 3, 'defeated': 3, 'fled': 0, 'vanished': 0}]); self.assertEqual(s.outcome(), 'victory')

    def test_unknown_names_distinct_numbers(self):
        s = HC.Tracking(); s.see([(0, 1), (1, 2)])
        self.assertEqual([e['name'] for e in s.enemies()], [LG.tr(HC.UNKNOWN_NAME), LG.tr(HC.UNKNOWN_NAME)])                          # two unnamed species: two entries, never merged
        s.assign_names({1: 'A', 2: 'A'}); self.assertEqual(s.enemies(), [{'name': 'A', 'total': 2, 'defeated': 0, 'fled': 0, 'vanished': 0}])           # same name = same species for the player

    def test_an_already_known_name_is_not_changed(self):
        s = HC.Tracking(); s.assign_names({1: 'Gluant'}); s.assign_names({1: 'Autre'}); self.assertEqual(s.names[1], 'Gluant')

    def test_counters_keep_largest_reading(self):
        s = HC.Tracking(); s.counters(3, 7); s.counters(6, 13); s.counters(0, 0); s.counters(5, 10)
        self.assertEqual((s.xp, s.gold), (6, 13))

    def test_outcomes(self):
        s = HC.Tracking(); s.see([(0, 1), (1, 1)]); s.dead(0, 1)
        self.assertEqual(s.outcome(), 'escape')                                                                          # one defeated monster out of two, no victory routine: gone
        s.escape_attempts = 3; self.assertEqual(s.outcome(), 'escape')
        self.assertEqual(s.outcome(defeat=True), 'defeat')
        s.victory = True; self.assertEqual(s.outcome(defeat=True), 'victory')                                         # the victory routine wins over a defeat flag left over from a previous battle
        s2 = HC.Tracking(); s2.see([(0, 1)]); s2.dead(0, 1); self.assertEqual(s2.outcome(), 'victory')                    # all defeated, even without the routine
        self.assertEqual(HC.Tracking().outcome(), 'escape')                                                                  # nothing seen, nothing defeated: the group is gone

    def test_gold_and_experience_only_for_victory(self):
        for defeat, won in ((False, True), (True, False)):
            s = HC.Tracking(); s.see([(0, 1), (1, 1)]); s.dead(0, 1); s.counters(5, 9)
            if won: s.dead(1, 1)
            d = HC.build_battle(s, 1234, defeat=defeat)
            self.assertEqual((d['gold'], d['xp']), (9, 5) if won else (0, 0)); self.assertEqual(d['outcome'], 'victory' if won else 'defeat')
        s = HC.Tracking(); s.see([(0, 1), (1, 1)]); s.dead(0, 1); s.counters(5, 9); d = HC.build_battle(s, 1)
        self.assertEqual((d['outcome'], d['gold'], d['xp']), ('escape', 0, 0))                                              # fleeing after a death: neither gold nor experience (the engine does not pay them out)

    def test_dict_shape(self):
        s = HC.Tracking(); s.assign_names({0: 'Gluant'}); s.see([(0, 0)]); s.dead(0, 0); s.counters(2, 3)
        d = HC.build_battle(s, 12345)
        self.assertEqual(d, {'t': 12345, 'enemies': [{'name': 'Gluant', 'total': 1, 'defeated': 1, 'fled': 0, 'vanished': 0}], 'gold': 3, 'xp': 2, 'outcome': 'victory', 'objects': []})
        self.assertEqual(sorted(d), ['enemies', 'gold', 'objects', 'outcome', 't', 'xp']); self.assertIn(d['outcome'], HC.OUTCOMES)
        for e in d['enemies']: self.assertEqual(sorted(e), ['defeated', 'fled', 'name', 'total', 'vanished'])
        self.assertTrue(all(type(v) is int for v in (d['t'], d['gold'], d['xp'])))

    def test_fled_and_vanished_monsters(self):
        """each monster has ONE fate (defeated, fled or vanished); anything with no fate is still there at the end."""
        s = HC.Tracking(); s.assign_names({0: 'Gluant', 5: 'Golem'}); s.see([(0, 0), (1, 0), (2, 0), (3, 5)]); s.dead(0, 0); s.fled(1, 0); s.vanished(2, 0)
        self.assertEqual(s.enemies(), [{'name': 'Gluant', 'total': 3, 'defeated': 1, 'fled': 1, 'vanished': 1}, {'name': 'Golem', 'total': 1, 'defeated': 0, 'fled': 0, 'vanished': 0}])
        self.assertEqual(s.deaths, 1)                                                                                  # (only the dead count as "dead": neither a flight nor a disappearance)

    def test_a_fled_monster_is_not_a_victory(self):
        s = HC.Tracking(); s.see([(0, 0), (1, 0)]); s.dead(0, 0); s.fled(1, 0)
        self.assertEqual(s.outcome(), 'victory')                                                                       # (no monster left: all defeated or gone, at least one defeated)
        s = HC.Tracking(); s.see([(0, 0), (1, 0)]); s.dead(0, 0)
        self.assertEqual(s.outcome(), 'escape')                                                                          # one monster remains: the group is gone
        s.victory = True; self.assertEqual(s.outcome(), 'victory')                                                    # (the victory routine of the game has the last word)

    def test_spell_of_a_monster_never_seen_or_already_decided(self):
        s = HC.Tracking(); s.fled(4, 7); s.vanished(5, 7)
        self.assertEqual(s.enemies(), [{'name': LG.tr(HC.UNKNOWN_NAME), 'total': 2, 'defeated': 0, 'fled': 1, 'vanished': 1}])
        s = HC.Tracking(); s.see([(0, 3)]); s.fled(0, 3); s.fled(0, 3)                                               # same slot, spell already noted: another monster
        self.assertEqual(s.enemies(), [{'name': LG.tr(HC.UNKNOWN_NAME), 'total': 2, 'defeated': 0, 'fled': 2, 'vanished': 0}])

    def test_won_items(self):
        s = HC.Tracking(); s.assign_names({0: 'Gluant'}); s.see([(0, 0)]); s.dead(0, 0); s.counters(2, 3)
        s.item(12, 'herbe médicinale'); s.item(40, 'pierre de vie')
        d = HC.build_battle(s, 1)
        self.assertEqual(d['objects'], [{'name': 'herbe médicinale'}, {'name': 'pierre de vie'}])
        s2 = HC.Tracking(); s2.see([(0, 0), (1, 0)]); s2.dead(0, 0); s2.item(12, 'x')
        self.assertEqual(HC.build_battle(s2, 1)['objects'], [])                                                    # no victory: no items brought back


# ---------------------------------------------------------------------------------------------------------------------------------- glued onto a fake engine
LIB = 0x10000000
A_PARTY, A_MONSTER, A_GAME, A_RESULT = 0x1000, 0x2000, 0x1f000, 0x1e000
FUNCTION_NAMES = {'_ZN6status15BasePartyStatus12getBattleExpEv': 0x30000, '_ZN6status15BasePartyStatus13getBattleGoldEv': 0x30010, '_ZN6status13MonsterStatus8isEnableEv': 0x30020,
                  '_ZN6status11PartyStatus11startBattleEv': 0x30100, '_ZN19BattleActorManager216execMonsterDeathEi': 0x30110, '_ZN23BattleExecDefeatMonster10initializeEv': 0x30120,
                  '_ZN16BattleExecEscape5setupEv': 0x30130, '_ZN6Global9endBattleEb': 0x30140,
                  HC.SYM_DEATH_CHECK: 0x30200, HC.SYM_ITEM_WON: 0x30300, HC.SYM_ITEM_NAME: 0x30400}
A_TASK = 0x31000                                                                                                    # the task BattleExecVictory32: the item number at +0xc
INTERNAL = {evt: (FUNCTION_NAMES[name_str] + off, word) for evt, name_str, off, word in HC.INTERNAL_HOOKS}                  # event -> (hook address, expected instruction)
ITEM_NAMES = {12: 'herbe ;médicinale', 40: 'pierre de vie', 7: '<ERR 0x04000000.7>'}                                # what TextAPI::extractText answers
MONSTER_NAMES = {0: 'gluant', 3: 'londuleux', 34: 'armure ;errante', 74: 'scara$somniaque', 5: 'chauve-sourat'}


def ldr_w(offset, rt=0): return 0xb9400000 | ((offset // 4) << 10) | rt                                        # ldr wRt, [x0, #offset]


class FakeUC:
    def __init__(self): self.hooks = {}; self.regs = {}
    def hook_add(self, typ, cb, ud, begin, end): self.hooks.setdefault(begin, []).append(cb)
    def reg_read(self, r): return self.regs.get(r, 0)
    def ctl_flush_tb(self): pass


class FakeCore:
    XREG = list(range(100, 131))
    def __init__(self, bad_version=False, fake_internal_word=None):
        self.ram = bytearray(0x40000); self.uc = FakeUC(); self.reads = 0; self.calls = []
        for name_str, a in FUNCTION_NAMES.items(): self.ram[a:a + 4] = struct.pack('<I', 0xd65f03c0)
        for evt, (a, word) in INTERNAL.items(): self.ram[a:a + 4] = struct.pack('<I', word ^ 1 if evt == fake_internal_word else word)
        off = {'_ZN6status15BasePartyStatus12getBattleExpEv': HC.OFF_XP, '_ZN6status15BasePartyStatus13getBattleGoldEv': HC.OFF_GOLD, '_ZN6status13MonsterStatus8isEnableEv': HC.OFF_NUMBER}
        for name_str, o in off.items(): self.ram[FUNCTION_NAMES[name_str]:FUNCTION_NAMES[name_str] + 4] = struct.pack('<I', ldr_w(o + (4 if bad_version else 0)))
        self.symbols = dict(FUNCTION_NAMES); self.symbols.update({'_ZN6status7g_PartyE': A_PARTY, '_ZN6status9g_MonsterE': A_MONSTER, '_ZN6status6g_GameE': A_GAME, '_ZN6status14g_BattleResultE': A_RESULT})
        for e in range(HC.SLOT_COUNT): self.drain(e)
    def export(self, name_str): return self.symbols.get(name_str)
    def mem(self, a, n): self.reads += 1; return bytes(self.ram[a:a + n])
    def write(self, a, fmt, *v): self.ram[a:a + struct.calcsize(fmt)] = struct.pack(fmt, *v)
    def place(self, e, num, group=0): self.write(A_MONSTER + HC.MONSTERS_START + e * HC.MONSTER_STEP + HC.OFF_NUMBER, '<2I', num, group)
    def drain(self, e): self.place(e, 0xffffffff, 0)
    def trigger(self, name_str, *args):
        for i, v in enumerate(args): self.uc.regs[self.XREG[i + 1]] = v
        for cb in self.uc.hooks[TRIGGERS[name_str]]: cb(self.uc, 0, 4, None)
    def trigger_internal(self, evt, **regs):
        """Hook in the middle of an engine function: regs = {'x20': value, 'x0': value}."""
        for r, v in regs.items(): self.uc.regs[self.XREG[int(r[1:])]] = v
        for cb in self.uc.hooks[INTERNAL[evt][0]]: cb(self.uc, 0, 4, None)
    def fled(self, i): self.trigger_internal('monster_fled', x20=i)
    def vanished(self, i): self.trigger_internal('monster_vanished', x20=i)
    def item(self, number, placement=0):
        """placement: what giveItem returned (member index, or -1: in the bag)."""
        self.write(A_TASK + HC.OFF_TASK_ITEM, '<I', number); self.trigger_internal('item', x20=A_TASK, x0=placement & 0xffffffff)
    # -- the call of an engine function (HC.BattleSensor._item_name: TextAPI::extractText)
    def malloc(self, n): return 0x3f000
    def scratch(self, name_str, n): return self.malloc(n)          # (Core.scratch keeps the buffer; one is enough here)
    def mem_w(self, a, b): self.ram[a:a + len(b)] = b
    def read_cstr(self, a, limit=1 << 20):
        end = self.ram.index(0, a); return bytes(self.ram[a:end])
    def call(self, f, *args, label=''):
        self.calls.append((f, args)); buf, arg = args; num = arg & 0xffffff; assert f == FUNCTION_NAMES[HC.SYM_ITEM_NAME]
        if arg & 0xf000000 == HC.KIND_MONSTER: name_str = MONSTER_NAMES.get(num, '<ERR 0x06000000.%d>' % num)
        else: assert arg & 0xf000000 == HC.KIND_ITEM; name_str = ITEM_NAMES.get(num, '<ERR 0x04000000.%d>' % num)
        self.mem_w(buf, name_str.encode('utf-8') + b'\0'); return buf


TRIGGERS = {'start': 0x30100, 'death': 0x30110, 'victory': 0x30120, 'escape': 0x30130, 'end': 0x30140}


class FakeState:
    def __init__(self): self.part = 0xc


class FakeUI:
    def __init__(self): self.f = {}


class FakeEngine:
    def __init__(self, bad_version=False, fake_internal_word=None):
        self.core = FakeCore(bad_version, fake_internal_word); self.state = FakeState(); self.frames = 100; self.ui = FakeUI()
    def step(self, sensor, n=1):
        outputs = []
        for _ in range(n): self.frames += 1; outputs.extend(sensor.do_update(self))
        return outputs
    def plates(self, names, port=15, layout=None):
        """Like Interface.apply: new dicts at each refresh."""
        self.ui.f[port] = {'type': 31, 'layout': len(names) if layout is None else layout, 'plates': {i: {'code': 2, 'name': n, 'params': [0, 0]} for i, n in enumerate(names)}}


def simple_battle(m, c, names=('Rat volant', 'Londuleux'), nums=(20, 3)):
    """Start, two monsters, plates, two deaths, victory, end; -> the returned dicts."""
    m.state.part = HC.PART_BATTLE; m.core.trigger('start'); m.core.place(0, nums[0], 0); m.core.place(1, nums[1], 1)
    outputs = m.step(c, 3); m.plates(list(names)); outputs += m.step(c, 3)
    m.core.trigger('death', 0); m.core.trigger('death', 1)
    m.core.write(A_PARTY + HC.OFF_XP, '<2I', 6, 13); outputs += m.step(c, 2)
    m.core.trigger('victory'); m.core.write(A_PARTY + HC.OFF_XP, '<2I', 6, 13); outputs += m.step(c, 2)
    m.core.write(A_PARTY + HC.OFF_XP, '<2I', 0, 0); m.core.write(A_GAME + 4, '<I', 5555)
    m.core.trigger('end', 0); outputs += m.step(c, 1)
    return outputs


class Glue(unittest.TestCase):
    def setUp(self): self.m = FakeEngine(); self.c = HC.BattleSensor(self.m)

    def test_hooks_installed(self):
        self.assertTrue(self.c.active)
        self.assertEqual(sorted(self.m.core.uc.hooks), sorted([FUNCTION_NAMES[n] for _e, n in HC.HOOKS] + [a for a, _m in INTERNAL.values()]))

    def test_unexpected_internal_hook_only_that_event_lost(self):
        """A different instruction at the hook location (other engine): no hook is placed at random; the rest of the capture works."""
        m = FakeEngine(fake_internal_word='monster_fled'); c = HC.BattleSensor(m)
        self.assertTrue(c.active); self.assertNotIn(INTERNAL['monster_fled'][0], m.core.uc.hooks); self.assertIn(INTERNAL['monster_vanished'][0], m.core.uc.hooks)
        self.assertEqual(len(simple_battle(m, c)), 1)

    def complete_scenario(self, objects=((12, 0), (40, -1)), fled=1, vanished=2, victory=True):
        """3 Gluants and 1 Golem: the 1st Gluant dies, another flees, the last one vanishes, the Golem dies; then victory (gold 13, experience 6), the items, the end."""
        m, c = self.m, self.c; m.state.part = HC.PART_BATTLE; m.core.trigger('start')
        for e, (num, grp) in enumerate(((0, 0), (0, 0), (0, 0), (5, 1))): m.core.place(e, num, grp)
        outputs = m.step(c, 3); m.plates(['Gluant\n\n\t×3', 'Golem']); outputs += m.step(c, 3)
        m.core.trigger('death', 0); outputs += m.step(c, 1)
        if fled is not None: m.core.fled(fled)
        if vanished is not None: m.core.vanished(vanished)
        outputs += m.step(c, 1); m.core.trigger('death', 3); m.core.write(A_PARTY + HC.OFF_XP, '<2I', 6, 13); outputs += m.step(c, 2)
        if victory: m.core.trigger('victory')
        for number, placement in objects: m.core.item(number, placement)
        outputs += m.step(c, 2); m.core.write(A_PARTY + HC.OFF_XP, '<2I', 0, 0); m.core.write(A_GAME + 4, '<I', 7777)
        m.core.trigger('end', 0); return outputs + m.step(c, 1)

    def test_fled_vanished_monsters_and_items(self):
        """who died, fled or vanished (by species), the gold and experience, the items (the name is requested from the engine, the ";" is removed; whether they go to a member or into the bag)."""
        outputs = self.complete_scenario(); self.assertEqual(len(outputs), 1); d = outputs[0]
        self.assertEqual(d['enemies'], [{'name': 'Gluant', 'total': 3, 'defeated': 1, 'fled': 1, 'vanished': 1}, {'name': 'Golem', 'total': 1, 'defeated': 1, 'fled': 0, 'vanished': 0}])
        self.assertEqual((d['outcome'], d['gold'], d['xp'], d['t']), ('victory', 13, 6, 7777))
        self.assertEqual(d['objects'], [{'name': 'herbe médicinale'}, {'name': 'pierre de vie'}])

    def test_item_name_requested_once_and_fallback_name(self):
        self.complete_scenario(objects=((12, 0), (12, 1), (7, -1), (99, 0)))
        self.assertEqual(len(self.m.core.calls), 3)                                                                   # 12, 7 and 99: one call per different item (the name is kept)

    def test_items_and_fallback_names_in_dict(self):
        d = self.complete_scenario(objects=((7, 0), (99, -1)))[0]
        self.assertEqual([o['name'] for o in d['objects']], ['Objet n°7', 'Objet n°99'])                                 # ("<ERR ... >" is never shown)

    def test_victory_without_item(self):
        d = self.complete_scenario(objects=(), victory=True)[0]; self.assertEqual(d['objects'], [])

    def test_name_requested_from_engine_without_plate(self):
        """Surprise attack (no plate): the name comes from the engine by monster number, capitalized; with no answer from the engine: "Monster"."""
        m, c = self.m, self.c; m.state.part = HC.PART_BATTLE; m.core.trigger('start')
        for e, num in enumerate((3, 34, 74, 99, 3)): m.core.place(e, num, e)
        m.step(c, 4)
        for e in range(5): m.core.trigger('death', e)
        m.core.trigger('victory'); m.core.trigger('end', 0); d, = m.step(c, 1)
        self.assertEqual([(e['name'], e['total']) for e in d['enemies']], [('Londuleux', 2), ('Armure errante', 1), ('Scara$somniaque', 1), (LG.tr(HC.UNKNOWN_NAME), 1)])          # (the "$" stays, never drawn)
        self.assertEqual(len(m.core.calls), 4)                                                                       # (one call per different monster number)

    def test_plates_prevail_over_engine_name(self):
        m, c = self.m, self.c; simple_battle(m, c); self.assertEqual(m.core.calls, [])                              # the two names come from the plates: the engine is not queried

    def test_fleeing_group_remaining_monsters_are_counted(self):
        """The party flees: the monster that had fled is recorded, those that remain have no fate."""
        m, c = self.m, self.c; m.state.part = HC.PART_BATTLE; m.core.trigger('start'); m.core.place(0, 3, 0); m.core.place(1, 3, 0); m.core.place(2, 3, 0)
        m.step(c, 3); m.plates(['Golem\n\n\t×3']); m.step(c, 3); m.core.fled(0); m.step(c, 1); m.core.trigger('escape'); m.core.trigger('end', 0)
        d, = m.step(c, 1)
        self.assertEqual((d['outcome'], d['objects'], d['gold'], d['xp']), ('escape', [], 0, 0))
        self.assertEqual(d['enemies'], [{'name': 'Golem', 'total': 3, 'defeated': 0, 'fled': 1, 'vanished': 0}])

    def test_for_single_sensor_per_engine(self):
        """BattleSensor.for_(eng): the single integration line; the hooks are installed only once."""
        m = FakeEngine(); a = HC.BattleSensor.for_(m); b = HC.BattleSensor.for_(m)
        self.assertIs(a, b); self.assertTrue(a.active)
        self.assertTrue(all(len(v) == 1 for v in m.core.uc.hooks.values()))
        for _ in range(3): self.assertEqual(HC.BattleSensor.for_(m).do_update(m), [])
        self.assertIsNot(HC.BattleSensor.for_(FakeEngine()), a)

    def test_for_engine_that_refuses_attribute(self):
        class Closed(FakeEngine):
            def __setattr__(self, name_str, value):
                if name_str == '_capteur_combat': raise AttributeError(name_str)
                object.__setattr__(self, name_str, value)
        m = Closed(); a = HC.BattleSensor.for_(m); self.assertIs(HC.BattleSensor.for_(m), a)
        self.assertTrue(all(len(v) == 1 for v in m.core.uc.hooks.values()))

    def test_unexpected_engine_capture_disabled(self):
        m = FakeEngine(bad_version=True); c = HC.BattleSensor(m)
        self.assertFalse(c.active); self.assertEqual(m.core.uc.hooks, {}); self.assertEqual(m.step(c, 3), [])

    def test_missing_hook_capture_disabled(self):
        m = FakeEngine(); del m.core.symbols['_ZN6Global9endBattleEb']; c = HC.BattleSensor(m)
        self.assertFalse(c.active); self.assertEqual(m.core.uc.hooks, {})                                          # (no half-installed hook)

    def test_complete_victory(self):
        outputs = simple_battle(self.m, self.c)
        self.assertEqual(outputs, [{'t': 5555, 'enemies': [{'name': 'Rat volant', 'total': 1, 'defeated': 1, 'fled': 0, 'vanished': 0}, {'name': 'Londuleux', 'total': 1, 'defeated': 1, 'fled': 0, 'vanished': 0}], 'gold': 13, 'xp': 6, 'outcome': 'victory', 'objects': []}])
        self.assertIsNone(self.c.tracking)

    def test_two_consecutive_battles(self):
        a = simple_battle(self.m, self.c); self.m.state.part = 0xc; self.m.core.drain(0); self.m.core.drain(1); self.m.step(self.c, 5)
        b = simple_battle(self.m, self.c, ('Gluant', 'Chauve-sourat'), (0, 5))
        self.assertEqual([[e['name'] for e in d['enemies']] for d in a + b], [['Rat volant', 'Londuleux'], ['Gluant', 'Chauve-sourat']])

    def test_death_index_among_present_monsters(self):
        """execMonsterDeath(i): i counts the OCCUPIED slots (getMonsterStatus), not the slots."""
        m, c = self.m, self.c; m.state.part = HC.PART_BATTLE; m.core.trigger('start'); m.core.place(2, 3, 0); m.core.place(5, 20, 1); m.core.place(9, 20, 1); m.step(c, 2)
        m.core.trigger('death', 1); m.step(c)                                                                         # the 2nd monster present = slot 5
        self.assertEqual([(eng['num'], eng['defeated']) for eng in c.tracking.monsters], [(3, False), (20, True), (20, False)])

    def test_previous_battle_plates_ignored(self):
        m, c = self.m, self.c; m.plates(['Vieux', 'Nom']); m.state.part = HC.PART_BATTLE; m.core.trigger('start'); m.core.place(0, 20, 0); m.core.place(1, 3, 1); m.step(c, 5)
        self.assertEqual(c.tracking.names, {})                                                                             # plates from before the start: never read
        m.plates(['Rat volant', 'Londuleux']); m.step(c); self.assertEqual(c.tracking.names, {20: 'Rat volant', 3: 'Londuleux'})

    def test_late_plates(self):
        m, c = self.m, self.c; m.state.part = HC.PART_BATTLE; m.core.trigger('start'); m.core.place(0, 20, 0); m.step(c, 5); self.assertEqual(c.tracking.names, {})
        m.plates(['Rat volant']); m.step(c); self.assertEqual(c.tracking.names, {20: 'Rat volant'})

    def test_no_plate_generic_name(self):
        m, c = self.m, self.c; m.state.part = HC.PART_BATTLE; m.core.trigger('start'); m.core.place(0, 20, 0); m.step(c, 3); m.core.trigger('death', 0)
        m.core.trigger('victory'); m.core.trigger('end', 0); d, = m.step(c)
        self.assertEqual(d['enemies'], [{'name': LG.tr(HC.UNKNOWN_NAME), 'total': 1, 'defeated': 1, 'fled': 0, 'vanished': 0}])

    def test_plates_after_a_death_ignored(self):
        m, c = self.m, self.c; m.state.part = HC.PART_BATTLE; m.core.trigger('start'); m.core.place(0, 20, 0); m.core.place(1, 3, 1); m.step(c, 3); m.core.trigger('death', 0); m.step(c)
        m.plates(['Londuleux']); m.step(c, 3); self.assertEqual(c.tracking.names, {})                                      # a group has gone: the matches are no longer sure

    def test_defeat(self):
        m, c = self.m, self.c; m.state.part = HC.PART_BATTLE; m.core.trigger('start'); m.core.place(0, 20, 0); m.step(c, 3); m.core.write(A_PARTY + HC.OFF_XP, '<2I', 3, 7); m.step(c)
        m.core.trigger('end', 1); d, = m.step(c)
        self.assertEqual((d['outcome'], d['gold'], d['xp']), ('defeat', 0, 0)); self.assertEqual(d['enemies'], [{'name': LG.tr(HC.UNKNOWN_NAME), 'total': 1, 'defeated': 0, 'fled': 0, 'vanished': 0}])

    def test_defeat_reported_by_result_flag(self):
        m, c = self.m, self.c; m.state.part = HC.PART_BATTLE; m.core.trigger('start'); m.core.place(0, 20, 0); m.step(c, 3)
        m.core.ram[A_RESULT + HC.OFF_DEFEAT] = 1; m.core.trigger('end', 0); d, = m.step(c)                              # defeat in a scenario battle: endBattle(false) but "lost" flag
        self.assertEqual(d['outcome'], 'defeat')

    def test_escape(self):
        m, c = self.m, self.c; m.state.part = HC.PART_BATTLE; m.core.trigger('start'); m.core.place(0, 20, 0); m.core.place(1, 20, 0); m.step(c, 3)
        m.core.trigger('death', 0); m.core.write(A_PARTY + HC.OFF_XP, '<2I', 3, 7); m.step(c, 2); m.core.trigger('escape'); m.step(c); m.core.trigger('escape'); m.core.trigger('end', 0); d, = m.step(c)
        self.assertEqual((d['outcome'], d['gold'], d['xp']), ('escape', 0, 0)); self.assertEqual(d['enemies'], [{'name': LG.tr(HC.UNKNOWN_NAME), 'total': 2, 'defeated': 1, 'fled': 0, 'vanished': 0}])

    def test_reinforcement_during_battle(self):
        m, c = self.m, self.c; m.state.part = HC.PART_BATTLE; m.core.trigger('start'); m.core.place(0, 20, 0); m.step(c, 3); m.core.place(1, 20, 0); m.step(c, 2)
        self.assertEqual([eng['num'] for eng in c.tracking.monsters], [20, 20])

    def test_outside_battle_nothing_to_do(self):
        m, c = self.m, self.c; m.step(c, 5); n = m.core.reads
        self.assertEqual(m.step(c, 1000), []); self.assertEqual(m.core.reads, n)                                    # no memory read outside battle

    def test_end_without_start_ignored(self):
        m, c = self.m, self.c; m.state.part = HC.PART_BATTLE; m.core.place(0, 20, 0); m.step(c, 3)
        m.core.trigger('death', 0); m.core.trigger('victory'); m.core.trigger('end', 0); self.assertEqual(m.step(c, 2), [])                  # sensor created in the middle of a battle: nothing false

    def test_savestate_loaded_in_battle(self):
        m, c = self.m, self.c; m.state.part = HC.PART_BATTLE; m.core.trigger('start'); m.core.place(0, 20, 0); m.step(c, 3); self.assertIsNotNone(c.tracking)
        m.state = FakeState(); m.state.part = HC.PART_BATTLE; m.frames -= 40                                          # Engine.state is replaced by savestates.apply, frames goes back
        m.step(c); self.assertIsNone(c.tracking)
        m.core.trigger('death', 0); m.core.trigger('victory'); m.core.trigger('end', 0); self.assertEqual(m.step(c, 2), [])

    def test_skipped_frames(self):
        m, c = self.m, self.c; m.state.part = HC.PART_BATTLE; m.core.trigger('start'); m.core.place(0, 20, 0); m.step(c, 3)
        m.frames += 500; m.step(c); self.assertIsNone(c.tracking)                                                          # the loaded savestate could have the same State object: the frame gap gives it away

    def test_frames_backward_same_objects(self):
        m, c = self.m, self.c; m.state.part = HC.PART_BATTLE; m.core.trigger('start'); m.core.place(0, 20, 0); m.step(c, 3)
        m.frames -= 100; m.step(c); self.assertIsNone(c.tracking)

    def test_a_new_start_replaces_the_tracking(self):
        m, c = self.m, self.c; m.state.part = HC.PART_BATTLE; m.core.trigger('start'); m.core.place(0, 20, 0); m.step(c, 3)
        m.core.drain(0); m.core.trigger('start'); m.core.place(0, 3, 0); m.step(c, 2); self.assertEqual([eng['num'] for eng in c.tracking.monsters], [3])        # (the first one did not finish: never reported)

    def test_battle_exit_without_end_is_abandoned(self):
        m, c = self.m, self.c; m.state.part = HC.PART_BATTLE; m.core.trigger('start'); m.core.place(0, 20, 0); m.step(c, 3)
        m.state.part = 0xc; m.step(c, HC.MAX_FRAMES_WITHOUT_BATTLE - 1); self.assertIsNotNone(c.tracking)
        m.step(c, 3); self.assertIsNone(c.tracking)                                                                        # back to the title screen, save loaded...: a fake battle is not kept

    def test_error_never_propagated(self):
        class Fake: pass
        self.assertEqual(self.c.do_update(Fake()), []); self.assertIsNotNone(self.c.error)
        self.assertEqual(self.c.do_update(self.m), [])                                                                       # the sensor keeps being used
        m, c = self.m, self.c; self.assertEqual(simple_battle(m, c)[0]['outcome'], 'victory')

    def test_failing_hook_raises_nothing(self):
        self.m.core.mem = lambda a, n: (_ for _ in ()).throw(RuntimeError('lecture impossible'))
        self.m.core.trigger('death', 0); self.m.core.trigger('end', 0); self.m.core.trigger('start')                # (the hooks swallow the error: the emulator never stops)

    def test_guardrail_events(self):
        for _ in range(1000): self.m.core.trigger('victory')
        self.assertLessEqual(len(self.c.events), 200)


# ---------------------------------------------------------------------------------------------------------------------------------- real engine (optional)
APK, SAVES = os.environ.get('DQ_APK'), os.environ.get('DQ_SAVES')
RE_XP = re.compile(r"reçoit (\d+) points? d'expérience")
RE_GOLD = re.compile(r"reçoit (\d+) pièces? d'or")


@unittest.skipUnless(APK and SAVES, 'real engine: DQ_APK=<folder of the patched APKs> DQ_SAVES=<folder of the saves>')
class RealEngine(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        import unicorn; from dq456_pc.core import engine as ENGINE; from dq456_pc.persistence import savestates as SS
        cls.ENGINE, cls.SS, cls.unicorn = ENGINE, SS, unicorn
        cls.eng = ENGINE.Engine(APK, SAVES, tempfile.mkdtemp(prefix='sv_hcb_')); c = cls.c = cls.eng.core
        SV.load_any(cls.eng)
        for _ in range(200): cls.eng.step(0, 0)
        SV.force_chapter(cls.eng, 1); SV.force_party(cls.eng, 3, 12)                      # Ragnar + Doc: the outcome of battles depends on the party, which comes from the player's save
        cls.cap = HC.BattleSensor(cls.eng)
        assert cls.cap.active
        cls.groups = [(3, 1)]; cls.enc = c.call(c.export('_ZN7Encount12getSingletonEv'), label='enc')
        def force(u, addr, sz, ud):                                                       # encounter composition: at most 4 groups, (monster number, count) at Encount + 0x34 / 0x44
            for j in range(4):
                i, n = cls.groups[j] if j < len(cls.groups) else (0, 0)
                c.mem_w(cls.enc + 0x34 + 4 * j, struct.pack('<I', i)); c.mem_w(cls.enc + 0x44 + 4 * j, struct.pack('<I', n))
        a = c.export('_ZN10BattleRoot12setupMonsterEv'); c.uc.hook_add(unicorn.UC_HOOK_CODE, force, None, a, a)
        c.uc.ctl_flush_tb()
        cls.party = c.export('_ZN6status7g_PartyE'); cls.orig = c.export('_ZN6status9PartyData15originalPlayer_E'); cls.double = c.export('_ZN6status10BaseAction11doubleFlag_E')
        cls.initial = SS.snapshot(cls.eng)

    def setUp(self):
        self.SS.apply(self.eng, self.initial)
        self.battles, self.msgs = [], []
        for _ in range(3): self.step()
        self.battles.clear(); self.msgs.clear()

    # -- tools
    def party_gold(self): return struct.unpack('<I', self.c.mem(self.party + 0x2e0, 4))[0]

    def xp_members(self):
        """Experience of each party member (HaveStatus +8 of HaveStatusInfo + 0x48; -1 = no experience, e.g. a guest)."""
        idx = [i for i in struct.unpack('<13I', self.c.mem(self.party + 0x304, 13 * 4)) if i]
        return {i: struct.unpack('<I', self.c.mem(self.orig + 0x530 * i + 0x60, 4))[0] for i in idx}

    def step(self, p=0, d=0):
        self.eng.step(p, d); self.eng.ui.damage = []
        self.battles.extend(self.cap.do_update(self.eng))
        for r in self.eng.sensor.drain(): self.msgs.append(r['text'].replace('\xa0', ' ').replace('\n', ' / ').strip(' /'))

    def launch(self, groups):
        ENGINE = self.ENGINE; type(self).groups = groups
        self.c.call(self.c.export('_ZN6Global11startBattleEv'), self.eng._global(), label='startBattle')
        n = 0
        while self.eng.state.part != ENGINE.PART_BATTLE and n < 1500: self.step(); n += 1
        self.assertEqual(self.eng.state.part, ENGINE.PART_BATTLE)

    def play(self, actions=('combattre',), maximum=6000, after=None):
        """Plays the battle the way test_battle_speed does (A on the menu, message advance); `actions`: one per top-level menu, 'combattre' or 'fuir' (button 3 of the type 30 menu)."""
        ENGINE, eng = self.ENGINE, self.eng; st = {'rel': None, 'pending': 0, 'k': 0}
        for i in range(maximum):
            p = d = 0
            if st['rel'] is not None: eng.send_menu(st['rel'], 1, -1, 0); st['rel'] = None
            port = eng.active_menu(); f = eng.ui.f.get(port) if port is not None else None
            if port is not None and not eng.msg_visible:
                st['pending'] += 1
                if st['pending'] % 4 == 0:
                    if f['type'] == 30:
                        action = actions[min(st['k'], len(actions) - 1)]; st['k'] += 1
                        eng.send_menu(port, 1, 3, 0x10) if action == 'fuir' else eng.send_menu(port, 1, -1, 0x10)
                    else: eng.send_menu(port, 1, -1, 0x10)
                    st['rel'] = port
            elif eng.msg_visible and (eng.ui.msg.get('feed') or eng.message_state()[1] in (3, 5)):
                st['pending'] += 1
                if st['pending'] % 4 == 0: p = d = ENGINE.A
            else: st['pending'] = 0
            prev = eng.state.part; self.step(p, d)
            if after: after(i)
            if eng.state.part != ENGINE.PART_BATTLE and prev == ENGINE.PART_BATTLE: return i
        self.fail('the battle does not end')

    def number_list(self, regex):
        return [int(x) for m in self.msgs for x in regex.findall(m)]

    def check_victory(self, battle, or0, xp0):
        """The dict, the game text and the memory say the same thing."""
        self.assertEqual(battle['outcome'], 'victory')
        self.assertEqual(self.number_list(RE_XP), [battle['xp']], 'experience of the message')
        self.assertEqual(self.number_list(RE_GOLD), [battle['gold']], 'gold of the message')
        self.assertEqual(self.party_gold() - or0, battle['gold'], 'gold of the party (before / after)')
        after = self.xp_members(); gains = {i: after[i] - xp0[i] for i in after if xp0[i] != 0xffffffff}
        self.assertTrue(gains and all(g == battle['xp'] for g in gains.values()), 'experience of each member %r' % (gains,))
        for e in battle['enemies']: self.assertEqual(e['defeated'] + e['fled'] + e['vanished'], e['total'])           # (a monster can flee: "Le gluant s'enfuit !" -- counted as such, like the game's message)
        self.assertEqual(sum(e['fled'] for e in battle['enemies']), sum(1 for m in self.msgs if "s'enfuit" in m), 'monster escapes: the game message and the dict')
        text = ' | '.join(self.msgs).lower()
        for e in battle['enemies']: self.assertIn(e['name'].lower(), text, 'the name must be the one the game writes')

    # -- scenarios
    def test_victory_two_species(self):
        or0, xp0 = self.party_gold(), self.xp_members()
        self.launch([(3, 2), (0, 1)]); self.play()
        self.assertEqual(len(self.battles), 1); c = self.battles[0]
        self.assertEqual([(e['name'], e['total']) for e in c['enemies']], [('Londuleux', 2), ('Gluant', 1)])
        self.assertGreater(c['gold'], 0); self.assertGreater(c['xp'], 0); self.check_victory(c, or0, xp0)
        self.assertGreaterEqual(c['t'], 0)

    def test_four_species_appearance_order(self):
        or0, xp0 = self.party_gold(), self.xp_members()
        self.launch([(3, 2), (20, 1), (0, 3), (5, 1)]); self.play()
        c, = self.battles
        self.assertEqual([(e['name'], e['total']) for e in c['enemies']], [('Londuleux', 2), ('Rat volant', 1), ('Gluant', 3), ('Chauve-sourat', 1)])
        self.check_victory(c, or0, xp0)

    def test_victory_message_per_character(self):
        """The party has several members: "Chaque membre de l'équipe reçoit N points d'expérience" (N = the per-member value, the same for everyone) and "L'équipe reçoit M pièces d'or" (M = the total)."""
        self.launch([(20, 3)]); self.play(); c, = self.battles
        self.assertTrue(any('Chaque membre' in m for m in self.msgs) or len(self.xp_members()) < 2)
        self.assertEqual(self.number_list(RE_XP), [c['xp']]); self.assertEqual(self.number_list(RE_GOLD), [c['gold']])

    def test_experience_doubled(self):
        """The game doubles the gold and experience (BaseAction::doubleFlag_) when awarding them: the dict gives the message's number, not the monsters'."""
        target = self.c.export('_ZN23BattleExecDefeatMonster10initializeEv')
        h = self.c.uc.hook_add(self.unicorn.UC_HOOK_CODE, lambda u, a, s, d: self.c.mem_w(self.double, b'\x01'), None, target, target); self.c.uc.ctl_flush_tb()
        try:
            or0, xp0 = self.party_gold(), self.xp_members()
            self.launch([(20, 2)]); self.play(); c, = self.battles
        finally:
            self.c.uc.hook_del(h); self.c.mem_w(self.double, b'\x00')
        self.assertEqual((c['xp'], c['gold']), (12, 28)); self.check_victory(c, or0, xp0)                       # 2 rats volants: 3 experience and 7 gold each, doubled

    def test_escape_after_a_death(self):
        or0, xp0 = self.party_gold(), self.xp_members()
        self.launch([(3, 2), (0, 3)]); self.play(actions=('combattre', 'fuir'))
        c, = self.battles
        self.assertEqual((c['outcome'], c['gold'], c['xp']), ('escape', 0, 0))
        self.assertEqual([(e['name'], e['total'], e['defeated']) for e in c['enemies']], [('Londuleux', 2, 1), ('Gluant', 3, 0)])
        self.assertEqual(self.party_gold(), or0); self.assertEqual(self.xp_members(), xp0)                       # the engine awards nothing for an escape
        self.assertTrue(any("s'enfuit" in m for m in self.msgs))

    def test_successful_escape_after_failures(self):
        """"Mais l'ennemi bloque le passage !": BattleExecEscape::setup runs on each attempt; only the last one ends the battle."""
        self.launch([(3, 2), (20, 2)]); self.play(actions=('fuir',), maximum=8000)
        c, = self.battles
        self.assertEqual((c['outcome'], c['gold'], c['xp']), ('escape', 0, 0)); self.assertEqual([e['defeated'] for e in c['enemies']], [0, 0])

    def test_defeat(self):
        or0 = self.party_gold()
        for i in self.xp_members():                                                       # 1 HP each: defeat is certain whatever the level of the party, which comes from the save
            self.c.mem_w(self.orig + 0x530 * i + 0x58 + 0x22, struct.pack('<H', 1))
        self.launch([(150, 3)]); self.play(maximum=9000)
        c, = self.battles
        self.assertEqual((c['outcome'], c['gold'], c['xp']), ('defeat', 0, 0))
        self.assertEqual([(e['total'], e['defeated']) for e in c['enemies']], [(3, 0)]); self.assertTrue(c['enemies'][0]['name'])
        self.assertLessEqual(self.party_gold(), or0)                                                              # (the game takes half the gold from a wiped-out party)

    def test_two_consecutive_battles(self):
        self.launch([(20, 1)]); self.play(); self.launch([(3, 1), (0, 1)]); self.play()
        self.assertEqual([[e['name'] for e in c['enemies']] for c in self.battles], [['Rat volant'], ['Londuleux', 'Gluant']])
        self.assertLess(self.battles[0]['t'], self.battles[1]['t']); self.assertTrue(all(c['outcome'] == 'victory' for c in self.battles))

    def test_interrupted_by_state_loaded_in_town(self):
        """Savestate taken in a town, loaded in the middle of a battle: nothing false, no crash, and the next battle is correctly reported."""
        SS = self.SS; town = SS.snapshot(self.eng)
        self.launch([(3, 2), (0, 1)])
        for _ in range(500): self.step()
        self.assertIsNotNone(self.cap.tracking)
        SS.apply(self.eng, town)
        for _ in range(200): self.step()
        self.assertIsNone(self.cap.tracking); self.assertEqual(self.battles, [])
        self.launch([(20, 1)]); self.play(); self.assertEqual([[e['name'] for e in c['enemies']] for c in self.battles], [['Rat volant']])

    def test_interrupted_by_mid_battle_state(self):
        """Savestate taken in the middle of a battle: the battle played to the end is reported; the reloaded savestate then finished is not (the start of that battle was not seen)."""
        SS = self.SS; self.launch([(3, 2), (0, 2)])
        for _ in range(480): self.step()
        middle = SS.snapshot(self.eng); self.play(); self.assertEqual(len(self.battles), 1); self.battles.clear()
        SS.apply(self.eng, middle); self.step(); self.assertEqual(self.eng.state.part, self.ENGINE.PART_BATTLE)
        self.play(); self.assertEqual(self.battles, [])

    def test_sensor_created_mid_battle(self):
        self.launch([(20, 2)])
        for _ in range(300): self.step()
        late = HC.BattleSensor(self.eng); outputs = []
        for _ in range(4000):
            self.step(*self._key_presses()); outputs.extend(late.do_update(self.eng))
            if self.eng.state.part != self.ENGINE.PART_BATTLE: break
        self.assertEqual(outputs, [])

    def _key_presses(self):
        eng = self.eng
        if eng.msg_visible and (eng.ui.msg.get('feed') or eng.message_state()[1] in (3, 5)): return self.ENGINE.A, self.ENGINE.A
        port = eng.active_menu()
        if port is not None and not eng.msg_visible: eng.send_menu(port, 1, -1, 0x10)
        return 0, 0

    def test_sensor_created_after_battles(self):
        """A sensor installed after the engine has already run the battle code (blocks translated by the emulator) also works."""
        self.launch([(20, 1)]); self.play(); self.battles.clear()
        late = HC.BattleSensor(self.eng); outputs = []
        self.launch([(3, 1)])
        orig = self.step
        def step(p=0, d=0): orig(p, d); outputs.extend(late.do_update(self.eng))
        self.step = step
        try: self.play()
        finally: del self.step
        self.assertEqual([[e['name'] for e in c['enemies']] for c in outputs], [['Londuleux']]); self.assertEqual(outputs[0]['xp'], self.battles[0]['xp'])

    def names_after_plates(self, ids):
        """Starts a battle against `ids` (one of each) and plays until the sensor has read the plates (opening of the target selection); -> ({number: name}, appearance messages)."""
        class Finished(Exception): pass
        def after(_i):
            if self.cap.tracking is not None and all(i in self.cap.tracking.names for i in ids): raise Finished()
        self.launch([(i, 1) for i in ids])
        try: self.play(maximum=2000, after=after)
        except Finished: pass
        return dict(self.cap.tracking.names), [m for m in self.msgs if 'apparaît' in m]

    def test_full_names_of_monsters_with_long_names(self):
        """The name in the dict is the one the game writes in its appearance message (without the split marks ";" and "$"), even when the plate splits it over two lines."""
        names, appearances = self.names_after_plates([0, 34, 74, 82])
        self.assertEqual(names, {0: 'Gluant', 34: 'Armure errante', 74: 'Scara$somniaque', 82: 'Gluant de mercure'})          # (the "$" stays, the history does not show it)
        text = ' | '.join(appearances).lower().replace(';', '')
        for n in names.values(): self.assertIn(n.lower(), text)

    def test_plate_names_in_group_order(self):
        """Four distinct species, in an order that is neither the numeric nor the alphabetical one: each monster number gets ITS name (verified by the appearance message)."""
        names, appearances = self.names_after_plates([20, 3, 5, 0])
        self.assertEqual(names, {20: 'Rat volant', 3: 'Londuleux', 5: 'Chauve-sourat', 0: 'Gluant'})
        self.assertEqual([m.lower() for m in appearances], ['un rat volant apparaît !', 'un londuleux apparaît !', 'un chauve-sourat apparaît !', 'un gluant apparaît !'])

    # --: fled / vanished monsters, items gained
    def force_spell(self, slot, sort):
        """Removes a monster the way the game does: "dead" state (setDeath) and escape flag (bit 4 of HaveStatusInfo + 0x424) or vanish flag (bit 5); checkDeathMonster then counts it at the next frame."""
        c = self.c; hsi = c.export('_ZN6status9g_MonsterE') + HC.MONSTERS_START + slot * HC.MONSTER_STEP + 0x10
        c.call(c.export('_ZN6status14HaveStatusInfo13setEscapeFlagEb' if sort == 'fled' else '_ZN6status14HaveStatusInfo16setDisappearFlagEb'), hsi, 1, label='drapeau')
        c.call(c.export('_ZN6status14HaveStatusInfo8setDeathEv'), hsi, label='setDeath')

    def test_fled_monster_and_vanished_monster(self):
        """One fled monster and one vanished monster (forced in the game's memory) are recorded by species; the others are defeated by the party; the outcome is a victory."""
        state = {'done': False}
        def cb(i):
            if i == 30 and not state['done']: state['done'] = True; self.force_spell(1, 'fled'); self.force_spell(2, 'vanished')
        self.launch([(3, 4)]); self.play(after=cb, maximum=9000)
        self.assertTrue(state['done']); c, = self.battles
        e, = c['enemies']; self.assertEqual((e['name'], e['total'], e['fled'], e['vanished']), ('Londuleux', 4, 1, 1)); self.assertEqual(e['defeated'], 2)
        self.assertEqual(c['outcome'], 'victory'); self.assertGreater(c['xp'], 0)

    def test_item_won_at_end_of_battle(self):
        """An item given by the game at the end of a battle ("Le londuleux laisse tomber un coffre au trésor ! ... Il contient un arc de chasseur !"; the loot is written into the monster group as the game does when the monster dies, BattleExecItem gives it): its name is the one in the game's message."""
        c = self.c; mp = c.export('_ZN6status9g_MonsterE'); state = {'done': False}
        def cb(i):                                                                                     # (the game writes the monster's loot when it dies: we set ours right after, before the victory)
            if not state['done'] and any('vaincu' in m for m in self.msgs):
                state['done'] = True; c.call(c.export('_ZN6status12MonsterParty11setDropItemEi'), mp, 12, label='drop'); c.call(c.export('_ZN6status12MonsterParty18setDropItemMonsterEi'), mp, 3, label='drop monstre')
        self.launch([(3, 1)]); self.play(after=cb, maximum=9000)
        self.assertTrue(state['done']); d, = self.battles; self.assertEqual(d['outcome'], 'victory')
        self.assertEqual(len(d['objects']), 1, self.msgs); o = d['objects'][0]
        self.assertTrue(o['name'] and not o['name'].startswith('Objet n'), o)
        text = ' | '.join(self.msgs).lower().replace(';', ''); self.assertIn(o['name'].lower(), text, 'the name must be the one the game writes')

    def test_cost_outside_battle(self):
        import time
        t0 = time.perf_counter(); n = 600
        for _ in range(n): self.eng.step(0, 0)
        t1 = time.perf_counter()
        for _ in range(n): self.eng.frames += 1; self.cap.do_update(self.eng)
        t2 = time.perf_counter()
        step_us, update_us = (t1 - t0) / n * 1e6, (t2 - t1) / n * 1e6
        print('\n  outside battle: update %.1f us per frame (one engine step: %.0f us)' % (update_us, step_us))
        self.assertLess(update_us, 200.0); self.assertLess(update_us, step_us * 0.1)


if __name__ == '__main__':
    unittest.main(verbosity=2)
