"""All the port's folders and files, in one place (tidy-up, English names).

Everything that belongs to you (APKs, saves, caches, settings) is in ONE folder, `data\\`, at the project root; it is never sent to GitHub (.gitignore):

    data\\
      apk\\                    one folder per game (games.py: `dq4\\`, `dq5\\`, `dq6\\`)
        dq4\\
          fr\\                  the 3 APKs of the French version (base.apk, split_config.arm64_v8a.apk, split_UnityDataAssetPack.apk)
          en\\                  the 3 APKs of the English version: the game takes the APKs from the folder of the chosen language at STARTUP
      saves\\                  one folder per game (`dq4\\`, `dq5\\`, `dq6\\`)
        dq4\\                  A SINGLE folder: the exact content of the export .zip, to copy the phone's saves in one go
          data1.dat ... data5.dat, data9.dat the game's adventure logs (read and written by the engine; the phone's are copied here)
          savestates\\           the savestates of each game (<game ID>\\state_01.dqs ...)
          rules\\                the rules of each game (<game ID>.json)
          before_import_<date>\\ backups made before each import of saves
          before_tidy_<date>\\     old `portage\\` and `mobile\\` folders tidied away as they were by the migration (see `migrate`): safe to delete once your game progress is verified
      cache\\                    what the port computes from the APKs (maps, sprites, sounds, menus): safe to delete
        dq4\\fr\\, dq4\\en\\       one folder per game, then one per language, never mixed (earlier versions used `cache\\` and `cache_en\\` for DQ4: see `cache_per_game`)
      settings\\               shared by all the games: settings.json, history_favorites.json, history_recent.json (history_messages.json: old, no longer read)
      logs\\                   window_errors.log
      resume.json               the steps of the migration from the old layout that are already done

The running game comes from the environment variable DQ_GAME (games.py; default dq4). Two more environment variables, for tests and special installations (the old names DQ4_DATA, DQ4_DONNEES and DQ4_JEUX still work):
  DQ_DATA : another location for the whole `data` folder (all the games).
  DQ4_GAMES : (old behavior, DQ4 only) a "jeux\\DQ4" folder containing `patched_apks` and `saves\\<date>`; it replaces `data\\apk\\dq4`, and `saves\\<date>` remains a READ-ONLY copy of saves (tests, special installations).

English names: the folders and files that earlier versions created in French (`donnees`, `sauvegardes`, `etats\\etat_NN.dqs`, `reglages`, `journaux`, `avant_import_...`, `reprise.json`...) are RENAMED in place on the first startup
(`english_names` in `resume.json`): a simple rename, without copying, without overwriting or deleting anything; if a name already exists at the new place, the old file stays where it is and the step is still
marked done (this name will remain taken: repeating it at every launch teaches nothing). A rename that FAILS (locked folder, permissions) leaves the step open and is retried at the next startup.

Every earlier layout is DQ4's (the only game of those versions): `migrate` always works on DQ4's folders, whatever the running game.
`migrate` also migrates the old layout (jeux\\DQ4, dq4_pc\\cache, dq4_pc\\sauvegardes, dq4_pc\\reglages.json ...): it COPIES (or, for the cache only, moves) to the new one,
without ever overwriting a file already present and without deleting anything. Each migration happens ONLY ONCE: `data\\resume.json` records the steps done, so that what you delete in `data\\`
(a `before_import_...` folder, an adventure log, settings) is not copied back from the old folder at the next startup. A layout already in service (adventure logs, savestates, settings or cache in `data\\`) counts as a migration done."""
import glob
import json
import os
import re
import shutil
import time

from dq456_pc import games as GM
from dq456_pc import language as LG

CODE = os.path.dirname(os.path.abspath(__file__))                 # .../<project>/dq456_pc
ROOT = os.path.dirname(CODE)                                    # .../<project>
RESUME_FILE = 'resume.json'                                        # in data\: the migration steps already done
OLD_RESUME_FILE = 'reprise.json'                                   # (its name; renamed at first startup)
LOGFILE_NAMES = tuple('data%d.dat' % n for n in (1, 2, 3, 4, 5, 9))     # the game's files: data1 to data3 = adventure logs, data4 = suspend save, data5 = auto-save, data9 = most recent adventure log
LEGACY_GAME = 'dq4'                                                # the game of every earlier layout (see `migrate`)
RE_GAME_FOLDER = re.compile(r'^dq\d+$', re.I)                      # (the folders of the games: `dq4`, `dq5`, `dq6`...)


def _norm(p):
    return os.path.normpath(os.path.abspath(p))


class Folders:
    """The folders and files of a game (`game`: a key of games.py; default: DQ_GAME, then dq4), computed from the data root (and the environment variables)."""

    def __init__(self, root=ROOT, env=None, game=None):
        env = os.environ if env is None else env
        self._args = (root, env)
        self.profile = GM.profile(game, env)
        self.game = self.profile.key
        self.root = _norm(root)
        data_env = env.get('DQ_DATA') or env.get('DQ4_DATA') or env.get('DQ4_DONNEES')            # (DQ4_DATA, DQ4_DONNEES: its earlier names)
        games_env = (env.get('DQ4_GAMES') or env.get('DQ4_JEUX')) if self.game == LEGACY_GAME else None          # (DQ4_JEUX: same; a layout of DQ4 only)
        self.data = _norm(data_env) if data_env else os.path.join(self.root, 'data')
        self.custom_data = bool(data_env)
        self.old_games = _norm(games_env) if games_env else None        # variable from before the tidy-up
        self.apk_root = os.path.join(self.data, 'apk')                          # one folder per game
        self.apk_game = os.path.join(self.apk_root, self.game)                   # (the APKs are in `apk\\<game>\\fr` and `apk\\<game>\\en`; earlier versions put DQ4's in `apk\\fr`, `apk\\en` or directly in `apk`, migrated by `migrate`)
        self.apk_fr = os.path.join(self.old_games, 'patched_apks') if self.old_games else os.path.join(self.apk_game, 'fr')
        self.apk_en = os.path.join(self.old_games, 'patched_apks_en') if self.old_games else os.path.join(self.apk_game, 'en')
        self.apk = self.apk_fr                                                  # (the tools (IL2CPP dump, original menus) read the French APKs: the game code is the same in both languages)
        self.saves_root = os.path.join(self.data, 'saves')                     # one folder per game
        self.saves = os.path.join(self.saves_root, self.game)
        self.mobile = os.path.join(self.old_games, 'saves') if self.old_games else os.path.join(self.saves, 'mobile')       # (old folder of the phone copy, taken over by `migrate`; DQ4_JEUX: a copy that is read only)
        self.portage = self.saves                                                  # a single folder, where the game reads AND writes its adventure logs (data1.dat...), next to `savestates\\`
        self.old_port_dir = os.path.join(self.saves, 'portage')                  # (old write folder, taken over by `migrate`)
        self.savestates = os.path.join(self.saves, 'savestates')
        self.cache_root = os.path.join(self.data, 'cache')                     # one folder per game, then one per language
        self.cache = os.path.join(self.cache_root, self.game, 'fr')
        self.cache_en = os.path.join(self.cache_root, self.game, 'en')
        self.old_cache_en = os.path.join(self.data, 'cache_en')                # (DQ4's English cache before the cache was arranged by game: see `cache_per_game`)
        self.settings_dir = os.path.join(self.data, 'settings')                # (shared by all the games)
        self.settings = os.path.join(self.settings_dir, 'settings.json')
        self.favorites = os.path.join(self.settings_dir, 'history_favorites.json')
        self.resume_file = os.path.join(self.data, RESUME_FILE)
        self.logfiles = os.path.join(self.data, 'logs')
        self.window_logfile = os.path.join(self.logfiles, 'window_errors.log')

    def code_apk(self):
        """The APK folder the tools read the game's code and menu resources from (IL2CPP dump, original window layout): the French one, or the English one when only it
        holds APK files (the code is the same in both languages)."""
        if not glob.glob(os.path.join(self.apk_fr, '*.apk')) and glob.glob(os.path.join(self.apk_en, '*.apk')): return self.apk_en
        return self.apk_fr

    def for_game(self, game):
        """The same folders (same root, same environment) for another game."""
        return self if game == self.game else Folders(*self._args, game=game)

    # ---- game language ----------------------------------------------------------------------------------------------------
    def apk_for(self, language):
        """APK folder of the language ('fr' or 'en')."""
        return self.apk_en if language == 'en' else self.apk_fr

    def cache_for(self, language):
        """Cache of the files computed from the APKs of this language (`data\\cache\\<game>\\fr` or `data\\cache\\<game>\\en`)."""
        return self.cache_en if language == 'en' else self.cache

    def choose_apk(self, language):
        """(APK folder, game language) for the chosen language: its folder if it has `base.apk`, otherwise the folder of the other language (the player put in only one of the two versions: better a game in the other language than no game); with neither: the folder of the chosen language."""
        for lg in (language, 'fr' if language == 'en' else 'en'):
            if os.path.isfile(os.path.join(self.apk_for(lg), 'base.apk')): return self.apk_for(lg), lg
        return self.apk_for(language), language

    # ---- saves -------------------------------------------------------------------------------------------------------------------
    def recent_mobile_save(self):
        """Folder of the most recent phone copy (`mobile\\<date>`: the old arrangement, or DQ4_JEUX\\saves\\<date>; the date sorts like alphabetical order), or None."""
        folders = sorted(d for d in glob.glob(os.path.join(self.mobile, '*')) if os.path.isdir(d))
        return folders[-1] if folders else None

    def savestates_folder(self, write_dir):
        """Savestates folder for this write folder: `saves\\savestates` with the usual location (`saves`), otherwise `<write_dir>\\savestates` (tests, --saves-write)."""
        return self.savestates if _norm(write_dir) == _norm(self.portage) else os.path.join(write_dir, 'savestates')

    def clones_folder(self, write_dir):
        """Folder that receives the `before_import_<date>` copies: `saves\\` with the usual location, otherwise the write folder itself."""
        return self.saves if _norm(write_dir) == _norm(self.portage) else write_dir

    def errors_logfile(self):
        return os.environ.get('DQ_WINDOW_LOG') or self.window_logfile


FOLDERS = Folders()


# ---- English names ---------------------------------------------------------------------------------------------------------
OLD_FOLDER_NAMES = {'sauvegardes': 'saves', 'reglages': 'settings', 'journaux': 'logs', 'etats': 'savestates'}       # folders: old name -> new
OLD_FILE_PREFIXES = (('reglages.json', 'settings.json'), ('historique_favoris.json', 'history_favorites.json'), ('historique_messages.json', 'history_messages.json'),
                     ('erreurs_fenetre.log', 'window_errors.log'))                # files (and their `.tmp`, `.bak`... copies: the start of the name is enough)
OLD_FOLDER_PREFIXES = (('avant_import_', 'before_import_'), ('avant_rangement_', 'before_tidy_'))
RE_OLD_SAVESTATE = re.compile(r'^etat_(\d\d)\.dqs$', re.I)
OLD_STAGES = {'sauvegardes_portage': 'saves_pc_port', 'sauvegardes_telephone': 'saves_phone', 'reglages': 'settings', 'journal': 'log'}       # steps of resume.json -> new name
ENGLISH_STAGE = 'english_names'


def english_name(name_str, is_dir):
    """The English name of a folder or file created by the versions (`etats` -> `savestates`, `etat_01.dqs` -> `state_01.dqs`, `avant_import_<date>` -> `before_import_<date>`...), or None if it has not changed."""
    if is_dir:
        if name_str in OLD_FOLDER_NAMES: return OLD_FOLDER_NAMES[name_str]
        for old, new in OLD_FOLDER_PREFIXES:
            if name_str.startswith(old): return new + name_str[len(old):]
        return None
    m = RE_OLD_SAVESTATE.match(name_str)
    if m: return 'state_%s.dqs' % m.group(1)
    for old, new in OLD_FILE_PREFIXES:
        if name_str.startswith(old): return new + name_str[len(old):]
    if name_str == OLD_RESUME_FILE: return RESUME_FILE
    return None


def _move(src, dst, moves, problems):
    """Renames `src` to `dst` (same folder or neighboring folders, hence without copying) without overwriting or deleting anything: `dst` absent -> plain rename; two folders -> the content of `src` is moved one by one into `dst`
    (then `src` is removed if it is empty); two files -> `src` stays where it is (problem noted). Appends (src, dst) to `moves` for each rename done, (src, dst, reason) to `problems` otherwise."""
    if not os.path.lexists(src): return
    if os.path.isdir(src) and not os.path.islink(src) and (os.path.isdir(dst) or not os.path.lexists(dst)):
        if not os.path.lexists(dst):
            try: os.replace(src, dst); moves.append((src, dst, True)); return
            except OSError: pass                           # (e.g. a folder open in Explorer: the contents are tried one by one)
            try: os.makedirs(dst)
            except OSError as ex: problems.append((src, dst, str(ex))); return
        for child in sorted(os.listdir(src)): _move(os.path.join(src, child), os.path.join(dst, child), moves, problems)
        try: os.rmdir(src)
        except OSError: pass                                   # (not empty or locked: it stays, nothing is lost)
        return
    if not os.path.lexists(dst):
        try: os.replace(src, dst); moves.append((src, dst, False))
        except OSError as ex: problems.append((src, dst, str(ex)))
        return
    problems.append((src, dst, 'exists'))


def _rename_children(folder, moves, problems, deep=False):
    """Renames the entries of `folder` that still have an old name; `deep`: descends into subfolders, except the copies archived by the migration (`portage`, `mobile`, `before_tidy_...`), which are left as they are."""
    try: names = sorted(os.listdir(folder))
    except OSError: return
    for name_str in names:
        p = os.path.join(folder, name_str); is_dir = os.path.isdir(p)
        new = english_name(name_str, is_dir)
        if new and new != name_str:
            target = os.path.join(folder, new)
            _move(p, target, moves, problems)
            if os.path.lexists(target): p, name_str = target, new
        if deep and os.path.isdir(p) and name_str not in ('portage', 'mobile') and not name_str.startswith(('before_tidy_', 'avant_rangement_')): _rename_children(p, moves, problems, True)


def english_names(d):
    """renames in place the folders and files that earlier versions created in French. -> (renames, problems); see `_move`."""
    moves, problems = [], []
    if not d.custom_data:                                        # (with DQ_DATA / DQ4_DATA / DQ4_DONNEES, the folder is yours: it is not touched, only its contents are renamed)
        _move(os.path.join(d.root, 'donnees'), d.data, moves, problems)
    if os.path.isdir(d.data):
        _rename_children(d.data, moves, problems)                # saves, settings, logs, resume.json
        _rename_children(d.saves_root, moves, problems, deep=True)    # savestates, state_NN.dqs, avant_import_..., avant_rangement_... (names written by earlier versions; in `saves` or already in its game folder)
        _rename_children(d.settings_dir, moves, problems)
        _rename_children(d.logfiles, moves, problems)
    return moves, problems


def _describe_english_names(d, moves, problems):
    """The sentences that say what `english_names` did (empty: nothing)."""
    out = []
    folders = [m for m in moves if m[2]]; files = [m for m in moves if not m[2]]
    rel = lambda p: os.path.relpath(p, d.root) if _norm(p).startswith(d.root) else p
    if folders: out.append('folders renamed to English: %s' % ', '.join('%s -> %s' % (rel(a), rel(b)) for a, b, _ in folders[:12]))
    if files: out.append('%d file(s) renamed to English (settings, history, logs, savestates...)' % len(files))
    taken = list({a: (a, b) for a, b, reason in problems if reason == 'exists'}.values())        # (one same entry may be visited by two passes of `_rename_children`: it is counted only once)
    if taken:                          # a single sentence, even for 300 cache files: the full list is in the migration log, not on the console
        out.append('%d old file(s) kept where they are: a file of the same name already exists under its English name, nothing is overwritten (%s%s)'
                   % (len(taken), ', '.join(rel(a) for a, _b in taken[:5]), ', ...' if len(taken) > 5 else ''))
    for a, b, reason in problems:
        if reason != 'exists': out.append('NOT renamed: %s (%s). Close the windows or programs that use this folder, then restart: the renaming is retried automatically' % (rel(a), reason))
    return out


# ---- migration from the old layout ------------------------------------------------------------------------------------------------
def _clone(src, dst, log, num):
    """Copies a file if it does not yet exist at the destination; returns 1 if copied."""
    if os.path.exists(dst): return 0
    os.makedirs(os.path.dirname(dst), exist_ok=True)
    tmp = dst + '.tmp'
    shutil.copy2(src, tmp); os.replace(tmp, dst)
    return 1


def split_apk_by_language(d):
    """the APKs of this game in `data\\apk\\dq4\\fr` and `data\\apk\\dq4\\en` (one folder per game): the `fr` and `en` folders of `data\\apk` (older layout) go into `dq4`, and the
    APKs that earlier versions put directly in `data\\apk` into `dq4\\fr`; simple moves (nothing copied, nothing overwritten: a file already in its new place keeps the old one where it is).
    The folders of the other games (`dq5`, `dq6`...) are left as they are. -> list of sentences describing what was done."""
    done = []
    if d.old_games or not os.path.isdir(d.data): return done      # (DQ4_JEUX: `patched_apks` remains the French folder; no `data`: first installation, nothing to tidy, `main` creates the folders as needed)
    moves, problems = [], []
    try:
        for lg, folder in (('fr', d.apk_fr), ('en', d.apk_en)):
            _move(os.path.join(d.apk_root, lg), folder, moves, problems)
            os.makedirs(folder, exist_ok=True)
        if moves: done.append('APK files moved: data\\apk\\fr, data\\apk\\en -> data\\apk\\%s (one folder per game)' % d.game)
        moved = 0
        for f in sorted(glob.glob(os.path.join(d.apk_root, '*.apk'))):
            dest = os.path.join(d.apk_fr, os.path.basename(f))
            if not os.path.exists(dest): os.replace(f, dest); moved += 1
        if moved: done.append('%d APK file(s) moved: data\\apk -> data\\apk\\%s\\fr (the French version; put the English APK files in data\\apk\\%s\\en)' % (moved, d.game, d.game))
        for a, _b, reason in problems: done.append('NOT moved into data\\apk\\%s: %s (%s)' % (d.game, os.path.relpath(a, d.apk_root), 'already there' if reason == 'exists' else reason))
    except OSError as ex:
        done.append('APK folders NOT arranged (%s): the APK files stay where they are' % ex)
    return done


def _rel_data(d, p):
    """`p` as written in the messages: `data\\...` (Windows separators, as in the other messages) for a folder of `data`."""
    return 'data\\' + os.path.relpath(p, d.data).replace(os.sep, '\\') if _norm(p).startswith(d.data + os.sep) else p


def cache_per_game(d):
    """the cache in one folder per game, then per language (`data\\cache\\<game>\\fr`, `\\en`): what earlier versions computed for DQ4 directly in `data\\cache` (French APKs)
    and in `data\\cache_en` (English APKs) goes into `data\\cache\\dq4\\fr` and `data\\cache\\dq4\\en` (`d`: DQ4's folders). Simple moves (same volume, no copy: the cache weighs several hundred MB),
    nothing overwritten; the folders of the games (`dq4`, `dq5`...) are left as they are. A file already in its new place keeps the old one where it is, without a message (it is only a cache:
    it is recomputed). Always done: it moves, so it does not repeat itself. -> sentences describing what was done."""
    moves, problems = [], []
    try: names = sorted(n for n in os.listdir(d.cache_root) if not RE_GAME_FOLDER.match(n)) if os.path.isdir(d.cache_root) else []
    except OSError as ex: return ['cache NOT arranged by game (%s): it will be recomputed' % ex]
    try:
        if names: os.makedirs(d.cache, exist_ok=True)
        if os.path.isdir(d.old_cache_en): os.makedirs(os.path.dirname(d.cache_en), exist_ok=True)
    except OSError as ex: return ['cache NOT arranged by game (%s): it will be recomputed' % ex]
    for n in names: _move(os.path.join(d.cache_root, n), os.path.join(d.cache, n), moves, problems)
    _move(d.old_cache_en, d.cache_en, moves, problems)
    out = []
    if moves: out.append('cache arranged by game: data\\cache -> %s, data\\cache_en -> %s' % (_rel_data(d, d.cache), _rel_data(d, d.cache_en)))
    failed = [a for a, _b, reason in problems if reason != 'exists']
    if failed: out.append('%d cache file(s) NOT moved (%s%s): they will be recomputed' % (len(failed), ', '.join(_rel_data(d, a) for a in failed[:3]), ', ...' if len(failed) > 3 else ''))
    return out


def language_cache(d, language, log=print):
    """the cache for the game's language. The English one (`data\\cache\\<game>\\en`) starts empty; only `ui_layout.json` (the menu layout, computed by `tools\\generate_ui.bat` from the game's code, the same in both languages) is copied into it from the French cache, so that the original menus also work in English."""
    cache = d.cache_for(language)
    if cache != d.cache:
        src = os.path.join(d.cache, 'ui_layout.json')
        try:
            if os.path.isfile(src) and _clone(src, os.path.join(cache, 'ui_layout.json'), log, 0): log('Migration: ui_layout.json copied: %s -> %s' % (_rel_data(d, d.cache), _rel_data(d, cache)))
        except OSError as ex: log('Migration: ui_layout.json NOT copied to the English cache (%s)' % ex)
    return cache


def _english_path(rel):
    """A relative path from an old layout, with each name put into English (`etats\\etat_01.dqs` -> `savestates\\state_01.dqs`)."""
    parts = [x for x in rel.split(os.sep) if x and x != '.']
    return os.path.join(*[english_name(x, i < len(parts) - 1) or x for i, x in enumerate(parts)]) if parts else ''


def _clone_tree(src, dst, log, num):
    n = 0
    for root, _, files in os.walk(src):
        rel = os.path.relpath(root, src)
        for f in files:
            n += _clone(os.path.join(root, f), os.path.normpath(os.path.join(dst, _english_path(os.path.join(rel, f)))), log, num)
    return n


def _merge_saves(sources, destination, log):
    """Copies the game's files (data1.dat... data9.dat) from the `sources` folders (in priority order) into `destination`, without overwriting anything: the first folder that has the file wins. -> number of files copied."""
    n = 0
    for src in sources:
        for name_str in LOGFILE_NAMES:
            p = os.path.join(src, name_str)
            if os.path.isfile(p): n += _clone(p, os.path.join(destination, name_str), log, 0)
    return n


def _tidy_old_folders(d, log):
    """a single saves folder. The adventure logs of the old `saves\\portage` (priority: that is what the game wrote) then those of the most recent phone copy (`saves\\mobile\\<date>`)
    are copied into `saves\\`, without overwriting anything (what the game used to read, file by file, in that order); then, once each file is found in its place, the two old folders are moved
    as they are into `saves\\before_tidy_<date>\\`: nothing is deleted. A failure leaves the old folders in place (the game still reads them). With DQ4_JEUX (phone copy elsewhere, read only): no effect.
    -> sentences describing what was done."""
    if d.old_games: return []
    old_dirs = [p for p in (d.old_port_dir, d.mobile) if os.path.isdir(p)]
    if not old_dirs: return []
    done = []
    try:
        recent = d.recent_mobile_save()
        sources = [d.old_port_dir] + ([recent] if recent else [])
        n = _merge_saves(sources, d.saves, log)
        if n: done.append('%d save file(s) copied into data\\saves (portage\\ then mobile\\)' % n)
        missing = [name_str for name_str in LOGFILE_NAMES if any(os.path.isfile(os.path.join(s, name_str)) for s in sources) and not os.path.isfile(os.path.join(d.saves, name_str))]
        if missing: raise OSError('files not found in the saves: %s' % ', '.join(missing))
        base = os.path.join(d.saves, 'before_tidy_' + time.strftime('%Y%m%d_%H%M%S')); target = base; k = 1
        while os.path.exists(target): k += 1; target = '%s_%d' % (base, k)
        os.makedirs(target)
        for p in old_dirs: os.replace(p, os.path.join(target, os.path.basename(p)))
        done.append('old folders moved: %s -> %s' % (', '.join('saves\\' + os.path.basename(p) for p in old_dirs), 'saves\\' + os.path.basename(target)))
    except OSError as ex:
        done.append('old save folders NOT moved (%s): they stay in place' % ex)
    return done


def saves_into_game_folder(d):
    """`data\\saves` holds one folder per game: what earlier versions kept directly in it (adventure logs, savestates, rules, backups, old folders) goes into `saves\\dq4`,
    a simple move (same folder: no copy), nothing overwritten (a name already taken in `dq4` stays where it is). The folders of the games (`dq4`, `dq5`, `dq6`...) are left as they are.
    -> sentences describing what was done."""
    if not os.path.isdir(d.saves_root): return []
    try: names = sorted(n for n in os.listdir(d.saves_root) if not RE_GAME_FOLDER.match(n))
    except OSError as ex: return ['saves NOT arranged by game (%s)' % ex]
    if not names: return []
    moves, problems = [], []
    try: os.makedirs(d.saves, exist_ok=True)
    except OSError as ex: return ['saves NOT arranged by game (%s): they stay in data\\saves' % ex]
    for n in names: _move(os.path.join(d.saves_root, n), os.path.join(d.saves, n), moves, problems)
    out = []
    if moves: out.append('%d save entr%s moved: data\\saves -> data\\saves\\%s (one folder per game)' % (len(moves), 'y' if len(moves) == 1 else 'ies', d.game))
    for a, _b, reason in problems: out.append('NOT moved into data\\saves\\%s: %s (%s)' % (d.game, os.path.basename(a), 'already there' if reason == 'exists' else reason))
    return out


STAGES = ('cache', 'apk', 'saves_pc_port', 'saves_phone', 'settings', 'log', ENGLISH_STAGE)       # the migrations that happen only once


def _read_resume(d):
    """The steps already done (`data\\resume.json`, or `reprise.json` if its renaming has not happened yet): dict name -> date, or {} (file missing or unreadable). Step names are translated."""
    for path in (d.resume_file, os.path.join(d.data, OLD_RESUME_FILE)):
        try:
            with open(path, encoding='utf-8') as f: content = json.load(f)
            stages = content.get('stages', content.get('etapes', {}))
            if isinstance(stages, dict): return {OLD_STAGES.get(k, k): str(v) for k, v in stages.items()}
        except (OSError, ValueError, AttributeError):
            continue
    return {}


def _note_resume(d, stages):
    try:
        os.makedirs(d.data, exist_ok=True)
        tmp = d.resume_file + '.tmp'
        with open(tmp, 'w', encoding='utf-8') as f: json.dump({'stages': stages}, f, ensure_ascii=False, indent=1)
        os.replace(tmp, d.resume_file)
    except OSError:
        pass                          # (without the file the migration is redone at the next startup: it overwrites nothing)


def _already_in_service(d):
    """For each step: its destination is already in use in `data\\` (a version already did the migration, or you copied your files yourself) -> nothing to copy over."""
    logfiles = any(os.path.isfile(os.path.join(d.saves, name_str)) for name_str in LOGFILE_NAMES) or os.path.isdir(d.savestates)
    return {'cache': os.path.exists(d.cache), 'apk': bool(glob.glob(os.path.join(d.apk, '*.apk'))),
            'saves_pc_port': logfiles, 'saves_phone': logfiles,
            'settings': bool(glob.glob(os.path.join(d.settings_dir, '*.json'))), 'log': os.path.isfile(d.window_logfile)}


def migrate(d=None, log=print):
    """Takes over the old layout into `data\\`. -> list of sentences describing what was done (empty: nothing to do).
    Copies without ever overwriting or deleting, except the cache (moved all at once if `data\\cache\\dq4\\fr` does not exist, otherwise left as is; and arranged by game: `cache_per_game`) and the old folders `saves\\portage` and `mobile` (moved into `avant_rangement_<date>` after copying); does nothing with unrecognized DQ4_DONNEES / DQ4_JEUX.
    Each migration happens only once: what you delete afterwards in `data\\` (a `before_import_...` folder, a log, settings) does not come back from the old folder.
    everything starts with the renaming to English of the folders and files of the earlier versions (`english_names`), so that the following migrations already arrive under the right names."""
    d = (d or FOLDERS).for_game(LEGACY_GAME)                              # (every earlier layout is DQ4's, whatever the running game)
    done = []
    code = os.path.join(d.root, 'dq4_pc')
    games = os.path.join(d.root, 'jeux', 'DQ4')
    noted = _read_resume(d); new_entries = {}
    if ENGLISH_STAGE not in noted:
        moves, problems = english_names(d)
        done += _describe_english_names(d, moves, problems)
        noted = _read_resume(d)                                    # (the migration file may just have changed folder or name)
        # The step is marked done from the first pass, even if some files stayed in place: a name already taken will remain so, and without this note the same sentence came back on EVERY launch
        # (and twice per launch: `launch_dq4.bat` calls `python -m dq456_pc.paths` and `main` calls `migrate` again) —. Only a FAILED rename (locked folder, permissions) is retried.
        if moves or problems:
            if not any(reason != 'exists' for _a, _b, reason in problems): new_entries[ENGLISH_STAGE] = time.strftime('%d/%m/%Y %H:%M:%S')
    done += saves_into_game_folder(d)                                      # (before `_already_in_service` and the other steps, which look in `saves\\dq4`; always done: it moves, so it does not repeat itself)
    done += split_apk_by_language(d)                                       # (before `_already_in_service`, which looks for the French APKs in `apk\\dq4\\fr`)
    done += cache_per_game(d)                                              # (before `_already_in_service` and step 1, which look for the cache in `cache\\dq4\\fr`; always done: it moves)
    in_service = _already_in_service(d)

    def is_pending(name_str):
        """Does the step remain to be done? If not (done before, or destination already in use) it is recorded as done, without copying anything."""
        if name_str in noted: return False
        if in_service[name_str]: new_entries[name_str] = 'en place'; return False
        return True

    def mark_done(name_str): new_entries[name_str] = time.strftime('%d/%m/%Y %H:%M:%S')

    # 1. cache: same volume, so a simple rename (it weighs several hundred MB)
    old = os.path.join(code, 'cache')
    if is_pending('cache') and os.path.isdir(old):
        try:
            os.makedirs(os.path.dirname(d.cache), exist_ok=True); os.replace(old, d.cache)
            done.append('cache moved: dq4_pc\\cache -> %s' % _rel_data(d, d.cache)); mark_done('cache')
        except OSError as ex:
            done.append('cache NOT moved (%s): it will be recomputed' % ex)
    # 2. APK francais : copies (jeux\DQ4\patched_apks -> data\apk\fr)
    if is_pending('apk') and not d.old_games and os.path.isdir(os.path.join(games, 'patched_apks')):
        n = _clone_tree(os.path.join(games, 'patched_apks'), d.apk, log, 0)
        if n: done.append('%d APK file(s) copied: jeux\\DQ4\\patched_apks -> data\\apk\\dq4\\fr' % n)
        mark_done('apk')
    # 3. the old folders data\saves\portage and \mobile\<date> are moved up into data\saves then tidied away (BEFORE the older migrations: what the game
    #    wrote in recent days takes priority over old copies)
    #    (always done: it moves these two folders, so it does not repeat itself)
    done += _tidy_old_folders(d, log)
    # 4. saves of the earlier port: dq4_pc\sauvegardes\{data*.dat, etats\, avant_import_*\} -> data\saves (a single folder; and renamed to English along the way)
    old = os.path.join(code, 'sauvegardes')
    if is_pending('saves_pc_port') and os.path.isdir(old):
        n = 0
        for f in glob.glob(os.path.join(old, '*')):
            name_str = os.path.basename(f)
            if os.path.isfile(f): n += _clone(f, os.path.join(d.saves, english_name(name_str, False) or name_str), log, 0)
            elif name_str == 'etats': n += _clone_tree(f, d.savestates, log, 0)
            elif name_str.startswith('avant_import_'): n += _clone_tree(f, os.path.join(d.saves, english_name(name_str, True)), log, 0)
        if n: done.append('%d save file(s) of the PC port copied: dq4_pc\\sauvegardes -> data\\saves' % n)
        mark_done('saves_pc_port')
    # 5. saves of the earlier phone copy: jeux\DQ4\saves\<most recent date> -> data\saves (what the game read second, file by file)
    if is_pending('saves_phone') and not d.old_games and os.path.isdir(os.path.join(games, 'saves')):
        newest = sorted(x for x in glob.glob(os.path.join(games, 'saves', '*')) if os.path.isdir(x))
        n = _merge_saves(newest[-1:], d.saves, log)
        if n: done.append('%d phone save file(s) copied: jeux\\DQ4\\saves -> data\\saves' % n)
        mark_done('saves_phone')
    # 6. settings and history favorites
    if is_pending('settings'):
        n = 0; found = False
        for name_str in ('reglages.json', 'historique_favoris.json', 'historique_messages.json'):
            src = os.path.join(code, name_str)
            if os.path.isfile(src): found = True; n += _clone(src, os.path.join(d.settings_dir, english_name(name_str, False)), log, 0)
        if n: done.append('%d settings file(s) copied: dq4_pc -> data\\settings' % n)
        if found: mark_done('settings')
    # 7. window error log
    src = os.path.join(code, 'erreurs_fenetre.log')
    if is_pending('log') and os.path.isfile(src):
        if _clone(src, d.window_logfile, log, 0): done.append('error log copied: data\\logs')
        mark_done('log')
    if new_entries: _note_resume(d, dict(noted, **new_entries))
    for ph in done: log('Migration: %s' % ph)
    return done


if __name__ == '__main__':           # `python -m dq456_pc.paths`: the migration alone (run by the launchers before the game), or `--cache`: the cache folder, so that the .bat does not hard-code `data\cache`
    import sys
    if '--cache' in sys.argv[1:]: print(FOLDERS.cache)
    else:
        LG.select_language(LG.read_setting(FOLDERS.settings))      # (the migration messages are in the tool's language)
        migrate()
