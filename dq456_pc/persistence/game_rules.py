"""Rules of each game, one small file per game: <saves>/rules/<ID in 8 hexadecimal digits>.json, next to the adventure logs (exported and imported with them).

The ID is the game's unique ID (status::g_Game + 8, kept in the adventure log). The original draws it among 256 values; the port gives each new game a 32-bit one, never below 256
(engine.UNIQUE_ID_STORE): a game whose ID is below 256 was started before the port's rules (its file is made the first time it is played, with the settings the port started with, no seed).
Contents: {"format": 1, "id", "created", "difficulty": {level, rates, heals}, "cheats": {...}, "randomizer": {"seed": code or null}} (files written before 16/11 also have "settings":
the display, sound and controls of that game, no longer read).
Each game keeps its rules (GAME_KEYS: difficulty, cheats; and its seed): a new game starts with their defaults (the "new game" panel), playing a game puts its own values in the
settings, and what is changed during it is written back to its file. Every other setting (APP_KEYS: display, sound, controls, interface, language, window) is the application's, the
same for every game and every save (decided on 16/11): the "new game" panel shows them too. A game whose file lacks some rules (older file, game started before the port's rules)
gets those the port started with."""
import json
import os
import re
import time

from dq456_pc.persistence import settings as RG
from dq456_pc.persistence.write_dir import atomic_write

FOLDER = 'rules'
FORMAT = 1
FIRST_PORT_UID = 0x100
DIFFICULTY_KEYS = ('difficulty',) + RG.RATE_KEYS + ('level_up_heal', 'battle_end_heal')
CHEAT_KEYS = ('random_encounters',)
GAME_KEYS = DIFFICULTY_KEYS + CHEAT_KEYS                                    # the rules of each game
APP_KEYS = tuple(k for k in RG.DEFAULT if k not in GAME_KEYS)                  # the application's: the same for every game (display, sound, controls, interface, language, window...)
SYNC_EVERY = 30                                                            # steps between two checks of the settings changed during a game (1 s; a slider being dragged is not written at every step)
RE_FILE = re.compile(r'^[0-9a-f]{8}\.json$')
RE_IN_ARCHIVE = re.compile(r'(?:^|[\\/])' + FOLDER + r'[\\/]([0-9a-fA-F]{8}\.json)$')


def folder(write_dir): return os.path.join(write_dir, FOLDER)


def path(write_dir, uid): return os.path.join(folder(write_dir), '%08x.json' % uid)


def _copy(x): return json.loads(json.dumps(x))


def sections(settings):
    """The rules of a game as the file keeps them (`settings`: read like a dict): {"difficulty", "cheats"}."""
    return {'difficulty': {k: _copy(settings[k]) for k in DIFFICULTY_KEYS}, 'cheats': {k: _copy(settings[k]) for k in CHEAT_KEYS}}


def snapshot(settings, seed_code):
    """The rules of a new game: the settings of the moment (`settings`: read like a dict), the randomizer's seed (None: a game without the randomizer)."""
    return dict({'format': FORMAT, 'created': time.strftime('%Y-%m-%d %H:%M:%S')}, **sections(settings), randomizer={'seed': seed_code})


def values(rules):
    """The rules of a game found in its file, checked like the settings file (settings.Settings: a wrong value gives the default): {key: value} for the keys it has."""
    data = {}
    for section in ('difficulty', 'cheats'):
        d = (rules or {}).get(section)
        if isinstance(d, dict): data.update(d)
    present = [k for k in GAME_KEYS if k in data]
    if not present: return {}
    data.setdefault('keys_version', RG.DEFAULT['keys_version']); data.setdefault('interface_version', RG.DEFAULT['interface_version'])
    v = RG.Settings(None, data=data).v
    return {k: v[k] for k in present}


def reset(settings):
    """The rules of a new game: the defaults (the application's settings stay)."""
    for k in GAME_KEYS: settings[k] = _copy(RG.DEFAULT[k])


def load(write_dir, uid):
    """The rules of the game `uid`, or None (no ID; file missing or unreadable)."""
    if not isinstance(uid, int) or uid < 0: return None
    try:
        with open(path(write_dir, uid), encoding='utf-8') as f: r = json.load(f)
        return r if isinstance(r, dict) else None
    except (OSError, ValueError): return None


def save(write_dir, uid, rules):
    """Writes the rules of the game `uid`. -> None, or the exception if the file could not be written (the game goes on, its rules stay in memory)."""
    return atomic_write(path(write_dir, uid), json.dumps(dict(rules, id=uid), ensure_ascii=False, indent=1).encode('utf-8'))


def files(write_dir):
    """The rules files of the saves folder: {name: path}."""
    try: names = sorted(n for n in os.listdir(folder(write_dir)) if RE_FILE.match(n))
    except OSError: return {}
    return {n: os.path.join(folder(write_dir), n) for n in names}


class GameRules:
    """The rules of the game being played, followed step by step (Game._step). A new game (Engine.new_game_uid) gets the rules prepared just before (the "new game" panel: `prepare`),
    otherwise those of the moment. Entering a game (adventure log, savestate, the new game itself) reads its file and puts its settings in `settings`; the settings it lacks (a game
    started before the port's rules, an older file) are those the port started with (`startup`). During the game, the settings changed are written to its file (checked every SYNC_EVERY steps)."""

    def __init__(self, write_dir, settings=None):
        self.write_dir = write_dir; self.uid = None; self.rules = None; self.pending = None; self.error = None; self.seen = None; self.steps = 0
        self.startup = {k: _copy(settings[k]) for k in GAME_KEYS} if settings is not None else None

    def prepare(self, rules): self.pending = rules

    def update(self, engine, settings, apply=None):
        """`apply`: called after the settings of the game entered are put in `settings`."""
        new = getattr(engine, 'new_game_uid', None)
        if new is not None:
            engine.new_game_uid = None
            r = dict(self.pending or snapshot(settings, None), id=new); self.pending = None          # (without the panel: no randomizer)
            self.error = save(self.write_dir, new, r); self.uid, self.rules = None, r          # (read again when the game is entered)
            if hasattr(engine, 'forget_items_plan'): engine.forget_items_plan()             # (the randomizer reads this game's seed again)
            return
        if not getattr(engine, 'in_game', lambda: True)(): self.uid = None; return              # (title, start menu: the next game entered reads its rules)
        uid = engine.game_uid() if hasattr(engine, 'game_uid') else None
        if uid is None: return
        if uid != self.uid:
            r = load(self.write_dir, uid) or {'format': FORMAT, 'created': time.strftime('%Y-%m-%d %H:%M:%S'), 'randomizer': {'seed': None}}
            r.pop('settings', None)                                                 # (an older file's display, sound and controls: the application's now, dropped at its next writing)
            vals = values(r); base = self.startup or {k: _copy(settings[k]) for k in GAME_KEYS}
            for k in GAME_KEYS: settings[k] = _copy(vals[k] if k in vals else base[k])
            self.uid = uid; self.rules = dict(r, id=uid, **sections(settings)); self.seen = json.dumps(sections(settings), sort_keys=True); self.steps = 0
            if len(vals) < len(GAME_KEYS): self.error = save(self.write_dir, uid, self.rules)          # (completed: written)
            if apply is not None: apply()
            return
        self.steps += 1
        if self.steps % SYNC_EVERY: return
        mine = sections(settings); seen = json.dumps(mine, sort_keys=True)
        if seen != self.seen:                                                       # (changed during the game: kept with it)
            self.seen = seen; self.rules = dict(self.rules, **mine); self.error = save(self.write_dir, uid, self.rules)

    def seed(self):
        """Seed code of the game being played, or None (game started without the randomizer)."""
        r = (self.rules or {}).get('randomizer')
        return r.get('seed') if isinstance(r, dict) else None

    def seed_of(self, uid):
        """Seed code of the game `uid` (the randomizer asks it as soon as the engine sets up a map, possibly before `update` has seen the game): the rules in memory if they are that
        game's (a new game's included), otherwise its file; None without the randomizer."""
        r = self.rules if self.rules is not None and self.rules.get('id') == uid else load(self.write_dir, uid)
        r = (r or {}).get('randomizer')
        return r.get('seed') if isinstance(r, dict) else None
