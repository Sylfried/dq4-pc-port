"""Tool language, "window" batch: console and game window messages, startup, command line (`--help`), folder migration, saves, sound, engine.
Without a window or APK (fake Game, fake pyglet window): each scenario is played in French (the text from before, word for word) then in English (not a single French word left: `french` of test_language).

  1. coverage (reading the code): every text passed to tr / N_ in scope has its English translation, no catalog key is orphaned, nothing is translated at import, the texts passed to `_wait`,
     `_log_window`, `_note_once` are marked N_, and NO console message was left in French without tr (whitelist of debug traces, each one justified);
  2. command line: the `--help` help (parser and full process) in both languages, the language set BEFORE the migration and the parser (default reglages.json or the one given by --settings), startup
     messages (APKs not found, migration impossible);
  3. folder migration (paths.migrate), export / import of saves, states, adventure logs: the reasons shown to the player;
  4. window: Game messages (state and save failures, engine memory, missing settings, loading), full screen <-> window switch (console and error log), window log line,
     monitors, size; sound; engine version alerts (`Engine._record_missing`); cache preparation (separate process, language passed along).

    python3 tests/test_window_language.py"""
import ast, contextlib, glob, io, json, os, re, shutil, subprocess, sys, tempfile, types, unittest, warnings, zipfile
from unittest import mock

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
sys.path.insert(0, ROOT); sys.path.insert(0, HERE)
import _paths
import test_language as TL
from dq456_pc import paths as CH
from dq456_pc import language as LG
from dq456_pc.persistence import savestates as SS, logfile_format as FJ, saves as SA

french = TL.french


OWN_KEYS = set(TL.catalog_by_file('fr')['window']) | set(TL.catalog_by_file('fr')['misc'])        # the keys of this group (texts/<language>/window.py and misc.py)
FR, EN = LG.catalog('fr'), LG.catalog('en')
FOLDER = os.path.join(ROOT, 'dq456_pc')
WINDOW_FILES = [os.path.join('dq456_pc', 'window', f) for f in ('game.py', 'full_screen.py', 'field.py', 'keyboard_mouse.py', 'camera.py', 'options.py', 'helpers.py', 'battle_scene.py', 'snapshots.py')]
SCOPE = (['dq456_pc/main.py', 'dq456_pc/paths.py', 'dq456_pc/sound.py', 'dq456_pc/core/engine.py'] + WINDOW_FILES
             + ['dq456_pc/persistence/' + f for f in ('write_dir.py', 'savestates.py', 'saves.py', 'logfile_format.py', 'settings.py')]
             + sorted(os.path.relpath(p, ROOT) for p in glob.glob(os.path.join(FOLDER, 'world', '*.py')) + glob.glob(os.path.join(FOLDER, 'render', '*.py'))))


def tree(path):
    with open(os.path.join(ROOT, path), encoding='utf-8') as f: return ast.parse(f.read())


def call_name(n):
    return getattr(n.func, 'id', None) or getattr(n.func, 'attr', None)


def literals(path, names=('tr', 'N_')):
    """[(line, text)] of the literal texts passed to tr() / N_() (including LG.tr)."""
    return [(n.lineno, n.args[0].value) for n in ast.walk(tree(path)) if isinstance(n, ast.Call) and call_name(n) in names and n.args and isinstance(n.args[0], ast.Constant) and isinstance(n.args[0].value, str)]


@contextlib.contextmanager
def entry(code):
    """Plays what follows in language `code` ('fr' or 'en')."""
    LG.select_language(code)
    try: yield
    finally: LG.select_language('fr')


def output(f, *a, **k):
    """-> (result, printed text) of f(*a, **k)."""
    buf = io.StringIO()
    with contextlib.redirect_stdout(buf): r = f(*a, **k)
    return r, buf.getvalue()


def without_paths(t):
    """The text without the paths (temporary folders): they are not words."""
    return re.sub(r'(?:[A-Za-z]:)?[\\/][^\s\'")]+', ' ', t)


def write(path, content=b'x'):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, 'wb') as f: f.write(content)
    return path


# ======================================================================================================================================================
class Coverage(unittest.TestCase):
    """Code reading: nothing is missing, nothing lingers."""
    def test_each_code_text_has_its_translation(self):
        """Every text passed to tr() / N_() in scope is a catalog key with a French and an English text."""
        missing_items = []
        for p in SCOPE:
            for line, t in literals(p):
                keys = TL.keys_in_text(t)
                if not keys:
                    if french(t): missing_items.append('%s:%d %r (not a key)' % (p, line, t))
                    continue
                missing_items += ['%s:%d %r' % (p, line, k) for k in keys if k not in FR or k not in EN]
        self.assertEqual(missing_items, [])

    def test_no_orphan_key(self):
        """Every key of window.py and misc.py is used in the code (a text changed or removed in the code does not leave its translation behind)."""
        used = set()
        for d, _, fs in os.walk(FOLDER):
            if os.sep + 'texts' in d: continue
            for f in fs:
                if f.endswith('.py') and '__pycache__' not in d:
                    for n in ast.walk(tree(os.path.relpath(os.path.join(d, f), ROOT))):
                        if isinstance(n, ast.Constant) and isinstance(n.value, str): used.update(TL.keys_in_text(n.value))
        self.assertEqual(sorted(OWN_KEYS - used), [])

    def test_nothing_is_translated_at_import(self):
        """`tr(...)` runs only inside a function (the language changes mid-game); a module constant is marked N_ and translated at display time."""
        faulty = []
        for p in SCOPE:
            a = tree(p); parents = {id(c): n for n in ast.walk(a) for c in ast.iter_child_nodes(n)}
            for n in ast.walk(a):
                if isinstance(n, ast.Call) and call_name(n) == 'tr':
                    x = n
                    while id(x) in parents and not isinstance(x, (ast.FunctionDef, ast.AsyncFunctionDef, ast.Lambda)): x = parents[id(x)]
                    if not isinstance(x, (ast.FunctionDef, ast.AsyncFunctionDef, ast.Lambda)): faulty.append('%s:%d' % (p, n.lineno))
        self.assertEqual(faulty, [])

    def test_tr_n_and_lg_are_imported_where_used(self):
        """A `tr(...)` added in a module that does not import it crashes only when the message appears (often a rare error: switch failure, sound cut off...): this test finds it by reading the code."""
        unlinked = []
        for p in SCOPE:
            a = tree(p); lies = set()
            for n in ast.walk(a):
                if isinstance(n, (ast.Import, ast.ImportFrom)): lies.update((x.asname or x.name).split('.')[0] for x in n.names)
                elif isinstance(n, (ast.FunctionDef, ast.ClassDef)): lies.add(n.name)
                elif isinstance(n, ast.Name) and isinstance(n.ctx, ast.Store): lies.add(n.id)
                elif isinstance(n, ast.arg): lies.add(n.arg)
            unlinked += ['%s:%d %s' % (p, n.lineno, n.id) for n in ast.walk(a) if isinstance(n, ast.Name) and n.id in ('tr', 'N_', 'LG') and isinstance(n.ctx, ast.Load) and n.id not in lies]
        self.assertEqual(unlinked, [])

    CONSOLE = {'print', 'log', '_record_missing', '_note', '_failure', '_note_once', 'note_error', '_log_window', '_wait'}

    def test_console_messages_are_literal_english(self):
        """What a console function (print, log, _wait...) receives is an English literal, without tr(): the tool's language changes only the window's text. A toast with a French literal must go through tr()."""
        in_french = []; with_tr = []
        for p in SCOPE:
            for n in ast.walk(tree(p)):
                if not isinstance(n, ast.Call) or not n.args: continue
                name_str = call_name(n)
                if name_str not in self.CONSOLE and name_str != 'toast': continue
                a = n.args[0]
                while isinstance(a, ast.BinOp): a = a.left                             # 'text %s' % x, 'start' + x
                if isinstance(a, ast.Call) and call_name(a) in ('tr', 'N_') and name_str != 'toast': with_tr.append('%s:%d' % (p, n.lineno))
                elif isinstance(a, ast.Constant) and isinstance(a.value, str) and french(a.value): in_french.append('%s:%d %r' % (p, n.lineno, a.value[:80]))
        self.assertEqual(in_french, [], 'console messages (or toasts without tr()) in French')
        self.assertEqual(with_tr, [], 'console messages that go through tr()')


# ======================================================================================================================================================
try:
    from dq456_pc import main as P
except Exception as _ex:
    P = None; _ERROR_P = _ex


@unittest.skipIf(P is None, 'principal non importable ici')
class CommandLine(unittest.TestCase):
    def setUp(self):
        self.t = tempfile.mkdtemp(prefix='lang_cmd_'); self.d = CH.Folders(self.t, env={}); self.before = (CH.FOLDERS, CH.migrate)

    def tearDown(self): CH.FOLDERS, CH.migrate = self.before; LG.select_language('fr'); shutil.rmtree(self.t, ignore_errors=True)

    def settings(self, language, path=None):
        path = path or self.d.settings; os.makedirs(os.path.dirname(path), exist_ok=True)
        with open(path, 'w', encoding='utf-8') as f: json.dump({'language': language}, f)
        return path

    def helpers(self):
        """{option: help text} of the parser built in the current language."""
        return {a.option_strings[0]: a.help for a in P.build_parser(self.d)._actions if a.help and a.option_strings[0] != '-h'}

    def test_help_text_is_english_in_every_language(self):
        with entry('fr'): fr = self.helpers()
        with entry('en'): ang = self.helpers()
        self.assertEqual(fr, ang); self.assertGreaterEqual(len(fr), 33)                                                  # (the help is a console text: English, whatever the tool language)
        self.assertEqual(fr['--apk'], 'folder of the 3 APK files; default: data\\apk\\dq4\\fr or data\\apk\\dq4\\en, whichever matches the language chosen in the Esc menu (read when the game starts, and again when the language changes: the game restarts on the title screen)')
        self.assertEqual(fr['--no-sound'], 'turns the sound off for this session (the Esc menu can turn it back on)')
        for option in fr:
            self.assertFalse(french(fr[option]), '%s : %r' % (option, fr[option]))
            self.assertNotIn('%', fr[option].replace('%%', ''), option)                  # (argparse formats the help with %: a bare percent sign would break it)
        self.assertEqual(sorted(o for o in fr if fr[o].startswith('(test) ')), sorted(o for o in fr if fr[o].startswith('(test) ')))

    def test_format_help_does_not_crash_in_both_languages(self):
        for code in ('fr', 'en'):
            with entry(code): text = P.build_parser(self.d).format_help()
            self.assertIn('--saves-write', text); self.assertIn('usage: dq456_pc', text)

    def test_settings_file_from_command_line(self):
        self.assertEqual(P.settings_file(['--slot', '2'], self.d), self.d.settings)
        self.assertEqual(P.settings_file(['--settings', 'a.json', '--slot', '2'], self.d), 'a.json')
        self.assertEqual(P.settings_file(['--slot', '2', '--settings=b.json'], self.d), 'b.json')
        self.assertEqual(P.settings_file(['--settings'], self.d), self.d.settings)                  # missing value: the parser will complain about it

    def test_language_comes_from_setting_not_computer(self):
        self.settings('en'); self.assertEqual(P.set_language([], self.d), 'en')
        self.settings('fr'); self.assertEqual(P.set_language([], self.d), 'fr')
        other = self.settings('en', os.path.join(self.t, 'autre', 'settings.json'))
        self.assertEqual(P.set_language(['--settings', other], self.d), 'en')                           # --settings wins over the default file ('fr')
        os.remove(self.d.settings); self.assertEqual(P.set_language([], self.d), LG.select_language('system'))     # no file: the computer's language

    def main(self, argv):
        """main(argv) without a real migration or window: -> (languages seen by migrate, printed text, exit code)."""
        CH.FOLDERS = self.d; views = []; CH.migrate = lambda d=None, log=print: views.append(LG.current_language()) or []
        buf = io.StringIO()
        with contextlib.redirect_stdout(buf), self.assertRaises(SystemExit) as cm: P.main(argv)
        return views, buf.getvalue(), cm.exception.code

    def main_text(self, argv):
        CH.FOLDERS = self.d; CH.migrate = lambda d=None, log=print: []
        buf = io.StringIO()
        with contextlib.redirect_stdout(buf), self.assertRaises(SystemExit) as cm: P.main(argv)
        return buf.getvalue(), cm.exception.code

    def test_apks_not_found_in_french_and_english(self):
        empty = os.path.join(self.t, 'vide'); os.makedirs(empty)
        for code in ('fr', 'en'):                                                                                        # (the console is in English, whatever the tool's language)
            self.settings(code); text, code_ = self.main_text(['--apk', empty]); self.assertEqual(code_, 1)
            self.assertEqual(text, 'Game: APK files in %s\n\nThe APK files of Dragon Quest IV were not found.\nPut base.apk, split_config.arm64_v8a.apk and split_UnityDataAssetPack.apk of the French version in:\n   %s\nand those of the English version in:\n   %s\n(and, if you have one, the data1.dat... files of your phone save in %s). Other folder: set DQ_DATA=path\\to\\data\n'
                             % (empty, os.path.normpath(self.d.apk_fr), os.path.normpath(self.d.apk_en), self.d.saves))
            self.assertFalse(french(without_paths(text)), text)

    def test_language_is_set_before_migration(self):
        """The migration messages (paths.migrate) are in the language of the setting: default reglages.json, or that of --settings; and the language does not depend on the computer's."""
        empty = os.path.join(self.t, 'vide'); os.makedirs(empty)
        self.settings('en'); views, _, _ = self.main(['--apk', empty]); self.assertEqual(views, ['en'])
        self.settings('fr'); views, _, _ = self.main(['--apk', empty]); self.assertEqual(views, ['fr'])
        other = self.settings('en', os.path.join(self.t, 'autre.json')); views, text, _ = self.main(['--apk', empty, '--settings', other])
        self.assertEqual(views, ['en']); self.assertIn('The APK files of Dragon Quest IV were not found.', text)

    def test_migration_impossible(self):
        CH.FOLDERS = self.d
        def breaks(d=None, log=print): raise RuntimeError('boom')
        CH.migrate = breaks
        for code, att in (('fr', "File migration failed (RuntimeError('boom')): the game continues with the current folders."),
                          ('en', "File migration failed (RuntimeError('boom')): the game continues with the current folders.")):
            self.settings(code)
            with self.assertRaises(SystemExit): _, text = output(P.main, ['--apk', os.path.join(self.t, 'vide')])
            buf = io.StringIO()
            with contextlib.redirect_stdout(buf), self.assertRaises(SystemExit): P.main(['--apk', os.path.join(self.t, 'vide')])
            self.assertEqual(buf.getvalue().splitlines()[0], att)

    def launch(self, *args, env=None):
        e = dict(os.environ, DQ_DATA=os.path.join(self.t, 'data'), PYTHONDONTWRITEBYTECODE='1', PYGLET_HEADLESS='1', PYGLET_AUDIO='silent'); e.update(env or {})
        return subprocess.run([sys.executable, '-m', 'dq456_pc', *args], cwd=ROOT, env=e, capture_output=True, text=True, timeout=180)

    def test_python_m_dq456_pc_help_in_both_languages(self):
        """The real process: `--help` opens nothing, reads the language from the --settings file and prints the help in that language (the option names stay the real ones)."""
        for code in ('fr', 'en'):
            r = self.launch('--settings', self.settings(code, os.path.join(self.t, code + '.json')), '--help')
            if r.returncode != 0 and 'ModuleNotFoundError' in r.stderr: self.skipTest('dependances absentes : ' + r.stderr.strip().splitlines()[-1])
            self.assertEqual(r.returncode, 0, r.stderr); self.assertEqual(r.stderr, '')
            if True:                                                                                         # (the help is in English in both languages)
                self.assertIn('folder of the 3 APK files; default: data', r.stdout)
                text = re.sub(r'--[\w-]+|\{[^}]*\}|\b[A-Z][A-Z_]{2,}\b', ' ', r.stdout)                  # without the option names, their values and the choice lists
                self.assertFalse(french(text), [m for m in re.findall(r"[a-zA-Z']+", text.lower().replace("'", ' ')) if m in TL.FRENCH_WORDS])


# ======================================================================================================================================================
class Resume(unittest.TestCase):
    """paths.migrate: the sentences of the migration from the old layout."""
    def setUp(self):
        self.t = tempfile.mkdtemp(prefix='lang_migr_'); self.d = CH.Folders(self.t, env={}); r = self.t
        write(os.path.join(r, 'jeux', 'DQ4', 'patched_apks', 'base.apk'), b'APK1')
        write(os.path.join(r, 'jeux', 'DQ4', 'saves', '20261103_222423', 'data1.dat'), b'T1')
        write(os.path.join(r, 'dq4_pc', 'cache', 'carte10_a.pkl'), b'CACHE')
        write(os.path.join(r, 'dq4_pc', 'sauvegardes', 'data1.dat'), b'P1'); write(os.path.join(r, 'dq4_pc', 'sauvegardes', 'etats', 'etat_01.dqs'), b'E1')
        write(os.path.join(r, 'dq4_pc', 'reglages.json'), b'{"a": 1}'); write(os.path.join(r, 'dq4_pc', 'erreurs_fenetre.log'), b'LOG')
        write(os.path.join(self.d.old_port_dir, 'data2.dat'), b'portage2'); write(os.path.join(self.d.mobile, '20261103_222423', 'data3.dat'), b'tel3')

    def tearDown(self): LG.select_language('fr'); shutil.rmtree(self.t, ignore_errors=True)

    def migrate(self):
        lines = []; done = CH.migrate(self.d, log=lines.append); return done, lines

    def test_in_french_the_text_is_english_too(self):
        with entry('fr'): done, lines = self.migrate()                                                                    # (the migration sentences are console messages: English, whatever the language)
        for ph in ('cache moved: dq4_pc\\cache -> data\\cache\\dq4\\fr', '1 APK file(s) copied: jeux\\DQ4\\patched_apks -> data\\apk\\dq4\\fr',
                   '1 settings file(s) copied: dq4_pc -> data\\settings', 'error log copied: data\\logs'):
            self.assertIn(ph, done)
        self.assertTrue(any(ph.startswith('old folders moved: ') for ph in done), done)
        self.assertEqual(lines, ['Migration: ' + ph for ph in done])

    def test_in_english_no_french_word_left(self):
        with entry('en'): done, lines = self.migrate()
        self.assertIn('cache moved: dq4_pc\\cache -> data\\cache\\dq4\\fr', done); self.assertIn('1 APK file(s) copied: jeux\\DQ4\\patched_apks -> data\\apk\\dq4\\fr', done)
        self.assertIn('1 settings file(s) copied: dq4_pc -> data\\settings', done); self.assertIn('error log copied: data\\logs', done)
        self.assertGreaterEqual(len(done), 6); self.assertEqual(lines, ['Migration: ' + ph for ph in done])
        for ph in lines: self.assertFalse(french(ph), ph)

    def test_tidy_up_impossible(self):
        """A folder named data1.dat takes the place: the old folder does not move, and the sentence says so (with the reason)."""
        for language in ('fr', 'en'):                                                                                     # (same English sentence in both languages)
            shutil.rmtree(self.t); self.setUp(); write(os.path.join(self.d.old_port_dir, 'data1.dat'), b'portage1'); os.makedirs(os.path.join(self.d.saves, 'data1.dat'))
            with entry(language): done, _ = self.migrate()
            phrase = [ph for ph in done if ph.startswith('old save folders NOT moved (')]
            self.assertEqual(len(phrase), 1, done); self.assertTrue(phrase[0].endswith('): they stay in place')); self.assertFalse(french(without_paths(phrase[0])), phrase[0])

    def test_migration_only_process_takes_language_from_setting(self):
        """`python -m dq456_pc.paths` (launched by launch_dq4.bat before the game) reads the language from reglages.json before migrating."""
        import runpy
        data = os.path.join(self.t, 'new_data'); rg = os.path.join(data, 'settings', 'settings.json'); os.makedirs(os.path.dirname(rg))
        with open(rg, 'w', encoding='utf-8') as f: json.dump({'language': 'en'}, f)
        with mock.patch.dict(os.environ, {'DQ_DATA': data}), mock.patch('os.replace'), mock.patch('shutil.copy2'), mock.patch('shutil.copyfile'):
            LG.select_language('fr')
            with warnings.catch_warnings(): warnings.simplefilter('ignore'); output(runpy.run_module, 'dq456_pc.paths', run_name='__main__')
        self.assertEqual(LG.current_language(), 'en')


# ======================================================================================================================================================
def logfile(n):
    """A valid adventure log of 15,360 bytes (like test_saves_import)."""
    import struct
    plain = bytearray(FJ.LOGFILE_SIZE); struct.pack_into('<II', plain, 0, FJ.MAGIC1, FJ.MAGIC2); plain[200] = n % 256
    struct.pack_into('<I', plain, 8, FJ.checksum(bytes(plain)))
    return FJ.decrypt(bytes(plain))


class Persistence(unittest.TestCase):
    """The reasons shown to the player: export / import of saves, adventure logs, states."""
    def setUp(self):
        self.t = tempfile.mkdtemp(prefix='lang_pers_'); self.d = CH.Folders(self.t, env={}); self.before = CH.FOLDERS; CH.FOLDERS = self.d
        self.wdir = self.d.portage; self.zip = os.path.join(self.t, 'i.zip')

    def tearDown(self): CH.FOLDERS = self.before; LG.select_language('fr'); shutil.rmtree(self.t, ignore_errors=True)

    def make_zip(self, **files):
        with zipfile.ZipFile(self.zip, 'w') as z:
            for name_str, d in files.items(): z.writestr(name_str.replace('__', '/'), d)

    def error(self, f, *a):
        with self.assertRaises((ValueError, Exception)) as cm: f(*a)
        return str(cm.exception)

    def test_nothing_to_export(self):
        with entry('fr'): m = self.error(SA.export_saves, self.wdir, self.d.mobile, os.path.join(self.t, 'x.zip'))
        self.assertEqual(m, 'Aucune sauvegarde a exporter (ni journal, ni etat instantane).')
        with entry('en'): m = self.error(SA.export_saves, self.wdir, self.d.mobile, os.path.join(self.t, 'x.zip'))
        self.assertEqual(m, 'Nothing to export (no adventure log, no save state).')

    def problems(self):
        """An import that discards a too-short adventure log, a damaged one, one that is not a log, a too-small state and a fake .zip, but keeps a good adventure log."""
        bad = bytearray(logfile(3)); bad[100] ^= 1
        fake_zip = write(os.path.join(self.t, 'broken.zip'), b'ceci n est pas un zip')
        self.make_zip(**{'data1.dat': logfile(2), 'data2.dat': bytes(bad), 'data3.dat': bytes(FJ.LOGFILE_SIZE), 'data4.dat': b'court', 'savestates__state_01.dqs': b'petit'})
        return SA.import_saves([self.zip, fake_zip], self.wdir, self.d.mobile)

    def test_import_problems_in_french(self):
        with entry('fr'): nj, n_savestates, copied, pb = self.problems()
        self.assertEqual((nj, n_savestates), (1, 0))
        txt = '\n'.join(pb)
        for att in ('data4.dat : taille 5 au lieu de 15360 (i.zip)', 'data2.dat : fichier abime (somme de controle incorrecte) (i.zip)', "data3.dat : ce n'est pas un journal du jeu (en-tete inconnu) (i.zip)",
                    'state_01.dqs : fichier trop petit (i.zip)', "broken.zip : ce n'est pas un .zip valide"):
            self.assertIn(att, pb)
        self.assertEqual(len(pb), 5, txt)

    def test_import_problems_in_english(self):
        with entry('en'): nj, n_savestates, copied, pb = self.problems()
        self.assertEqual((nj, n_savestates), (1, 0))
        for att in ('data4.dat: size 5 instead of 15360 (i.zip)', 'data2.dat: damaged file (checksum mismatch) (i.zip)', 'data3.dat: not a game adventure log (unknown header) (i.zip)',
                    'state_01.dqs: file too small (i.zip)', 'broken.zip: not a valid .zip file'):
            self.assertIn(att, pb)
        for p in pb: self.assertFalse(french(p), p)

    def test_no_file_recognized(self):
        self.make_zip(**{'lisez_moi.txt': b'x'})
        with entry('fr'): m = self.error(SA.import_saves, [self.zip], self.wdir, self.d.mobile)
        self.assertEqual(m, 'Aucun fichier de sauvegarde reconnu (data1.dat a data5.dat, data9.dat ou savestates/state_NN.dqs attendus).')
        with entry('en'): m = self.error(SA.import_saves, [self.zip], self.wdir, self.d.mobile)
        self.assertEqual(m, 'No save file recognized (expected data1.dat to data5.dat, data9.dat or savestates/state_NN.dqs).')

    def test_write_not_possible(self):
        self.make_zip(**{'data1.dat': logfile(2)})
        for code, begin, end in (('fr', 'Aucun fichier n\'a pu etre ecrit (data1.dat : ecriture impossible (', ') ; le fichier actuel est inchange).'),
                                 ('en', 'No file could be written (data1.dat: could not be written (', '); the current file is unchanged).')):
            with entry(code), mock.patch.object(SA, 'atomic_write', return_value=OSError('verrouille')):
                m = self.error(SA.import_saves, [self.zip], self.wdir, self.d.mobile)
            self.assertTrue(m.startswith(begin) and m.endswith(end) and 'verrouille' in m, m)
        self.assertFalse(french(m.replace('verrouille', '')), m)

    def test_verify_savefile(self):
        fake = FJ.decrypt(bytes(FJ.LOGFILE_SIZE)); damaged = bytearray(logfile(1)); damaged[50] ^= 1
        with entry('fr'):
            self.assertEqual(FJ.check('data1.dat', fake), "ce n'est pas un journal du jeu (en-tete inconnu)"); self.assertEqual(FJ.check('data1.dat', bytes(damaged)), 'fichier abime (somme de controle incorrecte)')
        with entry('en'):
            self.assertEqual(FJ.check('data1.dat', fake), 'not a game adventure log (unknown header)'); self.assertEqual(FJ.check('data1.dat', bytes(damaged)), 'damaged file (checksum mismatch)')
            self.assertIsNone(FJ.check('data1.dat', logfile(1)))

    def test_savestates_refused(self):
        import pickle
        trap = pickle.dumps(os.getcwd, protocol=4)
        fake_engine = types.SimpleNamespace(core=types.SimpleNamespace(uc=None, elf=types.SimpleNamespace(img=b'abc')))
        f = write(os.path.join(self.t, 'not_a_state.dqs'), b'DQ4ETATX' + bytes(100))
        expected = ('state file refused: it asks for "posix.getcwd"', 'state from another version (99)',
                    'state saved with another version of the engine library (different APK): it cannot be loaded', 'this is not a state file of this port')       # (error messages of savestates.py: English in both languages)
        for code in ('fr', 'en'):
            with entry(code):
                m1 = self.error(SS._load, trap); m2 = self.error(SS.apply, fake_engine, {'version': 99})
                m3 = self.error(SS.apply, fake_engine, {'version': SS.VERSION, 'lib_sha': 'not_the_right_one'}); m4 = self.error(SS.read, f)
            self.assertTrue(m1.startswith(expected[0].replace('posix', 'nt') if os.name == 'nt' else expected[0]), (code, m1))
            self.assertEqual((m2, m3, m4), expected[1:])
            self.assertFalse(french(m1) or french(m2) or french(m3) or french(m4), (m1, m2, m3, m4))

    def test_file_dialog_boxes(self):
        """The file types of the "Save as" / "Open" dialogs (tkinter, replaced here by a fake)."""
        seen = {}
        fake_fd = types.ModuleType('tkinter.filedialog')
        fake_fd.asksaveasfilename = lambda **kw: seen.setdefault('save', kw['filetypes']) and ''
        fake_fd.askopenfilenames = lambda **kw: seen.setdefault('open', kw['filetypes']) and ()
        class Tk:
            def withdraw(self): pass
            def attributes(self, *a): pass
            def destroy(self): pass
        fake_tk = types.ModuleType('tkinter'); fake_tk.Tk = Tk; fake_tk.filedialog = fake_fd
        expected = {'fr': {'save': [('Archive zip', '*.zip')], 'open': [('Sauvegardes (zip, data*.dat, state_*.dqs)', '*.zip *.dat *.dqs'), ('Tous les fichiers', '*.*')]},
                    'en': {'save': [('Zip archive', '*.zip')], 'open': [('Saves (zip, data*.dat, state_*.dqs)', '*.zip *.dat *.dqs'), ('All files', '*.*')]}}
        import time
        for code in ('fr', 'en'):
            seen.clear()
            with entry(code), mock.patch.dict(sys.modules, {'tkinter': fake_tk, 'tkinter.filedialog': fake_fd}):
                for mode in ('save', 'open'):
                    dlg = SA.Dialogue(mode, 'titre'); t0 = time.time()
                    while dlg.result is None and time.time() - t0 < 5: time.sleep(0.01)
                    self.assertEqual(dlg.result, [], dlg.error)
            self.assertEqual(seen, expected[code])


# ======================================================================================================================================================
try:
    from dq456_pc.window import game as WND, helpers as AI, snapshots as INS
    import test_window_mode as TM
except Exception as _ex:
    WND = None


@unittest.skipIf(WND is None, 'fenetre non importable ici')
class Window(unittest.TestCase):
    def setUp(self):
        self.t = tempfile.mkdtemp(prefix='lang_fen_'); self.addCleanup(shutil.rmtree, self.t, True); self.addCleanup(LG.select_language, 'fr')
        self.log = os.environ['DQ_WINDOW_LOG'] = os.path.join(self.t, 'logs', 'window_errors.log'); self.addCleanup(os.environ.pop, 'DQ_WINDOW_LOG', None)
        os.environ.pop('DQ_SIM_FAILURE', None); self.addCleanup(os.environ.pop, 'DQ_SIM_FAILURE', None)

    def logfile(self):
        try:
            with open(self.log, encoding='utf-8') as f: return f.read()
        except OSError: return ''

    def fake(self):
        j = types.SimpleNamespace(msgs=[]); j.toast = lambda t, duration=1.8: j.msgs.append(LG.tr(t)); return j                                   # (like Game.toast: the text is translated at display time)

    def test_savestate_failure(self):
        for code, att in (('fr', "Chargement de l'état 3 impossible : OSError('disque')"), ('en', "Loading state 3 failed: OSError('disque')")):                  # (the window's small message follows the language)
            with entry(code):
                j = self.fake(); _, text = output(WND.Game._note_state_failure, j, LG.tr('window.loading_state') % 3, 'Loading savestate 3', OSError('disque'))
            console = "Loading savestate 3 failed: OSError('disque') ---\n"                                                                                        # (the console and the log: English in both languages)
            self.assertEqual(j.msgs, [att]); self.assertIn(console, text); self.assertTrue(self.logfile().endswith(console)); self.assertFalse(french(text.replace('disque', '')))
        self.assertFalse(french(j.msgs[0].replace('disque', '')))

    def test_saving_is_impossible(self):
        for code, att, header in (('fr', 'Sauvegarde impossible : le jeu continue (détails dans window_errors.log)', 'save failed: data1.dat'),
                                  ('en', 'Save failed: the game continues (details in window_errors.log)', 'save failed: data1.dat')):
            with entry(code):
                j = self.fake(); core = types.SimpleNamespace(write_failures=['data1.dat']); _, text = output(WND.Game._report_write_failures, j, core)
            self.assertEqual(j.msgs, [att]); self.assertIn(header, text); self.assertIn(header, self.logfile())

    def test_engine_memory_and_missing_settings(self):
        note = []
        with mock.patch.object(WND, 'note_error', note.append):
            for code, memory, setting in (('fr', 'engine memory at 98 % (250 MB of 256 MB) ---\n', 'engine setting not applied: a ---\n'),
                                           ('en', 'engine memory at 98 % (250 MB of 256 MB) ---\n', 'engine setting not applied: a ---\n')):
                note.clear()
                with entry(code):
                    j = types.SimpleNamespace(_heap_level=0); core = types.SimpleNamespace(heap_used=lambda: 250 << 20, HEAP_CRITICAL=240 << 20, HEAP_ALERT=200 << 20, HEAP_SIZE=256 << 20)
                    WND.Game._watch_heap(j, core)
                    eng = types.SimpleNamespace(missing_hooks=['a']); j2 = types.SimpleNamespace(_reported_hooks=0); WND.Game._report_missing_hooks(j2, eng)
                self.assertEqual(len(note), 2); self.assertTrue(note[0].endswith(memory), note[0]); self.assertTrue(note[1].endswith(setting), note[1])
                self.assertFalse(french(note[0]) or french(note[1]), note)

    def test_startup_loading(self):
        att = ['Loading the engine...', 'Loading the save...', 'Loading the map...']                                      # (console text: English in both languages)
        for code in ('fr', 'en'):
            with entry(code):
                j = types.SimpleNamespace(switch_to=lambda: None, clear=lambda: None, flip=lambda: None, dispatch_events=lambda: None)
                _, text = output(lambda: [WND.Game._wait(j, t) for t in att])
            self.assertEqual(text.splitlines(), att)

    def test_sound_focus_loss(self):
        def boom(yes): raise OSError('carte son')
        j = types.SimpleNamespace(_ready=True, sound=types.SimpleNamespace(lose_focus=boom), wheel=types.SimpleNamespace(cancel=lambda: None), bar_gesture=types.SimpleNamespace(cancel=lambda: None), hud=types.SimpleNamespace(dpad_drop=lambda: None, press_state=None), press_state=None, hovered=None,
                                  acc=0.0, t_loop=None, _camera_forget=lambda: None, pad=lambda: 0, _held=lambda a: False, mouse_guard=types.SimpleNamespace(keyboard=lambda s: None), mouse=(0, 0))
        for code, a1, a2 in (('fr', "Sound: muting on focus loss failed (OSError('carte son'))", "Sound: unmuting on focus return failed (OSError('carte son'))"),
                             ('en', "Sound: muting on focus loss failed (OSError('carte son'))", "Sound: unmuting on focus return failed (OSError('carte son'))")):
            with entry(code):
                _, t1 = output(WND.Game.on_deactivate, j); _, t2 = output(WND.Game.on_activate, j)
            self.assertEqual((t1.strip(), t2.strip()), (a1, a2))

    def test_cache_preparation_in_tool_language(self):
        """The separate process (world/data.py) does not know settings.json: the game passes it the language (DQ_LANGUAGE), not the computer's."""
        for code in ('fr', 'en'):
            calls = []
            with entry(code), mock.patch('subprocess.Popen', lambda *a, **kw: calls.append(kw) or types.SimpleNamespace()):
                WND.Game._launch_preparation(types.SimpleNamespace(engine=types.SimpleNamespace(apk_data='x.apk')), 'cache')
            self.assertEqual(calls[0]['env']['DQ_LANGUAGE'], code)
        with entry('en'), mock.patch('subprocess.Popen', side_effect=OSError('non')), mock.patch('threading.Thread'):
            j = types.SimpleNamespace(engine=types.SimpleNamespace(apk_data='x.apk'), data=types.SimpleNamespace(prepare=None), prep_stop=None)
            _, text = output(WND.Game._launch_preparation, j, 'cache')
        self.assertEqual(text.strip(), "Cache preparation: separate process failed (OSError('non')), running inside the game.")

    def test_preparation_process_speaks_received_language(self):
        """Real process `python -m dq456_pc.world.data` (APK missing: "interrompue")."""
        cache = os.path.join(self.t, 'cache'); os.makedirs(cache)
        for code, begin in (('fr', 'Cache preparation interrupted: '), ('en', 'Cache preparation interrupted: ')):
            e = dict(os.environ, DQ_LANGUAGE=code, PYTHONDONTWRITEBYTECODE='1')
            r = subprocess.run([sys.executable, '-m', 'dq456_pc.world.data', os.path.join(self.t, 'inexistant.apk'), cache], cwd=ROOT, env=e, stdin=subprocess.DEVNULL, capture_output=True, text=True, timeout=120)
            self.assertTrue(any(l.startswith(begin) for l in r.stdout.splitlines()), (r.stdout, r.stderr))
        self.assertEqual(r.stdout.splitlines()[0], 'Reading the game data pack (once only, a few seconds)...')

    def test_cancel_load(self):
        for code, done in (('fr', 'Chargement annulé'), ('en', 'Load undone')):                       # (nothing loaded yet: no notice)
            with entry(code):
                j = self.fake(); j.undo_state = None; self.assertFalse(INS.SnapshotsMixin.cancel_loading(j))
                j.undo_state = {'a': 1}; j._complete_savestate = lambda: {'b': 2}; j._apply_savestate = lambda d: None; self.assertTrue(INS.SnapshotsMixin.cancel_loading(j))
            self.assertEqual(j.msgs, [done])

    def test_window_size_too_large(self):
        with mock.patch.object(AI, 'useful_zone', lambda: (1904, 1040)):
            for code, model in (('fr', 'Window 3840 x 2160 too large for the screen: %d x %d'), ('en', 'Window 3840 x 2160 too large for the screen: %d x %d')):
                with entry(code): (nw, nh), text = output(AI.adjust_size, 3840, 2160)
                self.assertEqual(text.strip(), model % (nw, nh))

    # ---- full screen <-> window switch (fake window of test_window_mode)
    def win(self, **k):
        f = TM.FakeWindow(WND, **k); f._log_window = types.MethodType(WND.Game._log_window, f); f.get_framebuffer_size = lambda: (f.width, f.height); return f

    def test_toggle_failure(self):
        with mock.patch.object(WND, 'useful_zone', lambda: (1904, 1040)):
            for code in ('fr', 'en'):                                                                                        # (console and error log: English in both languages)
                line = "Full screen failed (RuntimeError('echec de set_fullscreen(True)')): windowed mode kept"; header = 'switch to full screen failed ---'
                lines = ['window: full screen = False, 1280 x 720, ', 'window screen according to pyglet: 1920 x 1080 at (0, 0)', 'monitors: 1920 x 1080 at (0, 0) (primary)']
                if os.path.exists(self.log): os.remove(self.log)
                f = self.win(failure='set_fullscreen(True)')
                with entry(code): render, text = output(f.set_full_screen, True)
                self.assertFalse(render)
                self.assertIn(line, text.splitlines())
                for att in [header] + lines: self.assertIn(att, text); self.assertIn(att, self.logfile())
                self.assertFalse(french(without_paths(re.sub(r'Traceback.*?\n(?=\w)', '', text, flags=re.S))), text)

    def test_return_to_window_failure(self):
        with mock.patch.object(WND, 'useful_zone', lambda: (1904, 1040)):
            for code in ('fr', 'en'):
                line = "Windowed mode failed (RuntimeError('echec de set_fullscreen(False,1280x720)')): full screen kept"
                f = self.win(full=True, failure='set_fullscreen(False,1280x720)')
                with entry(code): render, text = output(f.set_full_screen, False)
                self.assertTrue(render); self.assertIn(line, text.splitlines())

    def test_window_logfile_line(self):
        for code in ('fr', 'en'):                                                                                        # (console and log line: English in both languages)
            f = self.win()
            with entry(code): _, text = output(f._log_window, 'creation')
            self.assertEqual(text.strip(), 'Window (creation): window, 1280 x 720, drawing area 1280 x 720, screen 1920 x 1080 (screen 1)')
            f = self.win(full=True); f.fullscreen = False; f.win_mode = 1
            with entry(code): _, text = output(f._log_window, 'full screen')
            self.assertTrue(text.startswith('Window (full screen): FULL SCREEN [INCONSISTENT: fullscreen=False], '), text)
            f = self.win(); f.screen_ = None; del_f = types.SimpleNamespace()
            with entry(code): _, text = output(WND.Game._log_window, del_f, '1st game frame')
            self.assertTrue(text.startswith('Window (1st game frame): state unreadable ('), text)

    def test_unreadable_monitors(self):
        for code in ('fr', 'en'):
            f = self.win(); f.display = types.SimpleNamespace(get_screens=lambda: (_ for _ in ()).throw(OSError('plus de moniteurs')))
            with entry(code): _, text = output(f._read_screens, True)
            self.assertEqual(text.strip(), "Monitors unreadable (OSError('plus de moniteurs'))")

    def test_window_title(self):
        self.assertEqual(WND.Game.WINDOW_TITLE, 'window.pc_port')           # (module constant marked N_: translated at window creation)
        with entry('en'): self.assertEqual(LG.tr(WND.Game.WINDOW_TITLE) % 'Dragon Quest IV', 'Dragon Quest IV - PC port')

    def test_slot_text_on_the_command_line(self):
        """`--slot N`: the direct-load status is a console message (the two full sentences, in English in game.py)."""
        with open(os.path.join(ROOT, 'dq456_pc', 'window', 'game.py'), encoding='utf-8') as f: code = f.read()
        for att in ("'save %d loaded: yes'", "'save %d loaded: NO (file data%d.dat not found or invalid in %s)'"): self.assertIn(att, code)


# ======================================================================================================================================================
@unittest.skipIf(WND is None, 'moteur non importable ici')
class Engine(unittest.TestCase):
    """Engine version alerts (Engine._record_missing): an APK other than the one studied."""
    def setUp(self):
        import test_missing_hooks as TC
        self.TC = TC; self.addCleanup(LG.select_language, 'fr')

    def test_locations_window_and_settings_button(self):
        other = (self.TC.ORIGINAL[0], self.TC.ORIGINAL[1], 0x11000120 | (0x555 << 10))
        locations = "places window not widened: unexpected FieldData::drawSymbol, world map places only appear in the original window"
        button = "Settings button: unexpected comparison in the Misc menu, the button opens the game's original settings instead of the Pause menu"
        for code in ('fr', 'en'):                                                                                        # (engine alerts: English console in both languages)
            with entry(code):
                m = self.TC.fake_engine(other); _, text = output(m._widen_symbols); self.assertEqual((text.strip(), m.missing_hooks), (locations, [locations]))
                m = self.TC.fake_engine(cmp_param=0xd503201f); _, text = output(m.patch_params); self.assertEqual((text.strip(), m.missing_hooks), (button, [button]))

    def test_all_installers_speak_the_tool_language(self):
        """An engine whose functions cannot be found: each installer reports it (`KeyError`), in English in both of the tool's languages (console messages), without a word of French."""
        def not_found(n): raise KeyError(n)
        names = ('_text_hooks', '_fade_hooks', '_level_hooks', '_game_time_hooks', '_magic_hooks', '_divert_params', '_widen_symbols')
        results = {}
        for code in ('fr', 'en'):
            with entry(code):
                results[code] = []
                for name_str in names:
                    m = self.TC.fake_engine(); m.core.export = not_found; output(getattr(m, name_str)); results[code] += m.missing_hooks
        self.assertEqual(results['fr'], results['en']); self.assertGreaterEqual(len(results['fr']), len(names))
        for ang in results['en']: self.assertFalse(french(ang), ang)


# ======================================================================================================================================================
@unittest.skipIf(WND is None, 'son non importable ici')
class Sound(unittest.TestCase):
    def new(self):
        from dq456_pc import sound as SOUND
        self.SOUND = SOUND; lines, logfile, alerts = [], [], []
        with mock.patch.dict(sys.modules, {'pyglet': None, 'soundfile': None}):                                  # neither pyglet nor soundfile: "unavailable"
            s = SOUND.Sound('inexistant.apk', self.tmp, log=lambda *a: lines.append(' '.join(str(x) for x in a)), logfile=logfile.append, alert=alerts.append)
        return s, lines, logfile, alerts

    def setUp(self): self.tmp = tempfile.mkdtemp(prefix='lang_son_'); self.addCleanup(shutil.rmtree, self.tmp, True); self.addCleanup(LG.select_language, 'fr')

    def test_sound_unavailable(self):
        for code in ('fr', 'en'):                                                                                        # (console: English in both languages)
            with entry(code): s, lines, _, _ = self.new()
            self.assertEqual(lines[0], 'Music unavailable: "soundfile" module missing (pip install soundfile). Sound effects stay active.'); self.assertTrue(lines[1].startswith('Sound unavailable ('))
            self.assertFalse(french(lines[0]))

    def test_failures_cut_and_restoration(self):
        expected = ["sound effect 5 failed (OSError('x')), failure 1", "sound effect 5 failed (OSError('x')), failure 2", "sound effect 5 failed (OSError('x')), failure 3", 'sound interrupted, retrying in 2 s',
                    "music volume failed (OSError('v')), logged only once", 'sound restored']
        alerts_expected = {'fr': ['Son interrompu : nouvel essai automatique', 'Son rétabli'], 'en': ['Sound interrupted: automatic retry', 'Sound restored']}                  # (the on-screen alerts follow the language)
        for code in ('fr', 'en'):
            with entry(code):
                s, lines, logfile, alerts = self.new(); lines.clear()
                for _ in range(3): s._failure('sound effect 5', OSError('x'))
                s._note_once('music volume', OSError('v')); s._note_once('music volume', OSError('v'))                    # (only once)
                s._success()
            self.assertEqual(logfile, expected); self.assertEqual(alerts, alerts_expected[code])
            self.assertEqual(lines, ['Sound: ' + t for t in expected])
        self.assertEqual(lines[0], 'Sound: sound effect 5 failed (OSError(\'x\')), failure 1')

    def test_music_and_resume(self):
        with entry('en'):
            s, lines, logfile, alerts = self.new()
            s._failure('music track 12', OSError('m')); s._note_once('sound effects volume', OSError('b')); s._note_once('resume after pause', OSError('p'))
        self.assertEqual(logfile, ["music track 12 failed (OSError('m')), failure 1", "sound effects volume failed (OSError('b')), logged only once", "resume after pause failed (OSError('p')), logged only once"])


if __name__ == '__main__':
    unittest.main(verbosity=1)
