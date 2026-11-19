"""The games of the port: one profile per game (Dragon Quest IV, V and VI share the same engine design and the same viewer).

The running game is chosen by the environment variable DQ_GAME (`dq4`, `dq5` or `dq6`; default `dq4`), which the launchers set
(`launch_dq4.bat`, `launch_dq5.bat`, `launch_dq6.bat`), or on the command line: `python -m dq456_pc --game dq5` (see `__main__.py`).
The game's key is also the name of its folders in `data\\apk`, `data\\saves` and `data\\cache` (see paths.py)."""
import os
from typing import NamedTuple

ENV = 'DQ_GAME'
DEFAULT = 'dq4'


class Profile(NamedTuple):
    key: str            # folder name in data\apk, data\saves and data\cache
    name: str           # name shown to the player
    library: str        # the game engine inside split_config.arm64_v8a.apk
    playable: bool      # this version runs the game; otherwise the launcher only checks its files and stops with a message
    title_map: str      # the map of the title screen (a scene without a hero whose camera the game sets by itself)


GAMES = {p.key: p for p in (
    Profile('dq4', 'Dragon Quest IV', 'lib/arm64-v8a/libdq4core.so', True, 'ev01'),
    Profile('dq5', 'Dragon Quest V', 'lib/arm64-v8a/libdq5core.so', True, 'ev17'),
    Profile('dq6', 'Dragon Quest VI', 'lib/arm64-v8a/libdq6core.so', True, 'e02din1'),
)}


def profile(key=None, env=None):
    """The profile of `key`, or of the game named by DQ_GAME in `env` (default: the process environment), or of the default game. Raises ValueError for an unknown game."""
    env = os.environ if env is None else env
    k = (key or env.get(ENV) or DEFAULT).strip().lower()
    if k not in GAMES: raise ValueError('unknown game "%s" (expected: %s)' % (k, ', '.join(GAMES)))
    return GAMES[k]


def game_from_argv(argv):
    """The value of `--game X` / `--game=X` in a command line, or None."""
    for i, x in enumerate(argv):
        if x == '--game' and i + 1 < len(argv): return argv[i + 1]
        if x.startswith('--game='): return x.split('=', 1)[1]
    return None
