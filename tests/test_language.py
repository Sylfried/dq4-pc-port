"""Language of the port's texts (dq4_pc/language.py), without window or engine: detection of the computer's language (French whatever the variant, otherwise English),
setting, `tr` / `N_`, reading the setting in settings.json, and rules of the catalogs (dq4_pc/texts/<language>/): the same keys in every language, each key in the file of
its domain, the same placeholders (%d, %s...) and the same spaces at the edges, no French in the English, and every key the code uses exists.

    python3 tests/test_language.py"""
import ast, json, os, re, sys, tempfile, unittest

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.join(HERE, '..')
sys.path.insert(0, ROOT)
from dq4_pc import language as LG

ACCENTS = re.compile('[àâäçéèêëîïôöùûüÿœÀÂÇÉÈÊËÎÏÔÙÛÜŒ]')
FRENCH_WORDS = {'le', 'la', 'les', 'des', 'du', 'une', 'et', 'ou', 'pour', 'dans', 'sur', 'avec', 'sans', 'est', 'pas', 'ces', 'aux', 'vos', 'votre', 'tes', 'tous', 'toutes', 'quand', 'comme', 'mais', 'donc', 'sont', 'chaque', 'sinon', 'aucun', 'aucune'}
GAPS = re.compile(r'%[-+ #0]*\d*(?:\.\d+)?[sdifgxXrc%]|\{[^{}]*\}')


def french(text):
    """The text contains an accented letter or a French function word."""
    if ACCENTS.search(text): return True
    return any(m in FRENCH_WORDS for m in re.findall(r"[a-zA-Z']+", text.lower().replace("'", ' ')))


def catalog_by_file(language):
    import importlib
    return {d: importlib.import_module('dq4_pc.texts.%s.%s' % (language, d)).TEXTS for d in LG.DOMAINS}


KEY = re.compile(r'^[a-z]+\.[a-z0-9_]+$')


def keys_in_text(t):
    """The catalog keys a string of the code holds: the string itself, or each part of a help text (keys separated by three spaces)."""
    return [p for p in re.split(r'\s{3,}', t.strip()) if KEY.match(p) and p.split('.')[1] not in FILE_EXTENSIONS]


FILE_EXTENSIONS = {'json', 'py', 'txt', 'log', 'dat', 'dqs', 'png', 'zip'}         # ('settings.json' is a file name, not a key)


class Detection(unittest.TestCase):
    def test_windows_all_french_variants(self):
        for code in (0x040C, 0x080C, 0x0C0C, 0x100C, 0x140C, 0x180C):                       # France, Belgium, Canada, Switzerland, Luxembourg, Monaco
            self.assertEqual(LG.system_language(lambda c=code: c), 'fr', hex(code))

    def test_windows_other_languages_give_english(self):
        for code in (0x0409, 0x0809, 0x0407, 0x0411, 0x0C0A, 0x0410, 0x0416, 0x0419, 0x0804):    # US / GB English, German, Japanese, Spanish, Italian, Portuguese, Russian, Chinese
            self.assertEqual(LG.system_language(lambda c=code: c), 'en', hex(code))

    def test_locales_as_text(self):
        for t in ('fr_FR.UTF-8', 'fr', 'fr_BE', 'fr-CA', 'French_France', 'fr_CH@euro'):
            self.assertEqual(LG.system_language(lambda t=t: t), 'fr', t)
        for t in ('en_US.UTF-8', 'C', 'POSIX', '', None, 'de_DE', 'fra', 'frisian', 'fi_FI'):              # ("fra", "frisian": not French)
            self.assertEqual(LG.system_language(lambda t=t: t), 'en', repr(t))

    def test_read_failure_gives_english(self):
        def outage(): raise OSError('pas de langue')
        self.assertEqual(LG.system_language(outage), 'en')


class Setting(unittest.TestCase):
    def tearDown(self): LG.select_language('fr')

    def test_choice(self):
        self.assertEqual(LG.CHOICES, ('system', 'en', 'fr'))
        self.assertEqual(LG.select_language('fr', reader=lambda: 0x0409), 'fr'); self.assertEqual(LG.current_language(), 'fr')
        self.assertEqual(LG.select_language('en', reader=lambda: 0x040C), 'en'); self.assertEqual(LG.requested(), 'en')
        self.assertEqual(LG.select_language('system', reader=lambda: 0x040C), 'fr'); self.assertEqual(LG.select_language('system', reader=lambda: 0x0409), 'en'); self.assertEqual(LG.requested(), 'system')

    def test_unknown_value_treated_as_system(self):
        self.assertEqual(LG.select_language('klingon', reader=lambda: 0x0409), 'en'); self.assertEqual(LG.requested(), 'system')
        self.assertEqual(LG.select_language(None, reader=lambda: 0x040C), 'fr')

    def test_read_setting_from_file(self):
        with tempfile.TemporaryDirectory() as t:
            p = os.path.join(t, 'settings.json')
            self.assertEqual(LG.read_setting(p), 'system')                                                 # absent
            for v, att in (('fr', 'fr'), ('en', 'en'), ('system', 'system'), ('xx', 'system'), (3, 'system')):
                with open(p, 'w', encoding='utf-8') as f: json.dump({'language': v}, f)
                self.assertEqual(LG.read_setting(p), att, v)
            with open(p, 'w', encoding='utf-8') as f: json.dump({'sound': True}, f)
            self.assertEqual(LG.read_setting(p), 'system')                                                 # key absent
            with open(p, 'w', encoding='utf-8') as f: f.write('{not json')
            self.assertEqual(LG.read_setting(p), 'system')                                                 # unreadable


class Translation(unittest.TestCase):
    def setUp(self): self.saved = LG._catalogs; LG._catalogs = {'fr': {'misc.hello': 'Bonjour', 'misc.files': '%d fichier(s)', 'misc.only_fr': 'Seulement'}, 'en': {'misc.hello': 'Hello', 'misc.files': '%d file(s)'}}
    def tearDown(self): LG._catalogs = self.saved; LG.select_language('fr')

    def test_french(self):
        LG.select_language('fr')
        self.assertEqual(LG.tr('misc.hello'), 'Bonjour'); self.assertEqual(LG.tr('misc.files') % 3, '3 fichier(s)')

    def test_english(self):
        LG.select_language('en')
        self.assertEqual(LG.tr('misc.hello'), 'Hello'); self.assertEqual(LG.tr('misc.files') % 3, '3 file(s)')

    def test_key_missing_in_english_falls_back_to_french(self):
        LG.select_language('en'); self.assertEqual(LG.tr('misc.only_fr'), 'Seulement')

    def test_unknown_text_is_returned_unchanged(self):
        for lang in ('fr', 'en'):
            LG.select_language(lang)
            for t in ('x2', '', 'misc.unknown_key'): self.assertEqual(LG.tr(t), t)

    def test_non_text_passes_through_unchanged(self):
        LG.select_language('en')
        for v in (None, 3, 1.5, ('a', 'b'), True): self.assertEqual(LG.tr(v), v)

    def test_N_marks_without_changing(self):
        LG.select_language('en'); self.assertEqual(LG.N_('misc.hello'), 'misc.hello'); self.assertEqual(LG.tr(LG.N_('misc.hello')), 'Hello')

    def test_language_change_is_immediate(self):
        LG.select_language('en'); self.assertEqual(LG.tr('misc.hello'), 'Hello'); LG.select_language('fr'); self.assertEqual(LG.tr('misc.hello'), 'Bonjour')


class Catalog(unittest.TestCase):
    """Rules of the catalogs (dq4_pc/texts/fr and dq4_pc/texts/en)."""
    def test_files_types_and_key_names(self):
        for lang in LG.LANGUAGES:
            for d, c in catalog_by_file(lang).items():
                self.assertIsInstance(c, dict, '%s/%s' % (lang, d))
                for k, t in c.items():
                    self.assertTrue(KEY.match(k) and k.startswith(d + '.'), '%s/%s: key %r' % (lang, d, k))
                    self.assertTrue(isinstance(t, str) and t.strip(), '%s/%s: %r -> %r' % (lang, d, k, t))

    def test_same_keys_in_every_language(self):
        fr = catalog_by_file('fr')
        for lang in LG.LANGUAGES:
            for d, c in catalog_by_file(lang).items(): self.assertEqual(sorted(c), sorted(fr[d]), '%s/%s' % (lang, d))

    def test_same_placeholders_and_same_edges(self):
        fr = catalog_by_file('fr'); en = catalog_by_file('en')
        for d in LG.DOMAINS:
            for k, a in fr[d].items():
                b = en[d][k]
                self.assertEqual(GAPS.findall(a), GAPS.findall(b), '%s: placeholders %r -> %r' % (k, a, b))
                self.assertEqual((a[:len(a) - len(a.lstrip())], a[len(a.rstrip()):]), (b[:len(b) - len(b.lstrip())], b[len(b.rstrip()):]), '%s: spaces at the edges %r -> %r' % (k, a, b))
                self.assertEqual(a.count('\n'), b.count('\n'), '%s: line breaks' % k)

    def test_no_french_in_english(self):
        fr = catalog_by_file('fr')
        for d, c in catalog_by_file('en').items():
            for k, t in c.items():
                if t == fr[d][k]: self.assertFalse(french(t), '%s: French left as it is: %r' % (k, t)); continue
                self.assertFalse(french(t), '%s: French in the English text %r' % (k, t))

    def test_every_key_of_the_code_exists_and_every_key_is_used(self):
        known = LG.catalog('fr'); used = set(); missing = []
        for d, _, fs in os.walk(os.path.join(ROOT, 'dq4_pc')):
            if os.sep + 'texts' in d: continue
            for f in fs:
                if not f.endswith('.py'): continue
                p = os.path.join(d, f)
                with open(p, encoding='utf-8') as fh: tree = ast.parse(fh.read())
                for n in ast.walk(tree):
                    if isinstance(n, ast.Constant) and isinstance(n.value, str):
                        for k in keys_in_text(n.value):
                            if k.split('.')[0] not in LG.DOMAINS: continue
                            used.add(k)
                            if k not in known: missing.append('%s:%d %r' % (os.path.relpath(p, ROOT), n.lineno, k))
        self.assertEqual(missing, [], 'keys used by the code but absent from the catalogs')
        self.assertEqual(sorted(set(known) - used), [], 'keys of the catalogs that no code uses')


if __name__ == '__main__':
    unittest.main(verbosity=1)
