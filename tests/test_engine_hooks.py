"""Test of the survey of the hooks installed in the engine.

The project's permanent rule: `libdq4core.so` is never modified on disk, and **everything the port places in memory** is listed in
`docs/engine-patches.md`. A hand-kept table drifts without anyone noticing.

This test redoes the survey **at runtime** — it counts the `Uc.hook_add` calls during engine creation — and fails as soon as the number changes. Adding or removing a hook therefore forces the
document to be updated in the same commit: that is the whole point of the rule.

    DQ_APK=<folder of the patched APKs> DQ_SAVES=<folder of the saves> python3 tests/test_engine_hooks.py
No screen, no GL. The saves are opened read-only (the engine writes to a temporary folder).
"""
import collections, io, os, re, sys, tempfile, traceback, unittest

ROOT = os.path.join(os.path.dirname(os.path.abspath(__file__)), '..')
sys.path.insert(0, ROOT)
APK, SAVES = os.environ.get('DQ_APK'), os.environ.get('DQ_SAVES')
NOTES = os.path.join(ROOT, 'docs', 'engine-patches.md')

EXPECTED = {'core/engine.py': 49, 'battle/battle_history.py': 8, 'core/pktlog.py': 3, 'core/history.py': 4, 'core/emu_core.py': 6}       # measured with the French texts (the English ones: core/engine.py 47, no copy-name elision hook nor status-name article hook)
OUTSIDE_EMU = sum(n for f, n in EXPECTED.items() if f != 'core/emu_core.py')


def count_hooks():
    """-> Counter {dq456_pc file: number of `hook_add`} during the creation of the engine."""
    import unicorn
    from dq456_pc.core import engine as ENGINE
    per_file = collections.Counter()
    real = unicorn.Uc.hook_add
    def spy(self, *a, **k):
        for fr in traceback.extract_stack()[::-1]:
            if os.sep + 'dq456_pc' + os.sep in fr.filename:
                per_file[fr.filename.split(os.sep + 'dq456_pc' + os.sep)[1].replace(os.sep, '/')] += 1; break
        return real(self, *a, **k)
    unicorn.Uc.hook_add = spy
    try:
        m = ENGINE.Engine(APK, SAVES, tempfile.mkdtemp(prefix='sv_crochets_'))
        for _ in range(3): m.step(0, 0)
    finally:
        unicorn.Uc.hook_add = real
    return per_file


class Document(unittest.TestCase):
    """Part without an APK: the document carries the figures of the last measurement."""

    @classmethod
    def setUpClass(cls):
        with io.open(NOTES, encoding='utf-8') as f: cls.notes = f.read()
        cls.count = cls.notes[cls.notes.index('**Count ('):]
        cls.count = cls.count[:cls.count.index('\n')]

    def test_the_total_is_written_down(self):
        self.assertIn('**%d hooks**' % (OUTSIDE_EMU + EXPECTED['core/emu_core.py']), self.count, self.count[:200])
        self.assertIn('**%d outside `emu_core.py`**' % OUTSIDE_EMU, self.count)

    def test_the_breakdown_matches(self):
        for f, n in EXPECTED.items():
            if f == 'core/emu_core.py': continue
            self.assertRegex(self.count, r'`%s`\s*\*\*%d\*\*' % (re.escape(f), n), '%s: %d expected' % (f, n))

    def test_the_survey_command_works_on_subfolders(self):
        """The command given to list the sites searches the subfolders of dq456_pc (`-r`)."""
        self.assertIn('grep -rn', self.count)


@unittest.skipUnless(APK and SAVES, 'real engine: DQ_APK=<folder of the patched APKs> DQ_SAVES=<folder of the saves>')
class RealEngine(unittest.TestCase):
    @classmethod
    def setUpClass(cls): cls.per_file = count_hooks()

    def test_the_engine_posts_exactly_what_the_document_says(self):
        self.assertEqual(dict(self.per_file), EXPECTED,
                         'the engine no longer posts the same hooks: redo the section "Writes and hooks in the engine memory" in docs/technical-notes-dq4-port.md, then EXPECTED here')

    def test_outside_emu_core(self):
        got = sum(n for f, n in self.per_file.items() if f != 'core/emu_core.py')
        self.assertEqual(got, OUTSIDE_EMU)


if __name__ == '__main__':
    unittest.main(verbosity=2)
