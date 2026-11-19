"""Language of the port's texts (dq456_pc/language.py), without window or engine: detection of the computer's language (each language of the port whatever its variant, otherwise
English; Chinese of Taiwan, Hong Kong, Macao in traditional characters), the setting and the codes of earlier versions ('fr' -> 'fr-fr'), `tr` / `N_` and the fallback (English, the only
one), the names of the languages, their fonts, line wrapping without spaces (Japanese, Chinese), the language files (format, round trip, problems, a file brought up to date),
adding a language (its file, the texts loaded again after they are edited), and the rules of the texts (dq456_pc/languages/<code>.json): the keys of the English file in the same order in
every language (the keys of the add-language screens only in English), "en" equal to the English text, the same placeholders (%d, %s...), spaces at the edges and line breaks as the
English text, no French in the English, a flag for every language, and every key the code uses exists and every key is used.

    python3 tests/test_language.py"""
import ast, json, os, re, shutil, sys, tempfile, unittest

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.join(HERE, '..')
sys.path.insert(0, ROOT)
from dq456_pc import language as LG

ACCENTS = re.compile('[àâäçéèêëîïôöùûüÿœÀÂÇÉÈÊËÎÏÔÙÛÜŒ]')
FRENCH_WORDS = {'le', 'la', 'les', 'des', 'du', 'une', 'et', 'ou', 'pour', 'dans', 'sur', 'avec', 'sans', 'est', 'pas', 'ces', 'aux', 'vos', 'votre', 'tes', 'tous', 'toutes', 'quand', 'comme', 'mais', 'donc', 'sont', 'chaque', 'sinon', 'aucun', 'aucune'}
GAPS = LG.GAPS
KEY = re.compile(r'^[a-z_]+\.[a-z0-9_]+$')
FILE_EXTENSIONS = {'json', 'py', 'txt', 'log', 'dat', 'dqs', 'png', 'zip'}         # ('settings.json' is a file name, not a key)
FLAGS = os.path.join(ROOT, 'dq456_pc', 'assets', 'flags')


def french(text):
    """The text contains an accented letter or a French function word."""
    if ACCENTS.search(text): return True
    return any(m in FRENCH_WORDS for m in re.findall(r"[a-zA-Z']+", text.lower().replace("'", ' ')))


def raw_entries(code):
    """[(key, en, text)] of a language file as it is written."""
    with open(LG.path_of(code), encoding='utf-8') as f: return [(e['key'], e['en'], e['text']) for e in json.load(f)['entries']]


def keys_in_text(t):
    """The catalog keys a string of the code holds: the string itself, or each part of a help text (keys separated by three spaces)."""
    return [p for p in re.split(r'\s{3,}', t.strip()) if KEY.match(p) and p.split('.')[1] not in FILE_EXTENSIONS]


class Detection(unittest.TestCase):
    def test_windows_all_french_variants(self):
        for code in (0x040C, 0x080C, 0x0C0C, 0x100C, 0x140C, 0x180C):                       # France, Belgium, Canada, Switzerland, Luxembourg, Monaco
            self.assertEqual(LG.system_language(lambda c=code: c), 'fr-fr', hex(code))

    def test_windows_languages_of_the_port(self):
        for code, lg in ((0x0409, 'en-us'), (0x0809, 'en-us'), (0x0407, 'de-de'), (0x0C07, 'de-de'), (0x0411, 'ja-jp'), (0x0C0A, 'es-es'), (0x080A, 'es-es'), (0x0410, 'it-it'),
                         (0x0810, 'it-it'), (0x0412, 'ko-kr'), (0x0804, 'zh-cn'), (0x1004, 'zh-cn'), (0x0404, 'zh-tw'), (0x0C04, 'zh-tw'), (0x1404, 'zh-tw')):
            self.assertEqual(LG.system_language(lambda c=code: c), lg, hex(code))      # (German of Austria, Spanish of Mexico, Chinese of Singapore, Taiwan, Hong Kong, Macao...)

    def test_windows_other_languages_give_english(self):
        for code in (0x0416, 0x0419, 0x0413, 0x041F):    # Portuguese, Russian, Dutch, Turkish
            self.assertEqual(LG.system_language(lambda c=code: c), 'en-us', hex(code))

    def test_locales_as_text(self):
        for t in ('fr_FR.UTF-8', 'fr', 'fr_BE', 'fr-CA', 'French_France', 'fr_CH@euro'):
            self.assertEqual(LG.system_language(lambda t=t: t), 'fr-fr', t)
        for t in ('en_US.UTF-8', 'C', 'POSIX', '', None, 'pt_BR', 'fra', 'frisian', 'fi_FI', 'jav'):              # ("fra", "frisian": not French; "jav": not Japanese)
            self.assertEqual(LG.system_language(lambda t=t: t), 'en-us', repr(t))
        for t, lg in (('de_DE.UTF-8', 'de-de'), ('de-AT', 'de-de'), ('German_Germany', 'de-de'), ('es_MX', 'es-es'), ('Spanish_Spain', 'es-es'), ('it_IT', 'it-it'), ('ja_JP.UTF-8', 'ja-jp'),
                      ('Japanese_Japan', 'ja-jp'), ('ko_KR', 'ko-kr'), ('Korean_Korea', 'ko-kr'), ('zh_CN', 'zh-cn'), ('zh-Hans', 'zh-cn'), ('zh_SG', 'zh-cn'), ('zh-TW', 'zh-tw'),
                      ('zh-Hant-HK', 'zh-tw'), ('zh_MO', 'zh-tw'), ('Chinese (Simplified)_China', 'zh-cn'), ('Chinese (Traditional)_Taiwan', 'zh-tw')):
            self.assertEqual(LG.system_language(lambda t=t: t), lg, t)

    def test_own_variant_first(self):
        """a language with several variants of its own: the computer's one if the port has it (here a fake fr-ca), otherwise the first one."""
        saved = list(LG.LANGUAGES)
        try:
            LG.LANGUAGES[:] = saved + ['fr-ca']
            self.assertEqual(LG.system_language(lambda: 'fr_CA'), 'fr-ca'); self.assertEqual(LG.system_language(lambda: 'fr_BE'), 'fr-fr')
        finally: LG.LANGUAGES[:] = saved

    def test_read_failure_gives_english(self):
        def outage(): raise OSError('pas de langue')
        self.assertEqual(LG.system_language(outage), 'en-us')


class Setting(unittest.TestCase):
    def tearDown(self): LG.select_language('fr-fr')

    def test_choices(self):
        self.assertEqual(LG.LANGUAGES[:9], ['en-us', 'fr-fr', 'de-de', 'es-es', 'it-it', 'ja-jp', 'ko-kr', 'zh-cn', 'zh-tw'])
        self.assertEqual(LG.CHOICES, ['system'] + LG.LANGUAGES)
        self.assertEqual(LG.select_language('fr-fr', reader=lambda: 0x0409), 'fr-fr'); self.assertEqual(LG.current_language(), 'fr-fr')
        self.assertEqual(LG.select_language('ja-jp', reader=lambda: 0x040C), 'ja-jp'); self.assertEqual(LG.requested(), 'ja-jp')
        self.assertEqual(LG.select_language('system', reader=lambda: 0x040C), 'fr-fr'); self.assertEqual(LG.select_language('system', reader=lambda: 0x0412), 'ko-kr'); self.assertEqual(LG.requested(), 'system')

    def test_codes_of_earlier_versions(self):
        for old, new in (('fr', 'fr-fr'), ('en', 'en-us'), ('de', 'de-de'), ('zh', 'zh-cn'), ('systeme', 'system'), ('system', 'system')):
            self.assertEqual(LG.normalized(old), new, old)
        self.assertEqual(LG.select_language('en', reader=lambda: 0x040C), 'en-us'); self.assertEqual(LG.requested(), 'en-us')
        self.assertEqual(LG.catalog('fr'), LG.catalog('fr-fr'))

    def test_unknown_value_treated_as_system(self):
        self.assertEqual(LG.select_language('klingon', reader=lambda: 0x0409), 'en-us'); self.assertEqual(LG.requested(), 'system')
        self.assertEqual(LG.select_language(None, reader=lambda: 0x040C), 'fr-fr')

    def test_read_setting_from_file(self):
        with tempfile.TemporaryDirectory() as t:
            p = os.path.join(t, 'settings.json')
            self.assertEqual(LG.read_setting(p), 'system')                                                 # absent
            for v, att in (('fr-fr', 'fr-fr'), ('fr', 'fr-fr'), ('en', 'en-us'), ('zh-tw', 'zh-tw'), ('system', 'system'), ('xx', 'system'), ('pt-br', 'system'), (3, 'system')):
                with open(p, 'w', encoding='utf-8') as f: json.dump({'language': v}, f)
                self.assertEqual(LG.read_setting(p), att, v)
            with open(p, 'w', encoding='utf-8') as f: json.dump({'sound': True}, f)
            self.assertEqual(LG.read_setting(p), 'system')                                                 # key absent
            with open(p, 'w', encoding='utf-8') as f: f.write('{not json')
            self.assertEqual(LG.read_setting(p), 'system')                                                 # unreadable


class Translation(unittest.TestCase):
    def setUp(self):
        self.saved = dict(LG._catalogs); LG._catalogs.clear()
        LG._catalogs.update({'fr-fr': {'misc.hello': 'Bonjour', 'misc.files': '%d fichier(s)', 'misc.only_fr': 'Seulement'}, 'en-us': {'misc.hello': 'Hello', 'misc.files': '%d file(s)'},
                             'de-de': {'misc.hello': 'Hallo'}})
    def tearDown(self): LG._catalogs.clear(); LG._catalogs.update(self.saved); LG.select_language('fr-fr')

    def test_french(self):
        LG.select_language('fr-fr')
        self.assertEqual(LG.tr('misc.hello'), 'Bonjour'); self.assertEqual(LG.tr('misc.files') % 3, '3 fichier(s)')

    def test_english(self):
        LG.select_language('en-us')
        self.assertEqual(LG.tr('misc.hello'), 'Hello'); self.assertEqual(LG.tr('misc.files') % 3, '3 file(s)')

    def test_key_missing_in_english_stays_a_key(self):
        LG.select_language('en-us'); self.assertEqual(LG.tr('misc.only_fr'), 'misc.only_fr')                  # (English is the only fallback: never French)

    def test_key_missing_in_another_language_falls_back_to_english(self):
        LG.select_language('de-de'); self.assertEqual(LG.tr('misc.hello'), 'Hallo'); self.assertEqual(LG.tr('misc.files') % 2, '2 file(s)'); self.assertEqual(LG.tr('misc.only_fr'), 'misc.only_fr')

    def test_unknown_text_is_returned_unchanged(self):
        for lang in ('fr-fr', 'en-us'):
            LG.select_language(lang)
            for t in ('x2', '', 'misc.unknown_key'): self.assertEqual(LG.tr(t), t)

    def test_non_text_passes_through_unchanged(self):
        LG.select_language('en-us')
        for v in (None, 3, 1.5, ('a', 'b'), True): self.assertEqual(LG.tr(v), v)

    def test_N_marks_without_changing(self):
        LG.select_language('en-us'); self.assertEqual(LG.N_('misc.hello'), 'misc.hello'); self.assertEqual(LG.tr(LG.N_('misc.hello')), 'Hello')

    def test_language_change_is_immediate(self):
        LG.select_language('en-us'); self.assertEqual(LG.tr('misc.hello'), 'Hello'); LG.select_language('fr-fr'); self.assertEqual(LG.tr('misc.hello'), 'Bonjour')


class Names(unittest.TestCase):
    def tearDown(self): LG.select_language('fr-fr')

    def test_own_names_flags_and_names_in_sentences(self):
        self.assertEqual([LG.NAMES[c] for c in LG.BUILT_IN], ['English', 'Français', 'Deutsch', 'Español', 'Italiano', '日本語', '한국어', '简体中文', '繁體中文'])
        self.assertEqual([LG.FLAGS[c] for c in LG.BUILT_IN], ['us', 'fr', 'de', 'es', 'it', 'jp', 'kr', 'cn', 'tw'])
        for lg in LG.LANGUAGES:
            self.assertEqual(LG.language_of_name(LG.NAMES[lg]), lg); self.assertTrue(os.path.isfile(os.path.join(FLAGS, LG.FLAGS[lg] + '.png')), lg)
        self.assertIsNone(LG.language_of_name('French')); self.assertIsNone(LG.language_of_name(None))
        self.assertEqual(sorted(LG.SENTENCE_NAMES), sorted(LG.BUILT_IN))
        LG.select_language('en-us'); self.assertEqual(LG.language_name('de-de'), 'German'); self.assertEqual(LG.language_name('zh-tw'), 'Traditional Chinese'); self.assertEqual(LG.language_name('xx-yy'), 'xx-yy')
        LG.select_language('fr-fr'); self.assertEqual(LG.language_name('en-us'), 'anglais')
        LG.select_language('ja-jp'); self.assertEqual(LG.tr('language.game_version') % LG.language_name('en-us'), 'ゲーム：英語')

    def test_fonts(self):
        game = ('GMaruGo',)
        self.assertEqual(LG.font_families(game, 'fr-fr'), game); self.assertEqual(LG.font_families(game, 'ja-jp')[0], 'GMaruGo')          # (the game font writes Japanese)
        self.assertEqual(LG.font_families(game, 'ko-kr')[0], 'Malgun Gothic'); self.assertEqual(LG.font_families(game, 'zh-cn')[:2], ('Microsoft YaHei UI', 'Microsoft YaHei'))
        self.assertEqual(LG.font_families(game, 'zh-tw')[0], 'Microsoft JhengHei UI'); self.assertEqual(LG.font_families(game, 'ko-kr')[-1], 'GMaruGo')
        self.assertEqual(LG.font_families(game, 'pt-br'), game)                                       # (a language added later: the game font, then the system fonts)
        LG.select_language('zh-cn'); self.assertEqual(LG.font_families(game)[0], 'Microsoft YaHei UI')

    def test_wrap(self):
        n = len
        self.assertEqual(LG.wrap('one two three four', 9, n), ['one two', 'three', 'four'])
        self.assertEqual(LG.wrap('a  ·  b', 50, n), ['a · b'])
        self.assertEqual(LG.wrap('supercalifragilistic x', 5, n), ['supercalifragilistic', 'x'])          # (a word wider than the line stays whole)
        self.assertEqual(LG.wrap('これはテストです。次の文。', 6, n), ['これはテスト', 'です。次の文。'])          # (between characters; 。 never starts a line)
        self.assertEqual(LG.wrap('Enter：決定する', 7, n), ['Enter：決', '定する'])
        self.assertEqual(LG.wrap('엔터 또는 클릭: 빈 칸', 9, n), ['엔터 또는 클릭:', '빈 칸'])            # (Korean: at spaces)

    def test_plural(self):
        LG.select_language('fr-fr'); self.assertEqual([LG.plural_one(n) for n in (0, 1, 2)], [True, True, False])
        LG.select_language('es-es'); self.assertEqual([LG.plural_one(n) for n in (0, 1, 2)], [False, True, False])


class TextFiles(unittest.TestCase):
    def test_round_trip_and_format(self):
        items = [('a.plain', 'Plain', 'Plain text'), ('a.edges', ' (fullscreen)', ' (plein écran)'), ('a.lines', 'one\ntwo', 'un\ndeux'), ('a.quoted', '"Normal"', '« Normal »'),
                 ('a.path', 'data\\apk\\dq4\\fr-fr', 'data\\apk\\dq4\\fr-fr'), ('a.nbsp', 'Gold: %d\xa0\xa0Exp: %d', 'Or : %d\xa0\xa0Exp : %d'), ('a.cjk', '"Settings"', '「設定」'), ('a.empty', 'Empty', '')]
        with tempfile.TemporaryDirectory() as t:
            p = os.path.join(t, 'xx-yy.json')
            self.assertTrue(LG.write_file(p, 'Name', 'br', items)); self.assertFalse(LG.write_file(p, 'Name', 'br', items))          # (the same content: not written again)
            with open(p, 'rb') as f: raw = f.read()
            self.assertEqual(raw.count(os.linesep.encode()), len(items) + 7)                                                     # (the system's line endings)
            raw = raw.replace(b'\r\n', b'\n')
            self.assertTrue(raw.startswith(b'{\n "name": "Name",\n "flag": "br",\n "help": ')); self.assertTrue(raw.endswith(b'\n ]\n}\n'))
            self.assertIn('  {"key": "a.lines", "en": "one\\ntwo", "text": "un\\ndeux"},\n'.encode('utf-8'), raw)                                   # (one entry per line)
            with open(p, 'wb') as f: f.write(raw.replace(b'\n', b'\r\n') if os.linesep == '\n' else raw)
            self.assertFalse(LG.write_file(p, 'Name', 'br', items))                                                              # (other line endings only: not written again)
            self.assertIn('"text": "「設定」"'.encode('utf-8'), raw)                                                                                   # (UTF-8, not \u escapes)
            self.assertEqual(LG.read_file(p), ('Name', 'br', {k: v for k, _, v in items}, []))

    def test_problems(self):
        with tempfile.TemporaryDirectory() as t:
            p = os.path.join(t, 'xx-yy.json')
            with open(p, 'w', encoding='utf-8') as f:
                json.dump({'name': ' Name ', 'flag': 'BR', 'entries': [{'key': 'a.one', 'text': 'One'}, {'key': 'Bad Key', 'text': 'x'}, {'text': 'no key'}, 'not an entry',
                                                                        {'key': 'a.one', 'text': 'Again'}, {'key': 'a.two', 'en': 'Two'}]}, f)
            name, flag, texts, problems = LG.read_file(p)
            self.assertEqual((name, flag, texts), ('Name', 'br', {'a.one': 'Again', 'a.two': ''})); self.assertEqual(len(problems), 4, problems)
            with open(p, 'w', encoding='utf-8') as f: f.write('{"name": "Name",\n "entries": [\n  {"key": "a.one", "text": "One"}\n  {"key": "a.two"}]}')
            name, flag, texts, problems = LG.read_file(p)
            self.assertIsNone(texts); self.assertIn('line 4', problems[0])                                                         # (not JSON: where it breaks)
            self.assertIsNone(LG.read_file(os.path.join(t, 'none.json'))[2])

    def test_check_text(self):
        self.assertIsNone(LG.check_text('State %d loaded', 'Etat %d chargé'))
        self.assertIn('placeholders', LG.check_text('State %d loaded', 'Etat chargé')); self.assertIn('placeholders', LG.check_text('%s: %d', '%d : %s'))
        self.assertIn('spaces', LG.check_text(' (fullscreen)', '(plein écran)')); self.assertIn('line breaks', LG.check_text('a\nb', 'a b')); self.assertEqual(LG.check_text('a', '  '), 'empty')


class Adding(unittest.TestCase):
    """create_language / check_language / save_language in a copy of dq456_pc/languages (the real folder is not touched)."""
    def setUp(self):
        self.tmp = tempfile.mkdtemp(prefix='lg_'); self.saved = LG.FOLDER
        LG.FOLDER = os.path.join(self.tmp, 'languages'); shutil.copytree(self.saved, LG.FOLDER); LG.refresh()
    def tearDown(self):
        LG.FOLDER = self.saved; LG.refresh(); LG.select_language('fr-fr'); shutil.rmtree(self.tmp, True)

    def edit(self, code, texts, extra=()):
        """Writes `texts` ({key: text}) into the file of `code`, as a translator would, and entries of `extra` at its end."""
        p = LG.path_of(code)
        with open(p, encoding='utf-8') as f: d = json.load(f)
        for e in d['entries']: e['text'] = texts.get(e['key'], e['text'])
        d['entries'] += list(extra)
        with open(p, 'w', encoding='utf-8') as f: json.dump(d, f, ensure_ascii=False, indent=1)

    def test_new_language(self):
        LG.create_language('pt-br', 'Português', 'BR')
        english = [(k, en) for k, en, _ in raw_entries('en-us') if not k.startswith(LG.ENGLISH_ONLY)]
        self.assertEqual(raw_entries('pt-br'), [(k, en, '') for k, en in english])                                             # (the English texts, nothing translated yet)
        self.assertIn('pt-br', LG.LANGUAGES); self.assertEqual((LG.NAMES['pt-br'], LG.FLAGS['pt-br']), ('Português', 'br')); self.assertEqual(LG.language_name('pt-br'), 'Português')
        LG.select_language('pt-br'); self.assertEqual(LG.tr('display.contrast'), 'Contrast')
        self.edit('pt-br', {'display.contrast': 'Contraste', 'display.limited_x_graphics_card': 'Limitado'}, [{'key': 'display.unknown', 'text': '?'}])
        done, left, problems = LG.check_language('pt-br')
        self.assertEqual((done, left), (1, len(english) - 1))
        self.assertTrue(any('limited_x_graphics_card' in x and 'placeholders' in x for x in problems), problems); self.assertTrue(any('display.unknown' in x for x in problems), problems)
        self.assertEqual(LG.tr('display.contrast'), 'Contraste'); self.assertEqual(LG.tr('display.limited_x_graphics_card'), 'Limited to x%d by this graphics card')          # (refused: English)
        self.assertEqual(LG.tr('new_language.title'), 'New language')
        with self.assertRaises(FileExistsError): LG.create_language('pt-br', 'Português', 'br')
        with self.assertRaises(ValueError): LG.create_language('portugues', 'Português', 'br')

    def test_a_broken_file_is_kept_as_it_is(self):
        LG.create_language('pt-br', 'Português', 'br'); p = LG.path_of('pt-br')
        with open(p, 'a', encoding='utf-8') as f: f.write(',')
        with open(p, 'rb') as f: before = f.read()
        done, left, problems = LG.check_language('pt-br')
        self.assertEqual(done, 0); self.assertIn('pt-br.json', problems[0]); self.assertIn('pt-br', LG.LANGUAGES)
        self.assertFalse(LG.save_language('pt-br'))
        with open(p, 'rb') as f: self.assertEqual(f.read(), before)
        LG.select_language('pt-br'); self.assertEqual(LG.tr('display.contrast'), 'Contrast')

    def test_a_file_brought_up_to_date(self):
        with open(LG.path_of('fr-fr'), encoding='utf-8') as f: d = json.load(f)
        removed = d['entries'].pop(5); d['entries'][0]['en'] = 'old English'; d['entries'].append({'key': 'display.gone', 'en': 'Gone', 'text': 'Parti'})
        with open(LG.path_of('fr-fr'), 'w', encoding='utf-8') as f: json.dump(d, f, ensure_ascii=False)
        self.assertTrue(LG.save_language('fr-fr')); self.assertFalse(LG.save_language('fr-fr'))
        entries = raw_entries('fr-fr')
        self.assertEqual([k for k, _, _ in entries], [k for k, _, _ in raw_entries('en-us') if not k.startswith(LG.ENGLISH_ONLY)])
        self.assertEqual(entries[0][1], raw_entries('en-us')[0][1]); self.assertEqual(entries[5], (removed['key'], removed['en'], ''))

    def test_edit_an_existing_language(self):
        done, left, problems = LG.check_language('fr-fr')
        self.assertEqual((problems, left), ([], 0)); self.assertEqual(done, len(raw_entries('fr-fr'))); self.assertEqual(LG.NAMES['fr-fr'], 'Français')


class Catalog(unittest.TestCase):
    """Rules of the texts (dq456_pc/languages/<code>.json, English the reference)."""
    def test_files_and_keys(self):
        self.assertEqual(sorted(os.listdir(LG.FOLDER)), sorted(c + '.json' for c in LG.LANGUAGES))
        english = raw_entries('en-us')
        for lang in LG.LANGUAGES:
            name, flag, texts, problems = LG.read_file(LG.path_of(lang))
            self.assertEqual(problems, [], lang); self.assertTrue(name and flag, lang)
            expected = [(k, en) for k, en, _ in english if lang == 'en-us' or not k.startswith(LG.ENGLISH_ONLY)]
            self.assertEqual([(k, en) for k, en, _ in raw_entries(lang)], expected, '%s: keys or "en" texts other than the English file' % lang)
            for k, t in texts.items():
                self.assertTrue(KEY.match(k) and k.split('.')[0] in LG.SECTIONS, '%s: key %r' % (lang, k))
                if lang in LG.BUILT_IN: self.assertTrue(t.strip(), '%s: %r not translated' % (lang, k))
        self.assertTrue(any(k.startswith(LG.ENGLISH_ONLY) for k, _, _ in english)); self.assertTrue(all(en == t for _, en, t in english))

    def test_written_as_save_language_writes_them(self):
        saved = LG.FOLDER; tmp = tempfile.mkdtemp(prefix='lg_')
        try:
            LG.FOLDER = os.path.join(tmp, 'languages'); shutil.copytree(saved, LG.FOLDER)
            self.assertEqual([c for c in LG.LANGUAGES if LG.save_language(c)], [])
        finally: LG.FOLDER = saved; shutil.rmtree(tmp, True)

    def test_same_placeholders_and_same_edges(self):
        en = LG.catalog('en-us')
        for lang in LG.LANGUAGES:
            for k, _, t in raw_entries(lang):
                if t: self.assertIsNone(LG.check_text(en[k], t), '%s %s: %r -> %r' % (lang, k, en[k], t))

    def test_no_ascii_double_quote_inside_cjk_texts(self):
        """(Japanese, Korean and Chinese texts quote with their own marks, as the game does.)"""
        for lang in ('ja-jp', 'ko-kr', 'zh-cn', 'zh-tw'):
            for k, _, t in raw_entries(lang): self.assertNotIn('"', t, '%s %s' % (lang, k))

    def test_no_french_in_english(self):
        for k, t in LG.catalog('en-us').items():
            if k.startswith('language.name_'): continue
            self.assertFalse(french(t), '%s: French in the English text %r' % (k, t))

    def test_every_key_of_the_code_exists_and_every_key_is_used(self):
        known = LG.catalog('en-us'); used = set(); missing = []
        for d, _, fs in os.walk(os.path.join(ROOT, 'dq456_pc')):
            for f in fs:
                if not f.endswith('.py'): continue
                p = os.path.join(d, f)
                with open(p, encoding='utf-8') as fh: tree = ast.parse(fh.read())
                for n in ast.walk(tree):
                    if isinstance(n, ast.Constant) and isinstance(n.value, str):
                        for k in keys_in_text(n.value):
                            if k.split('.')[0] not in LG.SECTIONS: continue
                            used.add(k)
                            if k not in known: missing.append('%s:%d %r' % (os.path.relpath(p, ROOT), n.lineno, k))
        self.assertEqual(missing, [], 'keys used by the code but absent from the texts')
        self.assertEqual(sorted(set(known) - used), [], 'keys of the texts that no code uses')


if __name__ == '__main__':
    unittest.main(verbosity=1)
