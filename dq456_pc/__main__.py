"""`python -m dq456_pc` launches the game; `--game dq5` (or the environment variable DQ_GAME) chooses which one (see games.py).

The game is chosen BEFORE the rest of the port is imported: paths.py computes its folders at import time. The exit code is the one of `main`
(1: the game stopped on an error, 3: this version does not run this game), read by the launchers."""
import os
import sys

from dq456_pc import games as GM

_game = GM.game_from_argv(sys.argv[1:])
try: GM.profile(_game)
except ValueError as ex:
    print('Game: %s' % ex, flush=True)
    sys.exit(2)
if _game: os.environ[GM.ENV] = _game.strip().lower()

from dq456_pc.main import main      # noqa: E402 (after the choice of the game)

sys.exit(main())
