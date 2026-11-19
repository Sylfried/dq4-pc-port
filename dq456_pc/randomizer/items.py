"""Randomizer, items (design: category 1): what the chests, jars, barrels, shelves, wardrobes and floor sparkles hold, and what the game's people and events give.

Where the game keeps them (read in libdq4core.so and the game files):
- Containers: each town or dungeon map file (`assets/map/<map>.stg`) has a furniture table (block 0, magic 0xbc32, rows of 0x18 bytes from block + 4, row count = byte + 0x16 of
  the table): + 6 item, + 8 gold, + 0xa formation and + 0xc monster of a mimic, + 0xe message (special furniture), + 0x12 the "taken" flag, + 0x14 the kind of furniture (7 = chest).
  The "taken" flags are one bit array for the whole game (StageStatus + 0x15a, getFurnFlag): a flag is one container, wherever its map is loaded (a few maps share one). The engine reads
  the table from the loaded map (TownStageManager + 0 -> block 0, TownFurnitureManager::initialize): the hook rewrites its rows when the map is set up (Engine._item_hooks).
- Gifts: the scripts (`assets/script/<map>.bin`) give items with command 18 (cmd_set_item: + 4 item, + 8 count, + 0xc 0 = give, 1 = take; 16 bytes) and gold with command 19
  (cmd_set_gold: + 4 amount, + 8 0 = give; 12 bytes). A script block (initialize / execute / terminate, ScriptParam::setup) = name (16 bytes), + 0x14 header size, + 0x24 command count,
  + 0x28 offsets table, + 0x30 commands; a command = u16 number, flags, then its arguments. The hook (on CommandFunction) rewrites a gift's command just before the game runs it.
  A gold gift's command is too short to hold an item: when it must give one, the game is made to run a cmd_set_item written elsewhere instead (`redirect`, Engine._item_hooks).
  Tokens: command 20 (cmd_set_coin: + 4 amount, + 8 0 = give; 12 bytes) like gold; and the bestiary's reward, 300 000 tokens given by the game's code once its 210 monsters are met
  (checkCompletePictureBook: `bl addCasinoCoin`), changed at that call (Engine._item_hooks, _reward_after). Tokens can only go to a gift (a container's row has no field for them).
  Gold and tokens are never protected by Safety: they can be earned elsewhere.
  Only the command that gives changes: the story's switches are other commands of the same scene (cmd_set_flag, read in every gold gift's scene: the chapter 3 tunnel's money, the
  silver statuette's sale...), always run; a sum that becomes an item or nothing has to be earned elsewhere.

Monster drops ("Monster drops" setting, 'loot'): MonsterStatus::getDropItem rolls a monster's drop (MonsterData, excelParam + 0x80, 0x3c bytes a monster: + 0x10 its item, + 0x1f its rate,
0 to 7, none above) and MonsterParty::checkDropItem keeps it (+ 0x3eac the item, + 0x3eb0 the monster); without one, in chapter 3, getSpecialDropItem may give one of Torneko's finds. Random:
the game rolls as it does, then the item it found is drawn again among all (Engine._item_hooks, `loot`).

Every draw is a fixed function of the game's random number and the container (its flag) or the gift (its script and place): reopening, reloading or loading a state always gives the
same thing. The game's own random draws are never used (a drop adds the game's random state, read and not changed: loading a state before the fight gives the same drop again).

Dragon Quest V and VI (GAMES): their map files (`assets/map/<map>.stg`, magic 0x78563412) give their furniture table's offset at + 4; rows of 0x14 bytes, the count at + 0x12 of the
first one: + 0 a message (special furniture), + 4 the object, + 6 item, + 8 gold, + 0xa the fight of a mimic (an encounter row), + 0xc the door flag, + 0xe the "taken" flag, + 0x10 the
kind (DQ V 68, DQ VI 55: a chest); kind 0 rows that hold something are the twinkling spots of the floor. Their gifts: cmd_set_item / cmd_set_gold / cmd_set_coin numbered 55 to 57
(DQ V) and 150 to 152 (DQ VI), an item's arguments from + 8 (gold and tokens: + 4, as in DQ IV); a gold or token gift keeps its kind and only its amount changes (their CommandFunction has no single return where a gold
gift turned into an item could be put back). No bestiary reward. Items: their item list (`leveldata/dq?ds_item_list.dat`): byte 36 (DQ VI 37) its kind (11: tools and key
items), byte 39 (DQ VI 40) its use (6 tools, 7 keys, 8 and 9 key items, 10 the mini medal, 11 unused).
"""
import random, struct, zlib

UNCHANGED, SHUFFLED, RANDOM = 0, 1, 2                 # the "Items" setting (seed code: 'items')
LOOT_UNCHANGED, LOOT_RANDOM = 0, 1                    # the "Monster drops" setting (seed code: 'loot')
FURNITURE_MAGIC = 0xbc32
ROW = 0x18
CHEST = 7                                             # furniture kind of a chest (the only container a mimic can be in)
SCENE_KINDS = frozenset({41})                         # furniture that only shows messages, its item given by the scene's script: the Zenithian sword stuck in the ground (tdf5,
                                                      # object 6221: cmd_search_map_object, then cmd_set_item 33, a gift); left as it is
MEDAL = 132                                           # mini medal (an item; cmd_set_item gives it to the medal count)
OP_ITEM, OP_GOLD, OP_COIN = 18, 19, 20                # script commands cmd_set_item / cmd_set_gold / cmd_set_coin (CommandFunction: table 0x23b4c0 + 8 x number)
BESTIARY_COINS = 300000                               # the bestiary's reward, once all its 210 monsters are met (MaterielMenu_PICTUREBOOK_ROOT::checkCompletePictureBook, in the game's code)
NOT_ITEMS = frozenset({0, 158, 159, 160, 161, 162})   # empty entry, the duplicate iron safe (158), the unused entries (kind 11)
ZENITH = frozenset({33, 34, 62, 80, 89})              # the Zenithian equipment
KEY_ITEMS = frozenset({123, 124, 125, 127, 128} | set(range(133, 158))) | ZENITH          # keys (kind 7), Ra's mirror, the lunch basket of chapter 3, the important items (kind 10)
ALL_ITEMS = tuple(i for i in range(1, 174) if i not in NOT_ITEMS)       # every real item, the version for mobiles' 163 to 171 included
DRAWN_ITEMS = tuple(i for i in ALL_ITEMS if i != MEDAL)                 # what an item draws (random mode; the mini medal has its own share), the key items included, with or without Safety
WEIGHTS = {'chest': (('item', 70), ('gold', 12), ('medal', 6), ('empty', 6), ('mimic', 6)),
           'other': (('item', 76), ('gold', 12), ('medal', 6), ('empty', 6)),
           'gift': (('item', 75), ('gold', 10), ('coins', 5), ('medal', 5), ('empty', 5))}         # random mode: what a container or a gift draws
GIFTS = ('gift', 'gold gift', 'coin gift', 'bestiary')                   # what can hold casino tokens (a container cannot: its row has no field for them)

V2_MAGIC, V2_ROW = 0x78563412, 0x14                   # DQ V / VI map files and their furniture rows
# The items of each game: every real item, the key items (kept in place with Safety), the mini medal, the items a random draw gives (the key items included; a second copy of a key item
# kept under the same name for a step of a quest is left out: DQ V's tea sets, music boxes, honey cakes, Yggdrasil shoots, pendants).
_DQ5_ITEMS = tuple(i for i in range(1, 275) if i not in (256, 262, 263))
_DQ5_KEYS = frozenset(set(range(190, 209)) | {180, 210, 211, 214, 215} | set(range(219, 251)))
_DQ6_ITEMS = tuple(i for i in range(1, 272) if i not in (257, 258))
_DQ6_KEYS = frozenset(range(227, 256)) - {237}
GAMES = {
    'dq4': dict(v2=False, chest=CHEST, scene=SCENE_KINDS, ops=(OP_ITEM, OP_GOLD, OP_COIN), args=4, medal=MEDAL, last=174, items=ALL_ITEMS, keys=KEY_ITEMS, drawn=DRAWN_ITEMS, amounts_only=False, bestiary=True),
    'dq5': dict(v2=True, chest=68, scene=frozenset(), ops=(55, 56, 57), args=8, medal=209, last=275, items=_DQ5_ITEMS, keys=_DQ5_KEYS,
                drawn=tuple(i for i in _DQ5_ITEMS if i not in (209, 220, 224, 231, 232, 241, 249)), amounts_only=True, bestiary=False),
    'dq6': dict(v2=True, chest=55, scene=frozenset(), ops=(150, 151, 152), args=8, medal=237, last=272, items=_DQ6_ITEMS, keys=_DQ6_KEYS,
                drawn=tuple(i for i in _DQ6_ITEMS if i != 237), amounts_only=True, bestiary=False),
}


def game_key():
    from dq456_pc import games as GM
    return GM.profile().key


def game(key=None):
    """The items data of a game (GAMES; None: the game being played)."""
    return GAMES.get(key or game_key(), GAMES['dq4'])


# ---- the game files
def furniture(data):
    """Furniture table of a map file -> [(row, kind, item, gold, formation, monster, message, flag)]."""
    if len(data) < 8: return []
    b = struct.unpack_from('<i', data, 4)[0]
    if b <= 0 or b + 4 + 0x18 > len(data) or struct.unpack_from('<I', data, b)[0] != FURNITURE_MAGIC: return []
    t = b + 4; out = []
    for i in range(data[t + 0x16]):
        o = t + i * ROW
        if o + ROW > len(data): break
        item, gold, form, mon, msg, _door, flag = struct.unpack_from('<7H', data, o + 6)
        out.append((i, data[o + 0x14], item, gold, form, mon, msg, flag))
    return out


def furniture_v2(data):
    """DQ V / VI: furniture table of a map file -> [(row, kind, item, gold, mimic fight, mimic fight, message, flag)] (a mimic has its fight only: given twice, like DQ IV's formation and monster)."""
    if len(data) < 8 or struct.unpack_from('<I', data, 0)[0] != V2_MAGIC: return []
    t = struct.unpack_from('<I', data, 4)[0]
    if not t or t + V2_ROW > len(data): return []
    out = []
    for i in range(data[t + 0x12]):
        o = t + i * V2_ROW
        if o + V2_ROW > len(data): break
        msg, _obj, item, gold, form, _door, flag = struct.unpack_from('<I6H', data, o)
        out.append((i, data[o + 0x10], item, gold, form, form, msg, flag))
    return out


def content_of(item, gold, form, mon):
    if item: return ('item', item)
    if gold: return ('gold', gold)
    if mon: return ('mimic', form, mon)
    return ('empty',)


def script_commands(data):
    """Commands of a script file -> [(file offset, command number, bytes of the command and what follows)]."""
    out = []; names = (b'initialize\x00', b'execute\x00', b'terminate\x00')
    for c in range(0, len(data) - 0x40, 16):
        if not any(data.startswith(n, c) for n in names): continue
        X, = struct.unpack_from('<I', data, c + 0x14); N, B, _, C, size = struct.unpack_from('<5I', data, c + 0x24)
        if N > 5000 or c + X + (C & ~3) + size > len(data) or c + X + (B & ~3) + 4 * N > len(data): continue
        base = c + X + (C & ~3)
        for o in struct.unpack_from('<%dI' % N, data, c + X + (B & ~3)):
            p = base + o
            if p + 12 <= len(data): out.append((p, struct.unpack_from('<H', data, p)[0], data[p:p + 20]))          # (12 bytes at least: cmd_set_gold / cmd_set_coin; 16 for cmd_set_item; DQ V / VI: 4 more)
    return out


SCRIPT_HEAD = 4096


def script_key(size, head):
    """What identifies a script file in the engine's memory: (size, CRC of its first 4 KB)."""
    return (size, zlib.crc32(bytes(head[:SCRIPT_HEAD])))


def script_id(data): return script_key(len(data), data)


class Catalog:
    """Every container and gift of the game files. `slots`: {flag: (kind 'chest' / 'other', content)}; `gifts`: {script id: {offset: (kind 'gift' / 'gold gift', content, count)}};
    `golds`, `mimics`: the gold amounts and the mimics found (random mode draws among them)."""
    def __init__(self, read, names, key=None):
        self.slots = {}; self.gifts = {}; G = self.G = game(key); op_item, op_gold, op_coin = G['ops']
        rows = furniture_v2 if G['v2'] else furniture
        for n in sorted(names):
            if n.startswith('assets/map/') and n.endswith('.stg'):
                for _i, kind, item, gold, form, mon, msg, flag in rows(read(n)):
                    if not flag or kind in G['scene'] or msg or flag in self.slots: continue          # (a message: special furniture; a scene's object)
                    if not kind and not (G['v2'] and (item or gold or mon)): continue                  # (kind 0: doors, statues; DQ V / VI: a twinkling spot of the floor when it holds something)
                    if item or gold or mon or kind == G['chest']: self.slots[flag] = ('chest' if kind == G['chest'] else 'other', content_of(item, gold, form, mon))
            elif n.startswith('assets/script/') and n.endswith('.bin'):
                data = read(n); g = {}
                A = G['args']                                                                       # (where the arguments start: + 4, DQ V / VI + 8)
                for p, op, raw in script_commands(data):
                    if op == op_item and len(raw) >= A + 12:
                        item, count, mode = struct.unpack_from('<3i', raw, A)
                        if mode == 0 and 0 < item < G['last'] and count > 0: g[p] = ('gift', ('item', item), count)
                    elif op in (op_gold, op_coin):
                        amount, mode = struct.unpack_from('<2i', raw, 4)                                # (gold and tokens: from + 4 in every game)
                        if mode == 0 and amount > 0: g[p] = ('gold gift', ('gold', amount), 1) if op == op_gold else ('coin gift', ('coins', amount), 1)
                if g: self.gifts[script_id(data + b'\x00' * (-len(data) % 16) if G['v2'] else data)] = g          # (DQ V / VI: the engine knows a script by its heap block, 16 bytes a step)
        every = [c for _k, c in self.slots.values()] + [c for g in self.gifts.values() for _k, c, _n in g.values()]
        self.golds = sorted({c[1] for c in every if c[0] == 'gold'}) or [10]
        self.coins = sorted({c[1] for c in every if c[0] == 'coins'} | ({BESTIARY_COINS} if G['bestiary'] else set()))
        self.mimics = sorted({c[1:] for c in every if c[0] == 'mimic'})

    @classmethod
    def from_fs(cls, fs, key=None):
        """From the engine's game files (emu_core.ApkFs), read straight from the archives (not kept in its file cache)."""
        names = [n for n in fs.names if n.startswith(('assets/map/', 'assets/script/'))]
        return cls(lambda n: fs.names[n].read(n), names, key)


# ---- the draws
def _key_of(slot):
    return slot[0] if isinstance(slot[0], str) else 'g%d:%08x:%d' % slot[0]


def plan(catalog, number, mode, safety):
    """-> {'furniture': {flag: content}, 'gifts': {script id: {offset: (content, count, size of the command)}}, 'bestiary': content or None}, or None ("Items" unchanged).
    `safety`: the key items stay where they are and the gifts of items do not change (gold and tokens are not protected: they can be earned elsewhere); in random mode a key item
    can still be drawn anywhere else, with or without Safety (a second Zenithian sword in a jar...)."""
    if mode not in (SHUFFLED, RANDOM): return None
    G = getattr(catalog, 'G', None) or game('dq4')
    fixed = lambda c: safety and c[0] == 'item' and c[1] in G['keys']
    slots = [('f%d' % flag, kind, c) for flag, (kind, c) in sorted(catalog.slots.items()) if not fixed(c)]
    amounts = []                                                                                  # (DQ V / VI: the gold and tokens people give keep their kind, only the amount changes)
    for sid, g in sorted(catalog.gifts.items()):
        for off, (kind, c, _n) in sorted(g.items()):
            if safety and kind == 'gift': continue
            (amounts if G['amounts_only'] and kind != 'gift' else slots).append(((sid[0], sid[1], off), kind, c))
    if G['bestiary']: slots.append(('bestiary', 'bestiary', ('coins', BESTIARY_COINS)))
    out = {}
    if mode == SHUFFLED:
        movable = [s for s in slots if s[2][0] != 'empty']                                       # (the empty containers stay empty)
        rng = random.Random('%d/items/shuffle' % number); taken = set(); placed = {}
        for what, where in (('mimic', ('chest',)), ('coins', GIFTS)):                            # (a mimic only in a chest, tokens only in a gift)
            contents = [s[2] for s in movable if s[2][0] == what]; room = [i for i, s in enumerate(movable) if s[1] in where and i not in taken]
            rng.shuffle(contents)
            for i, c in zip(sorted(rng.sample(room, min(len(contents), len(room)))), contents): placed[i] = c; taken.add(i)
        others = [s[2] for s in movable if s[2][0] not in ('mimic', 'coins')]; rng.shuffle(others); oi = iter(others)
        for i, s in enumerate(movable): out[_key_of(s)] = placed[i] if i in placed else next(oi, ('empty',))
    else:
        items = G['drawn']
        for s in slots:
            kind = 'gift' if s[1] in GIFTS else s[1]
            if kind == 'other' and s[2][0] == 'empty': continue                                   # (an empty jar, barrel... stays scenery: only the containers that held something, and every chest)
            r = random.Random('%d/items/%s' % (number, _key_of(s)))
            choices = [k for k, w in WEIGHTS[kind] if (k != 'mimic' or catalog.mimics) and (k != 'coins' or catalog.coins)]; weights = [w for k, w in WEIGHTS[kind] if k in choices]          # (DQ V / VI: no token anywhere)
            k = r.choices(choices, weights)[0]
            out[_key_of(s)] = (('item', r.choice(items)) if k == 'item' else ('gold', r.choice(catalog.golds)) if k == 'gold' else ('item', G['medal']) if k == 'medal'
                               else ('coins', r.choice(catalog.coins)) if k == 'coins' else ('mimic',) + tuple(r.choice(catalog.mimics)) if k == 'mimic' else ('empty',))
    if amounts:
        if mode == SHUFFLED:
            rng = random.Random('%d/items/amounts' % number)
            for kind in ('gold gift', 'coin gift'):
                group = [s for s in amounts if s[1] == kind]; values = [s[2] for s in group]; rng.shuffle(values)
                for s, v in zip(group, values): out[_key_of(s)] = v
        else:
            for s in amounts:
                r = random.Random('%d/items/%s' % (number, _key_of(s)))
                out[_key_of(s)] = ('gold', r.choice(catalog.golds)) if s[1] == 'gold gift' else ('coins', r.choice(catalog.coins))
    furn = {int(k[1:]): c for k, c in out.items() if k[0] == 'f'}
    gifts = {}
    for sid, g in catalog.gifts.items():
        for off, (_kind, _c, n) in g.items():
            k = 'g%d:%08x:%d' % (sid[0], sid[1], off)
            if k in out: gifts.setdefault(sid, {})[off] = (out[k], n, (G['args'] + 12) if _kind == 'gift' else 12)
    return {'furniture': furn, 'gifts': gifts, 'bestiary': out.get('bestiary')}


def loot(p, monster, item, state):
    """Monster drops: what monster `monster` drops instead of `item` (the game's own drop, its rate already rolled: never called without a drop), at the game's random state `state`.
    Random: any item (the mini medal aside), drawn again at each drop; with Safety, a monster whose drop is a key item keeps it (Ra's mirror, the silent sphere)."""
    l = p.get('loot') if p else None
    if not l or not item: return item
    G = game(l.get('game', 'dq4'))
    if l['safety'] and item in G['keys']: return item
    return random.Random('%d/loot/%d/%d/%d' % (l['number'], monster, item, state)).choice(G['drawn'])


def row_values(content, v2=False):
    """Content -> the (item, gold, formation, monster) of a furniture row (`v2`: DQ V / VI, (item, gold, mimic fight))."""
    k = content[0]
    if k == 'item': out = (content[1], 0, 0, 0)
    elif k == 'gold': out = (0, content[1], 0, 0)
    elif k == 'mimic': out = (0, 0, content[1], content[2])
    else: out = (0, 0, 0, 0)
    return out[:3] if v2 else out


def gift_command(content, count, room, ops=None, args=4):
    """Content of a gift -> (command number, its arguments) to write over the original command (`room`: its size, 16 for cmd_set_item, 12 for cmd_set_gold); None when it does not fit
    (an item in a gold gift's 12 bytes: see `redirect`). Gold or nothing (cmd_set_gold of 0) fits in 12. The command's flags (+ 2) stay. `ops`: the game's (item, gold, tokens) numbers;
    `args`: where the arguments start (DQ V / VI: + 8, their commands are 4 bytes longer)."""
    op_item, op_gold, op_coin = ops or (OP_ITEM, OP_GOLD, OP_COIN)
    if content[0] == 'item': return (op_item, struct.pack('<3i', content[1], count if count > 0 else 1, 0)) if room >= args + 12 else None
    if content[0] == 'coins': return op_coin, struct.pack('<2i', content[1], 0)
    return op_gold, struct.pack('<2i', content[1] if content[0] == 'gold' else 0, 0)


def redirect(content, flags):
    """The cmd_set_item the game runs instead of a gold gift that must give an item (written in a buffer of the port, 16 bytes; `flags`: the original command's 2 bytes at + 2,
    copied back to it after the run, so that the original keeps track of its run exactly as if it had run itself)."""
    return struct.pack('<H', OP_ITEM) + bytes(flags) + struct.pack('<3i', content[1], 1, 0)


# ---- the plan of a game
_catalogs = {}; _plans = {}


def plan_for_code(code, fs):
    """Items plan of a game from its seed code, with its monster drops ('loot': None unchanged); None: no randomizer, "Items" and "Monster drops" unchanged, or an unreadable code.
    The game files are read once (about 0.2 s), each plan made once."""
    from dq456_pc.randomizer import seed as SD
    s = SD.parse(code) if code else None
    if not s: return None
    o = s['options']; mode = o.get('items', UNCHANGED); safety = o.get('safety', 0) == 0
    if mode == UNCHANGED and o.get('loot', LOOT_UNCHANGED) == LOOT_UNCHANGED: return None
    key = (id(fs), s['code'])
    if key not in _plans:
        p = None; gk = game_key()
        if mode != UNCHANGED:
            cat = _catalogs.get(id(fs))
            if cat is None: cat = _catalogs[id(fs)] = Catalog.from_fs(fs, gk)
            p = plan(cat, s['number'], mode, safety)
        p = p or {'furniture': {}, 'gifts': {}, 'bestiary': None}
        p['loot'] = {'number': s['number'], 'safety': safety, 'game': gk} if o.get('loot') == LOOT_RANDOM else None
        _plans[key] = p
    return _plans[key]
