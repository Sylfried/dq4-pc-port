"""the name of a monster's copy of a character ("Le feutocopieur se transforme en portrait craché d'Alina !") was composed by the engine with the English prefix "copy of ;" (MsgVar::extract_var;
the French texts run as language 1, English). With French texts the viewer writes the French patch's own words for these copies (its monster names in `b1002000.mpt`: "double de ;Kiryl",
"double d'Alina"; ";" = break marker of the patch, not drawn): "Double d'Alina attaque !", "Inflige 9 points de dégâts à double de Borya." (the APK's text).

1. Without APK: the language test of the texts (French article of the first monster name), the vowel test of the elision, the strings.
2. Real engine (DQ_APK, DQ_SAVES): the prefix is French after the engine is created and again after a savestate is loaded (original library image put back); a forced battle against the
   feutocopieur (monster 122) names its copy "double d'Alina" / "double de Borya" and never "copy of"; the French patch writes the same names.
    DQ_APK=<patched APKs folder> DQ_SAVES=<saves folder> python3 tests/test_copy_name.py        (about a minute)
"""
import os, sys, tempfile, unittest, zipfile

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, '..'))
sys.path.insert(0, HERE)
from dq4_pc.core import engine as ENGINE
APK, SAVES = os.environ.get('DQ_APK'), os.environ.get('DQ_SAVES')


def pack(names):
    f = os.path.join(tempfile.mkdtemp(prefix='copy_'), 'pack.apk')
    with zipfile.ZipFile(f, 'w') as z: z.writestr(ENGINE.NAMES_MSG, names)
    return f


class WithoutApk(unittest.TestCase):
    def test_language_of_the_texts(self):
        self.assertTrue(ENGINE.Engine._french_texts(pack(b'\x00@0M@2le @3un @4gluant@5les @6des @7gluants@8N@9N@')))
        self.assertTrue(ENGINE.Engine._french_texts(pack(b"@0F@2la @3une @4bebete@8N@")))
        self.assertTrue(ENGINE.Engine._french_texts(pack(b"@0M@2l'@3un @4empereur@8N@")))
        self.assertFalse(ENGINE.Engine._french_texts(pack(b'@0N@2the @3a @4slime@5the @6some @7slimes@8N@')))
        self.assertFalse(ENGINE.Engine._french_texts('/nonexistent.apk'))

    def test_strings(self):
        self.assertEqual(len(ENGINE.COPY_PREFIX_FR), len(ENGINE.COPY_PREFIX_EN))           # (the 2 extra bytes take the start of the Korean string, language 2)
        self.assertEqual(ENGINE.COPY_PREFIX_EN[:10], b'copy of ;\x00'); self.assertEqual(ENGINE.COPY_PREFIX_FR, b'double de ;\x00')

    def test_vowels(self):
        for name in ('Alina', ';Alina', 'Élisa', 'Ève', 'ines', 'Yves', 'Olaf', 'Ulf'): self.assertTrue(ENGINE.starts_with_vowel(name.encode('utf-8')), name)
        for name in ('Kiryl', ';Borya', 'Ragnar', 'Psaro', 'Hector', ''): self.assertFalse(ENGINE.starts_with_vowel(name.encode('utf-8')), name)


try:
    import test_enemy_chest as CHEST
except Exception: CHEST = None


@unittest.skipUnless(APK and SAVES and CHEST, 'real engine: DQ_APK=<folder of the patched APKs> DQ_SAVES=<folder of the saves>')
class RealEngine(CHEST.ChestDroppedByEnemy if CHEST else unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        CHEST.FORCED_MONSTER = 122                                                     # feutocopieur
        super().setUpClass()

    def prefix(self):
        return bytes(self.c.mem(self.eng.L + ENGINE.COPY_PREFIX, len(ENGINE.COPY_PREFIX_EN)))

    def test_prefix_in_memory(self):
        self.assertTrue(self.eng.french_texts)
        self.assertEqual(self.prefix(), ENGINE.COPY_PREFIX_FR)
        self.c.mem_w(self.eng.L + ENGINE.COPY_PREFIX, ENGINE.COPY_PREFIX_EN)        # (what loading a savestate does: the library's original image)
        self.eng.reapply_fixes(); self.assertEqual(self.prefix(), ENGINE.COPY_PREFIX_FR)
        self.assertFalse([t for t in self.eng.missing_hooks if t.startswith('copy name')])

    def test_battle_against_the_copier(self):
        texts, _ = self.play(False)
        self.assertTrue(any('portrait craché' in t for _, t in texts), 'the copycat did not transform')
        self.assertFalse([t for _, t in texts if 'copy of' in t.lower()])
        copied = [t for _, t in texts if 'portrait craché' in t]
        names = set()
        for t in copied:                                                                           # "... portrait craché d'Alina !" / "... de Borya !": the character copied
            nm = t.split('portrait craché ')[1].split(' !')[0]; names.add(nm[2:] if nm.startswith("d'") else nm[3:])
        for nm in names:
            expected = ("double d'" if ENGINE.starts_with_vowel(nm.encode()) else 'double de ;') + nm
            self.assertTrue(any(expected in t or expected[0].upper() + expected[1:] in t for _, t in texts), (expected, [t for _, t in texts if 'ouble' in t][:3]))
        self.assertFalse([t for _, t in texts if "double de ;A" in t or "ouble de ;A" in t], 'no elision before a vowel')

    def test_message_sequence_and_only_sfx_300(self): pass          # (tests of the parent class: not repeated here)
    def test_without_chest_no_message(self): pass


if __name__ == '__main__':
    unittest.main(verbosity=2)
