"""Language of the port's texts: pages of the Settings menu (Pause), in English and French.

The menu is driven with a fake "game" (see test_pause_pages.py) and actually DRAWN in a hidden pyglet window (headless EGL on Linux); each label requested from the window (`_lbl`) is recorded.
The walkthrough covers all the pages (root, Display, Interface with each of its elements, Sound, Controls, Modifiers, Save states, Quit), all the values of all the lists, the help of each line, the prompts
for capturing a key and entering a value, the title bar tooltip, the confirmation window, the information messages (through their real calls), the names of all the keyboard keys.

    python3 tests/test_pause_language.py

Rules: (1) no catalog key is ever drawn as such (a key on screen = a missing `tr`), in either language; (2) in English, no drawn text is French; (3) every drawn French
text comes from the French catalog (whitelist: words identical in both languages) and its English text is drawn in the English walkthrough; (4) the menu DATA (labels, value
names, key names, messages) hold keys, translated when drawn; (5) no unused key and no empty or identical translation in dq456_pc/texts/*/settings.py; (6) control mutations:
a removed key, a `tr` removed from several places, an emptied translation or one left in French make the check fail."""
import contextlib, inspect, io, os, re, sys, tempfile, textwrap, time, types, unittest

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), '..'))
import _paths
import pyglet
if sys.platform.startswith('linux') and not os.environ.get('DISPLAY'): pyglet.options['headless'] = True; pyglet.options['shadow_window'] = False
import test_pause_pages as TP
import test_language as TL
from dq456_pc import language as LG
from dq456_pc.persistence import settings as RG, savestates as SS, pad_inputs as PI
from dq456_pc.menus import pause as PA
from dq456_pc.persistence import game_rules as GR
from dq456_pc.randomizer import seed as SD
from dq456_pc.texts.fr import settings as FR_SETTINGS
from dq456_pc.texts.en import settings as EN_SETTINGS

K = pyglet.window.key
PAGES = ('root', 'display', 'sound', 'controls', 'difficulty', 'randomizer', 'cheats', 'achievements', 'states', 'quit', 'interface')
# Words identical in French and English, or technical names: drawn as is in both languages, with no catalog entry
# (an identical entry would duplicate those in the other files).
NEUTRAL = {'Interface', 'Casino', 'Menu', 'Normal', 'Dragon', 'Randomizer', 'Action', 'Shader', 'Antialiasing', 'Tab', 'Alt', 'Alt Gr', 'EPX x8', 'Pixel perfect', 'x2', 'x4', 'x8',
           'RS ←', 'RS →', 'RS ↑', 'RS ↓', 'LS ←', 'LS →', 'LS ↑', 'LS ↓', 'Select', 'Start', 'Create', 'Options', 'UnknownWindow'}          # (the fake name that the fake game gives to a window the tool does not know)
_win = []


def window():
    """Hidden pyglet window (drawing the menu needs a GL context); SkipTest if the machine cannot open one."""
    if not _win:
        try: _win.append(pyglet.window.Window(width=1280, height=720, visible=False))
        except Exception as ex: raise unittest.SkipTest('no pyglet window possible: %r' % (ex,))
    return _win[0]


def png(color=(40, 90, 160)):
    from PIL import Image
    b = io.BytesIO(); Image.new('RGB', (64, 36), color).save(b, 'PNG'); return b.getvalue()


class FakeHud:
    taken = None
    def draw_all(self, *a): pass
    def rect(self, n): return (60.0 + 40 * len(n), 120.0, 90.0, 70.0)
    def take(self, *a): pass
    def move_to(self, *a): pass


class FakeGame(TP.FakeGame):
    """The fake game for the pages, with what `draw_all()` asks of it. `seen`: the texts requested from `_lbl`, recorded with the moment of the walkthrough (`moment`)."""
    is_fullscreen = False; mode = 4; res = (1280, 720); helptext = False
    NAMES = {n: [1] for n in PA.WINDOW_NAMES if n not in PA.OWN_INTERFACES}

    def __init__(self, savestates=True):
        super().__init__(); self.post = types.SimpleNamespace(max_msaa=None); self.hud = FakeHud(); self.seen = []; self.moment = 'page'; self.cache_label = {}; self.failure = None
        self.savestates = {1: ({'date': '2026-10-31 19:21:05', 'location': 'settings.world_map'}, png()), 2: ({'date': '2026-11-02 08:05:59', 'location': 'settings.battle'}, png((160, 60, 40))),
                      3: ({'location': 'mak1f1'}, None), 5: ({'date': '2026-11-03 23:59:00', 'location': 'settings.battle'}, None)} if savestates else {}
        self.sound = types.SimpleNamespace(active=True, listening=False, listen=lambda b: None, tick=lambda: None)
    def set_full_screen(self, v): self.is_fullscreen = v
    def resolutions(self): return [(1280, 720), (1920, 1080)]
    def current_resolution(self): return self.res
    def set_resolution(self, v): self.res = v
    def set_mode(self, v): self.mode = v
    def window_names(self): return dict(self.NAMES, UnknownWindow=[1])          # (+ a window unknown to the tool: "Other" group)
    def state_info(self, n): return self.savestates.get(n)
    def state_path(self, n): return os.path.join(tempfile.gettempdir(), 'dq4_test_langue_etat_inexistant_%d' % n)
    def save_state(self, n, thumbnail=b''):
        if self.failure: raise OSError(self.failure)
    def load_state(self, n):
        if self.failure: raise OSError(self.failure)
    def _png_thumbnail(self, t): return b''
    def preview_interface(self, target): return (300.0, 200.0, 700.0, 420.0)
    def new_sample(self): pass
    def set_info(self, v): self.helptext = v
    def quit_game(self): pass
    def back_to_title(self): pass
    def _lbl(self, text, size_value, color=(255, 255, 255, 255), fonts=()):
        self.seen.append((self.moment, text)); window()
        k = (text, round(size_value, 1), color)
        if k not in self.cache_label: self.cache_label[k] = pyglet.text.Label(text, font_size=size_value, color=color, anchor_x='left', anchor_y='baseline')
        return self.cache_label[k]


class PauseSpy(PA.Pause):
    """The menu that records each call of `_helptext_lines`: (raw text received, lines rendered)."""
    def __init__(self, game): super().__init__(game); self.helpers = []
    def _helptext_lines(self, text, maxw, fz):
        ls = super()._helptext_lines(text, maxw, fz); self.helpers.append((text, ls)); return ls


def menu(page, game=None, **attrs):
    J = game or FakeGame(); p = PauseSpy(J); p.opened = True; p.stack = [page]
    for k, v in attrs.items(): setattr(p, k, v)
    return J, p


def draw_page(p):
    window().switch_to(); window().clear(); p.draw_all()


class FrozenClock:
    """The menu's `time` module, whose time no longer moves (the blinking input cursor, the animations: the drawing is the same from one walkthrough to the next)."""
    def __getattr__(self, name_str): return getattr(time, name_str)
    @staticmethod
    def time(): return 1000.0


PAGE_METHODS = {'root': 'root', 'display': 'display', 'sound': 'sound', 'controls': 'commands', 'difficulty': 'difficulty', 'randomizer': 'randomizer', 'cheats': 'cheats', 'achievements': 'achievements', 'states': 'savestates', 'quit': 'quit', 'interface': 'interface'}      # page identifier (string) -> end of the name of the `page_...` method of Visite
PARTS = tuple('page_' + PAGE_METHODS[n] for n in PAGES) + ('messages', 'key_list')


class Visit:
    """The walkthrough of the menu interface in one language: `seen` = [(moment, text)] drawn (moment: page, help, tooltip, message); `helpers` = [(raw text, rendered lines)]. `parts`: the pieces
    of the walkthrough (all by default: the pages, the information messages, the key names)."""
    def __init__(self, language, parts=PARTS):
        self.language = language; self.seen = []; self.helpers = []; clock = PA.time
        LG.select_language(language); PA.time = FrozenClock(); self.catalog = LG.catalog(language)          # (the catalog in force during this walkthrough)
        try:
            for name_str in parts: getattr(self, name_str)()
        finally: LG.select_language('fr'); PA.time = clock

    def note(self, J, p):
        self.seen.extend(J.seen); self.helpers.extend(p.helpers); J.seen.clear(); p.helpers.clear()

    def image(self, J, p, moment='page'):
        J.moment = moment; draw_page(p); J.moment = 'page'; self.note(J, p)

    def lines(self, J, p):
        """The names of all the list values, and the help of each line (like the tooltip: sentences wrapped to the width)."""
        for entry in p._entries():
            if entry['t'] == 'choice':
                for v in entry['vals']: p._label(p._value_name(entry['l'], v), 12.0)
            for name_str in entry.get('notch_names', ()): p._label(name_str, 12.0)          # (a slider with notches: the name of each notch)
        J.moment = 'hint'
        for entry in p._entries():
            text = p._line_helptext(entry)
            if text:
                for l in p._helptext_lines(text, 520.0, 12.0): p._label(l, 12.0)
        J.moment = 'page'; self.note(J, p)

    def page(self, name_str, J=None, **attrs):
        J, p = menu(name_str, J, **attrs); self.image(J, p)
        b = p.has_bar                                                                    # scrolling page: each line goes through the window
        if b:
            d, end = b['base'], b['base'] + b['n'] - b['visible']
            while d < end: d = min(d + b['visible'] - 1, end); p.begin[name_str] = d; self.image(J, p)          # (one page of lines at a time, with one line of overlap)
        self.lines(J, p)
        return J, p

    def page_root(self): self.page('root')
    def page_difficulty(self): self.page('difficulty')
    def page_randomizer(self):
        self.page('randomizer')                                                             # (a game started without the randomizer)
        J = FakeGame(); J.game_rules = GR.GameRules(tempfile.mkdtemp(prefix='rules_lang_')); J.game_rules.rules = {'randomizer': {'seed': SD.new_code(number=1)}}; J.set_clipboard_text = lambda t: None
        J, p = self.page('randomizer', J); p._entries()[0]['ok'](); self.image(J, p, 'message')          # the game's seed, copied
        self.page('root', new_game=True, draft_seed=SD.new_code(number=2))                  # the rules panel of a new game
        self.page('randomizer', new_game=True)                                                # (randomizer mode off: the switch alone)
        J, p = self.page('randomizer', new_game=True, draft_seed=SD.new_code(number=3), randomizer_on=True); p.selected['randomizer'] = 1; p._start_text_entry(); self.image(J, p, 'infobulle')      # typing a seed: its prompt
        p.text('12'); p._end_entry(True); self.image(J, p, 'message')                       # "Invalid seed"
        J, p = menu('root', new_game=True, draft_seed=SD.new_code(number=4)); p.stack = ['root', 'gender']; p._help_zone = lambda *a: None
        self.image(J, p); p.hero_gender = 1; self.image(J, p)                              # the gender page: Masculin chosen, then Féminin (the root's line shows it)
        J.moment = 'hint'; p._helptext_lines(PA.GENDER_HINT, 520.0, 12.0); J.moment = 'page'; self.note(J, p)          # (its help, in the help zone: wrapped like a tooltip's)
        J, p = menu('root', new_game=True, draft_seed=SD.new_code(number=5), hero_gender=0); J.name_entry = types.SimpleNamespace(text='Solo'); self.image(J, p); self.lines(J, p)          # (name and gender chosen: "Start the adventure" active)
    def page_cheats(self): self.page('cheats')
    def page_achievements(self): self.page('achievements')
    def page_quit(self): self.page('quit')

    def page_savestates(self):
        J, p = self.page('states')
        for i in range(0, 5): p.selected['states'] = i; self.image(J, p)                  # each kind of slot: thumbnail and date, date only, nothing, empty ("No thumbnail", "Empty slot")
        p.selected['states'] = 0; p._validate(); self.image(J, p)                               # a slot holding a state: the list of what to do with it (load, create, delete)
        self.page('states', FakeGame(savestates=False))
        for n in (1, 9):
            J, p = menu('states'); p._request_deletion(n); self.image(J, p)          # confirmation window (n = 9: empty slot, no date)
        for language in ('fr', 'en'):                                                    # a state of the game's other language: "Switch the game to French / English to load this state?"
            J, p = menu('states'); J.load_state = lambda n, language=language: (_ for _ in ()).throw(SS.OtherLanguage('abcd', language)); p._load(2); self.image(J, p)

    def page_display(self):
        self.page('display')
        J = FakeGame(); J.reg['msaa'] = 8; J.post.max_msaa = 4; J.is_fullscreen = True; self.page('display', J)          # "Limited to x4..."; resolution grayed out in full screen
        self.lists_and_inputs('display')

    def page_sound(self): self.page('sound'); self.lists_and_inputs('sound')

    def page_commands(self):
        self.page('controls')
        self.page('controls', controls_pad=True)                                                                          # gamepad cells: "Bouton 1 / 2", the "Clavier / Manette" row, "View" (View button)
        J = FakeGame(); J.reg.bind_pad('info', 'PAD_TOUCH'); J.reg.bind_pad('chat', 'PAD_BACK'); self.page('controls', J, controls_pad=True)                     # "Touch pad" (an Xbox controller has no picture for it: its text is drawn)
        for action in ('up', 'accel', 'cam_left'):
            for col in (0, 1):
                for pad in (False, True):
                    J, p = menu('controls'); p.capture = (action, col, pad); self.image(J, p, 'infobulle')                  # "Press the key for..." / "... a gamepad button ..."
        self.lists_and_inputs('controls')

    def lists_and_inputs(self, name_str):
        J, p = menu(name_str); i = next(i for i, x in enumerate(p._entries()) if x['t'] == 'slider'); p.selected[name_str] = i; p.entry = [i, '4']; self.image(J, p, 'infobulle')       # entering a value
        for i, entry in enumerate(p._entries()):                                           # each drop-down list open
            if entry['t'] == 'choice' and entry.get('as_list'):
                J, p = menu(name_str); p.selected[name_str] = i; p.open_dropdown = [i, 0]; self.image(J, p)

    def page_interface(self):
        saved = os.environ.get('DQ_SPEED_ANCHOR')
        try:
            for anchor in ('1', '0'):                                                    # "Put back under the battle box" / "Put back on the left edge"
                os.environ['DQ_SPEED_ANCHOR'] = anchor; self.page('interface', target='speed_button')
        finally:
            if saved is None: os.environ.pop('DQ_SPEED_ANCHOR', None)
            else: os.environ['DQ_SPEED_ANCHOR'] = saved
        for target in ('buttons', 'speed_button', 'vehicle_button', 'msg', 'RootMenu', 'UnknownWindow'):          # (the vehicle button: listed in DQ VI only, its page is the same in every game)
            for mask in (False, True):                                                # hidden: "Hidden" / "Hidden" on the preview
                J = FakeGame(); J.reg['buttons'] = J.reg['speed_button'] = J.reg['vehicle_button'] = J.reg['dpad'] = not mask; J.reg['interface_hidden'] = ['msg', 'RootMenu', 'UnknownWindow'] if mask else []
                self.page('interface', J, target=target)
        J, p = menu('interface'); p.folded = True; self.image(J, p)                       # collapsed panel
        J, p = menu('interface'); p.open_dropdown = [0, 0]; self.image(J, p)                  # "Interface to edit" list open (group subheadings)

    def messages(self):
        """The information messages, through their real calls."""
        J, p = menu('states'); p._save(2); self.image(J, p, 'message')                # "State saved in slot 2."
        J, p = menu('states'); J.failure = 'disque plein'; p._save(2); self.image(J, p, 'message')
        J, p = menu('states'); J.failure = 'disque plein'; p._load(2); self.image(J, p, 'message')
        J, p = menu('states'); p._delete(2); self.image(J, p, 'message')              # (the file does not exist: "Could not delete the state")
        J, p = menu('states'); file = J.state_path(2)
        try:
            open(file, 'w').close(); p._delete(2); self.image(J, p, 'message')       # "State 2 deleted."
        finally:
            if os.path.exists(file): os.remove(file)
        for on_title in (False, True):                                                    # "The game will be reloaded in this language when you return to the title screen." / "... à la fermeture du menu." (the game started in the other language)
            J, p = menu('display'); J.game_language = 'en' if self.language == 'fr' else 'fr'; J.title = on_title; TP.by_caption(p, 'settings.language')['set'](self.language); J.reg['language'] = 'system'; self.image(J, p, 'message')
        J, p = menu('states'); J.load_state = lambda n: (_ for _ in ()).throw(SS.OtherEngine('abcd')); p._load(2); self.image(J, p, 'message')       # "Cet état a été enregistré avec d'autres fichiers APK du jeu..."
        J, p = menu('controls'); p.capture = ('menu', 1, False); p.key_press(K.F11); p.capture = None; self.image(J, p, 'message')             # "This key is reserved (F11)."
        J, p = menu('controls'); J.reg.bind('info', 0, K.TAB); p.capture = ('menu', 1, False); p.key_press(K.TAB); self.image(J, p, 'message')       # "Tab retirée de "On-screen info"."
        J, p = menu('controls'); J.reg.bind_pad('map', 'PAD_TOUCH'); p.capture = ('up', 0, True); p._capture(PI.SYMBOL['PAD_TOUCH']); self.image(J, p, 'message')       # "Pavé tactile retirée de "Map"." (an Xbox controller has no picture for it: its text is drawn in the "Up" line)
        J, p = menu('controls'); J.reg.bind_pad('map', 'PAD_BACK'); p.capture = ('up', 0, True); p._capture(PI.SYMBOL['PAD_BACK']); self.image(J, p, 'message')       # "Affichage retirée de "Map"." (View: no action by default since the History key is gone)
        J, p = menu('controls'); J.reg.bind('info', 0, K.TAB); TP.by_caption(p, 'settings.menu')['default'](); self.image(J, p, 'message')       # "Une touche d'origine est retirée de "On-screen info"."
        for action, _ in RG.ACTIONS:                                                    # "X retirée de "<each action, even those that are not in the page>"."
            J, p = menu('controls'); name_str = next(n for n in RG.DEFAULT_KEYS[action] if n)
            p.capture = ('up' if action != 'up' else 'down', 0, False); p.key_press(RG.key_symbol(name_str)); self.image(J, p, 'message')

    def key_list(self):
        """The names of all the keys the keyboard can give."""
        J, p = menu('controls')
        for name_str in sorted(n for n in dir(K) if n.isupper() and not n.startswith(('MOD_', 'MOTION'))): p._label(RG.key_name(name_str), 12.0)
        self.note(J, p)

    # ---- what we get out of it
    def texts(self, *moments):
        return [t for m, t in self.seen if m in moments]

    def help_lines(self): return [l for _, ls in self.helpers for l in ls]


def phrases(text): return [ph for ph in re.split(r'\s{3,}', text.strip()) if ph]


def _sliced(lookup_key):
    """Splits `lookup_key` into [text, placeholder, text, placeholder, ..., text]."""
    out = []; pos = 0
    for m in TL.GAPS.finditer(lookup_key): out += [lookup_key[pos:m.start()], m.group()]; pos = m.end()
    return out + [lookup_key[pos:]]


def template(lookup_key):
    """Regular expression of a catalog text with placeholders (%d, %s...)."""
    return re.compile('^' + ''.join('.+' if i % 2 else re.escape(x) for i, x in enumerate(_sliced(lookup_key))) + '$')


def without_letters(t):
    """Nothing to translate: no word (digits, dates, signs) or raw name of a key ("BRACKETLEFT", "F5": pyglet's technical names)."""
    return not re.search(r'[^\W\d_]{2,}', t) or re.fullmatch(r'[A-Z][A-Z0-9_]*', t) is not None


def problems(fr, entry, category):
    """What is wrong between the French walkthrough `fr` and the English walkthrough `entry` (Visit) according to `category` = (French texts, English texts) of the settings domain:
    list of texts, empty if all is well."""
    cat_fr, cat_en = category
    by_fr = {}
    for k, v in cat_fr.items(): by_fr.setdefault(v, k)
    gaps = [(template(v), k) for k, v in cat_fr.items() if TL.GAPS.search(v)]
    pb = []
    for walk in (fr, entry):                                                              # (1) a key drawn as it is: a `tr` is missing
        for t in sorted(set(walk.texts('page', 'infobulle', 'message', 'hint')) | set(walk.help_lines())):
            for part in re.split(r'\s+', t):
                if TL.KEY.match(part) and part.split('.')[0] in LG.DOMAINS: pb.append('key drawn instead of its text (%s): %r' % (walk.language, t)); break
    in_page = set(entry.texts('page', 'infobulle', 'message'))
    for t in sorted(in_page | set(entry.help_lines())):                                    # (2)
        if TL.french(t): pb.append('French drawn in English: %r' % t)
    for k in cat_fr:                                                                     # (5) empty or identical translations
        v = cat_en.get(k, '')
        if not v.strip(): pb.append('empty translation: %r' % k)
        elif v == cat_fr[k] and not without_letters(v) and v not in NEUTRAL: pb.append('translation identical to the French: %r' % k)
    for t in sorted({t for m, t in fr.seen if m in ('page', 'message')}):                  # (3) each French text drawn: its translation is drawn in English
        if without_letters(t) or t in NEUTRAL or TL.KEY.match(t): continue
        if t in by_fr:
            if cat_en.get(by_fr[t]) not in in_page: pb.append('translation not drawn: %r -> %r' % (t, cat_en.get(by_fr[t])))
            continue
        lookup_keys = [k for g, k in gaps if g.match(t)]
        prefixes = [k for k, v in cat_fr.items() if v.endswith(' ') and t.startswith(v)]          # ("Numpad " + the key's own name)
        if prefixes and not lookup_keys:
            if not any(cat_en.get(k, '') + t[len(cat_fr[k]):] in in_page for k in prefixes): pb.append('prefixed text not translated on screen: %r' % t)
            continue
        if not lookup_keys: pb.append('text not in the catalog: %r' % t); continue
        if not any(template(cat_en.get(k, '')).match(x) for k in lookup_keys for x in in_page): pb.append('template text not translated on screen: %r' % t)
    for text, _ in fr.helpers:                                                           # each help sentence is a key (or a neutral text)
        for ph in phrases(text):
            if ph in NEUTRAL or ph in cat_fr or without_letters(ph): continue
            if not any(g.match(ph) for g, k in gaps): pb.append('help sentence that is not a key: %r' % ph)
    for text, lines in entry.helpers:                                                      # in English, each received sentence is rendered translated (rejoined: the tooltip wraps it to its width)
        render = re.sub(r'\s+', ' ', ' '.join(lines))
        for ph in phrases(text):
            t = entry.catalog.get(ph, ph)
            if not without_letters(t) and re.sub(r'\s+', ' ', t) not in render: pb.append('help sentence not rendered translated: %r (rendered %r)' % (ph, render[:80]))
    return pb


_visits = {}


def visit(language, parts=PARTS):
    """The walkthrough in one language with the real catalog, done only once for all the tests (the menu and the catalog do not change from one test to the next)."""
    if (language, parts) not in _visits: _visits[(language, parts)] = Visit(language, parts)
    return _visits[(language, parts)]


class Base(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        window(); LG.select_language('fr')
        cls.fr = visit('fr'); cls.entry = visit('en'); cls.category = (dict(FR_SETTINGS.TEXTS), dict(EN_SETTINGS.TEXTS))
    def tearDown(self): LG.select_language('fr')


class Walkthrough(Base):
    def test_walkthrough_is_complete(self):
        texts = {t for m, t in self.fr.seen if m == 'page'}; FR = LG.catalog('fr')
        for expected in ('settings.settings', 'settings.resume', 'settings.fullscreen', 'settings.put_back_under_battle_box', 'settings.put_back_left_edge', 'settings.hidden_feminine', 'settings.hidden_masculine', 'Touche 2', 'settings.no_thumbnail', 'settings.empty_slot', 'settings.empty', 'settings.no_date',
                        'settings.other', 'settings.very_fast', 'settings.sure', 'settings.left_shift', 'Pavé 7', 'settings.hold_middle_click_move'):
            self.assertIn(FR.get(expected, expected), texts, expected)
        self.assertIn('Limité à x4 par cette carte graphique', [ph for t, _ in self.fr.helpers for ph in phrases(t)])
        self.assertGreater(len(texts), 250); self.assertGreater(len(self.fr.helpers), 80)
        for m in ('infobulle', 'message'): self.assertTrue(self.fr.texts(m), m)

    def test_no_problem(self):
        self.assertEqual(problems(self.fr, self.entry, self.category), [])

    def test_in_english_no_drawn_text_is_french(self):
        self.assertEqual(sorted({t for t in self.entry.texts('page', 'hint', 'infobulle', 'message') if TL.french(t)}), [])

    def test_in_english_translation_is_shown(self):
        texts = set(self.entry.texts('page'))
        for t in ('Settings', 'Resume', 'Display', 'Fullscreen', 'Contrast', 'Sharpness', 'Vignette effect', 'Supersampling', 'Brightness', 'Language', 'Sound', 'Controls', 'Save states', 'Quit', 'Yes', 'No', 'Are you sure?',
                  'Text speed', 'Battle speed', 'Very fast', 'Hold middle click + move', 'Key 1', 'Key 2', 'Restore default keys', 'L Shift', 'Numpad 7', 'Hidden', 'Casino: prizes',
                  'HP and MP restored on level up', 'Empty slot', 'World map', 'Battle'):
            self.assertIn(t, texts, t)

    def test_helptexts_rendered_translated_and_cut_to_width(self):
        lines = self.entry.help_lines()
        self.assertIn('Only available in towns and on the world map: the', ' '.join(lines)); self.assertGreater(len(lines), 150)
        self.assertTrue(all(len(l) < 120 for l in lines))

    def test_french_draws_no_key(self):
        """In French as in English, a drawn text is never a key (every label, value, help sentence and message goes through `tr`)."""
        self.assertEqual([x for x in problems(self.fr, self.entry, self.category) if x.startswith('key drawn')], [])

    def test_reload_notice_only_when_the_game_language_differs(self):
        """the game restarts on the title screen when the language chosen differs from the loaded game's; the message says when (menu closed on the title screen, or the return to the title screen)."""
        try:
            for game_language, chosen, notice in (('fr', 'en', True), ('en', 'fr', True), ('fr', 'fr', False), ('en', 'en', False)):
                for on_title in (False, True):
                    J, p = menu('display'); J.game_language = game_language; J.title = on_title; TP.by_caption(p, 'settings.language')['set'](chosen)
                    self.assertEqual(bool(p._message_text()), notice, (game_language, chosen))
                    if notice: self.assertEqual(p.message[3], 'settings.reload_language_at_menu_close' if on_title else 'settings.reload_language_at_title')
        finally: LG.select_language('fr')

    def test_state_of_the_other_language_offers_to_switch(self):
        """a state saved with the other language's game opens a Yes / No window (No preselected); Yes reloads the game in that language and loads the state; No changes nothing."""
        try:
            for language, title, detail in (('fr', 'Switch the game to French to load this state?', 'This state was saved with the French version of the game.'), ('en', 'Switch the game to English to load this state?', 'This state was saved with the English version of the game.')):
                LG.select_language('en')
                J, p = menu('states'); asked = []
                J.load_state = lambda n, language=language: (_ for _ in ()).throw(SS.OtherLanguage('abcd', language)); J.reload_game = lambda lg, n: asked.append((lg, n))
                p._load(3)
                self.assertEqual(p.popup['choice'], 1); self.assertEqual(LG.tr(p.popup['model']), title); self.assertEqual(p.popup['detail'], detail)
                p._validate_popup(False); self.assertEqual(asked, []); self.assertIsNone(p.popup)
                p._load(3); p._validate_popup(True); self.assertEqual(asked, [(language, 3)])
        finally: LG.select_language('fr')

    def test_each_catalog_key_is_used(self):
        """A key of the settings domain that the walkthrough never shows is a typo (the text would never appear) or a leftover."""
        cat_fr = self.category[0]
        seen = {t for m, t in self.fr.seen}; help_keys = {ph for t, _ in self.fr.helpers for ph in phrases(t)}
        messages = ' '.join(self.fr.texts('message'))                                                              # (an action name is drawn only in a message: "... retirée de "Next page".")
        def shown(k):
            v = cat_fr[k]
            if k in help_keys or v in seen or '« %s »' % v in messages: return True
            if v.endswith(' ') and any(x.startswith(v) for x in seen): return True          # (a prefix: "Numpad " of the numeric keypad's key names)
            return bool(TL.GAPS.search(v)) and any(template(v).match(x) for x in seen | {ph for t, ls in self.fr.helpers for ph in ls})
        self.assertEqual(sorted(k for k in cat_fr if not shown(k)), [])


class Data(unittest.TestCase):
    """The menu data hold keys whatever the language: the other tests, the window and the history rely on this; the translation happens when drawing."""
    def setUp(self): LG.select_language('en')
    def tearDown(self): LG.select_language('fr')

    def test_labels_values_and_keys(self):
        J, p = menu('controls')
        self.assertEqual(dict(RG.ACTIONS)['up'], 'settings.up'); self.assertEqual(dict(RG.ACTIONS)['info'], 'settings.screen_info')
        self.assertEqual(RG.key_name('LSHIFT'), 'settings.left_shift'); self.assertEqual(RG.key_name('NUM_7'), 'Numpad 7'); self.assertEqual(RG.key_name(None), '—')
        self.assertEqual(RG.BATTLE_SPEED_NAMES[3.0], 'settings.very_fast'); self.assertEqual(p._value_name('settings.text_speed', 0.5), 'settings.very_slow'); self.assertEqual(p._value_name('settings.interface_edit', 'buttons'), 'settings.screen_buttons_d_pad')
        self.assertEqual(p._value_name('settings.language', 'en'), 'settings.english'); self.assertEqual(p._value_name('settings.fullscreen', True), 'settings.yes')
        e = TP.by_caption(p, 'settings.menu'); self.assertEqual((e['l'], e['v']), ('settings.menu', ['settings.enter', 'Tab', 'PAD_Y']))
        self.assertTrue(PA.Pause.KEY_HELPTEXT.startswith('settings.enter_change_key'))

    def test_and_are_translated_when_drawn(self):
        self.assertEqual(LG.tr(dict(RG.ACTIONS)['up']), 'Up'); self.assertEqual(LG.tr(RG.key_name('LSHIFT')), 'L Shift'); self.assertEqual(LG.tr(RG.key_name('NUM_7')), 'Numpad 7')
        self.assertEqual(LG.tr(RG.BATTLE_SPEED_NAMES[3.0]), 'Very fast'); self.assertEqual(LG.tr(RG.key_name('F5')), 'F5'); self.assertEqual(LG.tr(RG.key_name(None)), '—')

    def test_message_keeps_its_key_and_is_displayed_translated(self):
        J, p = menu('controls'); J.reg.bind('info', 0, K.TAB); TP.by_caption(p, 'settings.menu')['default']()
        self.assertEqual(p.message[3], 'settings.default_key_removed_from'); self.assertFalse(p.message[2])
        self.assertEqual(p._message_text(), 'A default key is removed from "On-screen info".')
        p.message = (p.message[0], p.message[1] - 5.0) + p.message[2:]; self.assertEqual(p._message_text(), '')              # (more than 4 seconds: gone)
        J, p = menu('states'); J.failure = 'disque plein'; p._save(3)
        self.assertTrue(p.message[2])
        self.assertEqual(p._message_text(), "Could not save the state: OSError('disque plein')")
        LG.select_language('fr'); self.assertEqual(p._message_text(), "Impossible d'enregistrer l'état : OSError('disque plein')")

    def test_state_date_follows_language(self):
        """a savestate's name is its date, in day/month/year in French (as before) and in year-month-day in English (the French 03/11 is March 11 for an English-speaking reader). Same format in
        the list, the delete window and the thumbnail; a savestate without a date remains "No date"."""
        att = {'fr': ['31/10/2026  19:21:05', '02/11/2026  08:05:59', 'Sans date', '03/11/2026  23:59:00'], 'en': ['2026-10-31  19:21:05', '2026-11-02  08:05:59', 'No date', '2026-11-03  23:59:00']}
        for language in ('fr', 'en'):
            LG.select_language(language); J, p = menu('states')
            slots = [x for x in p._entries_savestates() if x['t'] == 'slot' and x['n'] in (1, 2, 3, 5)]
            self.assertEqual([LG.tr(x['l']) for x in slots], att[language], language)
            p._request_deletion(1); self.assertEqual(p.popup['detail'], att[language][0], language)
            self.assertEqual(PA.Pause._state_date('not a date'), ''); self.assertEqual(PA.Pause._state_date(None), '')

    def test_deletion_window_title(self):
        J, p = menu('states'); p._request_deletion(4)
        self.assertEqual(p.popup['model'], 'settings.delete_save_state_n'); self.assertEqual(p.popup['title'], 'Delete save state 4?'); self.assertEqual(p.popup['choice'], 1)

    def test_line_helptexts_hold_keys(self):
        J, p = menu('display')
        self.assertIn('settings.fullscreen_borderless_window_resolution_screen', p._line_helptext(TP.by_caption(p, 'settings.fullscreen')))
        J.post.max_msaa = 2; J.reg['msaa'] = 8; self.assertEqual(TP.by_caption(p, 'settings.antialiasing')['hint'], 'Limited to x2 by this graphics card')       # (text with placeholders: translated then filled in, see Pause._entries_display)


class Keys(unittest.TestCase):
    def tearDown(self): LG.select_language('fr')

    def test_all_key_names_in_english(self):
        LG.select_language('en')
        names = sorted({n for n in dir(K) if n.isupper() and not n.startswith(('MOD_', 'MOTION'))})
        self.assertGreater(len(names), 100)
        for n in names:
            fr = RG.key_name(n); entry = LG.tr(fr)
            self.assertFalse(TL.french(entry), '%s : %r -> %r' % (n, fr, entry)); self.assertNotIn('Pavé', entry)
            if fr != n and fr in EN_SETTINGS.TEXTS: self.assertNotEqual(entry, fr)
        self.assertEqual([LG.tr(RG.key_name(n)) for n in ('LSHIFT', 'RSHIFT', 'LCTRL', 'RCTRL', 'LALT', 'RALT', 'SPACE', 'RETURN', 'ENTER', 'BACKSPACE', 'DELETE', 'INSERT', 'HOME', 'END', 'PAGEUP', 'PAGEDOWN', 'CAPSLOCK', 'NUM_ADD', 'NUM_SUBTRACT')],
                         ['L Shift', 'R Shift', 'L Ctrl', 'R Ctrl', 'Alt', 'Alt Gr', 'Space', 'Enter', 'Numpad Enter', 'Backspace', 'Delete', 'Insert', 'Home', 'End', 'Page Up', 'Page Down', 'Caps Lock', 'Numpad +', 'Numpad -'])

    def test_in_french_nothing_changes(self):
        LG.select_language('fr')
        for n, att in (('LSHIFT', 'Maj G'), ('RETURN', 'Entrée'), ('NUM_3', 'Pavé 3'), ('F1', 'F1'), ('BACKSPACE', 'Retour arrière')): self.assertEqual(LG.tr(RG.key_name(n)), att)

    def test_whole_pyglet_numpad_is_translated(self):
        for language, prefix in (('fr', 'Pavé '), ('en', 'Numpad ')):
            LG.select_language(language)
            for n in dir(K):
                if n.startswith('NUM_'): self.assertTrue(LG.tr(RG.key_name(n)).startswith(prefix) or not RG.key_name(n).startswith(('Pavé', 'Numpad')), (language, n, RG.key_name(n)))


class Console(unittest.TestCase):
    """The console messages of settings.py and pause.py."""
    def tearDown(self): LG.select_language('fr')

    def output(self, f):
        s = io.StringIO()
        with contextlib.redirect_stdout(s): f()
        return s.getvalue().strip()

    def test_unreadable_settings(self):
        with tempfile.TemporaryDirectory() as t:
            path = os.path.join(t, 'settings.json')
            with open(path, 'w', encoding='utf-8') as f: f.write('{not json')
            LG.select_language('fr'); fr = self.output(lambda: RG.Settings(path))
            LG.select_language('en'); entry = self.output(lambda: RG.Settings(path))
        self.assertTrue(fr.startswith('Unreadable settings (%s): default values (' % path), fr); self.assertTrue(entry.startswith('Unreadable settings (%s): default values (' % path), entry)

    def test_settings_not_stored(self):
        with tempfile.TemporaryDirectory() as t:
            r = RG.Settings(os.path.join(t, 'dossier_absent', 'settings.json'))
            LG.select_language('fr'); fr = self.output(r.store)
            LG.select_language('en'); entry = self.output(r.store)
        self.assertTrue(fr.startswith('Settings not saved: '), fr); self.assertTrue(entry.startswith('Settings not saved: '), entry)

    def test_game_font_not_loaded(self):
        """The game font file exists but pyglet cannot load it (here: deliberately refused): the console says so in the tool's language."""
        add_file = pyglet.font.add_file
        def refused(*a, **k): raise OSError('police refusee')
        outputs = []
        try:
            pyglet.font.add_file = refused
            with tempfile.TemporaryDirectory() as t:
                open(os.path.join(t, 'ui_font.otf'), 'wb').close()
                for language in ('fr', 'en'):
                    J = FakeGame(); J.args = types.SimpleNamespace(cache=t); p = PA.Pause(J); LG.select_language(language); outputs.append(self.output(lambda: p._label('settings.sound', 12.0)))
        finally: pyglet.font.add_file = add_file
        self.assertTrue(outputs[0].startswith('game font not loaded: police refusee'), outputs[0]); self.assertTrue(outputs[1].startswith('game font not loaded: police refusee'), outputs[1])


class Catalog(unittest.TestCase):
    """The catalog rules (tests/test_language.py) for dq456_pc/texts/*/settings.py, plus: a key is ONE help sentence (help texts chain keys separated by three spaces)."""
    def test_rules(self):
        for k, fr in FR_SETTINGS.TEXTS.items():
            entry = EN_SETTINGS.TEXTS[k]
            self.assertTrue(entry.strip(), k)
            self.assertNotIn('   ', fr.strip(), 'a key is ONE help sentence: %r' % k); self.assertNotIn('   ', entry.strip(), k)


class Mutations(Base):
    """The check of the verification itself: each fault introduced by hand is seen by `problemes`."""

    def english(self, parts, catalogs=None):
        saved = LG._catalogs
        try:
            if catalogs is not None: LG._catalogs = {'fr': dict(catalogs[0]), 'en': dict(catalogs[1])}
            return Visit('en', parts)
        finally: LG._catalogs = saved

    def check(self, parts, catalogs=None, category=None):
        """`problems` for these pieces of the walkthrough, with these catalogs ((fr, en), None: the real ones) and the settings catalogs `category` according to `problems`."""
        return problems(visit('fr', parts), self.english(parts, catalogs), self.category if category is None else category)

    @contextlib.contextmanager
    def muter(self, klass, name_str, old, new):
        """Replaces, for the duration of the block, the method `klass.name_str` with a copy in which the text `old` has become `new` (executed with the globals of the class's module)."""
        f = getattr(klass, name_str); src = textwrap.dedent(inspect.getsource(f))
        self.assertIn(old, src, 'the mutation targets nothing: %r' % old)
        ns = dict(vars(sys.modules[klass.__module__])); exec(compile(src.replace(old, new, 1), '<mutation>', 'exec'), ns)
        setattr(klass, name_str, types.FunctionType(ns[name_str].__code__, vars(sys.modules[klass.__module__]), name_str, ns[name_str].__defaults__))          # (with the module globals as they are during the walkthrough: the frozen clock, for example)
        try: yield
        finally: setattr(klass, name_str, f)

    def without(self, *lookup_keys):
        """The walkthrough's catalogs and those of `problems` without these keys (in both languages)."""
        cut = lambda c: {k: v for k, v in c.items() if k not in lookup_keys}
        return (cut(LG.catalog('fr')), cut(LG.catalog('en'))), (cut(self.category[0]), cut(self.category[1]))

    def test_baseline_without_problem(self):
        for parts in (('page_root',), ('page_commands',), ('messages',), ('page_savestates',)): self.assertEqual(self.check(parts), [], parts)

    def test_a_key_removed_from_the_catalog(self):
        c, c_pause = self.without('settings.resume')
        pb = self.check(('page_root',), c, c_pause)
        self.assertTrue(any('settings.resume' in x for x in pb), pb)

    def test_a_help_sentence_removed_from_the_catalog(self):
        c, c_pause = self.without('settings.language_tool_settings_history_saves')
        pb = self.check(('page_display',), c, c_pause)
        self.assertTrue(any('settings.language_tool_settings_history_saves' in x for x in pb), pb)

    def test_a_key_name_removed_from_the_catalog(self):
        c, c_pause = self.without('settings.left_shift')
        pb = self.check(('key_list',), c, c_pause)
        self.assertTrue(any('settings.left_shift' in x for x in pb), pb)

    def test_tr_of_helptexts_removed(self):
        with self.muter(PA.Pause, '_helptext_lines', 'l = tr(l); cur', 'cur'): pb = self.check(('page_root',))
        self.assertTrue(any('key drawn' in x for x in pb), pb)

    def test_tr_of_key_n_removed(self):
        with self.muter(PA.Pause, '_draw_page', "self._label(tr('settings.button' if self.controls_pad else 'settings.key') % (c + 1)", "self._label(('settings.button %d' if self.controls_pad else 'settings.key %d') % (c + 1)"): pb = self.check(('page_commands',))
        self.assertTrue(any('key drawn' in x for x in pb), pb)

    def test_tr_of_message_values_removed(self):
        """The action name in "Tab retirée de "On-screen info"" is translated too."""
        with self.muter(PA.Pause, '_message_text', 'tuple(tr(v) for v in m[4])', 'm[4]'): pb = self.check(('messages',))
        self.assertTrue(any('removed from' in x for x in pb), pb)

    def test_an_emptied_translation(self):
        en = dict(LG.catalog('en'), **{'settings.contrast': ''})
        pb = self.check(('page_display',), (LG.catalog('fr'), en), (self.category[0], dict(self.category[1], **{'settings.contrast': ''})))
        self.assertTrue(any('empty' in x for x in pb), pb)

    def test_a_translation_left_in_french(self):
        fr_text = LG.catalog('fr')['settings.resume']; en = dict(LG.catalog('en'), **{'settings.resume': fr_text})
        pb = self.check(('page_root',), (LG.catalog('fr'), en), (self.category[0], dict(self.category[1], **{'settings.resume': fr_text})))
        self.assertTrue(any('identical' in x or 'French drawn' in x for x in pb), pb)

    def test_without_tr_french_shows_keys(self):
        """A menu without the `tr` on the help texts draws keys in French too."""
        with self.muter(PA.Pause, '_helptext_lines', 'l = tr(l); cur', 'cur'): f = Visit('fr', ('page_root',))
        self.assertTrue(any(TL.KEY.match(l) for _, ls in f.helpers for l in ls))


if __name__ == '__main__':
    unittest.main(verbosity=1)
