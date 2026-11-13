"""Test shortcut to the ending: talking to the King of Bastione plays the whole ending scene (either of the two endings) instead of his speech; settings in "Modifiers":
  - setting `test_ending` (off by default = like the game), line "Game ending by talking to the King of Bastione" under "Cheats"; setting `test_ending_which` (5 or 6), line "Ending played by this shortcut" just below;
  - on: a talk (decl 0x100) in Bastione's throne room (caf2a) within reach of its king (character 36) plays the whole ending instead (Engine.start_ending), the talk is not sent;
  - Engine.start_ending(1 | 2) = chapter 5's ending (Psaro defeated) or chapter 6's (Aamon defeated, Psaro in the party, his scene added), played by the game's own scripts from the place where the original starts it, the trigger of the map `ckout` (the shortcut only puts the hero there): its script (fade out, SE 305,
    BGM 34 that then plays through the whole ending), the black screen `ev09`, the party scene `fk01` (which places the balloon on the world map), everyone going home (cbf1 ... mhout), the hero's village ev08,
    the script of mlb1a (credits, "The End", the engine's save box), back to the title; the port only forces the chapter (5 or 6), the party, the flags of the trigger and 0x1af, and the party kept for the save.
    DQ_APK=<folder of the APKs> DQ_SAVES=<folder of the saves> python3 tests/test_ending_shortcut.py        (real engine part, about a minute)"""
import os, struct, sys, tempfile, types, unittest
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), '..'))
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from dq4_pc.persistence import settings as RG
try:
    import pyglet
    pyglet.options['shadow_window'] = False
    from dq4_pc.window import game as G
    from dq4_pc.core import engine as ENGINE
except Exception as ex:          # (the import alone is enough)
    G = None

APK, SAVES = os.environ.get('DQ_APK'), os.environ.get('DQ_SAVES')


def fake(map_name='caf2a', part=None, hero=(0.0, 0.05, 1.9), king=(0.0, 0.0, 3.05), king_id=36):
    st = types.SimpleNamespace(part=ENGINE.PART_TOWN if part is None else part, game_map=map_name, sprites={0: {'id': 103, 'pos': hero}, 8: {'id': king_id, 'pos': king}, 9: {'id': 34, 'pos': (2.0, 0.0, 0.66)}})
    return types.SimpleNamespace(engine=types.SimpleNamespace(state=st))


class Setting(unittest.TestCase):
    def test_off_by_default_and_a_boolean(self):
        self.assertIs(RG.DEFAULT['test_ending'], False); self.assertIn('test_ending', RG.SOUND_TEXT_BOOLEANS)

    def test_which_ending(self):
        self.assertEqual(RG.DEFAULT['test_ending_which'], 5)
        for good in (5, 6):
            self.assertEqual(self.loaded(good), good)
        for bad in (0, 4, 7, True, 'x', None, 5.5, [6]):                         # (anything but 5 or 6 goes back to the default)
            self.assertEqual(self.loaded(bad), 5, bad)

    def loaded(self, value):
        import json
        p = os.path.join(tempfile.mkdtemp(prefix='rg_ending_'), 'r.json')
        with open(p, 'w') as f: json.dump({'test_ending_which': value}, f)
        return RG.Settings(p).v['test_ending_which']


@unittest.skipIf(G is None, 'window not importable here')
class KingOfBastione(unittest.TestCase):
    def test_only_his_talk(self):
        f = lambda **kw: G.Game._talks_to_ending_king(fake(**kw))
        self.assertTrue(f())                                                         # facing him, across the throne's step
        self.assertFalse(f(hero=(0.0, 0.05, -1.0)))                                  # elsewhere in the room
        self.assertFalse(f(map_name='caf2b')); self.assertFalse(f(king_id=34)); self.assertFalse(f(part=ENGINE.PART_FIELD))

    def test_the_line_is_in_cheats(self):
        from dq4_pc.menus import pause as PA
        src = open(PA.__file__, encoding='utf-8').read()
        i = src.index("dict(t='sep', l=N_('settings.cheats')), end, which]"); self.assertGreater(i, src.index("'settings.game_ending_talking_king_bastione'")); self.assertGreater(i, src.index("'settings.ending_played_shortcut'"))
        self.assertEqual(G.ENDING_OF_CHAPTER, {5: 1, 6: 2})                       # (chapter 5 = ending 1, chapter 6 = ending 2)


@unittest.skipUnless(APK and SAVES, 'real engine: DQ_APK=<folder of the APKs> DQ_SAVES=<folder of the saves>')
class RealEngine(unittest.TestCase):
    def test_throne_room_king_and_ending(self):
        import _saves as SV
        out = tempfile.mkdtemp(prefix='sv_ending_')
        eng = ENGINE.Engine(APK, SAVES, out)
        for _ in range(3): eng.step(0, 0)
        if not eng.load_save(3): raise unittest.SkipTest('no save 3 (chapter 5, Ragnar: the king is on his throne)')
        SV.settle(eng); eng.start_town('caf2a')
        for _ in range(200): eng.step(0, 0)
        self.assertEqual(eng.state.game_map, 'caf2a')
        if 36 not in [s['id'] for s in eng.state.sprites.values()]: raise unittest.SkipTest('the king is not on his throne at this point of the story')
        for _ in range(60): eng.step(0, 0)
        self.assertEqual(sorted(eng.state.meshes), [])
        self.assertFalse(eng.start_ending(3)); self.assertFalse(eng.start_ending(0))                       # (only 1 and 2)
        self.assertTrue(eng.start_ending(1))                                                                # (from a town: the game goes to `ckout`, whose script starts the ending)
        for _ in range(300): eng.step(0, 0)
        self.assertEqual(eng.state.game_map, 'ev09')                                                         # (the script of `ckout` has gone on to the black screen)

    def play(self, which):
        """Plays the whole ending `which` like the player (A for the messages, the end screen's key, "No" then "Yes" to the save question) and returns what happened."""
        import _saves as SV
        out = tempfile.mkdtemp(prefix='sv_ending_%d_' % which)
        eng = ENGINE.Engine(APK, SAVES, out)
        for _ in range(3): eng.step(0, 0)
        eng.load_save(1); SV.settle(eng, 250, 1500)
        c = eng.core; party_addr = c.export('_ZN6status7g_PartyE')
        before = SV.chapter(eng)
        self.assertTrue(eng.start_ending(which))
        members = [i for i in struct.unpack('<13I', c.mem(party_addr + 0x304, 13 * 4)) if i]
        got = dict(members=members, chapter_start=SV.chapter(eng), chapter=None, maps=[], texts=[], staff=False, the_end=False, title=False, bgm=[], legs=[])
        leg = None
        last = eng.state.game_map; waiting = 0; release = None; said = ''
        for f in range(24000):
            p = d = 0
            if release is not None: eng.send_menu(release, 1, -1, 0); release = None
            port = eng.active_menu()
            feed = eng.msg_visible and (eng.ui.msg.get('feed') or eng.message_state()[1] in (3, 5))
            if port is not None or feed:
                waiting += 1
                if waiting % 6 == 0:
                    if port is None: p = d = ENGINE.A
                    else:
                        no = eng.ui.f[port].get('type') == 1 and 'renoncer' not in said
                        eng.send_menu(port, 1, -1, 0x20 if no else 0x10); release = port                  # (B = "No" on the first question, A = "Yes" on the "renoncer" one)
            else:
                waiting = 0
                if f % 40 == 0 and eng.the_end_started() and eng.state.part != ENGINE.PART_INITIAL: p = d = ENGINE.A                 # (the key the end screen waits for)
            eng.step(p, d)
            for sn in eng.sensor.drain(): said = sn['text']; got['texts'].append(said)
            got['bgm'] += [v for t, v in eng.state.sounds if t == 37]; eng.state.sounds.clear()
            if eng.state.part == ENGINE.PART_FIELD and leg is None: leg = f
            elif eng.state.part != ENGINE.PART_FIELD and leg is not None: got['legs'].append(f - leg); leg = None             # (the flights on the world map: lengths in steps)
            if eng.state.game_map != last:
                got['maps'].append(eng.state.game_map); last = eng.state.game_map
                if last == 'cbf1': got['chapter'] = SV.chapter(eng)                                                              # (`ev09` has set chapter 9)
            if eng.ui.staff and eng.ui.staff['live']: got['staff'] = True
            if eng.the_end_started(): got['the_end'] = True
            if eng.state.part == ENGINE.PART_INITIAL: got['title'] = True; break
        got['before'] = before; got['written'] = sorted(os.listdir(out))
        return got

    def check(self, got):
        self.assertEqual(got['chapter'], 9)                                                                                              # (the script of `ev09` sets it: the shortcut only sets the chapter of the fight before)
        self.assertEqual(got['maps'][:12], ['ckout', 'ev09', 'fk01', 'cbf1', 'cbf2', 'cbf3', 'caf1', 'mqout', 'hcout', 'miout', 'mhout', 'mhg1n1'])          # (the trigger, the black screen, the party, everyone going home, then the hero's village)
        self.assertIn(34, got['bgm']); i = got['bgm'].index(34); self.assertEqual(got['bgm'][i - 1:i + 1], [16392, 34])                 # (the script of `ckout` stops the music then starts BGM 34 ...)
        self.assertEqual(got['legs'][0], 892)                                                                                            # (the first flight leaves from the point where `fk01` puts the balloon: as long as in the original, not a long trip from wherever it was)
        self.assertIn('ev08', got['maps']); self.assertIn('mlb1a', got['maps'])                                                          # (the ending script of mlb1a)
        self.assertTrue(got['staff']); self.assertTrue(got['the_end'])                                                                    # (credits, then "The End")
        self.assertTrue(any('sauvegarder' in t for t in got['texts']))                                                                    # (the engine's own save question)
        self.assertTrue(any('renoncer' in t for t in got['texts']))
        self.assertTrue(got['title'])                                                                                                     # (back to the title)
        self.assertEqual([x for x in got['written'] if x.startswith('data') and x not in ('data9.dat',)], [])                             # ("No" then "Yes": no journal written

    def test_ending_1(self):
        got = self.play(1)
        self.assertEqual(got['members'], [1, 4, 5, 6, 3, 7, 8, 9]); self.check(got)                                                       # (the hero and the seven allies, not Psaro)

    def test_ending_2(self):
        got = self.play(2)
        self.assertEqual(got['members'], [1, 4, 5, 6, 3, 7, 8, 9, 25]); self.check(got)                                                   # (Psaro joins)


if __name__ == '__main__':
    unittest.main(verbosity=1)
