"""Captures battle results for the battle history: defeated enemies, gold won, experience gained.

    sensor = BattleSensor(engine)         # once, after the Engine is created (installs READ-ONLY hooks in the emulator; writes nothing to the engine's memory)
    for battle in sensor.do_update(engine): ... # ONCE per engine frame, after engine.step; returns the battles FINISHED at this frame (most often an empty list)

Each battle: {'t': game time at the end (1/60 s, status::g_Game + 4), 'ennemis': [{'nom': 'Gluant', 'total': 3, 'vaincus': 1, 'fuis': 1, 'disparus': 0}, ...] (one element per species, in order
of appearance; what remains, total - vaincus - fuis - disparus, is still there when the battle ends: the party fled or was defeated), 'or': int, 'xp': int, 'issue': 'victoire' | 'fuite' | 'defaite',
'objets': [{'nom': 'Herbe médicinale'}, ...] (the items the game gives the party at the end of the battle: "Le gluant laisse tomber un coffre au trésor !")}. Gold and experience: those of the game's victory message,
0 for a flee or a defeat (the engine does not award them).

Method (ESTABLISHED by reading the disassembled engine and then by measurement: see tests/test_battle_history.py):
- DEATHS are noted by a hook on BattleActorManager2::execMonsterDeath(this, i), the function the game calls once per defeated monster (not for a monster that flees or vanishes) and which adds
  the monster's experience to g_Party + 0x2f8 and its gold to g_Party + 0x2fc. These are the two counters that BattleExecVictory01 / BattleExecVictory20 read to build the messages "N points d'experience" and "N pieces d'or"
  (getBattleExp / getBattleGold, after the possible doubling by reflectBattleExp / reflectBattleGold): so the largest of their readings is kept from one frame to the next, until they are reset to zero.
- Monsters that FLEE and those that VANISH are noted by two hooks in the middle of BattleActorManager2::checkDeathMonster (the routine that, every frame, reviews the dead, fled or vanished monsters;
  it counts them inline in +0x7d24 / +0x7d28, BattleEndTask::initialize reads them, and it calls execMonsterDeath only for a dead one): just before the increment of the flee counter
  (+0x98, `ldr w8, [x23, #0xd24]`) and of the vanish counter (+0xc0, `ldr w8, [x23, #0xd28]`), w20 is the monster index (same index as for execMonsterDeath). Each monster goes through there only once
  (a mask of the monsters already processed, +0xd30, guards against repeats).
- The ITEMS won are given by BattleExecVictory32::setup (the task that follows victory: "laisse tomber un coffre au trésor !", "Ragnar l'ouvre.", "Il contient un arc de chasseur !"): it calls
  PartyStatus::giveItem(item = task + 0xc), which returns the index of the member who takes it, or -1 when it goes into the bag (measured: "Ragnar met l'arc de chasseur dans le sac." with -1); in both cases the item is
  obtained. Hook right after the call (+0x28, `cmn w0,`): x20 = the task. NOT VERIFIED: what the game does when the bag itself is full. The item name is requested from
  the engine itself (TextAPI::extractText(buffer, 0x4000000 | number), which is what the game does for the "item name" macro), between two frames, never inside a hook; the ";" (the patch's name break marker) is removed.
- The START is PartyStatus::startBattle, the END is Global::endBattle(bool) (true argument = party wiped out), the VICTORY BattleExecDefeatMonster::initialize (the "all enemies are defeated" routine,
  which awards the experience), the FLEE BattleExecEscape::setup (called on every flee ATTEMPT, successful or not: a successful flee is therefore "attempt made, no victory, battle ended").
- The ENEMIES are read every frame in g_Monster (12 slots of 0x538 bytes starting at +8; +0x4f8 = monster number, -1 if empty; +0x4fc = group number): one monster = one occupied slot;
  the species is the monster number. Reinforcements called during the battle are added to the total.
- The NAMES are those of the monster plates that the engine sends to Unity (Engine.ui, window of type 31: "Rat volant", "Gluant\\n\\n\\t×3" -> "Gluant"), associated with the groups in order (plate j carries the
  j-th group), only when there are as many plates as groups and before the first death. Without a plate (surprise attack: the game does not display any; plates for a different number of groups), the name
  is requested from the engine itself at the end of the battle, by monster number (TextAPI::extractText(buffer, 0x6000000 | number): "londuleux", "armure ;errante", "scara$somniaque" -> "Londuleux",
  "Armure errante", "Scara$somniaque": the "$" stays); "Monster" if the engine does not answer.
Everything is guarded: an error returns nothing and is written only once to the console. A battle whose start was not seen (savestate loaded mid-battle, sensor created during a battle) is never
reported: better to say nothing than to say something false."""
import re, struct
from dq456_pc.language import tr, N_

PART_BATTLE = 0xd
SLOT_COUNT = 12                   # g_Monster: at most 12 monsters
MONSTERS_START, MONSTER_STEP = 8, 0x538 # g_Monster + 8: array of MonsterStatus
OFF_NUMBER, OFF_GROUP = 0x4f8, 0x4fc  # in a MonsterStatus: monster number (-1 = empty slot), encounter group number
OFF_XP, OFF_GOLD = 0x2f8, 0x2fc         # in g_Party: experience and gold of the current battle (awarded on victory)
OFF_DEFEAT = 0x509                    # g_BattleResult + 0x509: the party lost (ExitTask::terminate tests it before calling endBattle)
UNKNOWN = 0xffffffff
UNKNOWN_NAME = N_('menus.monster')                      # (fallback name when the engine does not answer: translated at capture time, see BattleSensor)
OUTCOMES = ('victory', 'escape', 'defeat')
MAX_FRAMES_WITHOUT_BATTLE = 20            # consecutive frames outside the "battle" part before abandoning tracking (the normal end always arrives before the part change)
MAX_JUMP_FRAMES = 8                    # maximum gap in Engine.frames between two do_update calls without declaring a discontinuity (savestate loaded...)

# hooks (engine symbols): event -> name
HOOKS = (('start', '_ZN6status11PartyStatus11startBattleEv'), ('death', '_ZN19BattleActorManager216execMonsterDeathEi'), ('victory', '_ZN23BattleExecDefeatMonster10initializeEv'),
            ('escape', '_ZN16BattleExecEscape5setupEv'), ('end', '_ZN6Global9endBattleEb'))
# hooks in the MIDDLE of a function: (event, symbol, offset, instruction expected at that spot). The instruction is checked before installing the hook:
# a different engine does not get a hook placed at random (only the corresponding event is then lost, the capture goes on).
SYM_DEATH_CHECK = '_ZN19BattleActorManager217checkDeathMonsterEv'
SYM_ITEM_WON = '_ZN19BattleExecVictory325setupEv'
INTERNAL_HOOKS = (('monster_fled', SYM_DEATH_CHECK, 0x98, 0xb94d26e8),         # ldr w8, [x23, #0xd24]: monster flee counter
                     ('monster_vanished', SYM_DEATH_CHECK, 0xc0, 0xb94d2ae8),       # ldr w8, [x23, #0xd28]: vanish counter
                     ('item', SYM_ITEM_WON, 0x28, 0x3100041f))                    # cmn w0: right after PartyStatus::giveItem
SYM_ITEM_NAME = '_ZN7TextAPI11extractTextEPci'
KIND_ITEM = 0x4000000                                                              # "item name" in the game's text macros (setMACRO0(0xa, 0x4000000, number))
KIND_MONSTER = 0x6000000                                                            # "monster name" (BattleActorMacro::setMacroActor: setMACRO0(1, 0x6000000, monster number))
OFF_TASK_ITEM = 0xc                                                                # BattleExecVictory32: number of the item to give

# The same places in each engine: DQ IV's above; DQ V and VI keep the structure at other offsets (DQ VI's battle code is split into "BattleTask" tasks).
# hooks: event -> symbol; internal: (event, symbol, offset, expected instruction, register: the monster index or, for 'item', ('task', register, offset) / ('value', register));
# monsters: (number of slots, g_Monster + start, step, monster number, group number); party: (experience, gold) of the battle in g_Party; defeat: g_BattleResult + offset.
LAYOUTS = {
    'dq4': dict(hooks=HOOKS, internal=tuple((e, s_, o, w, 20 if e != 'item' else ('task', 20, OFF_TASK_ITEM)) for e, s_, o, w in INTERNAL_HOOKS),
                monsters=(SLOT_COUNT, MONSTERS_START, MONSTER_STEP, OFF_NUMBER, OFF_GROUP), party=(OFF_XP, OFF_GOLD), defeat=OFF_DEFEAT, text=SYM_ITEM_NAME),
    'dq5': dict(hooks=(('start', '_ZN6status18PartyStatusUtility11startBattleEv'), ('death', '_ZN3btl18BattleActorManager16execMonsterDeathEi'),
                       ('victory', '_ZN3btl23BattleExecDefeatMonster10initializeEv'), ('escape', '_ZN3btl16BattleExecEscape5setupEv'), ('end', '_ZN6Global9endBattleEb')),
                internal=(('monster_fled', '_ZN3btl18BattleActorManager17checkDeathMonsterEv', 0x98, 0xb9474ae8, 20),          # ldr w8, [x23, #0x748]: flee counter
                          ('monster_vanished', '_ZN3btl18BattleActorManager17checkDeathMonsterEv', 0xc0, 0xb9474ee8, 20),      # ldr w8, [x23, #0x74c]: vanish counter
                          ('item', '_ZN3btl19BattleExecVictory325setupEv', 0x78, 0x3100041f, ('task', 19, 0xc))),               # cmn w0, #1 after PartyStatusUtility::giveItem; x19 = the task
                monsters=(12, 8, 0x550, 0x508, 0x50c), party=(0x8, 0xc), defeat=0x4d9, text='_ZN4ardq7TextAPI11extractTextEPci'),
    'dq6': dict(hooks=(('start', '_ZN6status18PartyStatusUtility11startBattleEv'), ('death', '_ZN6status21DeadMonsterCollection16execMonsterDeathEi'),
                       ('victory', '_ZN3btl23BattleTaskDefeatMonster14initializeUserEv'), ('escape', '_ZN3btl18BattleTaskEscape005setupEv'), ('end', '_ZN6Global9endBattleEb')),
                internal=(('monster_fled', '_ZN6status21DeadMonsterCollection17checkDeathMonsterEv', 0x64, 0xb9400668, 22),     # ldr w8, [x19, #4]: flee counter (w22 = the monster)
                          ('monster_vanished', '_ZN6status21DeadMonsterCollection17checkDeathMonsterEv', 0x94, 0xb9400a68, 22), # ldr w8, [x19, #8]: vanish counter
                          ('item', '_ZN3btl14BattleTaskItem14initializeUserEv', 0x1c, 0x34000320, ('value', 0))),              # cbz w0 after MonsterParty::getDropItem: w0 = the item (0: none)
                monsters=(12, 8, 0x5f8, 0x34, 0x38), party=(0x8, 0xc), defeat=0x4bd, text='_ZN4ardq7TextAPI11extractTextEPci'),
}


def layout():
    """The places of the running game's engine (LAYOUTS)."""
    from dq456_pc import games as GM
    return LAYOUTS.get(GM.profile().key, LAYOUTS['dq4'])
UNKNOWN_ITEM_NAME = N_('menus.item')


# ---------------------------------------------------------------------------------------------------------------------------------- pure part (no emulator)
def plate_name(text):
    """Name displayed on a monster plate; None if empty. The game writes "Gluant\\n\\n\\t×3" (the count notation, which starts with a tab, is removed) and splits long names over two lines:
    "Armure \\n\\nerrante" -> "Armure errante"; "Scara-\\n\\nsomniaque" -> "Scara-somniaque" (a hyphen at the end of a line is rejoined without a space). Limitation: "Psaro l'Exter-\\n\\nminateur" gives
    "Psaro l'Exter-minateur" (the engine does not say whether the hyphen is a word break or a real hyphen)."""
    if not isinstance(text, str): return None
    name_str = ''
    for raw_value in text.replace('\r', '').split('\n'):
        if raw_value.startswith('\t'): break                                                 # "\t×3": the number of monsters in the group
        line = ''.join(ch for ch in raw_value if ch >= ' ' and ch != '\x7f').strip()
        if not line: continue
        if re.fullmatch(r'×\s*\d+', line): break
        name_str = line if not name_str else (name_str + line if name_str.endswith('-') else name_str + ' ' + line)
    return name_str or None


def group_names(groups, plates):
    """Associates plate names with monsters. groups: [(group number, monster number)] of the occupied slots; plates: [name, ...] in plate order (plate j = the j-th group,
    with groups taken in order of their number). -> {monster number: name}; {} if the number of plates differs from the number of groups (nothing is made up)."""
    order = sorted({g for g, _m in groups})
    names = [plate_name(p) for p in plates]
    if not order or len(order) != len(names) or any(n is None for n in names): return {}
    by_group = {}
    for g, m in groups: by_group.setdefault(g, m)
    return {by_group[g]: n for g, n in zip(order, names)}


def _monster(num): return {'num': num, 'defeated': False, 'fled': False, 'vanished': False}


def _is_gone(m): return m['defeated'] or m['fled'] or m['vanished']


class Tracking:
    """What is known about a battle in progress (pure data: no dependency on the engine; see BattleSensor for reading memory)."""

    def __init__(self):
        self.monsters = []             # one per monster seen, in order of appearance: {'num': monster number, 'defeated': bool, 'fled': bool, 'vanished': bool} (at most one of the three)
        self.objects = []               # items won: {'id': number, 'name': name}, in order
        self.places = {}               # slot -> index in monstres (current occupant)
        self.names = {}                 # monster number -> name
        self.deaths = 0                 # defeated monsters (execMonsterDeath hook)
        self.victory = False          # BattleExecDefeatMonster::initialize has run
        self.escape_attempts = 0      # BattleExecEscape::setup (successful or not)
        self.xp = 0; self.gold = 0      # largest readings of the party counters (g_Party + 0x2f8 / 0x2fc)

    def see(self, occupants):
        """A reading of the slots: occupants = [(slot, monster number)] of the occupied slots. A new occupant (a free slot that fills up, or a different number) is a new monster;
        a slot that empties is forgotten (the defeated or departed monster has already been counted)."""
        seen = set()
        for e, num in occupants:
            seen.add(e); i = self.places.get(e)
            if i is None or self.monsters[i]['num'] != num:
                self.monsters.append(_monster(num)); self.places[e] = len(self.monsters) - 1
        for e in [e for e in self.places if e not in seen]: del self.places[e]

    def _record_fate(self, lookup_key, slot, num):
        """The game declares that the monster in this slot is defeated / fled / vanished (key: 'defeated', 'fled' or 'vanished'). A monster never seen (gone in the frame of its appearance) is added, as is a monster
        whose fate is already noted (another monster arrived in the same slot)."""
        i = self.places.get(slot)
        if i is None or self.monsters[i]['num'] != num or _is_gone(self.monsters[i]):
            self.monsters.append(_monster(num)); i = len(self.monsters) - 1; self.places[slot] = i
        self.monsters[i][lookup_key] = True

    def dead(self, slot, num):
        """The game declares the monster in this slot defeated (execMonsterDeath hook)."""
        self.deaths += 1; self._record_fate('defeated', slot, num)

    def fled(self, slot, num):
        """The monster in this slot fled (the game counts it in checkDeathMonster)."""
        self._record_fate('fled', slot, num)

    def vanished(self, slot, num):
        """The monster in this slot vanished (same)."""
        self._record_fate('vanished', slot, num)

    def item(self, number, name_str):
        """The game gives an item to the party at the end of the battle."""
        self.objects.append({'id': int(number), 'name': name_str})

    def counters(self, xp, gold):
        """Reading of the battle's experience and gold counters: they only grow (doubling included) until they are reset to zero after the message; the largest is kept."""
        if xp > self.xp: self.xp = xp
        if gold > self.gold: self.gold = gold

    def assign_names(self, names):
        for num, name_str in names.items(): self.names.setdefault(num, name_str)

    def present_count(self): return len(self.places)

    def outcome(self, defeat=False):
        """Outcome of the battle at its end: the game's victory routine ran ('victoire'); otherwise the party is wiped out ('defaite'); otherwise all monsters seen are defeated ('victoire'); otherwise the party left ('fuite')."""
        if self.victory: return 'victory'
        if defeat: return 'defeat'
        if self.deaths > 0 and all(_is_gone(m) for m in self.monsters): return 'victory'
        return 'escape'

    def enemies(self):
        """[{'nom', 'total', 'vaincus', 'fuis', 'disparus'}] one entry per species (same name, or same number when the name is unknown), in order of first appearance."""
        species = {}
        for m in self.monsters:
            name_str = self.names.get(m['num'])
            lookup_key = ('n', name_str) if name_str else ('?', m['num'])
            e = species.setdefault(lookup_key, {'name': name_str or tr(UNKNOWN_NAME), 'total': 0, 'defeated': 0, 'fled': 0, 'vanished': 0})
            e['total'] += 1; e['defeated'] += 1 if m['defeated'] else 0; e['fled'] += 1 if m['fled'] else 0; e['vanished'] += 1 if m['vanished'] else 0
        return list(species.values())


def build_battle(tracking, t, defeat=False):
    """The finished battle: API dict (see the module header). Gold and experience count only for a victory."""
    outcome = tracking.outcome(defeat)
    won = outcome == 'victory'
    return {'t': int(t), 'enemies': tracking.enemies(), 'gold': int(tracking.gold) if won else 0, 'xp': int(tracking.xp) if won else 0, 'outcome': outcome,
            'objects': [{'name': o['name']} for o in tracking.objects] if won else []}


# ---------------------------------------------------------------------------------------------------------------------------------- reading the engine
def _ldr_w(word, base=0):
    """Offset of an `ldr wN, [xM, #imm]` (32-bit access, unsigned offset); None if it is not this instruction."""
    if word & 0xffc00000 != 0xb9400000 or (word >> 5) & 31 != base: return None
    return ((word >> 10) & 0xfff) * 4


_PER_ENGINE = {}                                                                         # (fallback if the engine rejects an additional attribute: id -> (engine, sensor))


class BattleSensor:
    L = LAYOUTS['dq4']                                                                  # (replaced by the running game's places in __init__)

    def __init__(self, engine):
        self.active = False; self.error = None
        self.tracking = None; self.outputs = []; self.events = []; self._item_names = {}; self._monster_names = {}; self._buffer = None
        self._state = None; self._frame = -10 ** 9; self._outside_battle = 0; self._old_plates = {}
        self.m = engine
        try:
            import unicorn
            c = self.c = engine.core
            self.L = layout()
            self.g_party = c.export('_ZN6status7g_PartyE'); self.g_monster = c.export('_ZN6status9g_MonsterE'); self.g_game = c.export('_ZN6status6g_GameE'); self.g_result = c.export('_ZN6status14g_BattleResultE')
            if not (self.g_party and self.g_monster and self.g_game and self.g_result) or not self._check():
                print('Battle history: unexpected engine, capture disabled', flush=True); return
            for evt, name_str in self.L['hooks']:
                a = c.export(name_str)
                if not a: print('Battle history: %s not found, capture disabled' % name_str, flush=True); return
            for evt, name_str in self.L['hooks']: c.uc.hook_add(unicorn.UC_HOOK_CODE, self._hook(evt), None, c.export(name_str), c.export(name_str))
            for evt, name_str, off, word, reg in self.L['internal']:                       # (with a different engine, only this event is lost)
                a = c.export(name_str)
                if not a or struct.unpack('<I', c.mem(a + off, 4))[0] != word:
                    print('Battle history: unexpected %s (+%#x), "%s" not tracked' % (name_str, off, evt), flush=True); continue
                c.uc.hook_add(unicorn.UC_HOOK_CODE, self._hook(evt, reg), None, a + off, a + off)
            try: c.uc.ctl_flush_tb()                                                    # (blocks already translated before the hooks: a sensor created after a few battles)
            except Exception: pass
            self.active = True
        except Exception as ex:
            self.error = repr(ex); print('Battle history: hooks not installed (%r)' % (ex,), flush=True)

    @classmethod
    def for_(cls, engine):
        """The sensor for this engine: created on first request, always the same afterwards (the hooks are installed only once). Allows adding just ONE line to the frame loop, without creating anything
        elsewhere: `for battle in BattleSensor.for_(eng).do_update(eng): ...` right after `eng.step`."""
        c = getattr(engine, '_battle_sensor', None) or _PER_ENGINE.get(id(engine), (None, None))[1]
        if c is None:
            c = cls(engine)
            try: engine._battle_sensor = c
            except Exception: _PER_ENGINE[id(engine)] = (engine, c)
        return c

    # ---- check: the engine is the one these offsets come from
    def _check(self):
        """The structures read are those of the studied engine: getBattleExp / getBattleGold do read g_Party + 0x2f8 / 0x2fc, MonsterStatus::isEnable does read +0x4f8 (monster number)."""
        try:
            c = self.c
            def offset(name_str):
                a = c.export(name_str)
                return _ldr_w(struct.unpack('<I', c.mem(a, 4))[0]) if a else None
            xp, gold = self.L['party']
            return (offset('_ZN6status15BasePartyStatus12getBattleExpEv') == xp and offset('_ZN6status15BasePartyStatus13getBattleGoldEv') == gold
                    and offset('_ZN6status13MonsterStatus8isEnableEv') == self.L['monsters'][3])
        except Exception:
            return False

    def _hook(self, evt, reg=None):
        def cb(uc, addr, size_value, _):
            try:
                c = self.c
                if evt == 'death':
                    i = uc.reg_read(c.XREG[1]) & 0xffffffff                              # index among the PRESENT monsters (getMonsterStatus counts the occupied slots), not the slot
                    occ = self._busy()
                    if 0 <= i < len(occ): self.events.append(('death', occ[i][0], occ[i][1], occ[i][2]))
                elif evt in ('monster_fled', 'monster_vanished'):
                    i = uc.reg_read(c.XREG[reg]) & 0xffffffff                             # monster index in the checkDeathMonster loop (same index as for execMonsterDeath; DQ IV / V: w20, DQ VI: w22)
                    occ = self._busy()
                    if 0 <= i < len(occ): self.events.append((evt, occ[i][0], occ[i][1]))
                elif evt == 'item':
                    if reg[0] == 'task':                                                  # the victory task (DQ IV: x20, DQ V: x19), the item's number at reg[2]
                        task = uc.reg_read(c.XREG[reg[1]]) & 0xffffffffffff
                        self.events.append(('item', struct.unpack('<I', c.mem(task + reg[2], 4))[0]))
                    else:
                        item = uc.reg_read(c.XREG[reg[1]]) & 0xffffffff                  # DQ VI: the item the monsters left (0: none)
                        if item: self.events.append(('item', item))
                elif evt == 'end':
                    self.events.append(('end', bool(uc.reg_read(c.XREG[1]) & 1), c.mem(self.g_result + self.L['defeat'], 1)[0] == 1))
                else: self.events.append((evt,))
                if len(self.events) > 200: del self.events[:100]               # (safeguard if do_update is never called)
            except Exception:
                pass
        return cb

    def _busy(self):
        """[(slot, monster number, group number)] of the occupied slots of g_Monster, in slot order."""
        count, start, step, off_number, off_group = self.L['monsters']
        raw_value = self.c.mem(self.g_monster + start, count * step)
        out = []
        for e in range(count):
            num, = struct.unpack_from('<I', raw_value, e * step + off_number); grp, = struct.unpack_from('<I', raw_value, e * step + off_group)
            if num != UNKNOWN and num < 4096: out.append((e, num, grp))
        return out

    def clock(self):
        """Game time in 1/60 s (status::g_Game + 4, like history.Sensor.time_and_key)."""
        try: return struct.unpack('<I', self.c.mem(self.g_game + 4, 4))[0]
        except Exception: return 0

    # ---- one frame
    def won(self):
        """Is the current battle won, its results being shown (from BattleExecDefeatMonster::initialize, read by do_update at the step of "the monsters are defeated", to the end
        of the battle)?"""
        return bool(self.tracking is not None and self.tracking.victory)

    def do_update(self, engine):
        """To be called ONCE per engine frame, after engine.step. -> list of battles finished at this frame (API dicts)."""
        if not self.active: return []
        try:
            state, image = engine.state, engine.frames
            discontinuity = state is not self._state or not 0 < image - self._frame <= MAX_JUMP_FRAMES
            self._state = state; self._frame = image
            if discontinuity and (self.tracking is not None):                                       # savestate loaded (or frames skipped): the tracked battle is no longer the one in memory
                self.tracking = None
            if self.tracking is None and not self.events and state.part != PART_BATTLE: return []        # outside battle: nothing else to do (most frequent path)
            ev, self.events = self.events, []
            for e in ev: self._event(e)
            if self.tracking is not None: self._observe(engine)
            if self.outputs: out, self.outputs = self.outputs, []; return out
            return []
        except Exception as ex:                                                              # the capture must never stop the game
            if self.error is None: print('Battle history: error (%r)' % (ex,), flush=True)
            self.error = repr(ex); self.tracking = None; self.events = []
            return []

    def _event(self, e):
        name_str = e[0]
        if name_str == 'start':
            self.tracking = Tracking(); self._outside_battle = 0; self._old_plates = self._plates()                       # (plates already there: those of the previous battle, not to be read)
        elif self.tracking is None: return                                                    # battle whose start was not seen: ignored
        elif name_str == 'death': self.tracking.dead(e[1], e[2])
        elif name_str == 'monster_fled': self.tracking.fled(e[1], e[2])
        elif name_str == 'monster_vanished': self.tracking.vanished(e[1], e[2])
        elif name_str == 'item': self.tracking.item(e[1], self._item_name(e[1]))
        elif name_str == 'victory': self.tracking.victory = True
        elif name_str == 'escape': self.tracking.escape_attempts += 1
        elif name_str == 'end':
            s, self.tracking = self.tracking, None
            for m in s.monsters:                                                          # monsters without a plate (surprise attack...): the name comes from the engine, by number
                if m['num'] not in s.names:
                    n = self._monster_name(m['num'])
                    if n: s.assign_names({m['num']: n})
            self.outputs.append(build_battle(s, self.clock(), defeat=e[1] or e[2]))

    def _observe(self, engine):
        """Reading of the frame for the tracked battle: slots, counters, names."""
        s = self.tracking
        if engine.state.part != PART_BATTLE:
            self._outside_battle += 1
            if self._outside_battle > MAX_FRAMES_WITHOUT_BATTLE: self.tracking = None                # left the battle without going through endBattle (return to title...): abandon
            return
        self._outside_battle = 0
        occ = self._busy()
        s.see([(e, num) for e, num, _g in occ])
        xp_off, gold_off = self.L['party']
        xp, = struct.unpack('<I', self.c.mem(self.g_party + xp_off, 4)); gold, = struct.unpack('<I', self.c.mem(self.g_party + gold_off, 4))
        s.counters(xp, gold)
        if occ and s.deaths == 0 and any(n not in s.names for _e, n, _g in occ): self._names(s, occ)

    def _engine_text(self, kind, number):
        """Text that the engine gives for (kind, number) -- TextAPI::extractText, which is what the game calls for a name macro --; None if no answer. Called between two frames (do_update), never from a hook.
        The ";" (patch name break) is removed; the "$" (break with hyphen) is kept: the history draws the names with the message font, which does not show it."""
        try:
            c = self.c; f = c.export(self.L['text'])
            if not f: return None
            self._buffer = c.scratch('battle_history', 256)          # buffer taken from the engine heap, never kept above a loaded savestate
            c.mem_w(self._buffer, b'\0' * 16)
            c.call(f, self._buffer, kind | number, label='engine name')
            t = c.read_cstr(self._buffer).decode('utf-8', 'replace').replace(';', '').strip()
            return t if t and not t.startswith('<ERR') else None
        except Exception:
            return None

    def _item_name(self, number):
        """Name of the item (the name the game displays); cached. No answer: "Objet n°12"."""
        name_str = self._item_names.get(number)
        if name_str is None: name_str = self._item_names[number] = self._engine_text(KIND_ITEM, number) or tr(UNKNOWN_ITEM_NAME) % number
        return name_str

    def _monster_name(self, number):
        """Name of the monster, with a capital letter (the engine gives the name as in a sentence: "londuleux"); cached. None if no answer."""
        name_str = self._monster_names.get(number)
        if name_str is None:
            t = self._engine_text(KIND_MONSTER, number)
            name_str = self._monster_names[number] = (t[:1].upper() + t[1:]) if t else ''
        return name_str or None

    def _plates(self):
        """{window: (dict of each plate, ...)} of the monster plates that Engine.ui holds in memory (window of type 31). The objects themselves are kept: the engine creates new ones on every refresh."""
        out = {}
        try:
            for port, f in self.m.ui.f.items():
                if f.get('type') != 31: continue
                plate_dict, layout = f.get('plates') or {}, f.get('layout')
                if isinstance(layout, int) and 1 <= layout <= 4 and all(j in plate_dict for j in range(layout)): out[port] = tuple(plate_dict[j] for j in range(layout))
        except Exception:
            pass
        return out

    def _names(self, s, occ):
        """Names of the monster plates sent by the engine to Unity, as long as no monster is defeated. Only plates that arrived since the start of this battle count (objects different from those of that time)."""
        for port, cur in self._plates().items():
            old = self._old_plates.get(port)
            if old is not None and len(old) == len(cur) and all(a is b for a, b in zip(old, cur)): continue
            res = group_names([(g, n) for _e, n, g in occ], [p.get('name') for p in cur])
            for n, name_str in list(res.items()):                                                  # a name the plate split at the patch's "$" ("Scara-" / "somniaque") keeps its "$" (shown without it)
                if name_str and '-' in name_str:
                    raw = self._engine_text(KIND_MONSTER, n)
                    if raw and '$' in raw and raw.replace('$', '-').lower() == name_str.lower(): res[n] = name_str.replace('-', '$') if name_str.count('-') == raw.count('$') else raw
            if res: s.assign_names(res); self._old_plates[port] = cur
