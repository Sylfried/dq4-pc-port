"""Seed code of the randomizer: every setting of the Randomizer page and a random number, in a short text the player can copy and type again ("58Q00000005H").

Entering a seed sets every setting of the page (no need to choose them); the seed of the game being played is shown in the menu, to reuse it in another game.
Code = format version (1 character), the settings of that version (in OPTIONS order; version 2: one character per setting; from version 3: packed together, a mixed-radix number
written in as few characters as it needs), the random number (8 characters, 40 bits), a check character;
Crockford's base 32 (no I, L, O, U: typing I or L gives 1, O gives 0, lowercase is accepted), shown in one piece (dashes and spaces typed are ignored). Each version keeps its list of settings:
a code of an older version keeps its meaning (the settings added after it take their first value, "unchanged"; renamed ones: _older)."""
import secrets

ALPHABET = '0123456789ABCDEFGHJKMNPQRSTVWXYZ'
VERSION = 7
OPTIONS = {1: (), 2: (('safety', 2), ('items', 3)),
           3: (('safety', 2), ('items', 3), ('zones', 4), ('groups', 3), ('terrain', 2)),
           4: (('safety', 2), ('items', 3), ('zones', 4), ('groups', 3), ('terrain', 2), ('bosses', 3), ('boss_encounters', 2), ('boss_companions', 2), ('two_bosses', 2)),
           5: (('safety', 2), ('items', 3), ('encounters', 3), ('boss_encounters', 2), ('terrain', 2), ('bosses', 3), ('two_bosses', 2)),
           6: (('safety', 2), ('items', 3), ('encounters', 3), ('boss_encounters', 2), ('bosses', 3), ('two_bosses', 2)),
           7: (('safety', 2), ('items', 3), ('loot', 2), ('encounters', 3), ('single_enemy', 2), ('boss_encounters', 2), ('bosses', 3), ('two_bosses', 2))}
# format version -> ((setting, number of values), ...): the Randomizer page's settings, added by the randomizer's steps (a new setting = a new version). 'safety' 0 on, 1 off;
# 'items' 0 unchanged, 1 shuffled, 2 random, 'loot' 0 unchanged, 1 random (randomizer/items.py); 'encounters' 0 unchanged, 1 shuffled, 2 random; 'single_enemy' 0 no, 1 yes (random encounters only); 'boss_encounters' 0 no, 1 yes; 'bosses' 0 unchanged,
# 1 shuffled, 2 random; 'two_bosses' 0 no, 1 yes (randomizer/encounters.py; Safety does not change the bosses). Versions 3 and 4 had 'zones' (4 values) and 'groups' (3 values)
# for the random encounters: read as 'encounters'; versions 3 to 5 had 'terrain', no longer a setting (_older).
RANDOM_DIGITS = 8                    # 40 bits
PACKED_FROM = 3                      # from this version, the settings are packed (a code stays short as the settings grow)


def _option_digits(version):
    opts = OPTIONS[version]
    if version < PACKED_FROM: return len(opts)
    total, n = 1, 0
    for _k, k_n in opts: total *= k_n
    while 32 ** n < total: n += 1
    return n


def _pack(version, values):
    """Characters of the settings `values` (in OPTIONS[version] order)."""
    if version < PACKED_FROM: return list(values)
    x = 0
    for (_k, n), v in zip(OPTIONS[version], values): x = x * n + v
    d = _option_digits(version); return [(x >> (5 * (d - 1 - i))) & 31 for i in range(d)]


def _unpack(version, chars):
    """-> the settings' values (in OPTIONS[version] order), or None if a value is out of range."""
    opts = OPTIONS[version]
    if version < PACKED_FROM: return None if any(v >= n for (_k, n), v in zip(opts, chars)) else list(chars)
    x = 0
    for c in chars: x = x * 32 + c
    values = []
    for _k, n in reversed(opts): values.append(x % n); x //= n
    return None if x else values[::-1]


def _check(values):
    return sum((i + 1) * v for i, v in enumerate(values)) % len(ALPHABET)


def _text(values):
    return ''.join(ALPHABET[v] for v in values + [_check(values)])


def new_code(options=None, number=None):
    """Code of the current version: `options` {setting: value} (missing: 0), `number` (default: drawn at random, 40 bits)."""
    options = options or {}
    if number is None: number = secrets.randbits(5 * RANDOM_DIGITS)
    values = [VERSION] + _pack(VERSION, [int(options.get(k, 0)) % n for k, n in OPTIONS[VERSION]])
    values += [(number >> (5 * (RANDOM_DIGITS - 1 - i))) & 31 for i in range(RANDOM_DIGITS)]
    return _text(values)


def _older(options):
    """The settings of an older version as the current version names them: 'zones' (1 tables swapped, 2 shuffled, 3 random) and 'groups' (1 among the existing, 2 free) of versions 3
    and 4 -> 'encounters' (random when the groups were free or the zones random, shuffled for the other changes); 'boss_companions' (version 4) and 'terrain' (versions 3 to 5)
    are no longer settings."""
    o = dict(options)
    zones, groups = o.pop('zones', None), o.pop('groups', None); o.pop('boss_companions', None); o.pop('terrain', None)
    if zones is not None or groups is not None:
        o['encounters'] = 2 if (zones == 3 or groups == 2) else 1 if (zones or groups) else 0
    return o


def parse(text):
    """-> {'version', 'options' {setting: value, every setting of the current version}, 'number', 'code' (written cleanly)}, or None if `text` is not a valid code."""
    raw = ''.join(c for c in str(text or '').upper() if c not in ' -_')
    raw = raw.replace('O', '0').replace('I', '1').replace('L', '1')
    if not raw or any(c not in ALPHABET for c in raw): return None
    values = [ALPHABET.index(c) for c in raw]
    version = values[0]
    if version not in OPTIONS: return None
    opts, d = OPTIONS[version], _option_digits(version)
    if len(values) != 1 + d + RANDOM_DIGITS + 1 or _check(values[:-1]) != values[-1]: return None
    got = _unpack(version, values[1:1 + d])
    if got is None: return None
    options = {k: 0 for k, _n in OPTIONS[VERSION]}
    options.update(_older({k: v for (k, _n), v in zip(opts, got)}))
    number = 0
    for v in values[1 + d:-1]: number = number * 32 + v
    return {'version': version, 'options': options, 'number': number, 'code': _text(values[:-1])}
