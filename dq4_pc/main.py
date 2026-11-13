"""Entry point of the port: `python -m dq4_pc` (this is what `launch_dq4.bat` does, at the project root).

Reads the arguments, takes over the old file layout if needed (paths.migrate), then opens the game window (fenetre/jeu.py).
All the default folders come from paths.py (the `data` folder at the project root)."""
import argparse
import gc
import os
import sys
import pyglet
from dq4_pc import paths as CH
from dq4_pc import language as LG
from dq4_pc.window.game import Game
from dq4_pc.window.helpers import restore_fullscreen_optimizations
from dq4_pc.persistence import settings as RG


def settings_file(argv, d):
    """This run's settings file: the command line's `--settings` if given, otherwise the default one (the language is read from it BEFORE building the parser: its help is in that language)."""
    a = list(sys.argv[1:] if argv is None else argv)
    for i, x in enumerate(a):
        if x == '--settings' and i + 1 < len(a): return a[i + 1]
        if x.startswith('--settings='): return x.split('=', 1)[1]
    return d.settings


def set_language(argv, d):
    """the tool's language ("language" setting of settings.json) for console messages and help, before the settings are loaded. -> 'fr' or 'en'."""
    return LG.select_language(LG.read_setting(settings_file(argv, d)))


def build_parser(d):
    """The command-line parser, in the current language (see set_language): `python -m dq4_pc --help`."""
    ap = argparse.ArgumentParser(prog='dq4_pc')
    ap.add_argument('--apk', default=None, help='folder of the 3 APK files; default: data\\apk\\fr or data\\apk\\en, whichever matches the language chosen in the Esc menu (read when the game starts, and again when the language changes: the game restarts on the title screen)')
    ap.add_argument('--saves-read', dest='saves_read', default=None, help='extra read-only folder containing data1.dat... (tests; default: none, the game reads and writes in data\\saves)')
    ap.add_argument('--saves-write', dest='saves_write', default=d.portage, help='saves folder (data1.dat... read and written by the game); default data\\saves (savestates are in data\\saves\\savestates)')
    ap.add_argument('--cache', default=None, help='folder of the files computed from the APKs; default data\\cache (French APK) or data\\cache_en (English APK)')
    ap.add_argument('--slot', type=int, default=0, help='save number to load directly (1-5), skipping the title screen; 0 (default) = the game starts with its logos, its title and its start menu')
    ap.add_argument('--force-monster', type=int, default=0, help='(test) every random encounter is this single monster (monster number of the game, as in the monster list); 0 (default) = the game as is. Scripted battles are not affected')
    ap.add_argument('--no-logos', action='store_true', help='skips the intro logos (SQUARE ENIX, ArtePiazza)')
    ap.add_argument('--logos', action='store_true', help='(test) plays the logos even for a screenshot')
    ap.add_argument('--width', dest='width_px', type=int, default=None, help='window width (default: the one from the Esc menu, otherwise 1280)'); ap.add_argument('--height', dest='height_px', type=int, default=None)
    ap.add_argument('--auto-message', type=int, default=0, help='automatically closes the message shown after loading')
    ap.add_argument('--clicks', dest='clicks', default=None, help='(test) simulated mouse clicks: "frame:x:y,frame:x:y:d,..." (d = 1 right click, 2 hover without click)')
    ap.add_argument('--original-message', action='store_true', help='keeps the field message window at its original (portrait) position instead of moving it to the bottom of the screen')
    ap.add_argument('--ui-pos', default='center', choices=['center', 'right', 'left'], help='position of the original interface column (portrait 450 x 800) in the 16/9 window')
    ap.add_argument('--no-preparation', action='store_true', help='(test) does not prepare the map, sprite and monster cache in the background')
    ap.add_argument('--hd', type=int, default=None, help='sprites: 0 original (sharp pixels), 1 EPX, 4 pixel perfect (2 and 3, removed, count as 1); default: the one from the Esc menu')
    ap.add_argument('--no-sound', action='store_true', help='turns the sound off for this session (the Esc menu can turn it back on)')
    ap.add_argument('--music-volume', dest='music_volume', type=float, default=None, help='music volume (0 to 1); default: the one from the Esc menu')
    ap.add_argument('--sfx-volume', dest='sfx_volume', type=float, default=None, help='sound effects volume (0 to 1); default: the one from the Esc menu')
    ap.add_argument('--full-screen', dest='full_screen', type=int, choices=(0, 1, 2), default=None, help='0 = starts the game in a window, 1 = full screen (borderless window at the desktop resolution); 2 (former exclusive full screen, removed) counts as 1; the window is created directly in this mode; default: the Esc menu setting (test screenshots stay windowed)')
    ap.add_argument('--edge-correction', dest='edge_correction', type=int, default=None, choices=range(0, 101), metavar='0-100', help="(debug) correction of the tilt of town sprites near the left / right edges of the screen, as a percentage: 0 = none (the original billboard, leaning outwards), 100 = full; default always full, it is no longer a player setting (environment variable DQ_EDGE_CORRECTION for the same thing)")
    ap.add_argument('--msaa', type=int, default=None, help='hardware antialiasing (0 = none, 4 = x4); default: the one from the Esc menu')
    ap.add_argument('--settings', dest='settings', default=d.settings, help='player settings file (Esc menu: display, sound, keys)')
    ap.add_argument('--history', dest='history', default=d.favorites, help='history favorites file (in data\\settings, never in the saves folder); the latest dialogues and battles go next to it, in history_recent.json')
    ap.add_argument('--battle-script', dest='battle_script', default=None, help='(test) keys during a battle: "n:mask,..." (n = frames since the start of the battle)')
    ap.add_argument('--shots-effect', dest='shots_effect', default=None, help='(test) screenshots at these frames of the battle start effect: "1,10,30,..."')
    ap.add_argument('--shots-battle', dest='shots_battle', default=None, help='(test) intermediate screenshots at these battle frames: "30,60,..."')
    ap.add_argument('--battle-frames', type=int, default=0, help='(test) takes the screenshot N frames after the start of a battle')
    ap.add_argument('--force-field', type=int, default=0, help='(test) forces the switch to the world map at this frame')
    ap.add_argument('--test-keys', dest='keys_test', default=None, help='(test) pressed keys: "loop_frame:NAME,..." (pyglet names: ESCAPE, DOWN, RETURN...)')
    ap.add_argument('--options-test', default=None, help='(test) Display page options applied along the way: "frame:Label=value;frame:Label=value" (JSON value)')
    ap.add_argument('--shots-loop', dest='shots_loop', default=None, help='(test) screenshots <shot>_b<n>.png at these loop frames (Esc menu included); the last one quits')
    ap.add_argument('--shot', default=None, help='(test) saves a screenshot then quits')
    ap.add_argument('--images', dest='frames', type=int, default=60)
    ap.add_argument('--script', default=None, help='(test) e.g. "20:2,30:0": frame:key mask')
    return ap


def choose_game_files(a, d):
    """the game version (APK) and its cache follow the chosen language; read when the game starts (and again when it starts again in another language)."""
    language = LG.current_language()
    if not a.apk_forced: a.apk, a.game_language = d.choose_apk(language)
    else: a.game_language = language
    if a.game_language != language: print('Game: no APK files for the language chosen (%s) in %s: using the %s ones' % (language, os.path.normpath(d.apk_for(language)), a.game_language), flush=True)
    if not a.cache_forced: a.cache = CH.language_cache(d, a.game_language)
    print('Game: APK files in %s' % a.apk, flush=True)


def args_for_restart(a, reg, d, request):
    """The arguments of the game started again (language change): the settings as they are now (the player may have changed them), the files of the new language, no entry logos, no direct start on a save;
    `request` (Game.reload_request): the savestate to load, the size and the position of the closed window."""
    a.hd = reg['sprite_mode']; a.msaa = reg['msaa']; a.full_screen = reg['window_mode']; a.music_volume = reg['music_volume']; a.sfx_volume = reg['sfx_volume']
    rs = request.get('size') or reg['resolution']
    if not (isinstance(rs, (list, tuple)) and len(rs) == 2): rs = (1920, 1080)
    a.width_px, a.height_px = int(rs[0]), int(rs[1]); a.reload_location = request.get('location')
    a.no_logos = True; a.logos = False; a.slot = 0; a.reload_state = request.get('state')
    choose_game_files(a, d)
    return a


def run_loop():
    """pyglet.app.run(interval=0): the fixed loop (Game._loop) runs before each draw, the drawing follows the vertical synchronization. pyglet schedules the redrawing of the windows at each call
    and never removes it: a game started again (language change, a savestate of the other language) drew every frame two times, then three... (the game slowed down, every vertical
    synchronization twice). The redrawing is removed when the loop stops."""
    try: pyglet.app.run(interval=0)
    finally: pyglet.clock.unschedule(pyglet.app.event_loop._redraw_windows)


def release_workers(game):
    """The background tasks of a game that closes stop (sprites and monsters smoothed in HD): what was still queued would run in the next game, beside it."""
    pool = getattr(game, 'pool', None)
    if pool is not None:
        try: pool.shutdown(wait=False, cancel_futures=True)
        except Exception: pass


def main(argv=None):
    d = CH.FOLDERS
    set_language(argv, d)             # (before the migration: its messages are in the tool's language)
    try: CH.migrate(d)
    except Exception as ex: print('File migration failed (%r): the game continues with the current folders.' % (ex,), flush=True)
    set_language(argv, d)             # (the migration may have brought reglages.json to its place)
    ap = build_parser(d)
    a = ap.parse_args(argv)
    reg = RG.Settings(a.settings)
    LG.select_language(reg['language'])          # language of the tool; the game's texts do not change
    if a.hd is None: a.hd = reg['sprite_mode']
    else: a.hd = reg['sprite_mode'] = RG.valid_sprites_mode(a.hd)
    if a.msaa is None: a.msaa = reg['msaa']
    else: reg['msaa'] = a.msaa
    if a.full_screen is None: a.full_screen = 0 if a.shot else reg['window_mode']
    else: a.full_screen = reg['window_mode'] = RG.valid_window_mode(a.full_screen)          # (2 = the old exclusive full screen: 1)
    rs = reg['resolution'] if isinstance(reg['resolution'], (list, tuple)) and len(reg['resolution']) == 2 else (1920, 1080)
    if a.width_px is None: a.width_px = int(rs[0]) if a.height_px is None else int(round(a.height_px * 16 / 9))
    if a.height_px is None: a.height_px = int(rs[1]) if a.width_px == int(rs[0]) else int(round(a.width_px * 9 / 16))
    if a.music_volume is None: a.music_volume = reg['music_volume']
    if a.sfx_volume is None: a.sfx_volume = reg['sfx_volume']
    a.apk_forced = a.apk is not None; a.cache_forced = a.cache is not None          # (--apk / --cache: tests, special installations; the game then keeps them when it starts again)
    choose_game_files(a, d)
    if not os.path.isfile(os.path.join(a.apk, 'base.apk')):
        for folder in (d.apk_fr, d.apk_en):
            try: os.makedirs(folder, exist_ok=True)         # (so that the player finds the two folders ready to receive the APKs)
            except OSError: pass
        print('\nThe APK files were not found.\nPut base.apk, split_config.arm64_v8a.apk and split_UnityDataAssetPack.apk of the French version in:\n   %s\nand those of the English version in:\n   %s\n(and, if you have one, the data1.dat... files of your phone save in %s). Other folder: set DQ4_DATA=path\\to\\data' % (os.path.normpath(d.apk_fr), os.path.normpath(d.apk_en), d.saves), flush=True)
        sys.exit(1)
    sys.setswitchinterval(0.001)      # the background HD computation must not delay the drawing
    if a.saves_read is None:
        a.saves_read = d.recent_mobile_save() or a.saves_write
    if a.script is not None:
        sc = {}; cur = 0; pts = sorted((int(x.split(':')[0]), int(x.split(':')[1], 0)) for x in a.script.split(','))
        a.script = {}
        for n in range(0, 100000):
            if n > a.frames + 5: break
            for (i, m) in pts:
                if n >= i: cur = m
            a.script[n] = cur
    lookup_key = lambda t: (int(t[1:].split('+')[0]), int((t[1:].split('+') + ['0'])[1])) if t[:1] == 'c' else int(t)
    a.keys_test = [(lookup_key(x.split(':')[0]), x.split(':')[1]) for x in a.keys_test.split(',')] if a.keys_test else []
    a.options_test = [(int(x.split(':', 1)[0]),) + tuple(x.split(':', 1)[1].split('=', 1)) for x in a.options_test.split(';')] if a.options_test else []
    a.shots_loop = set(lookup_key(x) for x in a.shots_loop.split(',')) if a.shots_loop else set()
    if a.shots_battle: a.shots_battle = set(int(x) for x in a.shots_battle.split(','))
    if a.shots_effect: a.shots_effect = set(int(x) for x in a.shots_effect.split(','))
    if a.clicks: a.clicks = [tuple(int(v) for v in c.split(':')) + (0,) * (4 - len(c.split(':'))) for c in a.clicks.split(',')]
    if a.battle_script is not None:
        pts = sorted((int(x.split(':')[0]), int(x.split(':')[1], 0)) for x in a.battle_script.split(','))
        sc = {}; cur = 0
        for n in range(0, 20000):
            for (i, m) in pts:
                if n >= i: cur = m
            sc[n] = cur
        a.battle_script = sc
    if not a.shot: restore_fullscreen_optimizations()      # (cancelled; Windows only, effective at the next launch)
    while True:
        game = Game(a, reg)
        try:
            run_loop()
        except Exception:
            game._fatal('the pyglet loop')          # last safeguard: an error outside _loop and on_draw
        if getattr(game, 'dead', False):
            return 1                                # the game stopped on an error: the launcher keeps the console open (launch_dq4.bat tests the exit code)
        request = getattr(game, 'reload_request', None)
        if request is None: return 0
        pyglet.clock.unschedule(game._guarded_loop); release_workers(game); del game; gc.collect()          # the game starts again (language change): this one is released (engine, textures) before the next one is created
        LG.select_language(reg['language'])
        a = args_for_restart(a, reg, d, request)


if __name__ == '__main__':
    sys.exit(main())
