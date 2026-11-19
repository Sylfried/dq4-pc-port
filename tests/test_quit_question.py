"""The "Quit the game?" question (Esc menu > "Quit the game", and the start menu's quit): no back button at the bottom of its window, its "No" already goes back.
The other pages keep theirs; Esc, Backspace, the B button and the right click still go back on the question too.

  python3 tests/test_quit_question.py        (draws the menu: needs a pyglet window, skipped without one)
"""
import os, sys, unittest

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, '..')); sys.path.insert(0, HERE)


class QuitQuestion(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        try:
            import test_pause_language as TL
            TL.window()
        except unittest.SkipTest: raise
        except Exception as ex: raise unittest.SkipTest('no pyglet window possible: %r' % (ex,))
        cls.TL = TL

    def drawn(self, page):
        J, p = self.TL.menu(page); self.TL.draw_page(p); return p

    def test_no_back_button_on_the_question(self):
        p = self.drawn('quit')
        self.assertIsNone(p.zone_ret, 'the question has no back button')
        self.assertIn('common.no', [e.get('l') for e in p._entries()], 'its "No" goes back')

    def test_other_pages_keep_it(self):
        for page in ('sound', 'controls', 'difficulty', 'cheats'):
            self.assertIsNotNone(self.drawn(page).zone_ret, page)

    def test_root_has_none(self):
        self.assertIsNone(self.drawn('root').zone_ret)


if __name__ == '__main__':
    unittest.main()
