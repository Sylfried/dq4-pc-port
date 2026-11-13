"""Test of the pure logic of the "Sauvegarde automatique" plate of the start menu (type 53), without a window or the engine:

1. button states (MenuParts.BUTTON_STATE_*): normal and pressed react; invisible / grayed out / inverted do not react (IButton: the hit test is switched off);
2. auto save availability: the engine's code 0 (1 = valid data5.dat, 0 = missing) wins; without a code, the label sent by the engine decides;
3. `Window.auto_plate`: plate ALWAYS visible with its label; without an auto save it is grayed out (state 3) and leaves the touch areas (`buttons`: no click, no hover, no keyboard confirmation);
   as soon as the auto save exists: normal state, engine label, touch area; the other plates ("Continuer"...) are untouched; the old behavior (hidden plate) remains available (DQ_AUTO_HIDDEN).

  python3 tests/test_start_menu_plate.py        (Linux without a screen: pyglet in "headless" mode)
"""
import os, sys, types, unittest

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), '..'))
import pyglet
if sys.platform.startswith('linux') and not os.environ.get('DISPLAY'): pyglet.options['headless'] = True; pyglet.options['shadow_window'] = False
from dq4_pc.menus import ui_menu as UM


def initial_type():
    """Minimal layout of the start menu: two plates ("Continuer" = button 0, "Sauvegarde automatique" = button 4), each with its label."""
    square = {'vtx': [[-100.0, 10.0], [100.0, 10.0], [100.0, -10.0], [-100.0, -10.0]], 'uv': [[0, 0], [1, 0], [1, 1], [0, 1]], 'sub': {'0': [0, 1, 2, 0, 2, 3]}}
    def plate(nid, button, z): return {'id': nid, 'par': 1, 'pos': [0.0, 4.0, z], 'act': True, 'mats': [{'sheet': 1, 'part': 7, 'color': [1, 1, 1, 1], 'shader': 'parts', 'offset': None}], 'mesh': square, 'parts': {'buttonId': button, 'gamepad': 16}}
    def text(nid, parent_idx): return {'id': nid, 'par': parent_idx, 'pos': [0.0, 8.0, -8.0], 'act': True, 'text': {'font': 'font', 'characterSize': 10.0, 'text': None}, 'mats': []}
    return {'name': 'Make_StartMenuSecond()', 'err': None,
            'nodes': [{'id': 1, 'par': None, 'pos': [0.0, 0.0, 0.0], 'act': True, 'mats': []}, plate(10, 4, 60.0), text(11, 10), plate(20, 0, 0.0), text(21, 20)],
            'parts': [{'node': 10, 'ib': [{'k': 'button'}, {'k': 'text', 'go': 11, 'variant': 0}]}, {'node': 20, 'ib': [{'k': 'button'}, {'k': 'text', 'go': 21, 'variant': 0}]}],
            'params': [{'id': 4, 'no': 0, 'parts': 0, 'base': 0}, {'id': 4, 'no': 1, 'parts': 0, 'base': 1}, {'id': 0, 'no': 0, 'parts': 1, 'base': 0}, {'id': 0, 'no': 1, 'parts': 1, 'base': 1}],
            'codes': [], 'builds': []}


def window():
    ml = types.SimpleNamespace(types={'53': initial_type()}, info=[], borders=[], hdr={'lang': {'hiro': 1.0}}, pushed=(0.0, 0.0))
    return UM.Window(ml, 53)


def text(wnd, nid): return wnd.N[nid]['text']['text']
def zones(wnd): return sorted(b[0] for b in wnd.buttons())


class TestStates(unittest.TestCase):
    def test_active_state(self):
        self.assertTrue(UM.is_state_active(UM.STATE_NORMAL)); self.assertTrue(UM.is_state_active(UM.STATE_PRESSED))
        for e in (UM.STATE_INVISIBLE, UM.STATE_GRAYED, UM.STATE_INVERTED): self.assertFalse(UM.is_state_active(e), e)
        self.assertEqual((UM.STATE_NORMAL, UM.STATE_PRESSED, UM.STATE_INVISIBLE, UM.STATE_GRAYED, UM.STATE_INVERTED), (0, 1, 2, 3, 4))      # MenuParts.BUTTON_STATE_*

    def test_availability(self):
        self.assertTrue(UM.auto_plate_available(1, '')); self.assertFalse(UM.auto_plate_available(0, 'Sauvegarde automatique'))      # code 0 wins
        self.assertTrue(UM.auto_plate_available(None, 'Sauvegarde automatique')); self.assertFalse(UM.auto_plate_available(None, '')); self.assertFalse(UM.auto_plate_available(None, '  ')); self.assertFalse(UM.auto_plate_available(None, None))


class TestAutoPlate(unittest.TestCase):
    def setUp(self): os.environ.pop('DQ_AUTO_HIDDEN', None)

    def test_without_autosave_grayed_and_inactive(self):
        wnd = window(); wnd.code(0, 0)                                                                   # the engine: no data5.dat, no label (4, 1)
        for _ in range(3): wnd.auto_plate()                                                              # idempotent: called at every frame
        pl = wnd.N[10]
        self.assertTrue(pl['act']); self.assertEqual(text(wnd, 11), UM.AUTO_CAPTION)                      # visible, with its label
        self.assertEqual(pl['state'], UM.STATE_GRAYED)                                                      # grayed out
        self.assertNotIn(4, zones(wnd)); self.assertIn(0, zones(wnd))                                       # inactive: no more touch area; "Continuer", for its part, stays active

    def test_with_normal_autosave(self):
        wnd = window(); wnd.param_str(4, 1, 'Sauvegarde automatique'); wnd.code(0, 1); wnd.auto_plate()
        self.assertEqual(wnd.N[10]['state'], UM.STATE_NORMAL); self.assertTrue(wnd.N[10]['act']); self.assertIn(4, zones(wnd))

    def test_engine_label_kept(self):
        wnd = window(); wnd.param_str(4, 1, 'Reprendre le dernier point'); wnd.code(0, 1); wnd.auto_plate()
        self.assertEqual(text(wnd, 11), 'Reprendre le dernier point')                                  # we never replace the label sent by the engine

    def test_save_appears_afterwards(self):
        wnd = window(); wnd.code(0, 0); wnd.auto_plate(); self.assertEqual(wnd.N[10]['state'], UM.STATE_GRAYED)
        wnd.param_str(4, 1, 'Sauvegarde automatique (nouvelle)'); wnd.code(0, 1); wnd.auto_plate()           # data5.dat appears: the engine sends back code and label
        self.assertEqual(wnd.N[10]['state'], UM.STATE_NORMAL); self.assertIn(4, zones(wnd)); self.assertEqual(text(wnd, 11), 'Sauvegarde automatique (nouvelle)'); self.assertFalse(wnd.auto_grayed)

    def test_then_vanishes(self):
        wnd = window(); wnd.param_str(4, 1, 'Sauvegarde automatique'); wnd.code(0, 1); wnd.auto_plate(); wnd.code(0, 0); wnd.auto_plate()
        self.assertEqual(wnd.N[10]['state'], UM.STATE_GRAYED); self.assertNotIn(4, zones(wnd)); self.assertTrue(text(wnd, 11))

    def test_without_code_the_label_decides(self):
        wnd = window(); wnd.auto_plate(); wnd.auto_plate()                                                # neither code nor label: grayed out (and our replacement label does not "validate" it at the next frame)
        self.assertEqual(wnd.N[10]['state'], UM.STATE_GRAYED); self.assertNotIn(4, zones(wnd))
        wnd.param_str(4, 1, 'Reprise automatique'); wnd.auto_plate()                                       # engine label (different from ours) without code: available
        self.assertEqual(wnd.N[10]['state'], UM.STATE_NORMAL); self.assertIn(4, zones(wnd))

    def test_other_plates_intact(self):
        wnd = window(); wnd.param_str(0, 1, 'Continuer votre aventure'); wnd.param_int(0, 0, UM.STATE_GRAYED); wnd.code(0, 0); wnd.auto_plate()
        self.assertEqual(wnd.N[20]['state'], UM.STATE_GRAYED); self.assertEqual(text(wnd, 21), 'Continuer votre aventure'); self.assertNotIn(0, zones(wnd))      # a plate grayed out by the engine (no bank): same rule

    def test_gray_text_of_grayed_plates(self):
        wnd = window(); wnd.param_str(0, 1, 'Continuer'); wnd.param_int(0, 0, UM.STATE_GRAYED); wnd.code(0, 0); wnd.auto_plate()
        self.assertEqual(wnd.N[21]['tcol'], UM.TEXT_GRAY); self.assertEqual(wnd.N[11]['tcol'], UM.TEXT_GRAY)                # "Continuer" (grayed out by the engine) and "Sauvegarde automatique" (grayed out by the viewer)
        wnd.param_int(0, 0, UM.STATE_NORMAL); wnd.auto_plate(); self.assertEqual(wnd.N[21]['tcol'], 0); self.assertEqual(wnd.N[11]['tcol'], UM.TEXT_GRAY)
        wnd.param_str(4, 1, 'Sauvegarde automatique'); wnd.code(0, 1); wnd.auto_plate(); self.assertEqual(wnd.N[11]['tcol'], 0)    # the auto save exists: normal text

    def test_state_sent_by_engine(self):
        wnd = window(); wnd.param_int(0, 0, UM.STATE_NORMAL); self.assertIn(0, zones(wnd))
        for state, expected in ((UM.STATE_PRESSED, True), (UM.STATE_INVISIBLE, False), (UM.STATE_GRAYED, False), (UM.STATE_INVERTED, False), (UM.STATE_NORMAL, True)):
            wnd.param_int(0, 0, state); self.assertEqual(0 in zones(wnd), expected, state)

    def test_original_behavior_on_request(self):
        os.environ['DQ_AUTO_HIDDEN'] = '1'
        try:
            wnd = window(); wnd.code(0, 0); wnd.auto_plate()
            self.assertFalse(wnd.N[10]['act']); self.assertNotIn(4, zones(wnd))                              # the original game hides the plate
        finally: os.environ.pop('DQ_AUTO_HIDDEN', None)


if __name__ == '__main__':
    unittest.main()
