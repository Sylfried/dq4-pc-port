"""The interface sheets of the cache (ui_MenuTexture.png, ui_Button.png) are decoded once per run (menus/sheets.py) and shared by every user.

Before, the menus, each icon of the field buttons, the D-pad, the icon bubbles, the damage digits and the Esc menu decoded the 1024 x 1024 sheet again on their first use; the field buttons and the
bubble appear together the first time the player gets control (after the welcome of the church when a log is loaded): a short stall, a few tens of milliseconds per decoding.

  python3 tests/test_ui_sheets.py
"""
import os, re, sys, tempfile, unittest
from unittest import mock

import numpy as np

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.join(HERE, '..')
sys.path.insert(0, ROOT)
from dq456_pc.menus import sheets as SH


class SharedSheets(unittest.TestCase):
    def setUp(self):
        from PIL import Image
        self.dir = tempfile.mkdtemp(prefix='sheets_')
        a = np.zeros((64, 96, 4), np.uint8); a[10:20, 30:40] = (200, 100, 50, 255)
        Image.fromarray(a, 'RGBA').save(os.path.join(self.dir, 'ui_MenuTexture.png')); self.ref = a

    def test_decoded_once(self):
        from PIL import Image
        real = Image.open
        with mock.patch.object(Image, 'open', side_effect=real) as op:
            a = SH.rgba(self.dir, 'ui_MenuTexture.png'); b = SH.rgba(self.dir, 'ui_MenuTexture.png'); im = SH.pil(self.dir, 'ui_MenuTexture.png'); im2 = SH.pil(self.dir, 'ui_MenuTexture.png')
        self.assertEqual(op.call_count, 1, 'one decoding for every user')
        self.assertIs(a, b); self.assertIs(im, im2)
        np.testing.assert_array_equal(a, self.ref); np.testing.assert_array_equal(np.asarray(im), self.ref)

    def test_read_only(self):
        a = SH.rgba(self.dir, 'ui_MenuTexture.png')
        self.assertFalse(a.flags.writeable)
        with self.assertRaises(ValueError): a[0, 0, 0] = 1
        cell = a[10:20, 30:40].copy(); cell[0, 0] = 0                                  # (a user copies the cells it takes)

    def test_missing_file_raises(self):
        with self.assertRaises(Exception): SH.rgba(self.dir, 'absent.png')


class NoOtherDecoding(unittest.TestCase):
    def test_sources(self):
        """No module of the port opens these two sheets itself any more: they all go through menus/sheets.py."""
        found = []
        for d, _, files in os.walk(os.path.join(ROOT, 'dq456_pc')):
            for f in files:
                if not f.endswith('.py') or f == 'sheets.py': continue
                src = open(os.path.join(d, f), encoding='utf-8').read()
                for m in re.finditer(r"Image\.open\([^\n]*?(ui_MenuTexture\.png|ui_Button\.png)", src): found.append('%s: %s' % (f, m.group(0)[:80]))
        self.assertEqual(found, [])


if __name__ == '__main__':
    unittest.main()
