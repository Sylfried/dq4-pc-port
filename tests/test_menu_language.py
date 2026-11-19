"""English version of the tool, "menus" batch: everything the tool writes itself outside the Settings pages, in English then in French, with fake objects (no window, no engine, no GL).

  - Saves screen (start menu): title, buttons, explanations, result messages of an export / import (succeeded, canceled, ignored, failure), file dialogs (titles, filters);
  - History window: title, tabs, "Favorites only" checkbox, help, empty lists, header and lines of a battle (texts the tool composes around the game's), favorite whose message is missing;
  - name entry, license (title; the game's original text and the "Privacy Policy" do not change), names of the interface editor's items, sample dialogue texts, F1 info, notifications,
    location of the savestates, console messages of these modules;
  - in English: no French word remains (apart from the whitelist, short and justified); in French: exactly the previous texts;
  - the catalog (dq456_pc/texts/<language>/menus.py) has no orphan key, and every key marked in these modules has its French and its English text.
The catalog's general rules (same placeholders, same edges, no French in the English, no duplicates, every `tr('...')` / `N_('...')` in the code has its translation) are in tests/test_language.py.

    python3 tests/test_menu_language.py"""
import ast, contextlib, importlib, io, os, shutil, sys, tempfile, types, unittest, zipfile
from unittest import mock

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.join(HERE, '..')
sys.path.insert(0, ROOT)
sys.path.insert(0, HERE)
import _paths          # (test helper: finding the source code in the subfolders of dq456_pc)
import pyglet
pyglet.options['shadow_window'] = False                     # (no display needed: nothing is drawn)
from dq456_pc import paths as CH
from dq456_pc import language as LG
from dq456_pc.battle import battle_history as HC
from dq456_pc.window import menu_display as AM
from dq456_pc.window import snapshots as IN
from dq456_pc.window import title_screen as TI
from dq456_pc.menus import pre_game as AP
from dq456_pc.menus import saves_screen as ES
from dq456_pc.menus import hud_mobile as HM
from dq456_pc.menus import pause as PA
from dq456_pc.menus import name_entry as SN
from dq456_pc.menus import ui_history as UH
from dq456_pc.menus import ui_menu as UM
from dq456_pc.core import history as HI
from dq456_pc.persistence import logfile_format as FJ
from dq456_pc.persistence import settings as RG
from dq456_pc.persistence import saves as S
from test_language import french, catalog_by_file, keys_in_text
import test_saves_import as TIS
import test_history_key as THC

LG.select_language('fr')          # (the computer's language does not matter here: each test picks its own)


def entry(): LG.select_language('en')


class Language(unittest.TestCase):
    """Each test picks its language; French is set back at the end (the other tests expect French)."""
    def setUp(self): LG.select_language('fr')
    def tearDown(self): LG.select_language('fr')

    def assert_no_french(self, texts, whitelist=()):
        """None of the `texts` contains French (apart from the `whitelist`: game texts, proper names), and there are some."""
        texts = [t for t in texts if t not in whitelist]
        self.assertTrue(texts)
        for t in texts: self.assertFalse(french(t), 'French left: %r' % (t,))


# ---------------------------------------------------------------------------------------------------------------------------------- fake objects
class FakeLabel:
    """Fake pyglet.text.Label: stores the text and records it when it is drawn."""
    def __init__(self, J, text): self.J = J; self.text = text; self.content_width = 5.0 * len(text); self.content_height = 12.0; self.x = self.y = 0.0
    def draw(self): self.J.drawn.append(self.text)


class FakeGame(types.SimpleNamespace):
    """What the screens ask of the window: `_lbl` (makes the labels), `pause` (the pages), size, device."""
    def __init__(self, **kw):
        super().__init__(width=1280, height=720, drawn=[], last_device='keyboard', **kw)
        self.pause = fake_pause(self)

    def _lbl(self, text, size_value, color=None, fonts=()): return FakeLabel(self, text)


def fake_pause(J):
    """The `Pause` tool page without its drawings: `_label` is the real one (it translates), the rest does nothing."""
    P = mock.MagicMock()
    P.J = J; P._pol = (); P.mouse_mode = False; P.mouse_pos = None
    P._label = lambda text, size_value, color=(255, 255, 255, 255): PA.Pause._label(P, text, size_value, color)
    P._hovered = lambda z: False; P._pointer_in = lambda z: False; P._scroll_bar = lambda *a, **k: None
    return P


@contextlib.contextmanager
def without_screen(*modules):
    """No GL: the modules' `gl` and the pyglet.shapes shapes are replaced with silent objects."""
    with contextlib.ExitStack() as st:
        for m in modules:
            if hasattr(m, 'gl'): st.enter_context(mock.patch.object(m, 'gl', mock.MagicMock()))
        shapes, gl = importlib.import_module('pyglet.shapes'), importlib.import_module('pyglet.gl')          # (the real modules: before its first import, `pyglet.shapes` is a lazy proxy that mock.patch cannot restore)
        for name_str in ('Rectangle', 'BorderedRectangle', 'Star', 'Line', 'Box', 'Triangle'): st.enter_context(mock.patch.object(shapes, name_str, mock.MagicMock()))
        for name_str in ('glDisable', 'glEnable', 'glBlendFunc'): st.enter_context(mock.patch.object(gl, name_str, mock.MagicMock()))
        yield


# ---------------------------------------------------------------------------------------------------------------------------------- Saves screen: result messages
class FakeDialogue:
    """Replaces S.Dialogue (tkinter): remembers what it is asked."""
    calls = []
    def __init__(self, mode, title_screen, initial_folder=None, initial_name=None):
        self.result = None; self.unavailable = False; FakeDialogue.calls.append((mode, title_screen))


class Saves(Language):
    def setUp(self):
        super().setUp()
        self.t = tempfile.mkdtemp(prefix='lm_sauv_'); self.addCleanup(shutil.rmtree, self.t, True)
        self.d = CH.Folders(self.t, env={}); before = CH.FOLDERS; CH.FOLDERS = self.d; self.addCleanup(setattr, CH, 'DOSSIERS', before)
        self.wdir, self.rdir = self.d.portage, self.d.mobile
        self.zip = os.path.join(self.t, 'i.zip')
        eng = types.SimpleNamespace(reread_savefiles=lambda: 'nouveau', initial_buttons_state=lambda x: x)
        self.J = FakeGame(args=types.SimpleNamespace(saves_write=self.wdir, saves_read=self.rdir), engine=eng, initial_status='ancien')
        self.e = ES.SavesScreen(self.J)

    def make_zip(self, **files):
        with zipfile.ZipFile(self.zip, 'w') as z:
            for name_str, d in files.items(): z.writestr(name_str.replace('__', '/'), d)

    def answer(self, action, result, unavailable=False):
        self.e.dialogue = types.SimpleNamespace(result=result, unavailable=unavailable); self.e.action = action; self.e.do_update()
        return list(self.e.msg)

    def dataset(self):
        TIS.write(os.path.join(self.wdir, 'data1.dat'), TIS.logfile(1)); TIS.write(os.path.join(self.wdir, 'data2.dat'), TIS.logfile(2))
        TIS.write(os.path.join(CH.FOLDERS.savestates_folder(self.wdir), 'state_01.dqs'), b'x' * 2000)

    # -- what the buttons request
    def test_dialog_boxes_opening(self):
        for language, titles, msgs in (('fr', ('Exporter les sauvegardes', 'Importer des sauvegardes'),
                                      ["Choisis où enregistrer le fichier dans la fenêtre qui vient de s'ouvrir…", "Choisis le .zip ou les fichiers de sauvegarde dans la fenêtre qui vient de s'ouvrir…"]),
                                     ('en', ('Export saves', 'Import saves'), ['Choose where to save the file in the window that just opened…', 'Choose the .zip or the save files in the window that just opened…'])):
            LG.select_language(language); FakeDialogue.calls = []
            with mock.patch.object(S, 'Dialogue', FakeDialogue):
                e = ES.SavesScreen(self.J); e.export_saves(); m1 = list(e.msg); e.dialogue = None; e.import_saves(); m2 = list(e.msg)
            self.assertEqual(FakeDialogue.calls, [('save', titles[0]), ('open', titles[1])], language); self.assertEqual([m1, m2], [[msgs[0]], [msgs[1]]], language)

    def test_file_dialog_filters(self):
        """The "Save as" / "Open" filters (tkinter): same patterns, translated labels."""
        seen = []
        class FakeFiledialog:
            @staticmethod
            def asksaveasfilename(**kw): seen.append(kw['filetypes']); return ''
            @staticmethod
            def askopenfilenames(**kw): seen.append(kw['filetypes']); return ()
        class FakeTk:
            def withdraw(self): pass
            def attributes(self, *a): pass
            def destroy(self): pass
        fake_tk = types.SimpleNamespace(Tk=FakeTk, filedialog=FakeFiledialog)
        for language, att in (('fr', [[('Archive zip', '*.zip')], [('Sauvegardes (zip, data*.dat, state_*.dqs)', '*.zip *.dat *.dqs'), ('Tous les fichiers', '*.*')]]),
                            ('en', [[('Zip archive', '*.zip')], [('Saves (zip, data*.dat, state_*.dqs)', '*.zip *.dat *.dqs'), ('All files', '*.*')]])):
            LG.select_language(language); seen.clear()
            with mock.patch.dict(sys.modules, {'tkinter': fake_tk, 'tkinter.filedialog': FakeFiledialog}), mock.patch.object(fake_tk, 'filedialog', FakeFiledialog, create=True):
                for mode in ('save', 'open'):
                    d = S.Dialogue.__new__(S.Dialogue); d.result = None; d.unavailable = False; d.error = None; d._body(mode, 'titre', None, None)
            self.assertEqual(seen, att, language)

    # -- export
    def test_export_cancelled_successful_and_empty(self):
        self.dataset(); path = os.path.join(self.t, 'sortie', 'sauv.zip')
        for language, canceled, ok, empty in (('fr', 'Export annulé.', 'Exporté : 2 fichiers de sauvegarde et 1 état instantané.', 'Impossible : Aucune sauvegarde a exporter (ni journal, ni etat instantane).'),
                                         ('en', 'Export canceled.', 'Exported: 2 save files and 1 save state.', 'Failed: Nothing to export (no adventure log, no save state).')):
            LG.select_language(language); e = self.e = ES.SavesScreen(self.J)
            self.assertEqual(self.answer('export', []), [canceled], language); self.assertEqual(e.msg_clr, ES.HELPTEXT)
            self.assertEqual(self.answer('export', [path]), [ok, path], language); self.assertEqual(e.msg_clr, ES.GREEN)
            self.J.args.saves_write = os.path.join(self.t, 'rien'); self.J.args.saves_read = os.path.join(self.t, 'rien2')
            self.assertEqual(self.answer('export', [os.path.join(self.t, 'x.zip')]), [empty], language); self.assertEqual(e.msg_clr, ES.RED)
            self.J.args.saves_write, self.J.args.saves_read = self.wdir, self.rdir

    def test_a_single_file_and_a_single_state(self):
        TIS.write(os.path.join(self.wdir, 'data1.dat'), TIS.logfile(1)); TIS.write(os.path.join(CH.FOLDERS.savestates_folder(self.wdir), 'state_01.dqs'), b'x' * 2000)
        for language, att in (('fr', 'Exporté : 1 fichier de sauvegarde et 1 état instantané.'), ('en', 'Exported: 1 save file and 1 save state.')):
            LG.select_language(language); self.assertEqual(self.answer('export', [os.path.join(self.t, language + '.zip')])[0], att)

    # -- import
    def test_import_cancelled(self):
        for language, att in (('fr', 'Import annulé.'), ('en', 'Import canceled.')):
            LG.select_language(language); self.assertEqual(self.answer('import', []), [att], language)

    def test_successful_import_with_copy_and_ignored_file(self):
        for language, line1, copied, ignores, do_update in (('fr', 'Importé : 1 fichier de sauvegarde et 0 état instantané.', 'Anciens fichiers copiés dans : ', 'Ignorés : data2.dat : fichier abime (somme de controle incorrecte) (i.zip)',
                                                     'Pour mettre à jour les boutons grisés du menu de départ, relance le jeu.'),
                                                    ('en', 'Imported: 1 save file and 0 save states.', 'Previous files copied to: ', 'Skipped: data2.dat: damaged file (checksum mismatch) (i.zip)',
                                                     'To update the grayed-out buttons of the start menu, restart the game.')):
            LG.select_language(language); shutil.rmtree(self.wdir, ignore_errors=True); self.e = ES.SavesScreen(self.J)
            TIS.write(os.path.join(self.wdir, 'data1.dat'), TIS.logfile(1)); bad = bytearray(TIS.logfile(3)); bad[100] ^= 1
            self.make_zip(**{'data1.dat': TIS.logfile(2), 'data2.dat': bytes(bad)})
            lines = self.answer('import', [self.zip])
            self.assertEqual(len(lines), 4, language); self.assertEqual(lines[0], line1, language); self.assertTrue(lines[1].startswith(copied) and 'before_import_' in lines[1], lines[1])
            self.assertEqual((lines[2], lines[3]), (ignores, do_update), language); self.assertEqual(self.e.msg_clr, ES.GREEN); self.assertTrue(self.e.needs_reload)

    def test_import_without_dialog_box(self):
        os.makedirs(os.path.join(self.wdir, 'import'), exist_ok=True)
        for language, att in (('fr', ['Pas de boîte de dialogue disponible : dépose tes fichiers (.zip, data1.dat…) dans', os.path.join(self.wdir, 'import'), 'puis clique de nouveau sur Importer.']),
                            ('en', ['No file dialog available: put your files (.zip, data1.dat…) in', os.path.join(self.wdir, 'import'), 'then click Import again.'])):
            LG.select_language(language)
            with mock.patch.object(os, 'startfile', create=True):
                self.assertEqual(self.answer('import', [], unavailable=True), att, language)
            self.assertEqual(self.e.msg_clr, ES.RED)

    def test_import_impossible(self):
        empty_zip = lambda: self.make_zip(**{'lisez_moi.txt': b'rien'})
        fake_zip = os.path.join(self.t, 'z.zip'); TIS.write(fake_zip, b'pas un zip')
        small = os.path.join(self.t, 'state_01.dqs'); TIS.write(small, b'x')
        short = os.path.join(self.t, 'data1.dat'); TIS.write(short, b'abc')
        att = {'fr': ('Impossible : Aucun fichier de sauvegarde reconnu (data1.dat a data5.dat, data9.dat ou savestates/state_NN.dqs attendus).',
                      "Impossible : Aucun fichier de sauvegarde reconnu (z.zip : ce n'est pas un .zip valide).",
                      'Impossible : Aucun fichier de sauvegarde reconnu (state_01.dqs : fichier trop petit (%s)).',
                      'Impossible : Aucun fichier de sauvegarde reconnu (data1.dat : taille 3 au lieu de 15360 (%s)).'),
               'en': ('Failed: No save file recognized (expected data1.dat to data5.dat, data9.dat or savestates/state_NN.dqs).',
                      'Failed: No save file recognized (z.zip: not a valid .zip file).',
                      'Failed: No save file recognized (state_01.dqs: file too small (%s)).',
                      'Failed: No save file recognized (data1.dat: size 3 instead of 15360 (%s)).')}
        for language in ('fr', 'en'):
            LG.select_language(language); nothing, bad_zip, too_small, size_value = att[language]
            empty_zip(); self.assertEqual(self.answer('import', [self.zip]), [nothing], language)
            self.assertEqual(self.answer('import', [fake_zip]), [bad_zip], language)
            self.assertEqual(self.answer('import', [small]), [too_small % self.t], language); self.assertEqual(self.answer('import', [short]), [size_value % self.t], language)
            self.assertEqual(self.e.msg_clr, ES.RED)

    def test_refused_savefile_says_why(self):
        for language, junk, damaged in (('fr', "ce n'est pas un journal du jeu (en-tete inconnu)", 'fichier abime (somme de controle incorrecte)'),
                                     ('en', 'not a game adventure log (unknown header)', 'damaged file (checksum mismatch)')):
            LG.select_language(language); j = bytearray(TIS.logfile(1)); j[0x500] ^= 1
            self.assertEqual(FJ.check('data1.dat', bytes(j)), damaged, language); self.assertEqual(FJ.check('data1.dat', bytes(range(256)) * 60), junk, language)

    def test_write_not_possible(self):
        TIS.write(self.zip, b'')
        self.make_zip(**{'data1.dat': TIS.logfile(2)})
        for language, att in (('fr', "Impossible : Aucun fichier n'a pu etre ecrit (data1.dat : ecriture impossible (disque) ; le fichier actuel est inchange)."),
                            ('en', 'Failed: No file could be written (data1.dat: could not be written (disque); the current file is unchanged).')):
            LG.select_language(language)
            with mock.patch.object(S, 'atomic_write', lambda path, raw, **kw: 'disque'):
                self.assertEqual(self.answer('import', [self.zip]), [att], language)

    # -- screen drawing
    def test_screen_drawing(self):
        explanation = {'fr': ['Exporter : enregistre tes journaux (data1 à data5, data9) et tes états instantanés dans un fichier .zip.',
                              'Importer : lit un .zip de ce genre, ou des fichiers data1.dat, data2.dat… (par exemple copiés depuis un téléphone Android).',
                              "Les fichiers remplacés sont d'abord copiés dans le dossier « before_import_… » de tes sauvegardes."],
                       'en': ['Export: saves your adventure logs (data1 to data5, data9) and your save states into a .zip file.',
                              'Import: reads a .zip like that, or data1.dat, data2.dat… files (for example copied from an Android phone).',
                              'Replaced files are first copied to the "before_import_…" folder in your saves folder.']}
        titles = {'fr': ('Sauvegardes', 'Exporter', 'Importer'), 'en': ('Saves', 'Export', 'Import')}
        for language in ('fr', 'en'):
            LG.select_language(language); J = FakeGame(); e = ES.SavesScreen(J); e._say(['Un message.'], ES.GREEN)
            with without_screen(ES): e.draw_all(J, 640.0, 360.0, 2.0)
            self.assertEqual(J.drawn[:1] + J.drawn[-3:], [titles[language][0], titles[language][1], titles[language][2], 'Un message.'], language)
            self.assertEqual(' '.join(J.drawn[1:-3]), ' '.join(explanation[language]), language)          # (the sentences may wrap: made the frame and its outside back button fit in the window's height)
        self.assert_no_french(J.drawn, whitelist=('Un message.',))

    def test_explanation_translated_in_full_before_being_cut(self):
        """Narrow window: the help sentences wrap onto several lines. English has a different word order: the sentence is translated
        as a whole THEN split (otherwise the French pieces have no translation and stay in French)."""
        for language in ('fr', 'en'):
            LG.select_language(language); J = FakeGame(); e = ES.SavesScreen(J)
            with without_screen(ES): e.draw_all(J, 640.0, 360.0, 0.4)
            lines = J.drawn[1:-2]                                                  # (without the title or the two buttons)
            self.assertGreater(len(lines), len(ES.EXPLANATION), 'the window must be narrow enough to cut the sentences')
            rejoined = ' '.join(lines)
            for phrase in ES.EXPLANATION: self.assertIn(LG.tr(phrase), rejoined, language)
            if language == 'en': self.assert_no_french(lines, whitelist=('before_import_…',))

    def test_start_menu_button(self):
        """The port puts its "Saves" button in the start menu (in place of "Sauv. cloud")."""
        ml = types.SimpleNamespace(types={'53': {'nodes': [], 'parts': [], 'params': [], 'codes': [], 'name': 'Make_StartMenuSecond'}})
        for language, att in (('fr', 'Sauvegardes'), ('en', 'Saves')):
            LG.select_language(language)
            with mock.patch.object(UM.Window, 'param_str') as ps: UM.Window(ml, 53)
            self.assertEqual([c.args for c in ps.call_args_list], [(5, 0, att)], language)


# ---------------------------------------------------------------------------------------------------------------------------------- history
def test_history():
    """Sample dialogues and battles (neutral texts: the names and dialogues are the game's, never translated)."""
    h = HI.History(None, lambda: 1000.0)
    h.add('Hello there.', 'Alena', 200); h.add('Welcome.', None, 5200)
    for i in range(1, 7):
        h.add_battle({'t': 100 * i, 'outcome': ('victory', 'escape', 'defeat')[i % 3], 'gold': 21, 'xp': 38,
                          'enemies': [{'name': 'Slime', 'total': 3, 'defeated': 3}, {'name': 'Golem', 'total': 2, 'defeated': 1}], 'objects': [{'name': 'Medicinal herb'}, {'name': 'Life stone'}]})
    return h


class FakeBitmapFont:
    """The game's bitmap font: only what draw_all() asks of it."""
    ascent = 18.0; leading = 24.0; PAD = 0.0
    def width_px(self, text): return 6.0 * len(text)


class History(Language):
    def make_view(self, h, tab=UH.O_DIALOGUES, favorites_only=False, with_font=True):
        J = FakeGame(history=h, reg=RG.Settings(None))
        if with_font: J.ui_render = types.SimpleNamespace(texts=types.SimpleNamespace(bitmap=FakeBitmapFont(), messages=None), ml=None, plate=lambda *a, **k: True, draw_all=lambda *a, **k: None)
        J.reg['history_favorites_only'] = favorites_only
        v = UH.HistoryView(J.pause); v.enter(tab); v.rec = []
        v._line = lambda bm, text, x, y, sc, clr, size_value: v.rec.append(text)                    # (the text line: the game's bitmap font or the system's)
        return v

    def draw_all(self, v):
        with without_screen(UH), mock.patch.object(UH, 'HM', mock.MagicMock()): v.draw_all()
        return v.rec

    # -- the header, the tabs, the help
    def test_window_border(self):
        h = test_history()
        att = {'fr': ('Historique', ('Dialogues', 'Combats'), 'Favoris seulement',
                      ['Haut / Bas : message précédent / suivant', 'Molette : défiler', 'Touches de caméra : onglet', 'Entrée : favori ★', 'Suppr : supprimer', 'F : favoris seulement', 'Échap : fermer']),
               'en': ('History', ('Dialogue', 'Battles'), 'Favorites only',
                      ['Up / Down: previous / next message', 'Mouse wheel: scroll', 'Camera keys: tab', 'Enter: favorite ★', 'Delete: delete', 'F: favorites only', 'Esc: close'])}
        for language in ('fr', 'en'):
            LG.select_language(language); title_screen, tabs, sieve, helptext = att[language]
            for with_font in (True, False):                                                                  # (the game's bitmap font, or fallback to the system font)
                rec = self.draw_all(self.make_view(h, with_font=with_font)); helptext_view = ' | '.join(rec)
                self.assertIn(title_screen, rec); self.assertEqual([t for t in rec if t in tabs], list(tabs)); self.assertIn(sieve, rec)
                for line in helptext: self.assertIn(line, helptext_view, (language, line))
        self.assert_no_french([t for t in rec if t not in ('Alena',)])

    def test_helptext_without_history_key(self):
        """No more History key: no "H : suite" line in the help, even with a key in an old settings file."""
        h = test_history()
        for language, line in (('fr', 'H : suite'), ('en', 'H: next')):
            LG.select_language(language); v = self.make_view(h); v.J.reg['keys']['history'] = ['H', None]; self.assertNotIn(line, ' | '.join(self.draw_all(v)))

    def test_empty_entries_texts(self):
        h = HI.History(None, lambda: 1000.0)
        att = {('fr', False, UH.O_DIALOGUES): "Aucun dialogue pour l'instant.", ('fr', False, UH.O_BATTLES): "Aucun combat pour l'instant.",
               ('fr', True, UH.O_DIALOGUES): 'Aucun dialogue en favori : décoche « Favoris seulement », choisis un dialogue et appuie sur Entrée (ou clique son étoile) pour le garder.',
               ('fr', True, UH.O_BATTLES): 'Aucun combat en favori : décoche « Favoris seulement », choisis un combat et appuie sur Entrée (ou clique son étoile) pour le garder.',
               ('en', False, UH.O_DIALOGUES): 'No dialogue yet.', ('en', False, UH.O_BATTLES): 'No battle yet.',
               ('en', True, UH.O_DIALOGUES): 'No favorite dialogue: uncheck "Favorites only", choose a dialogue and press Enter (or click its star) to keep it.',
               ('en', True, UH.O_BATTLES): 'No favorite battle: uncheck "Favorites only", choose a battle and press Enter (or click its star) to keep it.'}
        for (language, fav, tab), msg in att.items():
            LG.select_language(language); rec = self.draw_all(self.make_view(h, tab, fav))
            self.assertIn(msg, ' '.join(rec), (language, fav, tab))                       # (the message, cut into lines at spaces: the lines put end to end give it back)
            if language == 'en': self.assert_no_french(rec)

    # -- a battle: header (outcome), lines composed around the game's names
    def test_battle_header_and_lines(self):
        h = test_history()
        att = {'fr': (('Victoire', 'Fuite', 'Défaite'), 'Slime ×3', 'Golem ×2 : 1 vaincu, 1 resté', 'Or : 21\u00a0\u00a0\u00a0\u00a0\u00a0Expérience : 38', 'Objets : Medicinal herb, Life stone'),
               'en': (('Victory', 'Escaped', 'Defeat'), 'Slime ×3', 'Golem ×2: 1 defeated, 1 remained', 'Gold: 21\u00a0\u00a0\u00a0\u00a0\u00a0Experience: 38', 'Items: Medicinal herb, Life stone')}
        for language in ('fr', 'en'):
            LG.select_language(language); rec = self.draw_all(self.make_view(h, UH.O_BATTLES)); outcomes = att[language][0]
            for t in outcomes: self.assertIn(t, rec, (language, t))                              # (the header of each box: the outcome of the battle)
            for t in att[language][1:]: self.assertIn(t, rec, (language, t))                     # (the names of Slime, Golem, items: the game's, never translated)
        self.assert_no_french(rec)

    def test_battle_lines_all_outcomes(self):
        factory = lambda **kw: HI.battle_element(1, dict({'t': 5, 'outcome': 'victory', 'gold': 0, 'xp': 0, 'enemies': []}, **kw))
        def name_str(**kw): return {'name': 'Bat', 'total': 1, 'defeated': 0, **kw}
        scenario = [factory(outcome='defeat'),                                                                                           # no known enemy
               factory(outcome='escape', enemies=[name_str(fled=1)]), factory(outcome='escape', enemies=[name_str(vanished=1)]), factory(outcome='escape', enemies=[name_str()]),
               factory(outcome='escape', enemies=[{'name': 'Golem', 'total': 5, 'defeated': 2, 'fled': 1, 'vanished': 1}]),
               factory(outcome='escape', enemies=[{'name': 'Golem', 'total': 5, 'defeated': 1, 'fled': 2, 'vanished': 2}]),
               factory(**{'gold': 3, 'xp': 4})]                                                                                   # victory with no known enemy
        att = {'fr': [['Ennemis inconnus'], ['Bat : enfui'], ['Bat : disparu'], ['Bat : resté'], ['Golem ×5 : 2 vaincus, 1 enfui, 1 disparu, 1 resté'], ['Golem ×5 : 1 vaincu, 2 enfuis, 2 disparus'],
                      ['Ennemis inconnus', 'Or : 3\u00a0\u00a0\u00a0\u00a0\u00a0Expérience : 4']],
               'en': [['Unknown enemies'], ['Bat: fled'], ['Bat: vanished'], ['Bat: remained'], ['Golem ×5: 2 defeated, 1 fled, 1 vanished, 1 remained'], ['Golem ×5: 1 defeated, 2 fled, 2 vanished'],
                      ['Unknown enemies', 'Gold: 3\u00a0\u00a0\u00a0\u00a0\u00a0Experience: 4']]}
        for language in ('fr', 'en'):
            LG.select_language(language); self.assertEqual([HI.battle_lines(c) for c in scenario], att[language], language)
        self.assert_no_french([l for ls in att['en'] for l in ls])

    def test_outcome_labels(self):
        for language, att in (('fr', {'victory': 'Victoire', 'escape': 'Fuite', 'defeat': 'Défaite'}), ('en', {'victory': 'Victory', 'escape': 'Escaped', 'defeat': 'Defeat'})):
            LG.select_language(language); self.assertEqual({k: LG.tr(v) for k, v in HI.OUTCOME_CAPTION.items()}, att, language)

    def test_replacement_names_when_engine_does_not_respond(self):
        for language, monster, item in (('fr', 'Monstre', 'Objet n°12'), ('en', 'Monster', 'Item #12')):
            LG.select_language(language)
            s = HC.Tracking(); s.dead(4, 7); self.assertEqual(s.enemies()[0]['name'], monster, language)
            c = types.SimpleNamespace(_item_names={}, _engine_text=lambda kind, number: None); self.assertEqual(HC.BattleSensor._item_name(c, 12), item, language)

    def test_favorite_whose_message_is_missing(self):
        class Folder(THC.Base): pass
        b = Folder(); b.setUp()
        try:
            h = b.hist({802199: THC.RAW_SIMPLE}); h.toggle_favorite(h.add(HI.clean(THC.RAW_SIMPLE), None, 1, 802199))
            for language, att in (('fr', '(Message introuvable dans les fichiers du jeu : b0802000#199)'), ('en', '(Message not found in the game files: b0802000#199)')):
                LG.select_language(language); self.assertEqual(b.hist({}).favorites[0].text, att, language)
        finally: b.tearDown()

    # -- the console
    def test_console_messages(self):
        t = tempfile.mkdtemp(prefix='lm_hist_'); self.addCleanup(shutil.rmtree, t, True)
        def output(f):
            buffer = io.StringIO()
            with contextlib.redirect_stdout(buffer): f()
            return buffer.getvalue()
        for language, unreadable, not_written in (('fr', 'History favorites unreadable (', 'History favorites not saved: '), ('en', 'History favorites unreadable (', 'History favorites not saved: ')):
            LG.select_language(language)
            p = os.path.join(t, 'fav_%s.json' % language)
            with open(p, 'w', encoding='utf-8') as f: f.write('{not json')
            h0 = HI.History(p, lambda: 1.0); s = output(lambda: h0.set_adventure('0123456789a%s' % language[0])); self.assertTrue(s.startswith(unreadable), (language, s)); self.assertTrue(os.path.exists(h0.path + '.corrupt'))      # (the common file becomes the adventure's)
            block = os.path.join(t, 'un_fichier_%s' % language)
            with open(block, 'w') as f: f.write('x')
            h = HI.History(os.path.join(block, 'fav.json'), lambda: 1.0); h.set_adventure('0123456789ab'); h.add('Hello.', None, 1); h._dirty = True
            s = output(lambda: h.store(True)); self.assertTrue(s.startswith(not_written), (language, s))
        def refuse(sym): raise OSError('no symbol')
        for language, sensor, battle in (('fr', 'History: hooks not installed (', 'Battle history: '), ('en', 'History: hooks not installed (', 'Battle history: ')):
            LG.select_language(language)
            engine = types.SimpleNamespace(core=types.SimpleNamespace(export=refuse))
            s = output(lambda: HI.Sensor(engine)); self.assertTrue(s.startswith(sensor), (language, s))
            s = output(lambda: HC.BattleSensor(engine)); self.assertTrue(s.startswith(battle + 'hooks not installed ('), (language, s))
            engine = types.SimpleNamespace(core=types.SimpleNamespace(export=lambda sym: 0))                          # an engine without the expected symbols
            s = output(lambda: HC.BattleSensor(engine)); self.assertTrue(s.startswith(battle), (language, s)); self.assertFalse(french(s), s)


# ---------------------------------------------------------------------------------------------------------------------------------- name entry, license, interface editor, notifications...
class Other(Language):
    def test_name_entry(self):
        functions = list(SN.FUNCTIONS)
        for language, att in (('fr', ['Saisir un nom', 'Clavier : taper le nom', 'Entrée : valider · Échap : retour']), ('en', ['Enter a name', 'Keyboard: type the name', 'Enter: confirm · Esc: back'])):
            LG.select_language(language); J = FakeGame(); s = SN.NameEntry(J); s.open_menu(8)
            with without_screen(SN): s.draw_all(640.0, 360.0, 1.6)
            self.assertIn(att[0], J.drawn); self.assertIn(att[1], J.drawn); self.assertIn(att[2], J.drawn)
            self.assertEqual([t for t in J.drawn if t in functions], functions, language)                    # (the function button labels come from the game: not translated)
        self.assert_no_french(J.drawn, whitelist=('à À',))                                                         # whitelist: "à À" = the game's label (C_ALPHABET_ETC) of the accented-letters page button

    def test_license(self):
        for language, title_screen in (('fr', 'Licence'), ('en', 'License')):
            LG.select_language(language); J = FakeGame(); lic = AP.License(None)
            lay = types.SimpleNamespace(content_height=1000.0, height=500.0, x=0, y=0, view_y=0, draw=lambda: None)
            lic._layout = lambda J, ui_scale: lay
            with without_screen(): lic.draw_all(J, 640.0, 360.0, 1.5)
            self.assertEqual(J.drawn, [title_screen, 'Privacy Policy'], language)                                    # "Privacy Policy": the game's text
        # the port's header text is already in English, the original list follows: none of this depends on the language
        for language in ('fr', 'en'):
            LG.select_language(language); self.assertEqual(AP.License(None).text.replace('\n', ' ').count('This project is unofficial'), 1)
        self.assertFalse(french(AP.PROJECT_LICENSE))
        txt = AP.License(None).text
        self.assertIn('Dragon Quest IV PC port', txt); self.assertIn('engine (libdq4core.so)', txt); self.assertNotIn('{', txt)          # (the running game's name and engine: games.py)

    def test_interface_editor_element_names(self):
        att = {'fr': {'map': 'Carte', 'menu': 'Commandes', 'chat': 'Discussion', HM.EXTRA: 'Action du véhicule', HM.BATTLE: 'Vitesse de combat', HM.DPAD: 'Croix', HM.BAR: 'Barre de rotation'},
               'en': {'map': 'Map', 'menu': 'Controls', 'chat': 'Talk', HM.EXTRA: 'Vehicle action', HM.BATTLE: 'Battle speed', HM.DPAD: 'D-pad', HM.BAR: 'Camera rotation bar'}}
        for language in ('fr', 'en'):
            LG.select_language(language); self.assertEqual({k: LG.tr(v) for k, v in HM.CAPTION.items()}, att[language], language)
            J = FakeGame(reg=RG.Settings(None), engine=types.SimpleNamespace(dpad_size=lambda: 1)); b = HM.Buttons(J)
            with without_screen(HM), mock.patch.object(HM, 'border'), mock.patch.object(HM, 'draw_grid'), mock.patch.object(b, '_plate', return_value=True), mock.patch.object(b, '_sprite', return_value=(mock.MagicMock(), 1)), \
                    mock.patch.object(b, '_battle_arrows'), mock.patch.object(b, '_dpad'), mock.patch.object(b, '_bar'):
                b.draw_all(list(HM.BUTTONS) + [HM.DPAD, HM.BAR], editing=True)
            self.assertEqual(sorted(J.drawn), sorted(att[language].values()), language)                         # (in edit mode, each item carries its name)

    def test_sample_texts_of_the_dialogues(self):
        """Each of the editor's sample lines is translated, and the translated line is the one written to the canvas."""
        for language in ('fr', 'en'):
            LG.select_language(language); written_items = []
            drawing = mock.MagicMock(); drawing.text = lambda xy, t, **kw: written_items.append(t)
            j = types.SimpleNamespace(SAMPLE_TEXTS=AM.MenusMixin.SAMPLE_TEXTS, SAMPLE_HEIGHT=AM.MenusMixin.SAMPLE_HEIGHT, args=types.SimpleNamespace(cache='/inexistant'), _trial=1, new_sample=lambda: None)
            with mock.patch('PIL.ImageDraw.Draw', return_value=drawing): AM.MenusMixin._preview_canvas(j)
            self.assertEqual(written_items, [LG.tr(t) for t in AM.MenusMixin.SAMPLE_TEXTS[1]], language)
            if language == 'en': self.assertEqual(written_items, ['This is a test text.', 'It is used to adjust the size and', 'position of the dialogue boxes.'])
        entry(); self.assert_no_french([LG.tr(t) for lines in AM.MenusMixin.SAMPLE_TEXTS for t in lines])                    # (all the sample texts, not only the test's)

    def test_f1_info(self):
        att = {'fr': '50 images/s | moteur 1.0 pas/s (5.0 ms) | pire image 20 ms | dessin Python 3.0 ms', 'en': '50 frames/s | engine 1.0 steps/s (5.0 ms) | worst frame 20 ms | Python drawing 3.0 ms'}
        for language in ('fr', 'en'):
            LG.select_language(language)
            lbl = lambda: types.SimpleNamespace(text='', width=0, x=0, y=0, content_width=100.0, content_height=10.0, draw=lambda: None)
            j = types.SimpleNamespace(helptext=True, stats=True, spacings=[0.02] * 50, step_times=[0.0, 1.0, 2.0], dt_engine=0.005, dt_drawing=0.003, n=0, lbl_stats=lbl(), tag_label=lbl(), lbl_hd=lbl(), height=720, width=1280,
                                      helptext_key=None, helptext_width=0.0, helptext_border=lbl(), _info=lambda: None, _helptext_margin=lambda: ('right', 400))
            with without_screen(AM): AM.MenusMixin._draw_helptext(j)
            self.assertEqual(j.lbl_stats.text, att[language], language)
        self.assert_no_french([j.lbl_stats.text])

    def test_f1_panel_lines(self):
        """The first two lines of the F1 panel (location, window, display settings, sound): English without French, French exactly as before."""
        from dq456_pc.window import game as GA
        from dq456_pc.core import engine as ENGINE
        def panel(language, part, game_map, field, fullscreen, mode, smoothing, msaa, sound_ok, sound_active):
            LG.select_language(language)
            lbl = lambda: types.SimpleNamespace(text='')
            j = types.SimpleNamespace(engine=types.SimpleNamespace(state=types.SimpleNamespace(part=part, game_map=game_map, field=field), frames=118), mode=mode, width=1280, height=720, is_fullscreen=fullscreen,
                                      smoothing=smoothing, post=types.SimpleNamespace(msaa=msaa), _engine_yaw=lambda: 0.4, sound=types.SimpleNamespace(ok=sound_ok, active=sound_active, vol_music=1.0, vol_sfx=0.5),
                                      tag_label=lbl(), lbl_hd=lbl())
            GA.Game._info(j); return j.tag_label.text, j.lbl_hd.text
        cases = [(ENGINE.PART_FIELD, 'x', object(), False, 0, True, 0, True, True), (ENGINE.PART_BATTLE, 'bk1', None, True, 1, False, 4, True, False),
                 (ENGINE.PART_TOWN, 'mak1f1', None, False, 4, True, 0, False, False), (ENGINE.PART_TOWN, None, None, False, 0, True, 0, True, True)]
        fr = [panel('fr', *c) for c in cases]
        self.assertEqual(fr[0], ('Carte du monde | fenêtre 1280 x 720 | moteur : image 118, partie 0xe',
                                 'Sprites : Originaux (pixels nets)  |  Décor : rendu d\'origine lissé\nLissage des textures : oui  |  Antialiasing : non  |  Caméra : rotation 0 °\nSon : oui (musique 100 %, bruitages 50 %)'))
        self.assertEqual(fr[1], ('Combat bk1 | fenêtre 1280 x 720 (plein écran) | moteur : image 118, partie 0xd',
                                 'Sprites : EPX x8  |  Décor : EPX x8\nLissage des textures : non  |  Antialiasing : x4  |  Caméra : rotation 0 °\nSon : non (musique 100 %, bruitages 50 %)'))
        self.assertIn('Carte mak1f1 |', fr[2][0]); self.assertIn('Sprites : Pixel perfect  |  Décor : rendu d\'origine lissé', fr[2][1]); self.assertIn('Son : indisponible', fr[2][1]); self.assertIn('Carte ? |', fr[3][0])
        en = [panel('en', *c) for c in cases]
        self.assertEqual(en[0], ('World map | window 1280 x 720 | engine: frame 118, part 0xe',
                                 'Sprites: Originals (sharp pixels)  |  Scenery: smoothed original rendering\nTexture smoothing: yes  |  Antialiasing: no  |  Camera: rotation 0 °\nSound: yes (music 100 %, effects 50 %)'))
        self.assertEqual(en[1], ('Battle bk1 | window 1280 x 720 (fullscreen) | engine: frame 118, part 0xd',
                                 'Sprites: EPX x8  |  Scenery: EPX x8\nTexture smoothing: no  |  Antialiasing: x4  |  Camera: rotation 0 °\nSound: no (music 100 %, effects 50 %)'))
        self.assertIn('Map mak1f1 |', en[2][0]); self.assertIn('Sprites: Pixel perfect  |  Scenery: smoothed original rendering', en[2][1]); self.assertIn('Sound: unavailable', en[2][1]); self.assertIn('Map ? |', en[3][0])
        self.assert_no_french([t for pair in en for t in pair], whitelist=())

    def test_notifications(self):
        """Canceling a load (nothing to cancel: no message; then canceled) and importing saves: the messages the tool writes itself."""
        for language, att in (('fr', ['Chargement annulé', 'Sauvegardes importées']), ('en', ['Load undone', 'Saves imported'])):
            LG.select_language(language); msgs = []
            def toast(text, duration=1.8):
                j = types.SimpleNamespace(toasts=[]); AM.MenusMixin.toast(j, text, duration); msgs.append(j.toasts[0][0])
            j = types.SimpleNamespace(toast=toast, undo_state=None)
            self.assertFalse(IN.SnapshotsMixin.cancel_loading(j))                                         # nothing to cancel (silent)
            j.undo_state = {'a': 1}; j._complete_savestate = lambda: {'b': 2}; j._apply_savestate = lambda d: None; self.assertTrue(IN.SnapshotsMixin.cancel_loading(j))
            j.port_screen = types.SimpleNamespace(needs_reload=True); j._after_import = lambda: TI.TitleMixin._after_import(j); TI.TitleMixin._close_port_screen(j)
            self.assertEqual(msgs, att, language)

    def test_an_already_formatted_text_stays_as_is(self):
        """Messages with placeholders ("State 3 saved") are formatted BEFORE reaching toast: they pass through unchanged."""
        entry(); j = types.SimpleNamespace(toasts=[]); AM.MenusMixin.toast(j, 'État 3 enregistré'); self.assertEqual(j.toasts[0][0], 'État 3 enregistré')

    def test_savestates_location(self):
        """The location written in a savestate file is a catalog key (translated by the page that displays it), whatever the language."""
        from dq456_pc.core import engine as ENGINE
        cases = [(ENGINE.PART_CASINO, 'ev04', 'settings.casino_poker'), (ENGINE.PART_CASINO, 'ev05', 'settings.casino_slot_machine'), (ENGINE.PART_CASINO, 'ev99', 'settings.casino'), (ENGINE.PART_BESTIARY, 'x', 'settings.bestiary'),
                 (ENGINE.PART_FIELD, 'x', 'settings.world_map'), (ENGINE.PART_BATTLE, 'x', 'settings.battle'), (ENGINE.PART_TOWN, 'dnb1b2', 'dnb1b2')]
        for language in ('fr', 'en'):
            LG.select_language(language)
            for part, game_map, att in cases:
                j = types.SimpleNamespace(engine=types.SimpleNamespace(state=types.SimpleNamespace(part=part, game_map=game_map))); self.assertEqual(IN.SnapshotsMixin._location(j), att, (language, att))
        entry()
        self.assertEqual([LG.tr(a) for _, _, a in cases[:6]], ['Casino: poker', 'Casino: slot machine', 'Casino', 'Bestiary', 'World map', 'Battle'])

    def test_location_written_by_an_older_version(self):
        """A savestate written before the catalog keys holds the French text: it is still shown, in the current language."""
        for old, key in (('Carte du monde', 'settings.world_map'), ('Combat', 'settings.battle'), ('mak1f1', None)):
            self.assertEqual(PA.Pause._readable_location({'location': old}), key or '')

    def test_module_console_messages(self):
        """The console messages of the screens and resources (called for real with a missing or broken game): English without French, French as before."""
        from dq456_pc.menus import message_font as MF
        t = tempfile.mkdtemp(prefix='lm_cons_'); self.addCleanup(shutil.rmtree, t, True)
        def outage(*a, **kw): raise OSError('disque')
        for language in ('fr', 'en'):
            LG.select_language(language)
            logged = []; MF.extract_message_font(os.path.join(t, 'inexistant'), os.path.join(t, 'cache'), log=logged.append)
            logged_ap = []; AP.prepare(os.path.join(t, 'inexistant'), os.path.join(t, 'cache_ap'), log=logged_ap.append)
            logged_um = []; UM.prepare_resources(os.path.join(t, 'inexistant'), os.path.join(t, 'cache_um'), log=logged_um.append)
            output = io.StringIO()
            j = types.SimpleNamespace(_complete_savestate=outage, _apply_savestate=lambda d: None, state_path=lambda n: 'x', get_framebuffer_size=outage, engine=None)
            with contextlib.redirect_stdout(output), mock.patch.object(IN.SS, 'read', return_value={}), mock.patch.object(IN.SS, 'check'):
                IN.SnapshotsMixin.load_state(j, 1); IN.SnapshotsMixin._clone_thumbnail(j)
            starts = {'fr': ['Message font not extracted (', 'Title images unavailable', 'Menu resources unavailable'], 'en': ['Message font not extracted (', 'Title images unavailable', 'Menu resources unavailable']}[language]
            self.assertTrue(logged[-1].startswith(starts[0]) and logged_ap[-1].startswith(starts[1]) and logged_um[-1].startswith(starts[2]), (language, logged, logged_ap, logged_um))
            lines = output.getvalue().splitlines(); self.assertEqual(len(lines), 2, lines)
            self.assertEqual([l.split(':')[0].strip() for l in lines], {'fr': ['state before loading not kept', 'thumbnail failed'], 'en': ['state before loading not kept', 'thumbnail failed']}[language])
            self.assert_no_french([m.replace('SE-GARRIR', '') for m in logged + logged_ap + logged_um] + lines)


# ---------------------------------------------------------------------------------------------------------------------------------- the catalog
SOURCES = ('menus/saves_screen.py', 'menus/language_screen.py', 'menus/ui_history.py', 'core/history.py', 'battle/battle_history.py', 'menus/ui_menu.py', 'menus/pre_game.py', 'menus/name_entry.py', 'menus/hud_mobile.py',
           'menus/message_font.py', 'window/title_screen.py', 'window/snapshots.py', 'window/menu_display.py', 'window/battle_replay.py', 'persistence/saves.py', 'persistence/logfile_format.py')


def marked_texts(files):
    """{text: [file:line]} of the texts passed to tr(...) / N_(...) in these dq456_pc files."""
    out = {}
    for f in files:
        with open(os.path.join(ROOT, 'dq456_pc', f), encoding='utf-8') as fh: tree = ast.parse(fh.read())
        for n in ast.walk(tree):
            if isinstance(n, ast.Call) and getattr(n.func, 'id', None) in ('tr', 'N_') and n.args and isinstance(n.args[0], ast.Constant) and isinstance(n.args[0].value, str): out.setdefault(n.args[0].value, []).append('%s:%d' % (f, n.lineno))
    return out


class Catalog(Language):
    def test_each_marked_text_is_a_key_of_both_catalogs(self):
        """Every text marked in these modules (tr / N_) is a catalog key with its French and its English text (a typo in a key no longer lets a key through on screen)."""
        fr, en = LG.catalog('fr'), LG.catalog('en'); missing = []
        for t, locations in marked_texts(SOURCES).items():
            keys = keys_in_text(t)
            if not keys: self.assertFalse(french(t), 'not a key: %r (%s)' % (t, locations)); continue
            missing += ['%s (%s)' % (k, locations) for k in keys if k not in fr or k not in en]
        self.assertEqual(missing, [])

    def test_each_entry_is_used(self):
        """No orphan entry: every key of the `menus` catalog appears in the code."""
        used = set()
        for d, _, fs in os.walk(os.path.join(ROOT, 'dq456_pc')):
            if os.sep + 'texts' in d: continue
            for f in fs:
                if not f.endswith('.py'): continue
                with open(os.path.join(d, f), encoding='utf-8') as fh: tree = ast.parse(fh.read())
                used.update(k for n in ast.walk(tree) if isinstance(n, ast.Constant) and isinstance(n.value, str) for k in keys_in_text(n.value))
        self.assertEqual(sorted(set(catalog_by_file('fr')['menus']) - used), [])

    def test_each_language_gives_its_text(self):
        fr, en = catalog_by_file('fr')['menus'], catalog_by_file('en')['menus']
        LG.select_language('fr')
        for k, t in fr.items(): self.assertEqual(LG.tr(k), t)
        entry()
        for k, t in en.items(): self.assertEqual(LG.tr(k), t)


if __name__ == '__main__':
    unittest.main(verbosity=1)
