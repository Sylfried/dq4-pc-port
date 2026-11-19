"""The French patch's seed messages ask for a status name with its definite article ("%0%a02230 de Ragnar augmente de 1 !"), but the status names of `b1006000.mpt` have none (@1 only):
the game wrote "Force de Ragnar augmente de 1 !". The viewer gives them their article where the name table writes the name (Engine._status_article_hooks): "La Force de Ragnar augmente de 1 !",
"Le maximum de PV de Ragnar augmente de 4 points !"; the name alone (menus, Carac. page) does not change, nor do the names whose table has its own articles.

1. Without APK: the table of articles.
2. Real engine (DQ_APK, DQ_SAVES): the name table's function, called directly with the form of a variable (0: the name, 2: the definite article).
    DQ_APK=<patched APKs folder> DQ_SAVES=<saves folder> python3 tests/test_status_articles.py        (about 30 s)
"""
import os, struct, sys, tempfile, unittest

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, '..'))
from dq456_pc.core import engine as ENGINE
APK, SAVES = os.environ.get('DQ_APK'), os.environ.get('DQ_SAVES')


class WithoutApk(unittest.TestCase):
    def test_articles(self):
        for name, full in ENGINE.STATUS_DEFINITE_FR.items():
            self.assertTrue(full.startswith(('la ', 'le ', "l'")), full)
            if not name.startswith('Max.'): self.assertTrue(full.endswith(name), full)           # (the name as the patch writes it: "graine de Force", "l'Agilité")
        self.assertEqual(ENGINE.STATUS_DEFINITE_FR['Max. PV'], 'le maximum de PV')            # ("Son maximum de PV augmente de 4 !", the patch's level-up message)


@unittest.skipUnless(APK and SAVES, 'real engine: DQ_APK=<folder of the patched APKs> DQ_SAVES=<folder of the saves>')
class RealEngine(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.m = ENGINE.Engine(APK, SAVES, tempfile.mkdtemp(prefix='articles_'))
        for _ in range(3): cls.m.step(0, 0)
        if not cls.m.french_texts: raise unittest.SkipTest('English texts')

    def name(self, message, form):
        c = self.m.core; buf = c.scratch('test_articles', 256); c.mem_w(buf, bytes(256))
        c.mem_w(self.m.L + ENGINE.MSGVAR_FORM, struct.pack('<i', form))
        try: c.call(c.export('_ZN8TextHook18extractDefaultTextEPci') - 0x22c, buf, 9, message)        # (the local function that copies the article of the form, then the name: table 9 = b1006000)
        finally: c.mem_w(self.m.L + ENGINE.MSGVAR_FORM, struct.pack('<i', 0))
        raw = bytes(c.mem(buf, 64)); return raw[:raw.find(b'\x00')].decode('utf-8')

    def test_definite_article(self):
        self.assertEqual(self.name(1006007, 2), 'la Force'); self.assertEqual(self.name(1006008, 2), "l'Agilité")
        self.assertEqual(self.name(1006014, 2), 'le maximum de PV'); self.assertEqual(self.name(1006015, 2), 'le maximum de PM')

    def test_name_alone_unchanged(self):
        self.assertEqual(self.name(1006007, 0), 'Force'); self.assertEqual(self.name(1006014, 0), 'Max. PV')
        self.assertEqual(self.name(1006005, 2), 'Masculin')                                   # (not in the table: unchanged)


if __name__ == '__main__':
    unittest.main()
