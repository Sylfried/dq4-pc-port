"""World map: stacking order of the party members at landing ("once landed, Doc ended up in front of Ragnar").

    python3 tests/test_field_group_order.py                                                    (engine-less part: Linux without a screen, pyglet in "headless" mode)
    DQ_APK=<folder of the patched APKs> DQ_SAVES=<folder of the saves> python3 tests/test_field_group_order.py      (adds the real engine scenario)

Origin: FieldPartyDraw::draw (libdq4core 0x1ec5a8) sorts the party members by decreasing depth (selection sort, at equal depth the lowest slot keeps the head) then gives
them SpriteCharacter::setDepth 10, 9, 8...: at equal depth, the hero is IN FRONT of his teammates. A landing (Zoom, "aile de chimere") stacks the party on a single point (measured on the real engine: hero
and Doc at (2495.967; 391.967; z 200) after the descent), so the tie rule decides. Before: `sorted((z, y, slot))` put the largest slot in front (Doc).

  1. without engine (`field_depth_rank`): equal position -> hero in front; height z, then "further south", always take precedence; vehicles (>= 10): the most recent in front, without changing the party;
  2. real engine (save 1, party Ragnar + Doc): spell Teleportation (action 203) cast from the village of maout to the 2nd location (world map), descent until the stop: the party is stacked
     (same x, y, z) and the hero is in front of Doc; during the descent, Doc (to the north, smaller z) stays behind the hero."""
import os, sys, tempfile, unittest

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), '..'))
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import _saves as SV
import pyglet
if sys.platform.startswith('linux') and not os.environ.get('DISPLAY'): pyglet.options['headless'] = True; pyglet.options['shadow_window'] = False
from dq456_pc.window import game as F

APK, SAVES = os.environ.get('DQ_APK'), os.environ.get('DQ_SAVES')


def sp(x, y, z=None): return {'pos': (x, y) if z is None else (x, y, z)}


class OrderWithoutEngine(unittest.TestCase):
    def test_equal_position_hero_is_in_front(self):
        r = F.field_depth_rank({0: sp(2495.967, 391.967, 200.0), 1: sp(2495.967, 391.967, 200.0)})
        self.assertGreater(r[0], r[1])

    def test_group_of_four_stacked_in_group_order(self):
        r = F.field_depth_rank({n: sp(10.0, 20.0, 200.0) for n in range(4)})
        self.assertEqual(sorted(r, key=lambda n: -r[n]), [0, 1, 2, 3])          # front -> back

    def test_height_prevails(self):
        r = F.field_depth_rank({0: sp(10.0, 20.0, 180.0), 1: sp(10.0, 20.0, 200.0)})
        self.assertGreater(r[1], r[0])

    def test_southernmost_prevails_over_slot(self):
        r = F.field_depth_rank({0: sp(10.0, 20.0, 200.0), 1: sp(10.0, 26.0, 200.0)})
        self.assertGreater(r[1], r[0])
        r = F.field_depth_rank({0: sp(10.0, 26.0, 200.0), 1: sp(10.0, 20.0, 200.0)})
        self.assertGreater(r[0], r[1])

    def test_vehicles_most_recent_in_front_and_group_unchanged(self):
        r = F.field_depth_rank({0: sp(1.0, 2.0, 200.0), 1: sp(1.0, 2.0, 200.0), 10: sp(1.0, 2.0, 200.0), 11: sp(1.0, 2.0, 200.0)})
        self.assertGreater(r[11], r[10]); self.assertGreater(r[0], r[1])

    def test_sprite_without_position_ignored_and_z_absent(self):
        r = F.field_depth_rank({0: sp(1.0, 2.0), 1: {'pos': None}, 2: sp(1.0, 2.0)})
        self.assertEqual(set(r), {0, 2}); self.assertGreater(r[0], r[2])


@unittest.skipUnless(APK and SAVES, 'real engine: DQ_APK=<folder of the patched APKs> DQ_SAVES=<folder of the saves>')
class RealEngineLanding(unittest.TestCase):
    BTN_TALK, BTN_MENU = 0x100, 0x800
    RAGNAR, DOC = 3, 12                                                   # slots in originalPlayer_ (registry of all the game's characters: it does not depend on the save)

    def advance(self, eng, n, held=0, decl=None):
        for i in range(n): eng.step(held, (held if decl is None else (decl if i == 0 else 0)))

    def test_landing_on_world_map(self):
        from dq456_pc.core import engine as ENGINE

        def to_the_village(eng):
            """Needs chapter 1, the Ragnar + Doc party and the village `maout` outdoors. The first two are forced; the third
            requires the party to start close enough to the door of `mak1f1`, which depends on the save: we check by walking."""
            SV.settle(eng); SV.force_chapter(eng, 1); SV.force_party(eng, self.RAGNAR, self.DOC)
            c = eng.core
            ha = c.export('_ZN6status9PartyData15originalPlayer_E') + 0x530 * self.DOC + 0xd0
            c.call(c.export('_ZN6status10HaveAction5clearEv'), ha); c.call(c.export('_ZN6status10HaveAction3addEii'), ha, 203, 0)   # 203 = Teleportation
            eng.start_town('mak1f1'); self.advance(eng, 90)
            if eng._map_name() != 'mak1f1': return False
            eng.sensor.drain(); initial = eng._map_name()
            for _ in range(300):                                              # sortir de l'eglise (bas) : village de maout, en plein air
                self.advance(eng, 1, 2)
                if eng._map_name() != initial: break
            return eng._map_name() == 'maout'

        eng, _slot = SV.pick_save(lambda: ENGINE.Engine(APK, SAVES, tempfile.mkdtemp(prefix='sv_135_')), to_the_village,
                                  "une sauvegarde dont le groupe peut sortir de `mak1f1` vers le village `maout` (chapitre 1 et groupe Ragnar + Doc imposes)")
        self.advance(eng, 70)
        self.advance(eng, 1, 0, self.BTN_MENU); self.advance(eng, 20)
        eng.send_menu(4, 1, 1, 0x10); self.advance(eng, 20)                   # root menu: Magie
        eng.send_menu(5, 1, 3, 0x10); self.advance(eng, 25)                   # Doc
        before = dict(eng.ui.f.get(8, {}).get('cells', {}))
        eng.send_menu(8, 1, 0, 0x10); self.advance(eng, 20)                   # the spell: the info panel gives way to the list of known places
        if dict(eng.ui.f.get(8, {}).get('cells', {})) == before:
            self.skipTest('Teleportation opens no list of places: the known destinations come from the saved progress, '
                          'and no save of DQ_SAVES has any at chapter 1')
        eng.send_menu(8, 1, 1, 0x10)                                        # 2nd location: on the world map
        equal_count, descent_count = 0, 0
        for _ in range(900):
            self.advance(eng, 1)
            if eng.msg_visible and eng.frames % 20 == 0: self.advance(eng, 1, 0, self.BTN_TALK)
            if eng.state.part != ENGINE.PART_FIELD: continue
            s0, s1 = eng.state.sprites.get(0), eng.state.sprites.get(1)
            if not s0 or not s1 or s0['pos'] is None or s1['pos'] is None: continue
            r = F.field_depth_rank(eng.state.sprites)
            if s0['pos'] == s1['pos']: equal_count += 1; self.assertGreater(r[0], r[1], 'stacked: the hero must be in front (%s)' % (s0['pos'],))
            elif s1['pos'][2] < s0['pos'][2]: descent_count += 1; self.assertGreater(r[0], r[1], 'Doc (smaller z) must stay behind the hero')
        print('\n  images de descente (Doc au nord, z plus petit) : %d ; images empilees : %d ; positions finales : %s / %s' % (descent_count, equal_count, eng.state.sprites[0]['pos'], eng.state.sprites[1]['pos']), flush=True)
        self.assertGreater(descent_count, 5); self.assertGreater(equal_count, 5)          # the descent was indeed seen, and so was the stacked stop


if __name__ == '__main__':
    unittest.main(verbosity=2)
