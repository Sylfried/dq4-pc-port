"""the towns of chapters 2 to 9 loaded with the real engine.

From a save on the world map at chapter 5 or later (with the nine characters), the chapter is forced
(`StoryStatus::setChapter`, what the game does between two chapters) and a map is started (`Global::startTown`), then 600 engine steps.
The story flags stay those of the save, so what is checked is what the chapter's own scenario scripts do with the map (characters placed, 3D figures, an arrival message, a redirection),
not a playthrough. Measured over the 529 maps of the game and chapters 2 to 9 (4232 loads): see `docs/audit/decisions.md`.
    DQ_APK=<patched APKs folder> DQ_SAVES=<saves folder> python3 tests/test_chapters_towns.py        (about 30 seconds)
"""
import os, sys, tempfile, unittest

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, '..'))
sys.path.insert(0, HERE)
import _saves as SV

APK, SAVES = os.environ.get('DQ_APK'), os.environ.get('DQ_SAVES')
CHAPTERS = range(2, 10)
TOWNS = ('cdout', 'ceout', 'cgout1', 'hcout', 'maout', 'mbout', 'mhout', 'moout', 'ckout')        # outside maps of towns and castles, one or more per chapter's scenario
FIGURES = {'clf1a': (1000, 1000, 1000), 'ckf3f5': (1001,), 'ddb4': (1002,), 'cmf3b': (1003,), 'srout': (1004,), 'ddb5b': (1006, 1006), 'dpout': (1007,)}      # maps whose script places 3D figures (chapter 5), model numbers (c1000 + the character's graphic)


@unittest.skipUnless(APK and SAVES, 'real engine: DQ_APK=<folder of the patched APKs> DQ_SAVES=<folder of the saves>')
class ChaptersTowns(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        from dq4_pc.core import engine as ENGINE
        from dq4_pc.persistence import savestates as SS
        cls.E, cls.SS = ENGINE, SS

        def make():
            e = ENGINE.Engine(APK, SAVES, tempfile.mkdtemp(prefix='sv_chapitres_'))
            for _ in range(3): e.step(0, 0)
            return e
        def wanted(e): SV.settle(e, 200, 600); return e.state.part == ENGINE.PART_FIELD and SV.chapter(e) >= 5
        cls.e, _ = SV.pick_save(make, wanted, 'a save on the world map at chapter 5 or later')
        cls.snap = SS.snapshot(cls.e)
        cls.seen = {}
        for m in TOWNS:
            for ch in CHAPTERS: cls.seen[m, ch] = cls.visit(ch, m)
        for m in FIGURES: cls.seen[m, 5] = cls.visit(5, m)

    @classmethod
    def visit(cls, chapter, name):
        """Starts the map at the forced chapter. -> {'part', 'map', 'npcs' (sorted sprite sheets of the characters other than the party), 'texts' (messages heard on arrival)}."""
        e = cls.e
        cls.SS.apply(e, cls.snap); SV.force_chapter(e, chapter); e.sensor.drain()
        e.start_town(name)
        for _ in range(600): e.step(0, 0)
        npcs = sorted(s['id'] for k, s in e.state.sprites.items() if k >= 8 and s.get('id', -1) >= 0 and s.get('pos') is not None)
        return {'part': e.state.part, 'map': e.state.game_map, 'npcs': npcs, 'texts': [s['text'] for s in e.sensor.drain()],
                'figures': sorted((v['id'], v['visible'], tuple(v['pos'])) for v in e.state.fbx.values())}

    def test_every_map_loads_at_every_chapter(self):
        for (m, ch), r in self.seen.items():
            self.assertIn(r['part'], (self.E.PART_TOWN, self.E.PART_FIELD), (m, ch, r))

    def test_the_chapter_decides_who_is_there(self):
        different = [m for m in TOWNS if len({tuple(self.seen[m, ch]['npcs']) for ch in CHAPTERS}) > 1]
        self.assertGreaterEqual(len(different), 6, different)
        crowd = [m for m in TOWNS if self.seen[m, 5]['npcs']]
        self.assertGreaterEqual(len(crowd), 6, crowd)                                                 # (chapter 5, the hero's: the towns have their villagers)

    def test_arrival_message_at_zenithia(self):
        texts = ' '.join(self.seen['ckout', 5]['texts'])
        self.assertIn('Zénithia', texts)

    def test_a_town_that_sends_the_party_elsewhere(self):
        self.assertNotEqual(self.seen['mhout', 9]['map'], 'mhout')                                      # (chapter 9: the script of `mhout` goes on to another map, measured over the whole game)

    def test_town_figures_are_placed_by_the_engine(self):
        """the engine itself asks for the 3D figures (packet 31, model 1000 + graphic) and places them (packet 32) once the map's script has run; the port draws them (seen in the real window)."""
        for m, models in FIGURES.items():
            figures = self.seen[m, 5]['figures']
            self.assertEqual(tuple(f[0] for f in figures), models, (m, figures))
            for _, visible, pos in figures:
                self.assertTrue(visible, (m, figures)); self.assertNotEqual(pos, (0.0, 0.0, 0.0), (m, figures))


if __name__ == '__main__':
    unittest.main(verbosity=2)
