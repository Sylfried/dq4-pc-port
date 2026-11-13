"""History: the dialogues spoken on screen (outside battle), the latest battles and the favorites.

Three parts:
- `Sensor` (hooks in the engine, installed by Engine.__init__): the text of a message is known in only one place, TextBuffer::cat (called once per message page, macros resolved, with the
  speaker's name given by the engine itself: the "@a<name>@b" of the patch texts, that is, the name that the game DISPLAYS on the message window). The hook records the text, that name, the game time
  (status::g_Game + 4, in 1/60 s) and whether the call comes from a battle (battle messages do not enter the dialogue history: battle has its own, battle_history.py).
- `History` (pure data, no pyglet or emulator): the latest dialogues and battles OF THE ADVENTURE BEING PLAYED (100 of each, kept from one session to the next; one history per adventure)
  and ITS favorites (one file per adventure too; until the player removes the star; a favorite is a copy, so it outlives the element when it drops out of the latest 100).
  An adventure is an identifier given by the port: loading an adventure log (`SaveLoad::loadbank`) takes the history of that log, writing a log (church, auto-save) gives it the history of the adventure being
  played, a new game starts an empty one, the title screen leaves it; a savestate keeps the identifier of its adventure (Game._complete_savestate). Files: `history\\index.json` (adventure log -> adventure, with the
  game's own unique ID, `status::g_Game + 8`, a random number 0-255: a log overwritten by another game no longer matches), `history\\<adventure>.json` (latest elements) and `history\\<adventure>.favorites.json`,
  next to the old common favorites file (`--history`, `history_favorites.json`: taken over by the first adventure that becomes current).
- pure functions: text cleanup, line wrapping, battle formatting.

Dialogue favorites keep the message's KEY (its number in the game files, "b0802000#199": file = number // 1000 x 1000, rank = remainder), not its text: the text is requested again from the game engine at
launch (TextAPI::extractText, see `Sensor.model`), so a message modified in the patch also changes in the favorites. The number is known at the ui_MsgAdd hook (the text, for its part, goes through TextBuffer::cat). The
link is made only if the text given by the game files gives back EXACTLY what the player read (see `binding`: message page, game variables "[NONE 1,0]" replaced by the values seen);
otherwise (text built by the program, pages split differently...) the favorite keeps its text, as before.

A dialogue is shown as in the game: a message window, with the speaker's name in a name plate ONLY if the game displayed it at the time the dialogue was spoken; otherwise the text alone, as the game writes
it (the words of a character without a name start with "*:" in the FR patch: that start is kept). No "who said this" or "where" is deduced.
"""
import json, os, re, struct, threading, time, uuid
from dq4_pc.language import tr, N_
from dq4_pc.core.legacy_state import renamed_history

HISTORY_FOLDER = 'history'               # latest dialogues and battles of each adventure, in the folder of the favorites file
INDEX_FILE = 'index.json'
LEGACY_RECENT = 'history_recent.json'     # single history (one hour of life): becomes that of the first adventure
RECENT_VERSION = 1
VERSION = 3                        # favorites file (version 1 was the old per-saved-game message history: abandoned; version 2: French keys, read and rewritten as version 3)
OLD_VERSION = 2
MAX_DIALOGUES = 100                # kept from one session to the next: the oldest ones drop out (a favorite never does: it is a copy)
MAX_BATTLES = 100
MAX_FAVORITES = 500
MAX_TEXT = 1500                   # characters kept from a message
MAX_LOG = 200                      # battle messages kept per battle, for the rewind: a long boss battle is cut at the end
MAX_LOG_TEXT = 300                 # characters kept from a battle message
REPLAY_TAIL = 20                   # engine steps still recorded after the end of a battle (the start of its closing fade)
REPLAY_START_WAIT = 600            # engine steps between the start of the entry cascade and the engine's "start" of the battle (57 + the scene's loading, 240 at most) after which the recording is given up
RE_REPLAY = re.compile(r'^[0-9a-f]{8,32}/[0-9a-f]{8,32}\.dqs$')        # replay file of a battle, relative to the history folder: <adventure>/<battle>.dqs
PAGE = '\u3221'                    # "㈡": page break (new bubble) in the text of a message in the game files
RE_TOKEN = re.compile(r'\[[A-Z]+ [0-9, -]*\]')       # game variable not resolved in the text of a message in the files: "[NONE 1,0]" (the hero's name, a number, an item...)
MSG_ID_MAX = 1 << 24               # the text kind is stored in bits 24 and above of the identifier that TextAPI::extractText takes
SYM_UI_MSGADD = '_Z9ui_MsgAddib'   # ui_MsgAdd(int number, bool): the engine adds a message (number = key in the game files); it calls TextBuffer::cat
SYM_EXTRACT = '_ZN7TextAPI11extractTextEPci'
SYM_LOADBANK = '_ZN7profile8SaveLoad8loadbankEi'      # loadbank(int bank): the engine loads an adventure log (data<bank + 1>.dat), from the start menu as from Engine.load_save
SYM_TITLE = '_ZN6Global10startTitleEv'                # the title screen: no adventure is being played any more
WINDOW_WAIT = 180              # frames: a pending page is recorded if the message window has never opened after this delay (3 s)
TIME_MARGIN = 120                      # 2 s of game time (1/60 s): two identical messages closer together than that are a duplicate
STORAGE_DELAY = 5.0         # seconds: writes are grouped (favorites change only by hand: they are written immediately, see toggle_favorite)
PART_TOWN, PART_BATTLE, PART_FIELD = 0xc, 0xd, 0xe

KIND_NAME, KIND_GENERAL = 'n', 'g'                    # message with a name that the game displays / without a name
CATEGORY_TERRAIN, CATEGORY_BATTLE = 't', 'c'                      # out-of-battle message / battle message (never stored in the dialogues)
TYPE_DIALOGUE, BATTLE_TYPE = 'd', 'c'
MISSING = N_('menus.message_not_found_game_files')            # (translated when it replaces the text of a favorite: see History._resolve)

ENTRIES_TYPE = {'dialogues': TYPE_DIALOGUE, 'battles': BATTLE_TYPE}              # history list -> type of its elements (History.entries, "Favorites only" filter)
OUTCOMES = ('victory', 'escape', 'defeat')
OUTCOME_CAPTION = {'victory': N_('menus.victory'), 'escape': N_('menus.escaped'), 'defeat': N_('menus.defeat')}            # (translated by the window when drawing: tr(OUTCOME_CAPTION[...]))


# ---------------------------------------------------------------------------------------------------------------------------------- elements
class Element:
    """A history element: dialogue (type 'd': displayed name or None, text) or battle (type 'c': enemies [{'nom', 'total', 'vaincus', 'fuis', 'disparus'}], gold, xp, outcome, objects [{'nom'}]).
    `n`: sequence number (display key), `t`: game time (1/60 s), `fav`: number of the matching favorite (None: not a favorite)."""
    __slots__ = ('n', 'type', 't', 'name_str', 'text', 'enemies', 'gold', 'xp', 'outcome', 'fav', 'objects', 'mid', 'seg', 'val', 'linked', 'waiting', 'log', 'replay')

    def __init__(self, n, type_, t, name_str=None, text='', enemies=None, gold=0, xp=0, outcome='victory', fav=None, objects=None, mid=None, seg=None, val=None):
        self.n, self.type, self.t, self.name_str, self.text = n, type_, t, name_str, text
        self.enemies, self.gold, self.xp, self.outcome, self.fav = enemies or [], gold, xp, outcome, fav
        self.objects = objects or []
        self.mid, self.seg, self.val = mid, seg, val or {}      # dialogue: message number in the game files (None: unknown), message page (None: whole message), values of the variables [NONE a,b]
        self.linked = False                                         # dialogue favorite stored by key (the file does not keep the text)
        self.waiting = False                                     # ... and whose text has not yet been requested again from the engine (see History._resolve)
        self.replay = None                                       # battle: its replay file (state at the start of the battle + the engine inputs), relative to the history folder; None: no replay
        self.log = []                                            # battle: its messages for the rewind, [[game time since the first message (1/60 s), displayed name or None, text], ...]; empty for a battle recorded

    def lookup_key(self):
        """What makes up an element's identity (to recognize a duplicate, or an element already in the favorites): the content, not the number."""
        if self.type == TYPE_DIALOGUE: return (TYPE_DIALOGUE, self.name_str, self.text)
        return (BATTLE_TYPE, self.t, self.outcome, self.gold, self.xp, tuple((e['name'], e['total'], e['defeated'], e.get('fled', 0), e.get('vanished', 0)) for e in self.enemies),
                tuple(o['name'] for o in self.objects))

    def to_dict(self):
        if self.type == TYPE_DIALOGUE:
            if not self.linked: return {'k': TYPE_DIALOGUE, 'id': self.fav, 't': self.t, 'name': self.name_str, 'text': self.text}
            d = {'k': TYPE_DIALOGUE, 'id': self.fav, 't': self.t, 'name': self.name_str, 'mid': self.mid}          # (no text: it comes from the game files)
            if self.seg is not None: d['s'] = self.seg
            if self.val: d['v'] = dict(self.val)
            return d
        d = {'k': BATTLE_TYPE, 'id': self.fav, 't': self.t, 'enemies': [dict(e) for e in self.enemies], 'gold': self.gold, 'xp': self.xp, 'outcome': self.outcome, 'objects': [dict(o) for o in self.objects]}
        if self.log: d['log'] = [list(m) for m in self.log]
        if self.replay: d['replay'] = self.replay
        return d

    @staticmethod
    def from_dict(d, n, recent=False):
        """Element read from a file (favorites, or with `recent` the latest dialogues and battles, whose `id` is None when they are not a favorite); None if it is not valid (the rest of the file is kept)."""
        try:
            ident, t = d['id'], d['t']
            if not ((recent and ident is None) or (_is_integer(ident) and ident >= 1)) or not _is_integer(t) or t < 0: return None
            if d['k'] == TYPE_DIALOGUE:
                name_str = d.get('name')
                if not (name_str is None or isinstance(name_str, str)): return None
                name_str = (without_marks(name_str).strip()[:60] or None) if name_str else None
                if 'text' in d:                                                               # favorite that keeps its text (or a message that the game files do not give back as is)
                    text = d['text']
                    if not isinstance(text, str) or not text.strip(): return None
                    return Element(n, TYPE_DIALOGUE, t, name_str, without_marks(text)[:MAX_TEXT], fav=ident)
                mid, seg, val = d.get('mid'), d.get('s'), d.get('v', {})                      # favorite stored by key: the text will be requested again from the engine
                if not _is_integer(mid) or mid < 1 or mid >= MSG_ID_MAX or not (seg is None or (_is_integer(seg) and 0 <= seg < 1000)): return None
                if not isinstance(val, dict) or len(val) > 20 or any(not isinstance(k, str) or not isinstance(v, str) or len(k) > 40 or len(v) > 200 for k, v in val.items()): return None
                e = Element(n, TYPE_DIALOGUE, t, name_str, '', fav=ident, mid=mid, seg=seg, val=dict(val)); e.linked = e.waiting = True
                return e
            if d['k'] == BATTLE_TYPE:
                outcome, enemies = d['outcome'], d['enemies']
                if outcome not in OUTCOMES or not isinstance(enemies, list): return None
                es = valid_enemies(enemies)
                gain = [d.get('gold', 0), d.get('xp', 0)]
                if es is None or any(isinstance(x, bool) or not isinstance(x, int) or x < 0 for x in gain): return None
                obj = valid_objects(d.get('objects', []))                                      # (favorites have no fled, no vanished and no items)
                log = valid_log(d.get('log', []))                                              # (battles have no messages)
                if obj is None or log is None: return None
                e = Element(n, BATTLE_TYPE, t, enemies=es, gold=gain[0], xp=gain[1], outcome=outcome, fav=ident, objects=obj); e.log = log
                r = d.get('replay')
                e.replay = r if isinstance(r, str) and RE_REPLAY.match(r) else None
                return e
        except Exception:
            return None
        return None

    def __repr__(self): return 'Element(%r)' % (self.to_dict(),)


def _is_integer(x): return isinstance(x, int) and not isinstance(x, bool)


def valid_enemies(enemies):
    """List of species [{'name', 'total', 'defeated', 'fled', 'vanished'}] checked and copied (fled and vanished: 0 if they are missing, as in the favorites); None if it is not valid."""
    if not isinstance(enemies, list): return None
    es = []
    for e in enemies:
        if not isinstance(e, dict): return None
        name_str, total, defeated, fled, vanished = e.get('name'), e.get('total'), e.get('defeated'), e.get('fled', 0), e.get('vanished', 0)
        if not isinstance(name_str, str) or any(isinstance(x, bool) or not isinstance(x, int) or x < 0 for x in (total, defeated, fled, vanished)): return None
        es.append({'name': without_marks(name_str)[:60], 'total': total, 'defeated': defeated, 'fled': fled, 'vanished': vanished})
    return es[:12]


def valid_objects(objects):
    """List of items won [{'name'}] checked and copied; None if it is not valid."""
    if not isinstance(objects, list): return None
    out = []
    for o in objects:
        if not isinstance(o, dict) or not isinstance(o.get('name'), str): return None
        out.append({'name': without_marks(o['name']).strip()[:60]})
    return out[:8]


def valid_log(log):
    """Battle messages read from a file [[time, name or None, text], ...] checked and copied; None if it is not valid."""
    if not isinstance(log, list): return None
    out = []
    for m in log[:MAX_LOG]:
        if not isinstance(m, list) or len(m) != 3 or not _is_integer(m[0]) or m[0] < 0 or not (m[1] is None or isinstance(m[1], str)) or not isinstance(m[2], str): return None
        out.append([m[0], m[1][:60] if m[1] else None, m[2][:MAX_LOG_TEXT]])
    return out


def battle_log(records):
    """Messages recorded by the Sensor during a battle (records of category 'c') -> the element's log: times counted from the first message, text cleaned, empty ones dropped, at most MAX_LOG."""
    out = []; t0 = None
    for r in records:
        text = clean(r.get('text', ''))[:MAX_LOG_TEXT]
        if not text: continue
        t = int(r.get('t') or 0)
        if t0 is None: t0 = t
        name = (without_marks(str(r['val'])).strip()[:60] or None) if r.get('kind') == KIND_NAME and r.get('val') else None
        out.append([max(0, t - t0), name, text])
    return out[:MAX_LOG]


def without_marks(text):
    """Removes the ";" from the patch text: a break mark placed just after a space in item names ("bâton de ;cyprès", "l'herbe ;médicinale"), not punctuation (no punctuation ";"
    in the patch texts; see docs/viewer-notes-dq4-pc.md). The space before it stays: "l'herbe médicinale"."""
    return text.replace(';', '')


def clean(text):
    """Text as the game displays it: color codes (@c0...) and control characters removed, trailing spaces removed, line breaks kept (never more than one empty line). The "*:" at the start of the words
    of a character without a name is KEPT (it is the game's text). The ";" (the break mark of the patch's item names) is removed."""
    t = (text or '').replace('\r', '')
    t = re.sub(r'@c\d', '', t)
    t = without_marks(t)
    t = ''.join(ch for ch in t if ch == '\n' or (ch >= ' ' and not (0xe000 <= ord(ch) <= 0xf8ff) and ch != '\x7f'))
    t = '\n'.join(l.rstrip() for l in t.split('\n'))
    t = re.sub(r'\n{3,}', '\n\n', t).strip('\n ')
    return t[:MAX_TEXT]


def message_key(mid):
    """A message's key as it is cited for the patch: file (number // 1000 x 1000, 7 digits) # rank: 802199 -> "b0802000#199"."""
    return 'b%07d#%d' % (mid // 1000 * 1000, mid % 1000)


def value_list(model, text):
    """Values of the game variables ("[NONE 1,0]") that turn the text of the `model` game files into the read text `text`: {} if the model has no variable (or if the text shows them as they are, like the files) and
    the two are identical; {variable: value} if the text is found again by replacing each variable; None if the model does not give this text back."""
    mod = clean(model)
    if mod == text: return {}
    tokens = RE_TOKEN.findall(mod)
    if not tokens: return None
    r = re.match('^' + '(.*?)'.join(re.escape(m) for m in RE_TOKEN.split(mod)) + '$', text, re.S)
    if r is None: return None
    vals = {}
    for j, v in zip(tokens, r.groups()):
        if vals.setdefault(j, v) != v: return None                                  # (the same variable with two values: not the same message)
    return vals


def binding(raw_value, text):
    """How to find `text` (what the player read, cleaned) in the game files text `raw_value`: (page, values of the variables), `page` = rank of the message page (separated by ㈡) or None for the whole
    message; None if neither a page nor the whole message gives back EXACTLY this text (the favorite then keeps its text)."""
    attempts = [(None, raw_value)] + ([(i, p) for i, p in enumerate(raw_value.split(PAGE))] if PAGE in raw_value else [])
    for page, mod in attempts:
        v = value_list(mod, text)
        if v is not None: return page, v
    return None


def linked_text(raw_value, seg, val):
    """Text of a favorite stored by key: the page `seg` (None: whole message) of the game files text `raw_value`, variables replaced by the kept values (an unknown variable stays as it is). '' if `raw_value` is missing
    or does not have this page."""
    if not raw_value: return ''
    if seg is not None:
        pages = raw_value.split(PAGE)
        if seg >= len(pages): return ''
        raw_value = pages[seg]
    t = RE_TOKEN.sub(lambda m: val.get(m.group(0), m.group(0)), clean(raw_value))
    return t.strip('\n ')[:MAX_TEXT]


def wrap_text(text, width_px, measure):
    """Splits `text` into lines of at most `width_px` (measure(string) -> width): the text's line breaks are kept, the split is made at spaces (not at non-breaking spaces); a word wider than the line is cut."""
    lines = []
    for para in text.split('\n'):
        if not para.strip(): lines.append(''); continue
        cur = ''
        for word in re.split(r' +', para):
            cand = word if not cur else cur + ' ' + word
            if cur and measure(cand) > width_px: lines.append(cur); cur = word
            else: cur = cand
            while measure(cur) > width_px and len(cur) > 1:                               # word wider than the line
                i = len(cur) - 1
                while i > 1 and measure(cur[:i]) > width_px: i -= 1
                lines.append(cur[:i]); cur = cur[i:]
        lines.append(cur)
    while lines and not lines[-1]: lines.pop()
    return lines or ['']


def plural(n, singular, plural_form):
    """"1 vaincu", "2 vaincus": the singular or plural template (`singular`, `plural_form`: template texts "%d vaincu" / "%d vaincus", N_; English has only one form but keeps it as two)."""
    return tr(singular if n < 2 else plural_form) % n


SPELLS = ((N_('menus.count_defeated_one'), N_('menus.count_defeated_many')), (N_('menus.count_fled_one'), N_('menus.count_fled_many')), (N_('menus.count_vanished_one'), N_('menus.count_vanished_many')), (N_('menus.count_remained_one'), N_('menus.count_remained_many')))           # defeated, fled, vanished, remaining


def species_line(e):
    """An enemy species, on one line: "Gluant ×3" when all are defeated ("Gluant" if there was only one), otherwise each one's fate: "Gluant ×3 : 1 vaincu, 1 enfui, 1 disparu"; those that are neither defeated,
    nor fled, nor vanished are still there when the battle ends (the party fled or was defeated): "2 restés"."""
    tot, vai, fui, dis = e['total'], e['defeated'], e.get('fled', 0), e.get('vanished', 0)
    base = '%s ×%d' % (e['name'], tot) if tot > 1 else e['name']
    if vai >= tot: return base
    remainder = max(0, tot - vai - fui - dis)
    if tot == 1: return (tr('menus.name_fled') if fui else tr('menus.name_vanished') if dis else tr('menus.name_remained')) % base
    spells = [plural(n, *words) for n, words in zip((vai, fui, dis, remainder), SPELLS) if n > 0]
    return tr('menus.name_value') % (base, ', '.join(spells))


def battle_lines(c):
    """Text lines of a battle (Element of type 'c'), one per row: one per enemy species (species_line: who was there, who is defeated, fled, vanished or remaining), then, for a victory, the gold and experience
    won, then the items obtained ("Objets : Herbe médicinale, Pierre de vie"). Nothing is written when there was no item."""
    out = [species_line(e) for e in c.enemies]
    if not out: out.append(tr('menus.unknown_enemies'))
    if c.outcome == 'victory':
        out.append(tr('menus.gold_experience') % (c.gold, c.xp))          # (non-breaking spaces: line wrapping does not make them disappear)
        if c.objects: out.append(tr('menus.items') % ', '.join(o['name'] for o in c.objects))
    return out


def battle_element(n, battle):
    """Element of type 'c' from a dict of battle_history.BattleSensor.do_update; None if the dict is unusable."""
    try:
        outcome = battle['outcome']
        if outcome not in OUTCOMES: return None
        es = [{'name': str(e['name'])[:60], 'total': int(e['total']), 'defeated': int(e['defeated']), 'fled': int(e.get('fled', 0)), 'vanished': int(e.get('vanished', 0))} for e in battle['enemies']][:12]
        objects = [{'name': without_marks(str(o['name'])).strip()[:60]} for o in battle.get('objects', [])][:8]
        return Element(n, BATTLE_TYPE, int(battle['t']), enemies=es, gold=max(0, int(battle['gold'])), xp=max(0, int(battle['xp'])), outcome=outcome, objects=objects)
    except Exception:
        return None


# ---------------------------------------------------------------------------------------------------------------------------------- data
class History:
    """Latest dialogues and battles + favorites, in two files next to the viewer (never in the game's saves folder, which is not modified). Latest ones:
    {"version": 1, "dialogues": [{"k": "d", "id": null, ...}], "battles": [...]} (same element format as the favorites; `id` = number of the matching favorite or null). Favorites:
    {"version": 3, "next": 7, "favorites": [{"k": "d", "id": 3, "t": 12345, "name": "Alena", "text": "..."}, {"k": "c", "id": 5, "t": 1, "enemies": [...], "gold": 3, "xp": 4, "outcome": "victory", "objects": [{"name": "Herbe médicinale"}]}]}."""

    def __init__(self, path=None, clock=time.time):
        self.legacy_favorites = path; self.path = None; self.clock = clock     # common favorites file; favorites file of the adventure being played (None: no adventure)
        self.folder = os.path.join(os.path.dirname(path), HISTORY_FOLDER) if path else None
        self.adventure = None; self.recent_path = None      # adventure being played and the file of its history; None: title screen, or before the first game
        self.index = {}                                     # adventure log number (str) -> {'id': adventure, 'uid': the game's unique ID when it was written or loaded}
        self.dialogues = []                                 # latest 'd' Elements (this session and the previous ones), from oldest to newest
        self.battles = []                                   # latest 'c' Elements
        self.favorites = []                                   # Elements (d or c) kept in the file, in the order in which they were made favorites
        self.next_id = 1                                    # next favorite number
        self.removing = set()                               # numbers of the favorites whose star was removed while the history window is open: removed only when the window is left (apply_removals)
        self._n = 0                                         # counter of the sequence numbers (dialogues, battles, favorites: never the same one twice)
        self._wait = []                                  # pages of a message already prepared by the engine but not yet read (see _pages)
        self._feed = False; self._has_been_seen = False; self._n_att = 0       # end-of-page cursor of the previous frame; message window seen open since the burst; waiting frames
        self._dirty = False; self._dirty_recent = False; self._t_write = 0.0      # favorites / latest elements to write
        self.snapshotter = None                             # (Game) -> savestate of the game, taken at the start of each battle for its replay; None: no replay recorded
        self.replaying = False                              # a battle replay is being played: nothing is recorded, nothing changes in the history
        self._rec = None; self._tail = None                 # state at the start of the battle being recorded; [battle element, state, steps left] while its end is still recorded
        self._rec_state = None; self._rec_wait = 0          # engine State object the recording started with (a savestate loaded in the middle replaces it: recording given up); steps waited for the battle's "start"
        self._battle_log = []                               # battle messages (Sensor records of category 'c') of the battle in progress: given to the battle when it ends
        self._last = None                                   # last dialogue added in THIS session (the duplicate filter compares with it only: the game time restarts with the loaded game)
        self.error = None
        self._cap = None; self._models = {}                # Engine Sensor (once it exists); text of the game files already requested, by message number
        self._load_index()

    def _num(self):
        self._n += 1; return self._n

    # ---- favorites file
    def load(self):
        """Reads the favorites file. An unreadable file is set aside (.corrupt) and we start again from zero; an invalid favorite is ignored without losing the others."""
        self.favorites = []; self.next_id = 1
        if not self.path or not os.path.exists(self.path): return
        try:
            with open(self.path, encoding='utf-8') as f: d = json.load(f)
            if isinstance(d, dict) and d.get('version') == OLD_VERSION: d = renamed_history(d); d['version'] = VERSION; self._dirty = True            # (rewritten in English at the next write)
            if not isinstance(d, dict) or d.get('version') != VERSION or not isinstance(d.get('favorites'), list): raise ValueError('unknown format')
            seen = set()
            for x in d['favorites']:
                e = Element.from_dict(x, self._num()) if isinstance(x, dict) else None
                if e is not None and e.fav not in seen: seen.add(e.fav); self.favorites.append(e)
            self.favorites = self.favorites[-MAX_FAVORITES:]
            s = d.get('next')                                              # next number saved: never a number already taken, nor a number already given and then removed
            self.next_id = max([e.fav + 1 for e in self.favorites] + [s if isinstance(s, int) and not isinstance(s, bool) and s > 0 else 1])
        except Exception as ex:
            self.error = repr(ex); self.favorites = []; self.next_id = 1
            try: os.replace(self.path, self.path + '.corrupt')
            except Exception: pass
            print("History favorites unreadable (%s): set aside, starting again from scratch (%r)" % (self.path, ex), flush=True)

    # ---- one history per adventure
    def _load_index(self):
        self.index = {}
        p = os.path.join(self.folder, INDEX_FILE) if self.folder else None
        if not p or not os.path.exists(p): return
        try:
            with open(p, encoding='utf-8') as f: d = json.load(f)
            banks = d.get('banks') if isinstance(d, dict) and d.get('version') == RECENT_VERSION else None
            if not isinstance(banks, dict): raise ValueError('unknown format')
            self.index = {k: v for k, v in banks.items() if isinstance(k, str) and isinstance(v, dict) and isinstance(v.get('id'), str) and re.fullmatch(r'[0-9a-f]{8,32}', v['id'])}
        except Exception as ex:
            self.error = repr(ex)
            try: os.replace(p, p + '.corrupt')
            except Exception: pass
            print("History index unreadable (%s): set aside (%r)" % (p, ex), flush=True)

    def _write_index(self):
        if self.folder: self._write(os.path.join(self.folder, INDEX_FILE), {'version': RECENT_VERSION, 'banks': self.index}, 'History index not saved: %s')

    def set_adventure(self, ident):
        """Switches to the history of adventure `ident` (None: none, the title screen): the current one is written first."""
        if ident == self.adventure: return
        self.apply_removals(); self.store(True)
        self.adventure = ident; self._last = None; self._battle_log = []; self._dirty_recent = False; self._dirty = False
        self.recent_path = os.path.join(self.folder, ident + '.json') if (self.folder and ident) else None
        self.path = os.path.join(self.folder, ident + '.favorites.json') if (self.folder and ident) else None
        self._take_legacy_favorites()
        self.load(); self._load_recent()                    # (favorites first: a star whose favorite is gone is dropped from the latest elements)

    def _take_legacy_favorites(self):
        """The common favorites become those of the first adventure that becomes current (in practice, the main game)."""
        old = self.legacy_favorites
        if not self.path or os.path.exists(self.path) or not old or not os.path.exists(old): return
        try: os.makedirs(self.folder, exist_ok=True); os.replace(old, self.path)
        except Exception as ex: print('Common favorites not taken over (%r)' % (ex,), flush=True)

    def new_adventure(self):
        """A new game: a new, empty history. The history (a single file), if it is still there, becomes this one."""
        ident = uuid.uuid4().hex[:12]
        if self.folder and not self.index:
            old = os.path.join(os.path.dirname(self.folder), LEGACY_RECENT)
            try:
                if os.path.exists(old): os.makedirs(self.folder, exist_ok=True); os.replace(old, os.path.join(self.folder, ident + '.json'))
            except Exception as ex: print('History of #396 not taken over (%r)' % (ex,), flush=True)
        self.set_adventure(ident)
        return ident

    def bank_loaded(self, bank, uid):
        """The engine loaded adventure log `bank` (1-based; `uid` = the game's unique ID read just after): the history of that log, or a new one if the log was never seen or was overwritten by another game."""
        e = self.index.get(str(bank))
        if e is not None and e.get('uid') == uid: self.set_adventure(e['id'])
        else: self.new_adventure()
        self.index[str(bank)] = {'id': self.adventure, 'uid': uid}; self._write_index()

    def bank_written(self, bank, uid):
        """The engine wrote adventure log `bank` (church, auto-save): it now carries the history of the adventure being played."""
        if self.adventure is None: self.new_adventure()
        self.index[str(bank)] = {'id': self.adventure, 'uid': uid}; self._write_index(); self.store(True)

    def _load_recent(self):
        """Reads the latest dialogues and battles, after the favorites (a star whose favorite no longer exists is dropped). Unreadable file: set aside (.corrupt), empty history; an invalid
        element is ignored without losing the others."""
        self.dialogues = []; self.battles = []
        p = self.recent_path
        if not p or not os.path.exists(p): return
        try:
            with open(p, encoding='utf-8') as f: d = json.load(f)
            if not isinstance(d, dict) or d.get('version') != RECENT_VERSION or not isinstance(d.get('dialogues'), list) or not isinstance(d.get('battles'), list): raise ValueError('unknown format')
            favs = {f.fav for f in self.favorites}
            for name, kind, cap, out in (('dialogues', TYPE_DIALOGUE, MAX_DIALOGUES, self.dialogues), ('battles', BATTLE_TYPE, MAX_BATTLES, self.battles)):
                for x in d[name]:
                    e = Element.from_dict(x, self._num(), recent=True) if isinstance(x, dict) else None
                    if e is None or e.type != kind: continue
                    if e.fav not in favs: e.fav = None
                    out.append(e)
                del out[:-cap]
        except Exception as ex:
            self.error = repr(ex); self.dialogues = []; self.battles = []
            try: os.replace(p, p + '.corrupt')
            except Exception: pass
            print("History unreadable (%s): set aside, starting again from scratch (%r)" % (p, ex), flush=True)

    def store(self, force=False):
        """Writes the files that changed (favorites, latest elements). Writes are grouped: at most one every STORAGE_DELAY seconds, `force` for closing. -> True if a file was written."""
        if not (self.path or self.recent_path) or not (self._dirty or self._dirty_recent): return False
        now = self.clock()
        if not force and now - self._t_write < STORAGE_DELAY: return False
        self._t_write = now; written = False
        if self._dirty and not self.path: self._dirty = False                                    # (no adventure: the favorites stay in memory)
        if self._dirty and self._write(self.path, {'version': VERSION, 'next': self.next_id, 'favorites': [e.to_dict() for e in self.favorites]}, 'History favorites not saved: %s'):
            self._dirty = False; written = True
        if self._dirty_recent and not self.recent_path: self._dirty_recent = False                # (no adventure: nothing to keep)
        if self._dirty_recent and self._write(self.recent_path, {'version': RECENT_VERSION, 'dialogues': [e.to_dict() for e in self.dialogues], 'battles': [e.to_dict() for e in self.battles]}, 'History not saved: %s'):
            self._dirty_recent = False; written = True
        return written

    def _write(self, path, d, failure):
        """Atomic write (temporary file then replacement); an error is printed and kept, never raised."""
        try:
            os.makedirs(os.path.dirname(os.path.abspath(path)), exist_ok=True)
            tmp = path + '.tmp'
            with open(tmp, 'w', encoding='utf-8') as f: json.dump(d, f, ensure_ascii=False, separators=(',', ':'))
            os.replace(tmp, path)
            return True
        except Exception as ex:
            self.error = repr(ex); print(failure % (ex,), flush=True)
            return False

    # ---- lists
    def entries(self, tab, favorites_only=False):
        """Elements of a history tab, from oldest to newest: 'dialogues' or 'combats' (and 'favoris': all the favorites, see below). `favorites_only`: the window's "Favorites only" option -> only the
        favorites of that kind of element (dialogues or battles): those in the file, therefore also those of previous sessions, in the order in which they were made favorites (the most recent at the bottom)."""
        if favorites_only and tab in ENTRIES_TYPE: return [f for f in self.favorites if f.type == ENTRIES_TYPE[tab]]
        return list({'dialogues': self.dialogues, 'battles': self.battles, 'favorites': self.favorites}.get(tab, ()))

    # ---- favorites
    def is_favorite(self, e):
        """Is the element's star solid? A favorite marked for removal shows an empty star but stays a favorite until the window is left."""
        return e is not None and e.fav is not None and e.fav not in self.removing

    def toggle_favorite(self, e):
        """Makes the element a favorite (a copy is kept in the file, immediately) or unstars it. Unstarring only MARKS the favorite: it stays in the file and in "Favorites only",
        with an empty star, until the history window is left (apply_removals); starring it again cancels the mark (same number, same place). -> True if the star is now solid."""
        if e is None: return False
        if e.fav is not None:
            if e.fav in self.removing: self.removing.discard(e.fav); return True
            self.removing.add(e.fav); return False
        if len(self.favorites) >= MAX_FAVORITES: del self.favorites[0]
        copied = Element(self._num(), e.type, e.t, e.name_str, e.text, [dict(x) for x in e.enemies], e.gold, e.xp, e.outcome, fav=self.next_id, objects=[dict(o) for o in e.objects], mid=e.mid)
        copied.log = [list(m) for m in e.log]; copied.replay = e.replay              # (a battle favorite takes its messages and its replay with it)
        if e.linked: copied.seg, copied.val, copied.linked, copied.waiting = e.seg, dict(e.val), True, e.waiting      # (already stored by key: an element read from the file may not have its text yet)
        else: self._link(copied)
        e.fav = self.next_id; self.next_id += 1
        self.favorites.append(copied); self._dirty = self._dirty_recent = True; self.store(True)
        return True

    def _model(self, mid):
        """Text of message `mid` in the game files (requested from the engine; kept), or None (no engine, unknown message)."""
        if mid in self._models: return self._models[mid]
        cap = self._cap
        if cap is None or not hasattr(cap, 'model'): return None
        try: raw_value = cap.model(mid)
        except Exception: raw_value = None
        self._models[mid] = raw_value
        return raw_value

    def _link(self, f):
        """A dialogue (favorite or latest element) whose key is known: if the text of the game files gives back EXACTLY the text read, the favorite is stored by key (the file will not keep the text); otherwise it keeps its text."""
        if f.type != TYPE_DIALOGUE or not f.mid: return
        raw_value = self._model(f.mid)
        l = binding(raw_value, f.text) if raw_value else None
        if l is not None: f.seg, f.val = l; f.linked = True; f.waiting = False

    def _resolve(self):
        """Requests again from the engine the texts of the favorites stored by key (0.13 ms per call: the file's 500 favorites in 65 ms). A message that no longer exists or no longer has this page: a line says so, with the key."""
        if self._cap is None: return
        for f in self.favorites + self.dialogues:                                     # (dialogues: those read from the file of the latest ones)
            if not f.waiting: continue
            f.text = linked_text(self._model(f.mid), f.seg, f.val) or tr(MISSING) % message_key(f.mid)
            f.waiting = False; f.n = self._num()                                   # (new number: the layout kept by the window is no longer valid)

    def refresh(self):
        """When the history is opened: the texts of the favorites stored by key are requested again from the engine. The game files do not change while the viewer is running, but the engine chooses some
        variants of a text according to the current game (the hero's gender: "ma mignonne" / "mon chou"): a favorite therefore shows the text as the current game would give it."""
        self._models.clear()
        for f in self.favorites:
            if f.linked: f.waiting = True
        try: self._resolve()
        except Exception as ex: self.error = repr(ex); print('History: favorites text not requested again (%r)' % (ex,), flush=True)

    def apply_removals(self):
        """The history window is left (back to the Pause menu, menu closed, game closed): the favorites marked by toggle_favorite are removed and the file is written."""
        ids, self.removing = self.removing, set()
        if not ids: return
        gone = [f for f in self.favorites if f.fav in ids]
        self.favorites = [f for f in self.favorites if f.fav not in ids]
        for f in gone: self._drop_replay(f.replay, self.battles)                  # (favorites and latest battles belong to the same adventure)
        for e in self.dialogues + self.battles:
            if e.fav in ids: e.fav = None
        self._dirty = self._dirty_recent = True; self.store(True)

    def remove(self, e):
        """Deletes element `e` from the adventure's history (the window's trash): the latest element and, when it is a favorite, its copy among the favorites (or the reverse, from "Favorites only");
        its replay file goes with it. -> True if something was deleted."""
        if e is None: return False
        fav = e.fav
        same = lambda x: x is e or (fav is not None and x.fav == fav)
        gone = [x for x in self.dialogues + self.battles + self.favorites if same(x)]
        if not gone: return False
        self.dialogues = [x for x in self.dialogues if not same(x)]; self.battles = [x for x in self.battles if not same(x)]; self.favorites = [x for x in self.favorites if not same(x)]
        if fav is not None: self.removing.discard(fav)
        if self._last is not None and same(self._last): self._last = None
        for g in gone: self._drop_replay(g.replay, self.battles)
        self._dirty = self._dirty_recent = True; self.store(True)
        return True

    def clear(self, kind=None):
        """Empties the adventure's history but its favorites (`kind` = 'dialogues', 'battles' or None for both, chosen in the window): every latest element of that kind without a
        solid star goes, with its replay file; the favorites stay, in the list and in "Favorites only". -> number of elements deleted."""
        kinds = [k for k in ('dialogues', 'battles') if kind in (None, k)]
        gone = [x for k in kinds for x in getattr(self, k) if not self.is_favorite(x)]
        if not gone: return 0
        for k in kinds: setattr(self, k, [x for x in getattr(self, k) if self.is_favorite(x)])
        if self._last is not None and self._last in gone: self._last = None
        for g in gone: self._drop_replay(g.replay, self.battles)
        self._dirty_recent = True; self.store(True)
        return len(gone)

    def remove_favorite(self, ident):
        self.favorites = [f for f in self.favorites if f.fav != ident]
        for e in self.dialogues + self.battles:
            if e.fav == ident: e.fav = None
        self._dirty = self._dirty_recent = True; self.store(True)

    # ---- adding
    def add(self, text, name_str, t, mid=None):
        """Adds a dialogue (raw engine text, name displayed by the game or None, message number in the game files or None); -> the Element, or None (empty, duplicate). Stored by key when the game files
        give back exactly this text (see _link), so the file stays small."""
        text = clean(text)
        if not text: return None
        name_str = (without_marks(str(name_str)).strip()[:60] or None) if name_str else None
        e = Element(self._num(), TYPE_DIALOGUE, int(t), name_str, text, mid=mid if _is_integer(mid) and 0 < mid < MSG_ID_MAX else None)
        d = self._last
        if d is not None and self.dialogues and self.dialogues[-1] is d and d.lookup_key() == e.lookup_key() and abs(e.t - d.t) <= TIME_MARGIN: return None             # the engine displayed the message again (page came back, question asked again)
        self._link(e)
        self.dialogues.append(e); self._last = e; self._dirty_recent = True
        if len(self.dialogues) > MAX_DIALOGUES: del self.dialogues[:len(self.dialogues) - MAX_DIALOGUES]
        return e

    def add_battle(self, battle, records=()):
        """Adds a finished battle (dict from battle_history.BattleSensor.do_update) with the messages recorded during it (`records`, for the rewind); -> the Element, or None."""
        e = battle_element(self._num(), battle)
        if e is None: return None
        e.log = battle_log(records)
        self.battles.append(e); self._dirty_recent = True
        if len(self.battles) > MAX_BATTLES:
            gone = self.battles[:len(self.battles) - MAX_BATTLES]; del self.battles[:len(self.battles) - MAX_BATTLES]
            for g in gone: self._drop_replay(g.replay, self.battles)
        return e

    # ---- link with the engine
    def do_update(self, engine, objects=None, names=None):
        """Once per engine step: stores the messages recorded by the Sensor (out-of-battle dialogues) and the finished battles (BattleSensor), and writes the favorites if needed."""
        if self.replaying: return                                                # (a replayed battle writes nothing to the history)
        try:
            cap = getattr(engine, 'sensor', None)
            if cap is not None and cap.active:
                self._cap = cap
                self._adventure_events(engine, cap)
                game = engine.state.part in (PART_TOWN, PART_BATTLE, PART_FIELD)
                if game and self.adventure is None: self.new_adventure()                  # (a game began without loading a log: a new game)
                received_list = cap.drain()
                if not game: self._wait = []
                else: self._pages(engine, received_list)
            cc = getattr(engine, 'battle_sensor', None)
            if cc is not None:
                for c in cc.do_update(engine):
                    e = self.add_battle(c, self._battle_log); self._battle_log = []
                    if e is not None and self._rec is not None: self._tail = [e, self._rec, REPLAY_TAIL]; self._rec = None
                tracking = getattr(cc, 'tracking', None)
                if tracking is None: self._battle_log = []          # no battle tracked (finished, or its start was not seen: a savestate loaded mid-battle): its messages belong to no battle
                self._record_replay(engine, tracking)
            self._resolve()
            self.store()
        except Exception as ex:                                              # the history must never stop the game
            if self.error is None: print('History: error (%r)' % (ex,), flush=True)
            self.error = repr(ex)

    # ---- battle replays: the state of the game when a battle begins (its entry cascade when it has one), then every input the engine receives until a little after its end
    def _record_replay(self, engine, tracking):
        intro = bool(getattr(engine, 'battle_intro', False)); engine.battle_intro = False
        if self._tail is not None:
            self._tail[2] -= 1
            if self._tail[2] <= 0 or tracking is not None or intro: self.flush_recording(engine)
        if not hasattr(engine, 'record_inputs'): return
        if (tracking is not None or intro) and self._rec is None and self._tail is None and self.snapshotter is not None and self.adventure and self.folder:
            try: self._rec = self.snapshotter(); engine.record_inputs(True); self._rec_state = engine.state; self._rec_wait = 0
            except Exception as ex: self._rec = None; print('Battle replay not recorded (%r)' % (ex,), flush=True)
        elif self._rec is not None and tracking is None:
            self._rec_wait += 1                                                                      # (the cascade, then the battle scene's loading, come before the engine's "start": a few hundred steps at most)
            if engine.state is not self._rec_state or self._rec_wait > REPLAY_START_WAIT: self._rec = None; engine.record_inputs(False)          # (savestate loaded in the middle, or no battle after all)
        elif self._rec is not None and engine.state is not self._rec_state: self._rec = None; engine.record_inputs(False)

    def flush_recording(self, engine):
        """Ends the recording of the last battle now and writes its replay file (in the background: a state weighs about 0.4 MB)."""
        if self._tail is None: return
        e, state, _ = self._tail; self._tail = None
        inputs = engine.record_inputs(False) if hasattr(engine, 'record_inputs') else None
        if not inputs or not self.folder or not self.adventure: return
        rel = '%s/%s.dqs' % (self.adventure, uuid.uuid4().hex[:12])
        e.replay = rel; self._dirty_recent = True
        threading.Thread(target=self._write_replay, args=(os.path.join(self.folder, rel), dict(state, battle_inputs=inputs)), daemon=True).start()

    @staticmethod
    def _write_replay(path, d):
        try:
            from dq4_pc.persistence import savestates as SS
            SS.write(path, d, {'battle_replay': True})
        except Exception as ex: print('Battle replay not saved (%r)' % (ex,), flush=True)

    def replay_path(self, e):
        """Replay file of battle `e` if it exists, else None."""
        if e is None or not getattr(e, 'replay', None) or not self.folder: return None
        p = os.path.join(self.folder, e.replay)
        return p if os.path.exists(p) else None

    def _drop_replay(self, rel, keep=()):
        """Deletes a replay file that no element refers to any more (`keep`: other elements still listed)."""
        if not rel or not self.folder or any(x.replay == rel for x in list(keep) + self.favorites): return
        try: os.remove(os.path.join(self.folder, rel))
        except OSError: pass

    def _adventure_events(self, engine, cap):
        """Title screen, adventure log loaded (Sensor hooks), adventure log written (GameCore.h_fclose) since the last step."""
        events = cap.drain_events() if hasattr(cap, 'drain_events') else []
        written = getattr(getattr(engine, 'core', None), 'written_saves', None)
        if written: events += [('written', n) for n in written if 1 <= n <= 5]; del written[:]          # (data9.dat is not an adventure log: only the number of the last one)
        for ev in events:
            if ev[0] == 'title': self.set_adventure(None)
            elif ev[0] == 'load': self.bank_loaded(ev[1], cap.unique_id())
            elif ev[0] == 'written': self.bank_written(ev[1], cap.unique_id())

    def _store_record(self, r):
        if r['cat'] == CATEGORY_BATTLE:                                            # battle messages do not enter the dialogues: they go with their battle
            if len(self._battle_log) < 2 * MAX_LOG: self._battle_log.append(r)
            return
        self.add(r['text'], r['val'] if r['kind'] == KIND_NAME else None, r['t'], r.get('mid'))

    def _release(self, n):
        """Stores the first `n` pending pages (all of them if n is None)."""
        k = len(self._wait) if n is None else min(n, len(self._wait))
        pages, self._wait = self._wait[:k], self._wait[k:]
        for r in pages: self._store_record(r)

    def _pages(self, engine, received_list):
        """The engine prepares ALL the pages of a message at once (several TextBuffer::cat in the same frame, same game time): record only those that the player has read, otherwise the history
        would show the next page before it was read. The first page is recorded right away; each time the end-of-page cursor goes out (the player turns the page, Engine.ui.msg['feed']) the next one
        is recorded; everything that remains is recorded when the message window closes or when a new message arrives. Battle messages (automatic scrolling) are never held back."""
        msg = getattr(getattr(engine, 'ui', None), 'msg', None)
        feed = bool(msg.get('feed')) if isinstance(msg, dict) else False
        fell = self._feed and not feed; self._feed = feed
        visible = bool(getattr(engine, 'msg_visible', True))
        if received_list:
            self._release(None)                                      # new message: the previous one is finished (its remaining pages have been read or skipped)
            self._has_been_seen = visible; self._n_att = 0
            prev = None
            for r in received_list:
                lookup_key = (r['kind'], r['val'], r['cat'], r['map'], r['t'])
                if prev is not None and lookup_key == prev and r['cat'] != CATEGORY_BATTLE: self._wait.append(r)                # next page of the same message
                else: self._store_record(r)
                prev = lookup_key
            return
        if not self._wait: return
        if visible: self._has_been_seen = True
        else: self._n_att += 1
        if (not visible and self._has_been_seen) or self._n_att > WINDOW_WAIT: self._release(None)      # the window closed (or never opened): the message is finished
        elif fell: self._release(1)


# ---------------------------------------------------------------------------------------------------------------------------------- hooks in the engine
class Sensor:
    """Hook on the engine (Unicorn): TextBuffer::cat, called once per message page. The recorded messages wait in `output` until History.do_update picks them up (each one: texte, genre, val = name that the
    game displays or None, cat, carte, t, mid = message number in the game files or None). The number comes from a second hook, on ui_MsgAdd(number, bool): TextBuffer::cat is called from there (the stack shows it);
    a page that does not come from it (text built by the program) has no number. An error in a hook must never stop the engine."""

    def __init__(self, engine):
        self.active = False; self.output = []; self._mid = None; self._buffer = None; self.events = []
        self.m = engine; c = self.c = engine.core
        try:
            import unicorn
            self.g_game = c.export('_ZN6status6g_GameE'); category = c.export('_ZN10TextBuffer3catEPKcS1_')
            if not self.g_game or not category: return
            c.uc.hook_add(unicorn.UC_HOOK_CODE, self._cat, None, category, category)
            self.active = True
        except Exception as ex:
            print('History: hooks not installed (%r)' % (ex,), flush=True)
            return
        try:
            add = c.export(SYM_UI_MSGADD)
            if add: c.uc.hook_add(unicorn.UC_HOOK_CODE, self._add, None, add, add)
        except Exception as ex:
            print('History: message numbers not captured (%r)' % (ex,), flush=True)
        try:                                                                       # (which adventure is being played; read-only, like the others)
            for sym, f in ((SYM_LOADBANK, self._loadbank), (SYM_TITLE, self._title)):
                a = c.export(sym)
                if a: c.uc.hook_add(unicorn.UC_HOOK_CODE, f, None, a, a)
        except Exception as ex:
            print('History: adventure logs not followed (%r)' % (ex,), flush=True)

    def _loadbank(self, uc, addr, size_value, _):
        try: self.events.append(('load', (uc.reg_read(self.c.XREG[0]) & 0xffffffff) + 1))
        except Exception: pass

    def _title(self, uc, addr, size_value, _):
        self.events.append(('title',))

    def drain_events(self):
        s, self.events = self.events, []
        return s

    def unique_id(self):
        """The game's unique ID (GameStatus::getUniqueID: status::g_Game + 8, a random number 0-255 drawn at a new game and kept in the saves)."""
        try: return struct.unpack('<I', self.c.mem(self.g_game + 8, 4))[0]
        except Exception: return None

    def _add(self, uc, addr, size_value, _):
        """Entry of ui_MsgAdd: the message number (1st argument) that TextBuffer::cat is going to receive."""
        try: self._mid = uc.reg_read(self.c.XREG[0]) & 0xffffffff
        except Exception: self._mid = None

    def model(self, mid):
        """Text of message `mid` as the engine pulls it from the game files (TextAPI::extractText, kind 1 = message): raw, with the page breaks "㈡" and the variables "[NONE 1,0]"; None if the engine has none.
        To be called between two frames (never from a hook), like the names in battle_history."""
        try:
            c = self.c; f = c.export(SYM_EXTRACT)
            if not f or not isinstance(mid, int) or not 0 < mid < MSG_ID_MAX: return None
            self._buffer = c.scratch('history', 8192)          # buffer taken from the engine heap, never kept above a loaded savestate
            c.mem_w(self._buffer, b'\0' * 16)
            c.call(f, self._buffer, (1 << 24) | mid, label='message text', timeout_s=10)
            t = c.read_cstr(self._buffer).decode('utf-8', 'replace')
            return t if t.strip() and not t.startswith('<ERR') else None
        except Exception:
            return None

    def time_and_key(self):
        """-> (game time in 1/60 s, game identifier) read in status::g_Game."""
        try:
            t, uid = struct.unpack('<2I', self.c.mem(self.g_game + 4, 8)); return t, uid
        except Exception:
            return None, 0

    def drain(self):
        s, self.output = self.output, []
        return s

    def _stack(self, uc, n=24):
        """Names of the functions on the call stack (chain of frame pointers), from the immediate caller to the root."""
        c = self.c; names = [c.where(uc.reg_read(c.XREG[30])).split('+')[0]]
        fp = uc.reg_read(c.XREG[29])
        for _ in range(n):
            try: nfp, nlr = struct.unpack('<QQ', c.mem(fp, 16))
            except Exception: break
            if not nfp or nfp <= fp: break
            names.append(c.where(nlr).split('+')[0]); fp = nfp
        return names

    def _cat(self, uc, addr, size_value, _):
        try:
            c = self.c; x1, x2 = uc.reg_read(c.XREG[1]), uc.reg_read(c.XREG[2])
            text = c.read_cstr(x1).decode('utf-8', 'replace') if x1 else ''
            if not text.strip(): return
            name_str = c.read_cstr(x2).decode('utf-8', 'replace').strip() if x2 else ''           # the name that the game displays on the message window (empty: none)
            e = self.m.state
            stack = self._stack(uc)
            battle = e.part == PART_BATTLE or any('Battle' in s for s in stack)
            t, _u = self.time_and_key()
            mid = getattr(self, '_mid', None) if stack and stack[0] == SYM_UI_MSGADD else None            # (the immediate caller of TextBuffer::cat is ui_MsgAdd: the number comes from that call)
            self.output.append({'text': text, 'kind': KIND_NAME if name_str else KIND_GENERAL, 'val': name_str or None, 'cat': CATEGORY_BATTLE if battle else CATEGORY_TERRAIN,
                                'map': 'world' if e.part == PART_FIELD else e.game_map, 't': t or 0, 'mid': mid})
            if len(self.output) > 500: del self.output[:250]                      # (never emptied for lack of History.do_update: it does not grow endlessly)
        except Exception:
            pass
