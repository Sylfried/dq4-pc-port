"""Randomizer, encounters and bosses (design: category 3): the random encounters (monsters shuffled or groups built at random, a boss now and then) and the boss fights.
The other battles of the story (cmd_encount) and the mimics stay as they are.

How the game draws a random encounter (read in libdq4core.so):
- A "zone" is a row of EncountData (excelParam + 0xa0, 256 rows of 40 bytes): + 2 twelve monster slots A to L (u16, 1000 = none), two special parties M, N (EncountSpecial), then the
  zone's parameters. The zone of the place: on the world map, the block's byte in the chapter's tile table (chapters 1, 2, 4: EncountTile1, excelParam + 0x130; 3: Tile2, + 0x138;
  5, 6: Tile3, + 0x140), at sea the sea table (+ 0x128), and two small tables (+ 0x148, + 0x150); in a town or a dungeon, its entry of MonsterMap (+ 0xc0, 12 bytes: + 0 the zone).
  The zone is kept in Encount + 8.
- `Encount::brew` (called by FieldSystem::execEncount and Encount::execDungeon for a random encounter, by forceBrew / forceEventBrew for the story's battles and the mimics):
  EncountParam::setup(zone) (+ 0x4c), the game's pattern draws which slots appear and how many, the four groups are written in Encount + 0x34 (monsters) and + 0x44 (counts),
  then execThinning (+ 0x1c4) takes monsters off the largest group until they fit on the screen (the widths summed must not pass 255).
- The hooks (Engine._encounter_rando_hooks): a random encounter (or a script's fight) is told by brew's return address; its groups are rewritten just before execThinning, so that
  the game itself fits them on the screen.

Settings (seed code): 'encounters' 0 unchanged, 1 shuffled (each monster replaced everywhere by the same other one), 2 random (each battle draws its monsters and their number: 1 to 8
monsters, each number as likely, in 1 to 4 groups); 'single_enemy' (with random only): one monster at a time; 'boss_encounters': a random encounter is now and then a boss. Any monster can appear anywhere (sea or land: the terrain is not followed).
A shuffle is a fixed function of the seed; a random battle or a boss encounter is a fixed function of the seed and of the game's own random state at that moment (the same savestate
gives the same battle). The game's random draws are never used.

Bosses (with or without Safety: "Unchanged" keeps them): a boss fight is a row of EncountData that a script starts (cmd_encount and its variants: Encount::forceBrew / forceEventBrew, the row in Encount + 8)
whose special party (slot M: excelParam + 0xb8, 32 bytes, four groups of (monster, least, most) from + 2) holds a monster met nowhere else (BOSS_ROWS). Its boss part (those monsters)
and its companions (the monsters also met in random encounters) are kept apart. 'bosses' 0 unchanged, 1 shuffled (each boss fight gets another fight's boss part), 2 random (each draws
one, repeats allowed); 'two_bosses': a second boss part joins each boss fight. The fights the story needs as they are stay unchanged: the chapter 2 tournament (159 to 163), the chapter 4
fight lost in advance (169), the story's fights of ordinary monsters, the mimics. A boss fight is still won or lost as before: the scripts that follow only read the result; a boss met in
a random encounter sets no story switch (the scripts set them around cmd_encount). A replaced boss no longer drops its item (Sire Rosegarde, 193: the Orb of Silence, 142).
"""
import random, struct

UNCHANGED, SHUFFLED, RANDOM = 0, 1, 2                              # 'encounters'
NONE = 1000                                                        # an empty monster slot
ROW = 40; SLOTS = 12
TILES = ((0x130, 'EncountTile1'), (0x138, 'EncountTile2'), (0x140, 'EncountTile3'), (0x148, 'EncountGotTile'), (0x150, 'EncountYamiTile'))
SEA = (0x128, 'EncountSeaTile')
ZONES, MONSTER_MAP = 0xa0, 0xc0                                    # excelParam: EncountData, MonsterMap
FREE_TOTAL = 8                                                     # random: a battle's monsters, 1 to 8, each number as likely (then 1 to 4 groups, as many as that number allows;
                                                                   # the game then fits them on the screen): the game's own battles have 1 to 8 (mostly 1 to 3)
SPECIALS, SPECIAL_SIZE, SPECIAL_SLOT = 0xb8, 32, 12                # excelParam + 0xb8: the special parties (SpecialParty::setup); EncountData's slot M (12): a row's special party
BOSS_ROWS = (157, 158, 170, 172, 173, 174, 175, 176, 177, 179, 180, 181, 182, 183, 184, 185, 241, 243)    # the boss fights the scripts start (read in assets/script: cmd_encount 120,
                                                                   #  cmd_encount_set_flag 136, cmd_battle_end_flag_set 270, cmd_encount_first_strike 356); 180 / 181: the same boss
BOSS_ENCOUNTER_RATE = 1 / 32.0                                     # 'boss_encounters': part of the random encounters that become a boss
UNCHANGED_BOSSES, SHUFFLED_BOSSES, RANDOM_BOSSES = 0, 1, 2         # 'bosses'

# Dragon Quest V and VI: their tables are files of the game (`assets/leveldata/dq?ds_<name>.dat`, args::ExcelBinaryData: a header of 20 bytes, + 4 the row count, + 8 the row size, then the rows).
# `encount_data` (28 bytes a row): + 2 to + 0xb the ten monster slots (one byte: 0 = none), + 0xc the row's special party; `encount_special` (8 bytes): + 0 to + 3 the four groups' monsters, + 4 / + 5
# their counts, three bits each (btl::getAppearCount: 1 to 3 as is, 4: 1 or 2, 5: 2 or 3, 6: 2 to 4, 7: 4 to 7, 8: 8). The scripts start their fights with cmdEncount / cmd_encount_set_flag /
# cmd_battle_end_flag_set (DQ V 157 to 159, DQ VI 96 to 98; the row at + 8). Their bosses are the monsters the bestiary leaves out (`book_data`: one row per page, + 0 the monster;
# `monster`: one row per monster); their boss fights, the rows a script starts whose special party holds one. Kept as they are: the fights the story needs lost (DQ V: the ruins where Papas
# falls, rows 147 to 149; DQ VI: the first fight against Murdaw, 171); the mimics (furniture fights) are no script's.
V2 = {'dq5': dict(ops=(157, 158, 159), keep=(147, 148, 149)), 'dq6': dict(ops=(96, 97, 98), keep=(171,))}
APPEAR = {0: (0, 0), 1: (1, 1), 2: (2, 2), 3: (3, 3), 4: (1, 2), 5: (2, 3), 6: (2, 4), 7: (4, 7), 8: (8, 8)}


def level_table(data):
    """Rows of an args::ExcelBinaryData file."""
    n, size = struct.unpack_from('<2I', data, 4)
    return [data[20 + i * size: 20 + (i + 1) * size] for i in range(n) if 20 + (i + 1) * size <= len(data)]


class Catalog:
    """The random encounters of the game: `zones` {zone: [its 12 monster slots]}, `family` {zone: 'sea' / 'land'}, `monsters` {family: [monsters]} (those of its zones)."""

    def __init__(self, rows, sea, land, specials=None, special_of=None, boss_rows=BOSS_ROWS, boss_monsters=None):
        self.zones = {z: list(rows[z]) for z in sorted(set(sea) | set(land)) if 0 <= z < len(rows)}
        self.family = {z: ('sea' if z in sea else 'land') for z in self.zones}
        mons = {'sea': set(), 'land': set()}
        for z, slots in self.zones.items(): mons[self.family[z]].update(m for m in slots if m != NONE)
        self.monsters = {f: sorted(m) for f, m in mons.items()}
        self.all = sorted(mons['sea'] | mons['land'])
        self.bosses = {}                                                     # {row: (special party, [boss groups (monster, least, most)], [companion groups])}
        for row in boss_rows:
            sp = (special_of or {}).get(row)
            groups = [g for g in (specials or {}).get(sp, ()) if g[0] != NONE and g[2] > 0]
            boss = [g for g in groups if (g[0] in boss_monsters if boss_monsters is not None else g[0] not in mons['sea'] | mons['land'])]
            if boss: self.bosses[row] = (sp, boss, [g for g in groups if g not in boss])

    @classmethod
    def from_core(cls, core):
        """From the engine's memory (the tables are part of the game's code, reached through status::excelParam)."""
        ep = core.export('_ZN6status10excelParamE')
        P = lambda off: struct.unpack('<Q', core.mem(ep + off, 8))[0]
        I = lambda cls_, f: struct.unpack('<i', core.mem(core.export('_ZN5param%d%s%d%sE' % (len(cls_), cls_, len(f), f)), 4))[0]
        def table(off, name): return set(core.mem(P(off), I(name, 'width_') * I(name, 'height_'))) - {0xff}
        n = I('EncountData', 'size_'); data = core.mem(P(ZONES), n * ROW)
        rows = [struct.unpack_from('<12H', data, z * ROW + 2) for z in range(n)]
        land = set()
        for off, name in TILES: land |= table(off, name)
        mm = P(MONSTER_MAP)
        for i in range(I('MonsterMap', 'size_')):
            z = struct.unpack('<H', core.mem(mm + 12 * i, 2))[0]
            if z: land.add(z)                                                                # (0: a place without random encounters)
        sp = core.mem(P(SPECIALS), SPECIAL_SIZE * 128)
        specials = {i: [struct.unpack_from('<3H', sp, i * SPECIAL_SIZE + 2 + 6 * k) for k in range(4)] for i in range(128)}
        special_of = {r: struct.unpack_from('<H', data, r * ROW + 2 + 2 * SPECIAL_SLOT)[0] for r in BOSS_ROWS if r < n}
        return cls(rows, table(*SEA), land - table(*SEA), specials, special_of)

    @classmethod
    def from_files(cls, read, names, key):
        """DQ V / VI: from their game files (`read(name)` -> bytes; `names`: the script files' names). The empty slots (0) become NONE."""
        from dq456_pc.randomizer import items as IT
        G = V2[key]
        data = level_table(read('assets/leveldata/%sds_encount_data.dat' % key)); spec = level_table(read('assets/leveldata/%sds_encount_special.dat' % key))
        rows = [tuple((m or NONE) for m in r[2:0xc]) + (NONE, NONE) for r in data]
        zones = {z for z, r in enumerate(data) if any(r[2:0xc])}
        specials = {i: [(r[k] or NONE, ) + APPEAR.get((r[4 + k // 2] >> (3 * (k % 2))) & 7, (0, 0)) for k in range(4)] for i, r in enumerate(spec)}
        book = {struct.unpack_from('<H', r, 0)[0] for r in level_table(read('assets/leveldata/%sds_book_data.dat' % key))}
        boss_monsters = set(range(1, len(level_table(read('assets/leveldata/%sds_monster.dat' % key))))) - book
        fights = set()
        for n in names:
            for _p, op, raw in IT.script_commands(read(n)):
                if op in G['ops'] and len(raw) >= 12: fights.add(struct.unpack_from('<i', raw, 8)[0])
        boss_rows = tuple(sorted(r for r in fights if 0 <= r < len(data) and r not in zones and r not in G['keep'] and 0 < data[r][0xc] < len(spec)
                                 and any(m in boss_monsters for m in spec[data[r][0xc]][:4])))
        special_of = {r: data[r][0xc] for r in boss_rows}
        return cls(rows, set(), zones, specials, special_of, boss_rows, boss_monsters)


def plan(cat, number, encounters, bosses=UNCHANGED_BOSSES, boss_encounters=0, two_bosses=0, single_enemy=0):
    """-> {'mode', 'monster_map' {zone: {monster: monster}}, 'zones' (the random encounters' zones), 'free' [monsters], 'number', 'boss_map' {row: [groups (monster, least, most)]},
    'boss_parts' [boss parts] (the bosses a random encounter may become, empty: none), 'single' (random encounters: one monster at a time; only with `encounters` random)},
    or None (everything as in the game)."""
    if encounters == UNCHANGED and not (bosses or boss_encounters or two_bosses): return None
    out = {'mode': encounters, 'monster_map': {}, 'zones': set(cat.zones), 'free': cat.all, 'number': number, 'single': bool(single_enemy) and encounters == RANDOM,
           'boss_map': _boss_map(cat, number, bosses, two_bosses), 'boss_parts': _boss_parts(cat) if boss_encounters else []}
    if encounters == SHUFFLED:
        rng = random.Random('%d/encounters/monsters' % number); other = list(cat.all); rng.shuffle(other); perm = dict(zip(cat.all, other))
        for z, slots in cat.zones.items(): out['monster_map'][z] = {m: perm[m] for m in set(slots) if m != NONE}
    return out


def _boss_parts(cat):
    """The boss parts of the game, one per boss (rows of the same special party: one boss), in row order."""
    seen, out = set(), []
    for row, (sp, boss, _c) in sorted(cat.bosses.items()):
        if sp not in seen: seen.add(sp); out.append(boss)
    return out


def _boss_map(cat, number, bosses, two_bosses):
    """{row: its groups [(monster, least, most)], at most 4} for each boss fight that changes."""
    if not (bosses or two_bosses) or not cat.bosses: return {}
    parts = _boss_parts(cat); sps = []
    for row, (sp, _b, _c) in sorted(cat.bosses.items()):
        if sp not in sps: sps.append(sp)
    rng = random.Random('%d/encounters/bosses' % number); index = {sp: i for i, sp in enumerate(sps)}
    if bosses == SHUFFLED_BOSSES: order = list(range(len(parts))); rng.shuffle(order)
    elif bosses == RANDOM_BOSSES: order = [rng.randrange(len(parts)) for _ in parts]
    else: order = list(range(len(parts)))
    second = [rng.choice([j for j in range(len(parts)) if j != order[i]] or [order[i]]) for i in range(len(parts))]
    out = {}
    for row, (sp, _b, comp) in sorted(cat.bosses.items()):
        i = index[sp]; g = list(parts[order[i]]) + (list(parts[second[i]]) if two_bosses else [])
        out[row] = (g + list(comp))[:4]
    return out


def boss_groups(p, row, state):
    """The four groups [(monster, count)] of the boss fight `row` (its counts drawn between least and most from the game's random state `state`), or None (unchanged)."""
    g = p.get('boss_map', {}).get(row)
    if not g: return None
    r = random.Random('%d/encounters/boss/%d/%d' % (p['number'], row, state))
    out = [(m, r.randint(lo, max(lo, hi))) for m, lo, hi in g]
    return out + [(0, 0)] * (4 - len(out))


def groups_for(p, zone, groups, state):
    """The four groups [(monster, count)] of a random encounter after the game's draw (`groups`, `zone`: its zone): now and then a boss ('boss_encounters'), otherwise the zone's
    monsters shuffled, or groups built at random ('single': one monster, a boss too)."""
    single = p.get('single')
    if p.get('boss_parts'):
        r = random.Random('%d/encounters/boss encounter/%d/%d' % (p['number'], zone, state))
        if r.random() < BOSS_ENCOUNTER_RATE:
            part = r.choice(p['boss_parts']); out = [(m, 1 if single else r.randint(lo, max(lo, hi))) for m, lo, hi in part][:1 if single else 4]
            return out + [(0, 0)] * (4 - len(out))
    if p['mode'] == RANDOM and zone in p['zones']:
        r = random.Random('%d/encounters/free/%d/%d' % (p['number'], zone, state)); ms = p['free']
        if single: return [(r.choice(ms), 1)] + [(0, 0)] * 3
        total = r.randint(1, FREE_TOTAL); n = r.randint(1, min(4, total)); cuts = sorted(r.sample(range(1, total), n - 1))
        return [(r.choice(ms), b - a) for a, b in zip([0] + cuts, cuts + [total])] + [(0, 0)] * (4 - n)
    m = p['monster_map'].get(zone)
    if not m: return groups
    return [(m.get(mon, mon), n) if n else (mon, n) for mon, n in groups]


# ---- the plan of a game
_catalogs = {}; _plans = {}


def plan_for_code(code, core):
    """Encounters plan of a game from its seed code (None: no randomizer, or everything as in the game)."""
    from dq456_pc.randomizer import seed as SD
    s = SD.parse(code) if code else None
    if not s: return None
    o = s['options']
    args = (o.get('encounters', 0), o.get('bosses', 0), o.get('boss_encounters', 0), o.get('two_bosses', 0), o.get('single_enemy', 0))
    if args[0] == UNCHANGED and not any(args[1:]): return None
    key = (id(core), s['code'])
    if key not in _plans:
        cat = _catalogs.get(id(core))
        if cat is None:
            from dq456_pc import games as GM
            gk = GM.profile().key
            if gk in V2:
                fs = core.fs; names = [n for n in fs.names if n.startswith('assets/script/')]
                cat = Catalog.from_files(lambda n: fs.names[n].read(n), names, gk)
            else: cat = Catalog.from_core(core)
            _catalogs[id(core)] = cat
        _plans[key] = plan(cat, s['number'], *args)
    return _plans[key]
