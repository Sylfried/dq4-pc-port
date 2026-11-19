""""Language" setting: `language` key of settings.json (default `system`, unknown value replaced), line of the "Display" page above "Fullscreen" ("System" / "English" / "French",
"System" / "English" / "French" in English), immediate effect of the choice, and translation by the pages (`Pause._label`). Fake "game" for the Pause menu pages test.

    python3 tests/test_page_language.py"""
import json, os, sys, tempfile, unittest

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), '..'))
import _paths
import test_pause_pages as TP
from dq456_pc import language as LG
from dq456_pc.persistence import settings as RG


class FakeGameDisplay(TP.FakeGame):
    """The pages' fake game, with what the "Display" page asks of it."""
    is_fullscreen = False; mode = 4; current_resolution = (1280, 720)
    def __init__(self):
        super().__init__(); self.post = type('P', (), {'max_msaa': None})()
    def set_full_screen(self, v): self.is_fullscreen = v
    def resolutions(self): return [(1280, 720), (1920, 1080)]
    def set_resolution(self, v): self.current_resolution = v
    def set_mode(self, v): self.mode = v


def menu(screen_page):
    J = FakeGameDisplay(); p = TP.PA.Pause(J); p.opened = True; p.stack = [screen_page]
    return J, p


class Key(unittest.TestCase):
    def test_default_and_validation(self):
        self.assertEqual(RG.DEFAULT['language'], 'system')
        with tempfile.TemporaryDirectory() as t:
            p = os.path.join(t, 'settings.json')
            self.assertEqual(RG.Settings(p)['language'], 'system')
            for v, att in (('en', 'en'), ('fr', 'fr'), ('system', 'system'), ('xx', 'system'), (7, 'system'), (None, 'system')):
                with open(p, 'w', encoding='utf-8') as f: json.dump({'language': v}, f)
                self.assertEqual(RG.Settings(p)['language'], att, v)

    def test_saved(self):
        with tempfile.TemporaryDirectory() as t:
            p = os.path.join(t, 'settings.json'); r = RG.Settings(p); r['language'] = 'en'; r.store()
            self.assertEqual(RG.Settings(p)['language'], 'en')


class Page(unittest.TestCase):
    def setUp(self): LG.select_language('system', reader=lambda: 0x040C)
    def tearDown(self): LG.select_language('fr')

    def test_line_above_full_screen(self):
        _, p = menu('display'); e = p._entries()
        self.assertEqual([x['l'] for x in e[:2]], ['settings.language', 'settings.fullscreen']); self.assertEqual(e[0]['t'], 'choice'); self.assertEqual(e[0]['vals'], ['system', 'en', 'fr'])

    def test_names_in_french_and_english(self):
        J, p = menu('display'); e = p._entries()[0]
        self.assertEqual([p._value_name('settings.language', v) for v in e['vals']], ['settings.system', 'settings.english', 'settings.french'])
        LG.select_language('en')
        self.assertEqual([LG.tr(p._value_name('settings.language', v)) for v in e['vals']], ['System', 'English', 'French']); self.assertEqual(LG.tr('settings.language'), 'Language')

    def test_system_follows_the_computer_language(self):
        J, p = menu('display'); self.assertEqual(J.reg['language'], 'system')
        LG.select_language(J.reg['language'], reader=lambda: 0x0409); self.assertEqual(LG.current_language(), 'en')
        LG.select_language(J.reg['language'], reader=lambda: 0x080C); self.assertEqual(LG.current_language(), 'fr')

    def test_choice_applies_immediately_and_is_kept(self):
        J, p = menu('display'); e = p._entries()[0]
        e['plus'](); self.assertEqual(J.reg['language'], 'en'); self.assertEqual(LG.current_language(), 'en')           # system -> en
        e['plus'](); self.assertEqual(J.reg['language'], 'fr'); self.assertEqual(LG.current_language(), 'fr')           # en -> fr
        e['minus'](); self.assertEqual(LG.current_language(), 'en')

    def test_default_value_of_the_line(self):
        J, p = menu('display'); e = p._entries()[0]; e['plus'](); self.assertFalse(e['is_default']()); e['default'](); self.assertEqual(J.reg['language'], 'system'); self.assertTrue(e['is_default']())

    def test_pages_translate_what_they_draw(self):
        J, p = menu('display')
        seen = []
        J._lbl = lambda text, size_value, color=None, fonts=(): seen.append(text) or type('E', (), {'content_width': 10.0})()
        p._label('settings.language', 12.0); LG.select_language('en'); p._label('settings.language', 12.0); p._label('Text without translation', 12.0)
        self.assertEqual(seen, ['Langue', 'Language', 'Text without translation'])


if __name__ == '__main__':
    unittest.main(verbosity=1)
