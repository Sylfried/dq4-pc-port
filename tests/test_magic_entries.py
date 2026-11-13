"""Field magic menu (Make_NameButton, Make_MagicInfo, Make_TargetCharaList) and uses with no effect: the original engine decides.

    python3 tests/test_magic_entries.py                                          (interface part: Linux without a screen, pyglet in "headless" mode)
    DQ_APK=<folder of the patched APKs> DQ_SAVES=<folder of the saves> python3 tests/test_magic_entries.py      (adds the real-engine scenarios)

Interface part (no engine): the named-button list (type 8) receives from the engine its code 6 = layout preset (`MenuPortItemTable.name_button_param`). Without it, the 5th row
stayed visible and clickable: a tap there sent the engine a nonexistent spell (<ERR 0x07000000.0> on screen, "Cout en PM 0/ 30").
  1. preset 0 (4 rows: spell list): only the rows whose code is not 0 are touch zones; rows 4 and 5 do not exist;
  2. preset 1 (5 rows: menu "Utiliser / Transferer / Abandonner"); presets 2 to 4: y coordinate of the first row, following rows 67 below;
  3. code 6 replayed (or arriving after the row codes) does not shift twice; an unknown preset is ignored; going back to preset 0 puts the rows back in place;
  4. the cost line "Cout en PM:<tab> 2" (TextMesh.tabSize 8): the tab becomes 8 spaces in the magic list only (a text without a tab or without tabSize does not change).

  4 bis. French texts in their frames (had left them overflowing): cost line of the info panels (types 7 and 38) compressed to fit the frame, cost line of the lists (types 8 and 35) fitted in its button and raised by 4 units,
     description re-wrapped to 2 lines (tests/test_item_description.py).

Engine part (DQ_APK and DQ_SAVES: the saves are opened read-only, the engine writes to a temporary folder). The party and hit points no longer come from the player's save, which changes as soon as they play:
  the party is **imposed** (`status::PartyStatus`: clear then add Ragnar and Doc, 30 MP, who knows "Premiers secours") and HP are requested as "max" or "hurt" (5 less), the max HP being read from the save:
  5. Doc's list: a single row, "Premiers secours", row code 2, rows 1 to 3 hidden;
  6. Premiers secours on wounded Ragnar: MP 30 -> 28, HP restored to max; on Ragnar at full HP: NO MP spent (BaseAction::useMp spends only if the action had an effect) and, outside battle, "Mais il ne se passe rien." (official message of Evac', id 0xc3d6d) in place of the healing success message
     (hook Engine._magic_hooks; EXPECTED RESULT DELIBERATELY CHANGED: before, the engine displayed "Les blessures de Ragnar guerissent !" without spending MP);
  7. uses with no effect decided by the engine: Rappel on a living character, Antipoison with no poison: "Mais rien ne se passe.", no MP spent; insufficient MP: "Pas assez de PM !";
  8. Rappel on a dead character: "revient a la vie", MP spent; Antipoison on a poisoned character: "n'est plus empoisonne";
  9. rule "a spell that costs MP and spends none": healing at full HP (Premiers secours, Soins partiels, Soins complets), group healing (Multisoin: a single message, no healing sound effect pending);
     non-regressions: spell with an effect (MP spent, game message), Multisoin with a wounded character (healing messages kept), the game's own failure messages (Evac' outside a dungeon), 0-MP spells (Mappille, Sifflet).
 10. sound effects (SoundManager::playSe): the cast sound effect (306, the same for all spells) is played in all cases; the healing sound effect (501) is NOT played when the spell had no effect (Premiers secours, Soins partiels,
     Soins complets at full HP; Multisoin at full health) and stays played when the spell is useful (twice for a heal on one target, once per target for Multisoin); a useful heal after a useless one plays its sound effect again."""
import os, struct, sys, tempfile, types, unittest

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), '..'))
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import _saves as SV
import pyglet
if sys.platform.startswith('linux') and not os.environ.get('DISPLAY'): pyglet.options['headless'] = True; pyglet.options['shadow_window'] = False
from dq4_pc.menus import ui_menu as UM
import _text_render as TR          # (test helper: the real Render._text without GL)
PAD_SLACK = 4.5                    # a quad overflows the texture margin (2 px on each side): ink = width - 4

APK, SAVES = os.environ.get('DQ_APK'), os.environ.get('DQ_SAVES')


def list_type():
    """Minimal Make_NameButton: the root then 6 rows (parts[1 + k], button k, y coordinate 382 - 67 k) with one child text each."""
    square = {'vtx': [[-100.0, 10.0], [100.0, 10.0], [100.0, -10.0], [-100.0, -10.0]], 'uv': [[0, 0], [1, 0], [1, 1], [0, 1]], 'sub': {'0': [0, 1, 2, 0, 2, 3]}}
    nodes = [{'id': 1, 'par': None, 'pos': [0.0, 0.0, 0.0], 'act': True, 'mats': []}]; parts = [{'node': 1, 'ib': []}]
    for k in range(6):
        z = 382.0 - 67.0 * k
        nodes.append({'id': 100 + k, 'par': 1, 'pos': [0.0, 4.0, z], 'act': True, 'mats': [{'sheet': 1, 'part': 7, 'color': [1, 1, 1, 1], 'shader': 'parts', 'offset': None}], 'mesh': square, 'parts': {'buttonId': k, 'gamepad': 16}})
        nodes.append({'id': 200 + k, 'par': 100 + k, 'pos': [0.0, 8.0, z - 5.0], 'act': True, 'text': {'font': 'font', 'characterSize': 10.0, 'text': None}, 'mats': []})
        parts.append({'node': 100 + k, 'ib': [{'k': 'button'}, {'k': 'text', 'go': 200 + k, 'variant': 0}]})
    nodes.append({'id': 300, 'par': 100, 'pos': [20.0, 12.0, 340.0], 'act': True, 'text': {'font': 'font', 'characterSize': 6.63, 'text': None, 'anchor': 3, 'alignment': 0, 'lineSpacing': 0.84, 'tabSize': 8.0}, 'mats': []})      # cost line of row 0
    nodes.append({'id': 301, 'par': 100, 'pos': [20.0, 12.0, 340.0], 'act': True, 'text': {'font': 'font', 'characterSize': 6.63, 'text': None, 'anchor': 3, 'alignment': 0, 'lineSpacing': 0.84}, 'mats': []})              # same anchoring, no tabSize
    return {'name': 'Make_NameButton()', 'err': None, 'nodes': nodes, 'parts': parts,
            'params': [{'id': k, 'no': 0, 'parts': 1 + k, 'base': 0} for k in range(6)], 'builds': [],
            'codes': [{'id': k, 'kind': 'func', 'method': 'Sub_NameButton', 'fx': {'-1': {'err': None, 'd': {}}, '0': {'err': None, 'd': {str(100 + k): {'act': False}}}, '1': {'err': None, 'd': {}}, '2': {'err': None, 'd': {}}}} for k in range(5)]}


def window():
    ml = types.SimpleNamespace(types={'8': list_type()}, info=[], borders=[], hdr={'lang': {'hiro': 1.0}}, pushed=(0.0, 0.0))
    return UM.Window(ml, 8)


def zones(wnd): return sorted(b[0] for b in wnd.buttons())
def z_row(wnd, k): return wnd.N[100 + k]['pos'][2]


class TestNameEntries(unittest.TestCase):
    def test_exported_presets(self):
        """The engine's 5 presets (NAME_BUTTON_Y / NAME_BUTTON_DY): number of rows, y coordinate of the first, step."""
        self.assertEqual(UM.NAMES_PRESETS[0], (4, 382.0, 67.0)); self.assertEqual(UM.NAMES_PRESETS[1], (5, 382.0, 67.0)); self.assertEqual(len(UM.NAMES_PRESETS), 5)
        self.assertEqual((UM.NAMES_START, UM.NAMES_STEP), (382.0, 67.0))

    def test_spell_entries_one_row(self):
        """Doc knows one spell: codes 0 = 2 (two lines), 1 to 3 = 0, code 6 = 0. Only row 0 is a touch area (the 5th, a ghost, led to <ERR 0x07000000.0>)."""
        wnd = window()
        self.assertEqual(zones(wnd), [0, 1, 2, 3, 4, 5], 'before code 6: everything is visible (exported state)')
        for i, v in ((0, 2), (1, 0), (2, 0), (3, 0), (6, 0)): wnd.code(i, v)
        self.assertEqual(zones(wnd), [0])
        for k in range(1, 6): self.assertFalse(wnd.N[100 + k]['act'], k)

    def test_spell_entries_four_rows(self):
        wnd = window()
        wnd.code(6, 0)
        for i in range(4): wnd.code(i, 2)
        self.assertEqual(zones(wnd), [0, 1, 2, 3])                          # 4 rows at most: neither the 5th nor the 6th
        wnd.code(2, 0)
        self.assertEqual(zones(wnd), [0, 1, 3])

    def test_code_6_before_or_after_row_codes(self):
        wnd = window()
        for i, v in ((0, 1), (1, 0), (2, 0), (3, 0), (4, 0)): wnd.code(i, v)           # replay of a window: the row codes first
        wnd.code(6, 1)
        self.assertEqual(zones(wnd), [0])
        fe2 = window(); fe2.code(6, 1)
        for i, v in ((0, 1), (1, 1), (2, 1), (3, 0), (4, 0)): fe2.code(i, v)
        self.assertEqual(zones(fe2), [0, 1, 2])                            # "Utiliser / Transferer / Abandonner" menu: preset 1, three rows

    def test_preset_positions(self):
        wnd = window()
        base = [z_row(wnd, k) for k in range(6)]
        for preset, (num, initial, step) in enumerate(UM.NAMES_PRESETS):
            wnd.code(6, preset)
            for k in range(6):
                self.assertAlmostEqual(z_row(wnd, k), base[k] + (initial - step * k) - (382.0 - 67.0 * k), msg=(preset, k))
                self.assertAlmostEqual(wnd.N[200 + k]['pos'][2], base[k] - 5.0 + (initial - step * k) - (382.0 - 67.0 * k), msg=('texte', preset, k))      # the text follows its plate
        wnd.code(6, 0)
        self.assertEqual([z_row(wnd, k) for k in range(6)], base)        # back to preset 0: everything is put back in place

    def test_no_double_offset(self):
        wnd = window(); wnd.code(6, 2); a = [z_row(wnd, k) for k in range(6)]
        wnd.code(6, 2); wnd.code(6, 2)
        self.assertEqual([z_row(wnd, k) for k in range(6)], a)

    def test_unknown_preset_ignored(self):
        wnd = window(); before = [(z_row(wnd, k), wnd.N[100 + k]['act']) for k in range(6)]
        for c in (-1, 5, 99, None, 'x', 1.5): wnd.code(6, c)
        self.assertEqual([(z_row(wnd, k), wnd.N[100 + k]['act']) for k in range(6)], before)


class TestCostLine(unittest.TestCase):
    """"Cout en PM:<tab>  2": TextMesh.tabSize (8) turns the tab into 8 spaces; the game's font has no glyph for the tab (zero width) and the number stuck to the label instead of being in the right-hand column."""
    def test_cost_line_tab(self):
        wnd = window()
        wnd.params[(0, 1)] = {'id': 0, 'no': 1, 'parts': 1, 'base': 2}
        wnd.parts[1]['ib'].append({'k': 'text', 'go': 300, 'variant': 0})
        self.assertEqual(wnd.N[300]['text'].get('tabSize'), 8.0)
        wnd.param_str(0, 1, 'Coût en PM:\t  2')
        self.assertEqual(wnd.N[300]['text']['text'], 'Coût en PM:' + ' ' * 8 + '  2')
        wnd.param_str(0, 1, 'Coût en PM:\t 10')
        self.assertEqual(wnd.N[300]['text']['text'], 'Coût en PM:' + ' ' * 8 + ' 10')           # the number field keeps its width: the column stays aligned

    def test_text_without_tab_unchanged(self):
        wnd = window()
        wnd.params[(0, 1)] = {'id': 0, 'no': 1, 'parts': 1, 'base': 2}
        wnd.parts[1]['ib'].append({'k': 'text', 'go': 300, 'variant': 0})
        wnd.param_str(0, 1, 'Premiers secours'); self.assertEqual(wnd.N[300]['text']['text'], 'Premiers secours')

    def test_without_tabsize_the_tab_remains(self):
        wnd = window()                                                     # text 301 has no tabSize: nothing is replaced
        wnd.params[(0, 1)] = {'id': 0, 'no': 1, 'parts': 1, 'base': 2}
        wnd.parts[1]['ib'].append({'k': 'text', 'go': 301, 'variant': 0})
        wnd.param_str(0, 1, 'a\tb'); self.assertEqual(wnd.N[301]['text']['text'], 'a\tb')


@unittest.skipUnless(os.path.exists(os.path.join(TR.CACHE, 'ui_layout.json')) and TR.real_font() is not None, 'real layout and font: interface cache (DQ_UI_CACHE: ui_layout.json, ui_garrir.json / .png)')
class TestFrenchSpellTexts(unittest.TestCase):
    """French spell texts in their frames (let them overflow as on mobile): the "Cout en PM 2/ 30" line of the info panels (field, type 7, and battle, type 38) is compressed to fit its frame (right edge 214, at most x0.7);
    the "Cout en PM:<tab> 2" line of the lists (field, type 8, and battle, type 35) is set against the right edge of its button and raised by 4 units (the game's ink touched the bottom edge of the button); the description is re-wrapped to 2 lines (tests/test_item_description.py)."""
    @classmethod
    def setUpClass(cls):
        cls.ml = UM.PageLayout(os.path.join(TR.CACHE, 'ui_layout.json')); cls.font = TR.real_font(); cls.r = TR.render(cls.font, ml=cls.ml)

    def cell(self, typ, port, no, text, unraised=False):
        wnd = UM.Window(self.ml, typ); pt, ib = wnd._ib(wnd.params[(port, no)]); wnd.param_str(port, no, text); node = wnd.N[ib['go']]
        if unraised: node.pop('raise', None); node.pop('in_plate', None)
        return wnd, node, TR.draw(wnd, node, r=self.r)

    def test_cost_line_of_the_cards_fits_its_frame(self):
        for typ, port, no in ((7, 0, 2), (38, 2, 4)):
            for text in ('Coût en PM  2/ 30', 'Coût en PM  10/ 30', 'Coût en PM  2/  0'):
                wnd, node, quads = self.cell(typ, port, no, text)
                self.assertEqual(node['fit_x'], UM.CARD_COST_X_MAX); self.assertEqual(node['text']['text'], text)
                for q in quads: self.assertLessEqual(q.x + q.width, UM.CARD_COST_X_MAX + PAD_SLACK, (typ, text)); self.assertGreaterEqual(q.ts, UM.COMPRESSION_MIN - 1e-6)
            self.assertLess(self.cell(typ, port, no, 'Coût en PM  2/ 30')[2][0].ts, 1.0)                                      # longer than the frame: compressed
            self.assertAlmostEqual(self.cell(typ, port, no, 'PM 2')[2][0].ts, 1.0, places=5)                                   # a text that fits is left untouched

    def test_cost_of_the_lists_is_inside_its_button(self):
        """The field's list (type 8): the cost line in its button. The battle's (type 35) keeps the game's place: see test_battle_cost_at_the_game_place."""
        for typ, rows in ((8, 4),):
            for row in range(rows):
                for text in ('Coût en PM:\t  2', 'Coût en PM:\t 10', 'Coût en PM:\t100'):
                    wnd, node, quads = self.cell(typ, row, 1, text)
                    left, right = self.r._plate_x(wnd, node, node['pos'][2] - self.ml.hdr['lang']['dy'])
                    self.assertTrue(node['in_plate']); self.assertEqual(node['raise'], 4.0)
                    for q in quads: self.assertGreaterEqual(q.x, left, (typ, row, text)); self.assertLessEqual(q.x + q.width, right + PAD_SLACK, (typ, row, text)); self.assertAlmostEqual(q.ts, 1.0, places=5)     # neither compressed nor outside the button

    def test_lists_without_costs(self):
        """(replaces for battle): the battle spell list shows no cost line (the spell's panel gives it), its names are centered in their plate; the field's list too (replaces for the field: the spell's panel, type 7, gives the cost)."""
        for typ, rows in ((35, range(4)), (8, range(4))):
            for row in rows:
                wnd, node, quads = self.cell(typ, row, 1, 'Coût en PM:\t 10')
                self.assertTrue(node.get('mute'), typ); self.assertEqual(quads, [])
                wnd, name, quads = self.cell(typ, row, 0, 'Glace'); self.assertTrue(name.get('ink_center'), typ); self.assertEqual(len(quads), 1)
                bottom, top = self.r._plate_z(wnd, name, name['pos'][2] - self.ml.hdr['lang']['dy'])
                cap = self.font.bm.cap_height() * name['text']['characterSize'] * 0.1
                self.assertAlmostEqual(quads[0].base + cap / 2, (bottom + top) / 2, delta=0.5, msg=typ)                                   # (the middle of the capitals at the middle of the plate)



def _hp(c, base, v):
    """Resolves a hit point request: an integer as is, 'max' = the character's max HP, 'hurt' = 5 less (the max HP come from the player's save and change when the character levels up: no more hard-coded 47)."""
    if isinstance(v, int): return v
    top = struct.unpack_from('<H', c.mem(base + 0x24, 2))[0]
    return top if v == 'max' else max(1, top - 5)


def _stat(eng, i):
    return struct.unpack_from('<4H', eng.core.mem(eng.core.export('_ZN6status9PartyData15originalPlayer_E') + 0x530 * i + 0x58, 0x30), 0x22)          # HP, max HP, MP, max MP


@unittest.skipUnless(APK and SAVES, 'real engine: DQ_APK=<folder of the patched APKs> DQ_SAVES=<folder of the saves>')
class RealEngine(unittest.TestCase):
    RAGNAR, DOC = 3, 12                                                   # PlayerStatus slots in originalPlayer_ (the registry of all the game's characters: it does not depend on the save)
    FIRST_AID, REVIVE, ANTIDOTE = 196, 200, 202                   # action identifiers of the field spells
    MULTIHEAL, EVAC, SAFE_PASSAGE, MAPPILLE, WHISTLE = 199, 204, 206, 209, 216          # (Multiheal: 10 MP, no target; Evac': 1 MP; Safe passage: 2 MP; map and whistle spells: 0 MP)
    BTN_MENU, BTN_TALK = 0x800, 0x100

    def advance(self, eng, n, decl=0):
        for i in range(n): eng.step(0, decl if i == 0 else 0)

    def ready(self, sort=None, hit_points=None, mp=30, poison=False):
        from dq4_pc.core import engine as ENGINE
        eng = ENGINE.Engine(APK, SAVES, tempfile.mkdtemp(prefix='sv_magie_')); eng.load_save(1); self.advance(eng, 120)
        for _ in range(30):                                                # the opening dialogue must be closed and the player free
            self.advance(eng, 1, self.BTN_TALK); self.advance(eng, 20)
            if not eng.msg_visible and not (eng.flags() & 4): break
        self.advance(eng, 30); c = eng.core
        SV.force_party(eng, self.RAGNAR, self.DOC)                        # the party comes from the player's save: we impose it, otherwise row 3 of the list is no longer Doc
        orig = c.export('_ZN6status9PartyData15originalPlayer_E'); hs = lambda i: orig + 0x530 * i + 0x58
        if sort is not None:
            ha = orig + 0x530 * self.DOC + 0xd0
            c.call(c.export('_ZN6status10HaveAction5clearEv'), ha); c.call(c.export('_ZN6status10HaveAction3addEii'), ha, sort, 0)
        c.mem_w(hs(self.DOC) + 0x26, struct.pack('<H', mp))
        for i, v in (hit_points or {}).items(): c.mem_w(hs(i) + 0x22, struct.pack('<H', _hp(c, hs(i), v)))
        if poison: c.call(c.export('_ZN6status14HaveStatusInfo9setPoisonEv'), hs(self.RAGNAR) - 0x48)          # HaveStatusInfo = HaveStatus - 0x48
        eng.sensor.drain()
        return eng

    def open_list(self, eng):
        self.advance(eng, 1, self.BTN_MENU); self.advance(eng, 20)
        eng.send_menu(4, 1, 1, 0x10); self.advance(eng, 20)               # root menu: "Magie"
        eng.send_menu(5, 1, 3, 0x10); self.advance(eng, 25)               # character list: Doc

    def launch(self, eng, target=0):
        self.open_list(eng)
        eng.send_menu(8, 1, 0, 0x10); self.advance(eng, 20)               # the spell of row 0
        eng.send_menu(6, 1, target, 0x10); self.advance(eng, 3)            # the target
        return self.messages(eng)

    def launch_group(self, eng):
        """Group spell or spell with no target: the spell info panel (port 8, "Lancer" button = row 2), no target choice."""
        self.open_list(eng)
        eng.send_menu(8, 1, 0, 0x10); self.advance(eng, 20)
        self.assertEqual(eng.ui.f[8]['cells'].get((2, 0)), 'Lancer')
        eng.send_menu(8, 1, 2, 0x10); self.advance(eng, 3)
        return self.messages(eng)

    def messages(self, eng):
        texts = []
        for k in range(500):
            self.advance(eng, 1)
            for t in (x['text'] for x in eng.sensor.drain()):
                if not texts or texts[-1] != t: texts.append(t)
            if eng.msg_visible and k % 30 == 29: self.advance(eng, 1, self.BTN_TALK)
            if not eng.msg_visible and k > 60: break
        return [t.replace('\xa0', ' ').replace(';', '').strip() for t in texts]

    LAUNCH, HEAL_SFX = 306, 501                                              # SoundManager::playSe: cast sound effect (all spells); heal sound effect

    def sounds(self, eng):
        """List (filled as it goes) of the `SoundManager::playSe` sound effects played by the engine from now on; sound effect 300 (confirming a key in the messages) is discarded."""
        import unicorn
        c = eng.core; entries = []; a = c.export('_ZN12SoundManager6playSeEi')
        c.uc.hook_add(unicorn.UC_HOOK_CODE, lambda uc, ad, sz, u: entries.append(uc.reg_read(c.XREG[0]) & 0xffffffff), None, a, a); c.uc.ctl_flush_tb()
        return entries

    def sound_effects(self, sort, hit_points, group=False):
        eng = self.ready(sort=sort, hit_points=hit_points); sounds = self.sounds(eng)
        texts = self.launch_group(eng) if group else self.launch(eng)
        return texts, [x for x in sounds if x != 300]

    def test_heal_sfx_without_effect(self):
        for sort in (self.FIRST_AID, self.FIRST_AID + 1, self.FIRST_AID + 2):
            texts, sounds = self.sound_effects(sort, {self.RAGNAR: 'max'})
            self.assertEqual(texts[-1], 'Mais il ne se passe rien.'); self.assertEqual(sounds, [self.LAUNCH], 'spell %d: the cast stays, the healing sound effect is cut' % sort)

    def test_useful_heal_sfx_kept(self):
        for sort in (self.FIRST_AID, self.FIRST_AID + 1, self.FIRST_AID + 2):
            texts, sounds = self.sound_effects(sort, {self.RAGNAR: 'hurt'})
            self.assertIn('Les blessures de Ragnar guérissent !', texts); self.assertEqual(sounds, [self.LAUNCH, self.HEAL_SFX, self.HEAL_SFX], 'sort %d' % sort)

    def test_group_heal_sfx(self):
        texts, sounds = self.sound_effects(self.MULTIHEAL, {self.RAGNAR: 'max', self.DOC: 'max'}, group=True)
        self.assertEqual(texts[-1], 'Mais il ne se passe rien.'); self.assertEqual(sounds, [self.LAUNCH])
        texts, sounds = self.sound_effects(self.MULTIHEAL, {self.RAGNAR: 'hurt', self.DOC: 'max'}, group=True)
        self.assertEqual(sounds, [self.LAUNCH, self.HEAL_SFX, self.HEAL_SFX], 'un bruitage de soin par cible soignee')

    def test_heal_sfx_returns_after_failure(self):
        eng = self.ready(hit_points={self.RAGNAR: 'max'}); sounds = self.sounds(eng)
        self.launch(eng); self.assertEqual([x for x in sounds if x != 300], [self.LAUNCH])
        c = eng.core; orig = c.export('_ZN6status9PartyData15originalPlayer_E'); c.mem_w(orig + 0x530 * self.RAGNAR + 0x58 + 0x22, struct.pack('<H', _hp(c, orig + 0x530 * self.RAGNAR + 0x58, 'hurt')))
        self.advance(eng, 60); del sounds[:]
        texts = self.launch(eng)
        self.assertIn('Les blessures de Ragnar guérissent !', texts); self.assertEqual([x for x in sounds if x != 300], [self.LAUNCH, self.HEAL_SFX, self.HEAL_SFX])

    def test_doc_entries(self):
        eng = self.ready(); self.open_list(eng)
        f = eng.ui.f[8]
        self.assertEqual(f['type'], 8)
        self.assertEqual(f['cells'][(0, 0)], 'Premiers secours'); self.assertTrue(f['cells'][(0, 1)].startswith('Coût en PM'))
        self.assertEqual([f['indicators'].get(i) for i in (0, 1, 2, 3, 6)], [2, 0, 0, 0, 0])      # row 0 on two lines, 1 to 3 hidden, preset 0

    def test_heal_on_wounded(self):
        eng = self.ready(hit_points={self.RAGNAR: 'hurt'}); texts = self.launch(eng)
        self.assertEqual(_stat(eng, self.RAGNAR)[0], _stat(eng, self.RAGNAR)[1], 'the HP are restored to the maximum'); self.assertEqual(_stat(eng, self.DOC)[2], 28)
        self.assertIn('Les blessures de Ragnar guérissent !', texts)

    def test_heal_on_full_hp_spends_no_mp(self):
        eng = self.ready(hit_points={self.RAGNAR: 'max'}); texts = self.launch(eng)
        self.assertEqual(_stat(eng, self.DOC)[2], 30, 'the engine spends no MP when the healing was useless')
        self.assertEqual(_stat(eng, self.RAGNAR)[0], _stat(eng, self.RAGNAR)[1])
        self.assertEqual(texts, ['Doc lance le sort Premiers secours !', 'Mais il ne se passe rien.'])          # the official Evac' message (id 0xc3d6d), not "Les blessures de Ragnar guérissent !"

    def test_insufficient_mp(self):
        eng = self.ready(hit_points={self.RAGNAR: 'hurt'}, mp=1); texts = self.launch(eng)
        self.assertEqual(texts, ['Pas assez de PM !'])
        self.assertEqual(_stat(eng, self.DOC)[2], 1); self.assertLess(_stat(eng, self.RAGNAR)[0], _stat(eng, self.RAGNAR)[1], 'the wounded one is not healed')

    def test_revive_spell_on_living(self):
        eng = self.ready(sort=self.REVIVE, hit_points={self.RAGNAR: 'max'}); texts = self.launch(eng)
        self.assertEqual(texts[-1], 'Mais rien ne se passe.'); self.assertEqual(_stat(eng, self.DOC)[2], 30)

    def spell_on(self, sort, hit_points, group=False, **kw):
        eng = self.ready(sort=sort, hit_points=hit_points, **kw); pm0 = _stat(eng, self.DOC)[2]
        texts = self.launch_group(eng) if group else self.launch(eng)
        return eng, texts, pm0, _stat(eng, self.DOC)[2]

    def test_heals_at_full_hp_all_powers(self):
        for sort, name_str in ((self.FIRST_AID + 1, 'Soins partiels'), (self.FIRST_AID + 2, 'Soins complets')):
            eng, texts, pm0, pm1 = self.spell_on(sort, {self.RAGNAR: 'max'})
            self.assertEqual(texts, ['Doc lance le sort %s !' % name_str, 'Mais il ne se passe rien.']); self.assertEqual((pm0, pm1), (30, 30), name_str)

    def test_group_heal_at_full_health(self):
        eng, texts, pm0, pm1 = self.spell_on(self.MULTIHEAL, {self.RAGNAR: 'max', self.DOC: 'max'}, group=True)
        self.assertEqual(texts, ['Doc lance le sort Multisoin !', 'Mais il ne se passe rien.'], 'only once, not once per character'); self.assertEqual((pm0, pm1), (30, 30))
        self.assertEqual(eng.core.mem(eng.L + 0x257f84, 1)[0], 0, 'no more healing sound effect pending (the engine plays one per remaining target)')

    def test_group_heal_with_wounded_member_keeps_messages_and_mp(self):
        eng, texts, pm0, pm1 = self.spell_on(self.MULTIHEAL, {self.RAGNAR: 'hurt', self.DOC: 'max'}, group=True)
        self.assertEqual(texts, ['Doc lance le sort Multisoin !', 'Les blessures de Ragnar guérissent !', 'Les blessures de Doc guérissent !']); self.assertEqual((pm0, pm1), (30, 20))
        self.assertEqual(_stat(eng, self.RAGNAR)[0], _stat(eng, self.RAGNAR)[1], 'the wounded one is healed')

    def test_spell_with_effect_but_no_result_message_spends_its_mp(self):
        eng, texts, pm0, pm1 = self.spell_on(self.SAFE_PASSAGE, {self.RAGNAR: 'max'}, group=True)
        self.assertEqual(texts, ['Doc lance le sort Passage sûr !']); self.assertEqual((pm0, pm1), (30, 28))

    def test_game_own_failure_message_kept(self):
        eng, texts, pm0, pm1 = self.spell_on(self.EVAC, {self.RAGNAR: 'max'}, group=True)                       # Evac' in Strattbourg: the game has its own message ("Mais il ne se passe rien.")
        self.assertEqual(texts, ["Doc lance le sort Évac' !", 'Mais il ne se passe rien.']); self.assertEqual((pm0, pm1), (30, 30))

    def test_zero_mp_spells_not_concerned(self):
        for sort, last in ((self.MAPPILLE, "Mais il n'a pas une bonne visibilité."), (self.WHISTLE, 'Mais rien ne se passe.')):
            eng, texts, pm0, pm1 = self.spell_on(sort, {self.RAGNAR: 'max'}, group=True)
            self.assertEqual(texts[-1], last, texts); self.assertEqual((pm0, pm1), (30, 30)); self.assertEqual(len(texts), 2, texts)

    def test_antidote_without_poison(self):
        eng = self.ready(sort=self.ANTIDOTE); texts = self.launch(eng)
        self.assertEqual(texts[-1], 'Mais rien ne se passe.'); self.assertEqual(_stat(eng, self.DOC)[2], 30)

    def test_antidote_on_poisoned(self):
        eng = self.ready(sort=self.ANTIDOTE, poison=True); texts = self.launch(eng)
        self.assertEqual(texts[-1], "Ragnar n'est plus empoisonné !"); self.assertEqual(_stat(eng, self.DOC)[2], 28)

    def test_revive_spell_on_dead(self):
        """Rappel on a dead character: the spell SUCCEEDS OR FAILS at random (the engine rolls), but in both cases it was used, so **the MP are spent** (30 -> 22):
        this is the counterexample to the rule "a spell with no effect spends no MP". So the test does not bet on the roll (before, the test expected success)."""
        eng = self.ready(sort=self.REVIVE, hit_points={self.RAGNAR: 0}); texts = self.launch(eng)
        self.assertIn(texts[-1], ('Ragnar revient à la vie !', 'Ragnar ne revient pas à la vie.'), texts)
        self.assertEqual(_stat(eng, self.DOC)[2], 22, 'the MP are spent, whether the revive succeeds or not')
        if texts[-1].endswith('vie !'): self.assertGreater(_stat(eng, self.RAGNAR)[0], 0)


if __name__ == '__main__':
    unittest.main()
