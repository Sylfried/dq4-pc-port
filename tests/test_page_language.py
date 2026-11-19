""""Language" setting: `language` key of settings.json (default `system`, unknown value replaced), line of the "Display" page above "Fullscreen" ("System", then each language in
its own language: "English", "Français", "Deutsch"...), immediate effect of the choice, and translation by the pages (`Pause._label`, a language's own name in its fonts). Fake "game" for
the Pause menu pages test.

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
            for v, att in (('en-us', 'en-us'), ('fr-fr', 'fr-fr'), ('zh-tw', 'zh-tw'), ('en', 'en-us'), ('fr', 'fr-fr'), ('system', 'system'), ('xx', 'system'), (7, 'system'), (None, 'system')):          # ('fr': an earlier version's code)
                with open(p, 'w', encoding='utf-8') as f: json.dump({'language': v}, f)
                self.assertEqual(RG.Settings(p)['language'], att, v)

    def test_saved(self):
        with tempfile.TemporaryDirectory() as t:
            p = os.path.join(t, 'settings.json'); r = RG.Settings(p); r['language'] = 'en-us'; r.store()
            self.assertEqual(RG.Settings(p)['language'], 'en-us')


class Page(unittest.TestCase):
    def setUp(self): LG.select_language('system', reader=lambda: 0x040C)
    def tearDown(self): LG.select_language('fr')

    def test_line_above_full_screen(self):
        _, p = menu('display'); e = p._entries()
        self.assertEqual([x['l'] for x in e[:2]], ['language.title', 'display.fullscreen']); self.assertEqual(e[0]['t'], 'choice'); self.assertEqual(e[0]['vals'], ['system', 'en-us', 'fr-fr', 'de-de', 'es-es', 'it-it', 'ja-jp', 'ko-kr', 'zh-cn', 'zh-tw'])

    def test_names_in_their_own_language(self):
        J, p = menu('display'); e = p._entries()[0]
        names = ['English', 'Français', 'Deutsch', 'Español', 'Italiano', '日本語', '한국어', '简体中文', '繁體中文']
        self.assertEqual([LG.tr(p._value_name('language.title', v)) for v in e['vals']], ['Système'] + names)
        LG.select_language('en')
        self.assertEqual([LG.tr(p._value_name('language.title', v)) for v in e['vals']], ['System'] + names); self.assertEqual(LG.tr('language.title'), 'Language')

    def test_system_follows_the_computer_language(self):
        J, p = menu('display'); self.assertEqual(J.reg['language'], 'system')
        LG.select_language(J.reg['language'], reader=lambda: 0x0409); self.assertEqual(LG.current_language(), 'en-us')
        LG.select_language(J.reg['language'], reader=lambda: 0x080C); self.assertEqual(LG.current_language(), 'fr-fr')

    def test_choice_applies_immediately_and_is_kept(self):
        J, p = menu('display'); e = p._entries()[0]
        e['plus'](); self.assertEqual(J.reg['language'], 'en-us'); self.assertEqual(LG.current_language(), 'en-us')           # system -> en-us
        e['plus'](); self.assertEqual(J.reg['language'], 'fr-fr'); self.assertEqual(LG.current_language(), 'fr-fr')           # en-us -> fr-fr
        e['minus'](); self.assertEqual(LG.current_language(), 'en-us')
        for _ in range(8): e['plus']()
        self.assertEqual((J.reg['language'], LG.current_language(), LG.tr('language.title')), ('zh-tw', 'zh-tw', '語言'))

    def test_default_value_of_the_line(self):
        J, p = menu('display'); e = p._entries()[0]; e['plus'](); self.assertFalse(e['is_default']()); e['default'](); self.assertEqual(J.reg['language'], 'system'); self.assertTrue(e['is_default']())

    def test_pages_translate_what_they_draw(self):
        J, p = menu('display')
        seen = []
        J._lbl = lambda text, size_value, color=None, fonts=(): seen.append((text, fonts[:1])) or type('E', (), {'content_width': 10.0})()
        p._pol = ('Game font',)
        p._label('language.title', 12.0); LG.select_language('en'); p._label('language.title', 12.0); p._label('Text without translation', 12.0)
        p._label('한국어', 12.0); LG.select_language('ko'); p._label('language.title', 12.0); p._label('Deutsch', 12.0)
        self.assertEqual(seen, [('Langue', ('Game font',)), ('Language', ('Game font',)), ('Text without translation', ('Game font',)),
                                ('한국어', ('Malgun Gothic',)), ('언어', ('Malgun Gothic',)), ('Deutsch', ('Game font',))])          # (Korean letters: Korean fonts first)


if __name__ == '__main__':
    unittest.main(verbosity=1)
