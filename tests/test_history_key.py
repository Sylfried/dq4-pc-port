"""History favorites (dialogue history) stored by the message KEY: the favorites file keeps the message's number in the game files ("b0802000#199"), not its text; the text is
requested again from the engine (TextAPI::extractText), so a message modified in the patch also changes in the favorites.

  1. pure functions: `message_key`, `value_list` (the game's "[NONE 1,0]" variables), `binding` (whole message or page separated by ㈡), `linked_text`;
  2. `History` with a fake engine: the favorite is stored by key only if the files' text gives back EXACTLY what was read; otherwise it keeps its text (as before); the file then contains no text;
     read again with another text in the files, the favorite shows the new text; message gone: a line says so with the key; old files (with "texte") and invalid entries;
  3. `Sensor` (fake emulator): the number comes from ui_MsgAdd, only when TextBuffer::cat is called directly; `Sensor.model` queries TextAPI::extractText (kind 1);
  4. with the real engine (if DQ_APK and DQ_SAVES are given): the numbers captured during the prologue, a favorite stored by key then read again in a second engine, a modified text that is reflected.

    python3 tests/test_history_key.py
"""
import json, os, shutil, sys, tempfile, types, unittest

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), '..'))
from dq456_pc import language as LG
LG.select_language('fr')          # (the expectations of this test are in French, whatever the language of the computer)
from dq456_pc.core import history as HI

RAW_SIMPLE = "Il était une fois, dans un pays lointain.\n"
RAW_PAGES = "*: Vous êtes née dans cette ville, n'est-ce pas\xa0?\nIl ne manquerait plus que je vous fasse\npayer.\n㈡\n*: Alors, vous restez\xa0?\n"
RAW_VAR = "*: Je vais vous prendre [NONE 10,0]. Je peux vous en donner [NONE 62,0] pièces d'or.\n"


ADVENTURE = '0123456789ab'          # (favorites belong to the adventure being played)


class FakeSensor:
    """Fake sensor: `files` = {number: text of the game files}; `calls` = numbers requested."""
    def __init__(self, files): self.active = True; self.files = files; self.calls = []; self.output = []
    def drain(self): return []
    def model(self, mid): self.calls.append(mid); return self.files.get(mid)


class FakeEngine:
    def __init__(self, cap): self.sensor = cap; self.state = types.SimpleNamespace(part=0xc, game_map='x'); self.ui = types.SimpleNamespace(msg={'feed': False}); self.msg_visible = True


class Clock:
    def __call__(self): return 1000.0


class TestPureFunctions(unittest.TestCase):
    def test_message_key(self):
        self.assertEqual(HI.message_key(802199), 'b0802000#199')
        self.assertEqual(HI.message_key(2002), 'b0002000#2')
        self.assertEqual(HI.message_key(1004957), 'b1004000#957')
        self.assertEqual(HI.message_key(1000), 'b0001000#0')

    def test_identical_text_values(self):
        self.assertEqual(HI.value_list(RAW_SIMPLE, HI.clean(RAW_SIMPLE)), {})
        self.assertIsNone(HI.value_list(RAW_SIMPLE, 'Autre texte.'))

    def test_variable_values_replaced(self):
        read_value = "*: Je vais vous prendre Ragnar. Je peux vous en donner 120 pièces d'or."
        self.assertEqual(HI.value_list(RAW_VAR, read_value), {'[NONE 10,0]': 'Ragnar', '[NONE 62,0]': '120'})
        self.assertEqual(HI.value_list(RAW_VAR, HI.clean(RAW_VAR)), {})                                  # (variables left untouched by the game: nothing to remember)
        self.assertIsNone(HI.value_list(RAW_VAR, "*: Je vais vous prendre Ragnar. Je peux autre chose."))     # the surrounding text changed: not this message
        self.assertIsNone(HI.value_list("[NONE 1,0] et [NONE 1,0]", 'Ragnar et Alena'))                       # (same variable, two values: rejected)
        self.assertEqual(HI.value_list("[NONE 1,0] et [NONE 1,0]", 'Ragnar et Ragnar'), {'[NONE 1,0]': 'Ragnar'})

    def test_variable_on_several_lines_or_with_semicolon(self):
        self.assertEqual(HI.value_list("Bonjour [NONE 1,0] !\n", 'Bonjour Maître\nZoom !'), {'[NONE 1,0]': 'Maître\nZoom'})
        self.assertEqual(HI.value_list("Il trouve [NONE 3,0].", "Il trouve l'herbe médicinale."), {'[NONE 3,0]': "l'herbe médicinale"})        # (the patch's ";" is already removed from the text read)

    def test_binding_whole_message(self):
        self.assertEqual(HI.binding(RAW_SIMPLE, HI.clean(RAW_SIMPLE)), (None, {}))

    def test_binding_page_of_multi_page_message(self):
        pages = RAW_PAGES.split(HI.PAGE)
        self.assertEqual(HI.binding(RAW_PAGES, HI.clean(pages[0])), (0, {}))
        self.assertEqual(HI.binding(RAW_PAGES, HI.clean(pages[1])), (1, {}))
        self.assertEqual(HI.binding(RAW_PAGES, HI.clean(RAW_PAGES)), (None, {}))                      # (the engine can also give the whole message at once)
        self.assertIsNone(HI.binding(RAW_PAGES, 'Nothing to see.'))

    def test_binding_page_with_variable(self):
        raw_value = "Page un.\n㈡\n*: [NONE 1,0] arrive.\n"
        self.assertEqual(HI.binding(raw_value, '*: Alena arrive.'), (1, {'[NONE 1,0]': 'Alena'}))

    def test_linked_text(self):
        self.assertEqual(HI.linked_text(RAW_SIMPLE, None, {}), 'Il était une fois, dans un pays lointain.')
        self.assertEqual(HI.linked_text(RAW_PAGES, 1, {}), "*: Alors, vous restez\xa0?")
        self.assertEqual(HI.linked_text(RAW_PAGES, 0, {}), "*: Vous êtes née dans cette ville, n'est-ce pas\xa0?\nIl ne manquerait plus que je vous fasse\npayer.")
        self.assertEqual(HI.linked_text(RAW_VAR, None, {'[NONE 10,0]': 'Ragnar', '[NONE 62,0]': '120'}), "*: Je vais vous prendre Ragnar. Je peux vous en donner 120 pièces d'or.")
        self.assertEqual(HI.linked_text(RAW_VAR, None, {'[NONE 10,0]': 'Ragnar'}), "*: Je vais vous prendre Ragnar. Je peux vous en donner [NONE 62,0] pièces d'or.")      # unknown variable: left as is
        self.assertEqual(HI.linked_text(RAW_PAGES, 5, {}), '')                                                # no longer this page
        self.assertEqual(HI.linked_text(None, None, {}), '')
        self.assertLessEqual(len(HI.linked_text('x' * 5000, None, {})), HI.MAX_TEXT)

    def test_round_trip_binding_then_text(self):
        for raw_value, read_value in ((RAW_SIMPLE, HI.clean(RAW_SIMPLE)), (RAW_VAR, "*: Je vais vous prendre Ragnar. Je peux vous en donner 120 pièces d'or."), (RAW_PAGES, "*: Alors, vous restez\xa0?")):
            seg, val = HI.binding(raw_value, read_value); self.assertEqual(HI.linked_text(raw_value, seg, val), read_value)


class Base(unittest.TestCase):
    def setUp(self):
        self.folder = tempfile.mkdtemp(prefix='hist_cle_'); self.path = os.path.join(self.folder, 'fav.json')

    def tearDown(self): shutil.rmtree(self.folder, ignore_errors=True)

    def hist(self, files=None, do_update=True):
        h = HI.History(self.path, Clock()); h.set_adventure(ADVENTURE)
        if files is not None:
            h.cap = FakeSensor(files); h.m = FakeEngine(h.cap)
            if do_update: h.do_update(h.m)
        return h

    def fav_file(self): return os.path.join(self.folder, HI.HISTORY_FOLDER, ADVENTURE + '.favorites.json')          # (the favorites of the adventure)

    def file(self):
        with open(self.fav_file(), encoding='utf-8') as f: return json.load(f)

    def raw_value(self):
        with open(self.fav_file(), encoding='utf-8') as f: return f.read()


class TestFavoritesPerKey(Base):
    def test_stored_by_key_without_text(self):
        h = self.hist({2002: RAW_SIMPLE}); e = h.add(HI.clean(RAW_SIMPLE), None, 10, 2002)
        self.assertTrue(h.toggle_favorite(e))
        (d,) = self.file()['favorites']
        self.assertEqual((d['k'], d['mid'], d['name']), ('d', 2002, None)); self.assertNotIn('text', d); self.assertNotIn('s', d); self.assertNotIn('v', d)
        self.assertNotIn('Il était', self.raw_value())                           # (the text is nowhere in the file)

    def test_reread_with_text_modified_in_files(self):
        h = self.hist({2002: RAW_SIMPLE}); h.toggle_favorite(h.add(HI.clean(RAW_SIMPLE), 'Alena', 10, 2002))
        h2 = self.hist({2002: "Il était une autre fois.\n"})
        (f,) = h2.favorites; self.assertEqual((f.text, f.name_str, f.fav), ('Il était une autre fois.', 'Alena', 1))
        h3 = self.hist({2002: RAW_SIMPLE}); self.assertEqual(h3.favorites[0].text, 'Il était une fois, dans un pays lointain.')

    def test_page_and_variables(self):
        h = self.hist({7: RAW_PAGES, 8: RAW_VAR})
        h.toggle_favorite(h.add(HI.clean(RAW_PAGES.split(HI.PAGE)[1]), None, 1, 7))
        h.toggle_favorite(h.add("*: Je vais vous prendre Ragnar. Je peux vous en donner 120 pièces d'or.", None, 2, 8))
        d1, d2 = self.file()['favorites']
        self.assertEqual((d1['mid'], d1['s']), (7, 1)); self.assertEqual((d2['mid'], d2['v']), (8, {'[NONE 10,0]': 'Ragnar', '[NONE 62,0]': '120'}))
        h2 = self.hist({7: RAW_PAGES.replace('restez', 'partez'), 8: RAW_VAR.replace('prendre', 'acheter')})
        self.assertEqual([f.text for f in h2.favorites], ["*: Alors, vous partez\xa0?", "*: Je vais vous acheter Ragnar. Je peux vous en donner 120 pièces d'or."])

    def test_favorite_keeps_its_text_when_files_do_not_return_it(self):
        h = self.hist({2002: RAW_SIMPLE}); e = h.add('A text built by the program.', None, 10, 2002)        # (the number does not match this text)
        h.toggle_favorite(e); (d,) = self.file()['favorites']
        self.assertEqual(d['text'], 'A text built by the program.'); self.assertNotIn('mid', d)

    def test_without_number_or_engine_the_text_is_kept(self):
        h = self.hist({2002: RAW_SIMPLE}); h.toggle_favorite(h.add('No number.', None, 1))
        h2 = self.hist(); h2.toggle_favorite(h2.add(HI.clean(RAW_SIMPLE), None, 2, 2002))             # (no engine: cannot verify)
        self.assertTrue(all('text' in d for d in self.file()['favorites']))

    def test_vanished_message(self):
        h = self.hist({802199: RAW_SIMPLE}); h.toggle_favorite(h.add(HI.clean(RAW_SIMPLE), None, 1, 802199))
        (f,) = self.hist({}).favorites
        self.assertEqual(f.text, '(Message introuvable dans les fichiers du jeu : b0802000#199)')
        self.assertEqual((self.file()['favorites'][0]['mid']), 802199)                                    # (the file keeps the key: it can be found again)
        (f,) = self.hist({802199: RAW_PAGES}).favorites; self.assertTrue(f.text.startswith('*: Vous êtes née'))   # the message is back: the text returns

    def test_vanished_page(self):
        h = self.hist({7: RAW_PAGES}); h.toggle_favorite(h.add('*: Alors, vous restez\xa0?', None, 1, 7))
        (f,) = self.hist({7: RAW_SIMPLE}).favorites; self.assertIn('introuvable', f.text)

    def test_resolved_text_is_never_written(self):
        h = self.hist({2002: RAW_SIMPLE}); h.toggle_favorite(h.add(HI.clean(RAW_SIMPLE), None, 1, 2002))
        h2 = self.hist({2002: 'Nouveau.\n'}); h2.toggle_favorite(h2.add('Autre.', None, 5))              # another favorite: the file is rewritten in full
        d = self.file()['favorites'][0]; self.assertNotIn('text', d); self.assertNotIn('Nouveau', self.raw_value())

    def test_favorite_removal(self):
        h = self.hist({2002: RAW_SIMPLE}); e = h.add(HI.clean(RAW_SIMPLE), None, 1, 2002); h.toggle_favorite(e); self.assertFalse(h.toggle_favorite(e))
        self.assertEqual(self.file()['favorites'], [])

    def test_before_engine_text_waits_then_arrives(self):
        h = self.hist({2002: RAW_SIMPLE}); h.toggle_favorite(h.add(HI.clean(RAW_SIMPLE), None, 1, 2002))
        h2 = self.hist(); (f,) = h2.favorites; self.assertEqual((f.text, f.waiting), ('', True))
        h2.do_update(FakeEngine(FakeSensor({2002: RAW_SIMPLE}))); self.assertEqual((f.text, f.waiting), ('Il était une fois, dans un pays lointain.', False))

    def test_refresh_requests_texts_again(self):
        files = {2002: RAW_SIMPLE}; h = self.hist(files); h.toggle_favorite(h.add(HI.clean(RAW_SIMPLE), None, 1, 2002))
        h2 = self.hist(files); (f,) = h2.favorites; n0 = f.n; num = len(h2.cap.calls); self.assertEqual(f.text, 'Il était une fois, dans un pays lointain.')
        files[2002] = 'Autre.\n'; self.assertEqual(f.text, 'Il était une fois, dans un pays lointain.')            # (nothing changes as long as it is not requested again)
        h2.refresh(); self.assertEqual(f.text, 'Autre.'); self.assertNotEqual(f.n, n0); self.assertEqual(len(h2.cap.calls), num + 1)

    def test_a_number_of_another_kind_is_ignored(self):
        h = self.hist(); self.assertIsNone(h.add('A.', None, 1, 0).mid); self.assertIsNone(h.add('B.', None, 2, -4).mid)
        self.assertIsNone(h.add('C.', None, 3, True).mid); self.assertIsNone(h.add('D.', None, 4, 1 << 24).mid); self.assertEqual(h.add('E.', None, 5, 12).mid, 12)

    def test_crashing_engine(self):
        h = self.hist({2002: RAW_SIMPLE}); h.toggle_favorite(h.add(HI.clean(RAW_SIMPLE), None, 1, 2002))
        h2 = self.hist()
        class BadSensor(FakeSensor):
            def model(self, mid): raise RuntimeError('émulateur')
        h2.do_update(FakeEngine(BadSensor({}))); self.assertIn('introuvable', h2.favorites[0].text)                 # (the game does not stop: the favorite says the text is missing)


class TestFile(Base):
    def write(self, favorites):
        with open(self.path, 'w', encoding='utf-8') as f: json.dump({'version': 2, 'next': 99, 'favorites': favorites}, f)

    def test_old_file_with_text(self):
        self.write([{'k': 'd', 'id': 1, 't': 5, 'name': 'Alena', 'text': 'Un vieux texte.'}])
        (f,) = self.hist({1: 'Autre.\n'}).favorites; self.assertEqual((f.text, f.linked, f.mid), ('Un vieux texte.', False, None))      # (the saved text is authoritative: nothing is requested again)

    def test_invalid_entries_ignored(self):
        good_entries = {'k': 'd', 'id': 1, 't': 5, 'name': None, 'mid': 12}
        self.write([good_entries, {'k': 'd', 'id': 2, 't': 5, 'name': None, 'mid': 'x'}, {'k': 'd', 'id': 3, 't': 5, 'name': None, 'mid': 0}, {'k': 'd', 'id': 4, 't': 5, 'name': None, 'mid': True},
                     {'k': 'd', 'id': 5, 't': 5, 'name': None, 'mid': 12, 's': -1}, {'k': 'd', 'id': 6, 't': 5, 'name': None, 'mid': 12, 'v': {'a': 1}}, {'k': 'd', 'id': 7, 't': 5, 'name': None, 'mid': 1 << 24},
                     {'k': 'd', 'id': 8, 't': 5, 'name': None}, {'k': 'd', 'id': 9, 't': 5, 'name': 3, 'mid': 12}, {'k': 'd', 'id': 10, 't': 5, 'name': None, 'mid': 12, 'v': {'x' * 50: 'y'}}])
        h = HI.History(self.path, Clock()); h.set_adventure(ADVENTURE); self.assertEqual([f.fav for f in h.favorites], [1])

    def test_round_trip_dictionary(self):
        e = HI.Element(1, 'd', 5, 'Alena', '', fav=3, mid=802199, seg=1, val={'[NONE 1,0]': 'Ragnar'}); e.linked = True
        self.assertEqual(e.to_dict(), {'k': 'd', 'id': 3, 't': 5, 'name': 'Alena', 'mid': 802199, 's': 1, 'v': {'[NONE 1,0]': 'Ragnar'}})
        f = HI.Element.from_dict(e.to_dict(), 9); self.assertEqual((f.mid, f.seg, f.val, f.linked, f.waiting, f.name_str), (802199, 1, {'[NONE 1,0]': 'Ragnar'}, True, True, 'Alena'))


class FakeCore:
    """Fake emulator: registers, C strings, memory, function names, calls."""
    XREG = list(range(100, 131)); LIB_BASE = 0

    def __init__(self, strings=None, memory=None, names=None, exports=None, engine_text=None):
        self.strings = strings or {}; self.memory = memory or {}; self.names = names or {}; self.exports = exports or {}; self.engine_text = engine_text or {}; self.calls = []; self.buffer = 0x5000
    def read_cstr(self, a): return self.strings[a] if a in self.strings else self.memory.get(('s', a), b'')
    def mem(self, a, n): return self.memory[a][:n]
    def where(self, a): return self.names.get(a, '?+0')
    def export(self, name_str): return self.exports.get(name_str)
    def malloc(self, n): return self.buffer
    def scratch(self, name_str, n): return self.malloc(n)          # (Core.scratch keeps the buffer; one is enough here)
    def mem_w(self, a, b): self.memory[('s', a)] = b''
    def call(self, f, buffer, ident, label='', timeout_s=0):
        self.calls.append((f, buffer, ident)); self.memory[('s', buffer)] = self.engine_text.get(ident, ('<ERR 0x%08x.%d>' % (ident & 0xff000000, ident & 0xffffff)).encode())


class TestSensor(unittest.TestCase):
    def sensor(self, stack, mid=802199, text='Bonjour.'):
        names, memory, fp = {0x1000: stack[0] + '+8'}, {0x9000 + 4: b'\x05\x00\x00\x00\x42\x00\x00\x00'}, 0x2000
        for i, n in enumerate(stack[1:]):
            memory[fp] = (fp + 0x100).to_bytes(8, 'little') + (0x1100 + i).to_bytes(8, 'little'); names[0x1100 + i] = n + '+4'; fp += 0x100
        memory[fp] = bytes(16)
        c = FakeCore({0x10: text.encode()}, memory, names)
        regs = {c.XREG[0]: 0x100000000 | mid if mid is not None else 0, c.XREG[1]: 0x10, c.XREG[2]: 0, c.XREG[30]: 0x1000, c.XREG[29]: 0x2000}
        cap = HI.Sensor.__new__(HI.Sensor); cap.active = True; cap.output = []; cap.c = c; cap.g_game = 0x9000; cap._mid = None; cap._buffer = None
        cap.m = types.SimpleNamespace(state=types.SimpleNamespace(part=0xc, game_map='caf1'))
        uc = types.SimpleNamespace(reg_read=lambda r: regs[r])
        if mid is not None: cap._add(uc, 0, 0, None)
        cap._cat(uc, 0, 0, None)
        return cap, cap.drain()

    def test_number_captured_when_category_called_by_ui_msgadd(self):
        cap, (r,) = self.sensor((HI.SYM_UI_MSGADD, 'addMessageCount', 'root')); self.assertEqual((r['mid'], r['text']), (802199, 'Bonjour.')); self.assertEqual(cap._mid, 802199)      # (the low 32 bits only)

    def test_no_number_when_category_comes_from_elsewhere(self):
        for stack in (('Foo::bar', HI.SYM_UI_MSGADD, 'root'), ('Foo::bar', 'root')):
            _cap, (r,) = self.sensor(stack); self.assertIsNone(r['mid'], stack)

    def test_old_number_not_reused_without_ui_msgadd(self):
        cap, _ = self.sensor((HI.SYM_UI_MSGADD, 'root'), mid=12)
        c = cap.c; regs = {c.XREG[1]: 0x10, c.XREG[2]: 0, c.XREG[30]: 0x1000, c.XREG[29]: 0x2000}; c.names[0x1000] = 'Foo::bar+8'
        cap._cat(types.SimpleNamespace(reg_read=lambda r: regs[r]), 0, 0, None); self.assertIsNone(cap.drain()[0]['mid'])

    def test_history_receives_the_number(self):
        _cap, rs = self.sensor((HI.SYM_UI_MSGADD, 'root'), mid=2002)
        h = HI.History(None); m = FakeEngine(FakeSensor({})); m.sensor.drain = lambda: rs; h.do_update(m); self.assertEqual([(e.mid, e.text) for e in h.dialogues], [(2002, 'Bonjour.')])

    def test_model(self):
        c = FakeCore(exports={HI.SYM_EXTRACT: 0x777}, engine_text={(1 << 24) | 2002: 'Il était une fois.\n'.encode()})
        cap = HI.Sensor.__new__(HI.Sensor); cap.c = c; cap._buffer = None
        self.assertEqual(cap.model(2002), 'Il était une fois.\n'); self.assertEqual(c.calls[0][0], 0x777); self.assertEqual(c.calls[0][2], (1 << 24) | 2002)      # kind 1: message
        self.assertIsNone(cap.model(5)); self.assertIsNone(cap.model(0)); self.assertIsNone(cap.model(-3)); self.assertIsNone(cap.model('x')); self.assertIsNone(cap.model(1 << 24))      # ("<ERR ... >": unknown)
        cap2 = HI.Sensor.__new__(HI.Sensor); cap2.c = FakeCore(); cap2._buffer = None; self.assertIsNone(cap2.model(2002))                                                        # (symbol absent)


@unittest.skipUnless(os.environ.get('DQ_APK') and os.environ.get('DQ_SAVES'), 'engine: DQ_APK and DQ_SAVES')
class TestRealEngine(unittest.TestCase):
    """The start of a prologue save with the real engine (save 1: messages 2002 to 2011 of file b0002000): numbers captured, favorite stored by key, read again in a second engine."""
    @classmethod
    def setUpClass(cls):
        from dq456_pc.core import engine as ENGINE
        cls.ENGINE = ENGINE; cls.folder = tempfile.mkdtemp(prefix='hist_cle_mo_')

    @classmethod
    def tearDownClass(cls): shutil.rmtree(cls.folder, ignore_errors=True)

    def engine(self): return self.ENGINE.Engine(os.environ['DQ_APK'], os.environ['DQ_SAVES'], tempfile.mkdtemp(dir=self.folder))

    def play(self, path):
        """First save (1 by default, or DQ_SLOT_PROLOGUE, then the others) whose start plays at least 3 dialogues with the A key: (engine, history); None if none."""
        attempts = [int(os.environ['DQ_SLOT_PROLOGUE'])] if os.environ.get('DQ_SLOT_PROLOGUE') else [1, 2, 3, 5, 9]
        for slot in attempts:
            eng = self.engine(); h = HI.History(path)
            for _ in range(3): eng.step(0, 0); h.do_update(eng)
            try:
                if not eng.load_save(slot): continue
            except Exception: continue
            for i in range(1800): eng.step(0, 0x10 if i % 9 == 5 else 0); h.do_update(eng)
            if len(h.dialogues) >= 3: return eng, h
        return None

    def test_end_to_end(self):
        path = os.path.join(self.folder, 'fav.json'); r = self.play(path)
        if r is None: self.skipTest('none of these saves starts with dialogues (DQ_SLOT_PROLOGUE: the number of the prologue save)')
        eng, h = r; self.assertTrue(all(e.mid for e in h.dialogues))
        first = h.dialogues[0]
        self.assertTrue(h.toggle_favorite(first))
        with open(h.path, encoding='utf-8') as f: d = json.load(f)['favorites'][0]                     # (the favorites of the adventure being played)
        self.assertEqual(d['mid'], first.mid); self.assertNotIn('text', d)
        mo2 = self.engine(); h2 = HI.History(path)
        for _ in range(5): mo2.step(0, 0); h2.do_update(mo2)
        h2.set_adventure(h.adventure); h2.do_update(mo2)                                                   # (the same adventure, as when its log is loaded again)
        self.assertEqual(h2.favorites[0].text, first.text)                                               # (the engine gives back the text read)
        actual = mo2.sensor.model; mo2.sensor.model = lambda mid: (actual(mid) or '').replace(first.text[:2], '##') if mid == first.mid else actual(mid)
        h3 = HI.History(path); h3.set_adventure(h.adventure); h3.do_update(mo2); self.assertTrue(h3.favorites[0].text.startswith('##'))     # (a text modified in the patch is reflected)


if __name__ == '__main__':
    unittest.main(verbosity=1)
