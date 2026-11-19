""""History" window ('history' page of the settings menu, see pause.py): two tabs, "Dialogue" (outside battle) and "Battles"; the most recent at the bottom. A "Favorites only" checkbox (to the right of the tabs) keeps in
the open tab's list only its favorites; it is shared by both tabs (it stays checked when the tab changes and when the window is reopened) and its state is saved in the settings (key `history_favorites_only`, written on every change):
it is restored as is from one session to the next, like the favorites themselves (file history_favorites.json, see history.py).

THE LIST IS A SINGLE CONTINUOUS COLUMN: the oldest entries at the top, the most recent at the bottom, and the view opens at the very bottom (last entry visible). Scrolling is continuous, per pixel: no page, no notch, no
layout that depends on the position (the boxes are laid out once and for all, the position only moves them); an entry that extends past the edge of the list is simply clipped by a scissor rectangle (glScissor), like
scrolling text. List shorter than the window: stuck to the bottom, like a message thread (the most recent always stays in the same place, at the bottom). Pure functions: `arrange` (stacking), `element_au_repere`.

Each element is drawn in a game DIALOGUE BOX (the field message window, 3 lines: frame 452 x 126 interface units, taken from the original layout; same scale as in the game; class
`Box`), with the game's frame and name tab (frameData 192 and 191, drawn by ui_menu.MessageWindow), the original font SE-GARRIR and the lines laid out as in the game: a dialogue with the speaker's name
in the tab ONLY if the game displayed it when it was said; a battle with its outcome, each enemy species (which is defeated, fled, vanished or remains), the gold and experience gained and the items obtained.
A dialogue fits in a 3-line box (the rest is in a following box, "2/2": a simple label, scrolling does not stop there). A BATTLE GROWS IN HEIGHT to hold everything: the box has as many
lines as the battle requires, at least 3; the game's frame is stretched (it is a nine-slice frame: only the middle grows, the corners keep their size); beyond MAX_BATTLE_LINES lines, the rest
continues in a following box. A star at the top right of each element makes it a favorite (it is then kept
in a file until the star is removed; the latest 100 dialogues and 100 battles are also kept from one session to the next). The window background is as transparent as the other game windows (hud_mobile.GAME_OPACITY).
The game DOES NOT STOP while the window is open (no pause in any menu): no key or click reaches the game, but it keeps running and writing to the history; the list follows (`follow_game`: new
messages are added at the bottom when the view is at the bottom; when reading further up, the list does not move, it updates on returning to the bottom).
Keyboard: up / down (previous / next message, repeated while the key is held), previous / next page (one window page minus two lines), Home / End, camera keys (tab, looping), Enter, Menu or Action
(star of the selected message), F or Map ("Favorites only" checkbox), the history key ("Dialogue" -> "Battles" -> close), Esc / Cancel (back). Mouse: wheel (2 lines per notch), scrollbar (arrows: one line,
track: one page, thumb: drag), drag in the list (the content follows the pointer), click on a tab, on the checkbox or on a star.
SELECTED MESSAGE (`selected`, target of the Enter key): up / down move from message to message (they do not scroll the list); the view scrolls ONLY to show the selected message in full, when it is cut by an edge of the
window or outside the window, and by the minimum necessary (its edge reaches the window edge: `offset_to_see`). With the mouse, the hovered message is the selected message. The selected message carries the small golden arrow, with the keyboard
as with the mouse, and nothing else: neither grayed nor lightened on hover or on selection (an exception to the general rule of the menus). Scrolling with the wheel, the bar or by dragging does not change the selected message; with the keyboard, a selected
message that is no longer in the window at all is first replaced by the nearest visible message."""
import time
import pyglet
from pyglet import gl
from dq456_pc.core import history as HI
from dq456_pc.menus import battle_rewind as BR
from dq456_pc.menus import hud_mobile as HM
from dq456_pc.persistence import settings as RG
from dq456_pc.menus import ui_menu as UM
from dq456_pc.language import tr, N_
from dq456_pc.window import inputs as EN

GOLD = (255, 235, 4); WHITE = (255, 255, 255); GRAY = (150, 150, 150); HELPTEXT = (175, 175, 175); STAR = (255, 210, 40); EMPTY_STAR = (20, 20, 20)
TABS = ((N_('settings.dialogue'), 'dialogues'), (N_('menus.battles'), 'battles'))            # (names translated when drawn)
O_DIALOGUES, O_BATTLES = 0, 1
FILTER_CAPTION = N_('menus.favorites_only')
CLEAR_CAPTION = N_('menus.clear_all')                                    # plate of the tab row: empties the adventure's history but its favorites; three choices, no Yes / No (choosing is the confirmation)
CLEAR_QUESTION = N_('menus.clear_what')
CLEAR_DETAIL = N_('menus.favorites_kept')
CLEAR_CHOICES = ((N_('menus.clear_dialogues'), 'dialogues'), (N_('menus.clear_battles'), 'battles'), (N_('menus.clear_all'), None))
TRASH = (200, 70, 60)                                               # trash of an element when hovered
TRASH_OFF = (70, 70, 70)                                            # grayed trash of a favorite (a favorite cannot be deleted: unstar it first)
BOX_SCALE = 1.12                 # enlargement of the game windows relative to H / 800 (= window.UI_ZOOM): the history box has the size of a game dialogue box on screen
TEXT_SCALE = 1.09                     # one pixel of the original font (SE-GARRIR) = 1.09 interface units in the game's message canvas (measured: a line of 371 font pixels = 407 screen pixels at scale 1.008; the layout header states 1.105, the engine rounds the advances)
EMPTY_MESSAGES = {'dialogues': N_('menus.no_dialogue_yet'), 'battles': N_('menus.no_battle_yet')}
EMPTY_FAVORITES = {'dialogues': N_('menus.no_favorite_dialogue_uncheck_favorites'),
                 'battles': N_('menus.no_favorite_battle_uncheck_favorites')}            # (translated when drawn, as a whole before being wrapped at words)


def wrap_words(text, width_px, max_width):
    """Splits `text` into lines at spaces so that none exceeds `max_width` (width_px(t) = width of a line t, in the unit of max_width). A single word wider than the limit stays alone on its line (it cannot be split). -> list of lines, never empty."""
    lines = []; cur = ''
    for word in text.split():
        cand = word if not cur else cur + ' ' + word
        if cur and width_px(cand) > max_width: lines.append(cur); cur = word
        else: cur = cand
    lines.append(cur)
    return lines


REWIND_LINES = 4                    # text lines of the rewind's message box (the box grows like a battle box)
NOTICE_SECONDS = 3.0
NO_REWIND = N_('menus.battle_cannot_replayed_was_recorded')
REWIND_TITLE = N_('menus.battle_replay')
REWIND_END = N_('menus.end_battle')

PAGE_MESSAGES = 3                   # messages skipped by PgUp / PgDn (and the L / R keys)
WHEEL_STEP = 2.0                   # text lines (Box.STEP: 28 units) per wheel notch: a fine, constant step, never a whole entry
ENTRIES_MARGIN = 6.0                    # (in k) empty space above the first box and below the last box of the list (the content is never glued to the edge of the clipping window)
TOLERANCE_PX = 0.5                   # pixels: below this, a message is "fully visible" (drawing rounding)
ELEMENT_SPACING, PAGE_SPACING = 12.0, 4.0      # (in k) gap between two elements, between two boxes of the same element
MAX_BATTLE_LINES = 12               # text lines (header included) that a battle box can hold before continuing in a following box (the box is then 126 + 9 x 28 = 378 units high)


def arrange(inputs, border_top, tab_top, spacing, page_spacing, margin):
    """Stacks the whole list in ONE column, from the oldest (at the top) to the most recent (at the bottom). `inputs`: one tuple per element, (number of boxes, name tab on the first one?) or (number of boxes, tab?,
    [frame height of each box]) when the boxes do not all have the same height (a battle grows with its text); `border_top` is the height of the others. Distances in pixels, counted from
    the top of the content (downward): -> (boxes, starts, ends, height).
    boxes: (element, box, number of boxes, top, tab top, frame top); `topmost` = top edge of the box, name tab included (the frame starts `tab_top` lower);
    starts[i], ends[i]: top of the first box and bottom of the last box of element i; height: content height, top and bottom margins included (0 if the list is empty).
    Does not depend on any scroll position: the position only moves everything."""
    boxes = []; starts = []; ends = []; y = margin
    for i, ent in enumerate(inputs):
        num, with_name = ent[0], ent[1]; tops = ent[2] if len(ent) > 2 else ()
        starts.append(y)
        for p in range(max(1, num)):
            hn = tab_top if (p == 0 and with_name) else 0.0; hc = tops[p] if p < len(tops) else border_top
            boxes.append((i, p, max(1, num), y, hn, hc)); y += hn + hc
            if p < max(1, num) - 1: y += page_spacing
        ends.append(y); y += spacing
    return boxes, starts, ends, ((y - spacing + margin) if inputs else 0.0)


def extent(starts, ends, hc, i):
    """What must be shown for message i to be "fully visible": (top, bottom) in pixels from the top of the content. The message itself (starts[i]: name tab included, ends[i]); for the first and the last
    of the list, plus the list margin (the first goes up to the top of the content, the last down to the bottom: when it gets there, the list is at the very top / the very bottom)."""
    return (0.0 if i == 0 else starts[i]), (hc if i == len(starts) - 1 else ends[i])


def offset_to_see(starts, ends, hc, hv, scroll_offset, i):
    """New offset of the view (pixels from the bottom: 0 = all the way down) that shows message i in full, changing the offset BY THE MINIMUM: unchanged if the message is already fully visible, otherwise just what is needed for
    its cut edge to reach the window edge (top or bottom). A message taller than the window: its start at the top of the window. The window is hv pixels tall and shows, from the top of the content, hc - scroll_offset - hv to hc - scroll_offset."""
    topmost, bottom = extent(starts, ends, hc, i); top = hc - scroll_offset - hv
    if bottom - topmost >= hv: top = topmost
    elif topmost < top - TOLERANCE_PX: top = topmost
    elif bottom > top + hv + TOLERANCE_PX: top = bottom - hv
    else: return scroll_offset
    return min(max(0.0, hc - hv), max(0.0, hc - hv - top))


def visible_elements(starts, ends, hc, hv, scroll_offset, fully_visible_only):
    """Indices of the messages visible in the window (see offset_to_see): those that are entirely in it (`fully_visible_only`), otherwise those that are at least partly in it."""
    top = hc - scroll_offset - hv; r = []
    for i in range(len(starts)):
        topmost, bottom = extent(starts, ends, hc, i)
        if (topmost >= top - TOLERANCE_PX and bottom <= top + hv + TOLERANCE_PX) if fully_visible_only else (ends[i] > top and starts[i] < top + hv): r.append(i)
    return r


def game_time(t):
    """Game time (1/60 s) -> "1:05:12"."""
    s = max(0, int(t)) // 60
    return '%d:%02d:%02d' % (s // 3600, s % 3600 // 60, s % 60)


def next_tab(i, d=1): return (i + d) % len(TABS)


class Box:
    """Field dialogue box (MenuMessage type 0) with 3 lines, in game interface units (800 high): the size of the frame (frameData 192), of the name tab (frameData 191) and the placement of the text
    lines. The dimensions come from the original layout when it is loaded (`from_ml`), otherwise from values measured on game screenshots. A single box for everything: 1, 2 or 3 lines, dialogue or battle."""
    WIDTH, UP = 452.0, 126.0                  # frame: x -223 to 229, z -251 to -125
    TAB_L, TAB_H = 246.0, 32.0           # name tab: x -223 to 23, z -125 to -93 (extends above the frame)
    LINES, STEP = 3, 28.0                      # three lines of 28 (PageLayout: limit_lines(types[0], 3, 28.0))
    TEXT_X, BASE_1 = 12.0, 37.2               # left edge of the text and baseline of the 1st line: distances from the frame's top-left corner (measured on a game screenshot: text 11 px from the frame's left stroke, 1st baseline 31 px from the top stroke, at scale 1.008)
    NAME_X, NAME_TOP = 118.5, -21.0             # middle of the name (from the frame's left edge) and top of the name text (from the top of the frame: MenuMessage.m_who, 21 above) -- fallback without layout

    def __init__(self, wid=None, topmost=None, tab=None, x0=-223.0, z0=-251.0, win=(0.0, 10.0, 86.0), text_scale=TEXT_SCALE):
        if wid: self.WIDTH = wid
        if topmost: self.UP = topmost
        if tab: self.TAB_L, self.TAB_H = tab
        self.x0, self.z0, self.win, self.text_scale = x0, z0, tuple(win), text_scale

    @classmethod
    def from_ml(cls, ml):
        """Box read from the original layout (PageLayout); the measured values if it is missing or unusable."""
        try:
            t = ml.message['types'][0]; vt = t['frame_mesh']['vtx']; xs = [v[0] for v in vt]; zs = [v[1] for v in vt]
            tab = None; wn = int(t.get('frame', UM.BORDER_WITH_NAME + 1)) - 1                  # (the frame with a name tab: just before type 0's)
            if len(ml.borders) > wn:
                c = ml.borders[wn]['vtx']; hs = [v for v in c if v[1] > max(zs) + 0.5]
                if hs: tab = (max(v[0] for v in hs) - min(v[0] for v in hs), max(v[1] for v in hs) - max(zs))
            return cls(max(xs) - min(xs), max(zs) - min(zs), tab, min(xs), min(zs), t['win'])
        except Exception:
            return cls()

    MARGINS = 120.0                              # (in units of k) margins of the history window around the box: left, star column, scrollbar

    def scale_factor(self, H, W, k):
        """Pixels per unit: that of the game windows (H / 800 x BOX_SCALE), reduced so that the box, its star column and the margins fit in the viewer window."""
        return max(0.3, min(H / 800.0 * BOX_SCALE, (W - 40 * k - self.MARGINS * k) / self.WIDTH))

    def base(self, rank):
        """Distance from the baseline of line `rank` (0, 1, 2...) to the top of the frame, units."""
        return self.BASE_1 + rank * self.STEP

    BASE_MSG = 35.0                            # same with the game's message font (the engine canvas's): the canvas starts 15 units below the top of the frame, a line's cell is 20 rows above the baseline

    def base_msg(self, rank):
        """Like `base`, for text drawn with the game's message font."""
        return self.BASE_MSG + rank * self.STEP

    def top_for(self, lines):
        """Frame height (units) for `lines` text lines: that of the game's box up to 3 lines, then one more line (STEP) per line."""
        return self.UP + max(0, int(lines) - self.LINES) * self.STEP

    def text_width(self):
        """Usable width of a text line (units): from the left edge of the text to the right margin of the canvas (the canvas is WIDTH - 18 wide)."""
        return self.WIDTH - self.TEXT_X - 12.0


def stretch_border(vtx, extra):
    """Vertices of a nine-slice frame (frameData 192: 12-unit corners, stretching middle) lengthened by `extra` units upward: every vertex of the upper half moves up, the top corners keep their size, the
    middle lengthens (its UVs do not change: the middle pattern is stretched, as the game does when it enlarges a frame). -> new list (the original layout is never modified)."""
    if not vtx: return []
    zs = [v[1] for v in vtx]; mi = (min(zs) + max(zs)) / 2.0
    return [[v[0], v[1] + (extra if v[1] > mi else 0.0)] + list(v[2:]) for v in vtx]


def box_lines(page, is_first, battle):
    """Number of text lines in a box: the page's rows, plus the header (outcome and time) on the first box of a battle; at least three (the game's box)."""
    return max(Box.LINES, len(page) + (1 if (battle and is_first) else 0))


def paginate(rows, with_header, lines=3):
    """Text rows -> pages of at most `lines` rows (at least one page, even empty); on the 1st page of a battle, the header (outcome and time) takes up one row."""
    pages = []; cap = max(1, lines - (1 if with_header else 0)); i = 0
    while True:
        pages.append(list(rows[i:i + cap])); i += cap; cap = lines
        if i >= len(rows): return pages


def wrap_like_the_game(font, text):
    """Lines of `text` wrapped the way the engine wraps a message (MessageFont.wrap_text: the text's line breaks kept, no trailing space on a line or empty line at the end; at least one line)."""
    lines = [l.rstrip(' ') for l in font.wrap_text(text)]
    while lines and not lines[-1]: lines.pop()
    return lines or ['']


def rows_of(e, measure, width_px, font=None):
    """Text rows of an element, wrapped at `width_px` (measure(string) -> width in the same unit): the text of a dialogue (its line breaks kept); for a battle one row per enemy species (with the
    fate of each), then the gold and experience, then the items (HI.battle_lines); a line too wide for the box continues on the next row. The outcome and the time are in the header.
    With `font` (the game's message font, MessageFont) the lines are wrapped exactly as the engine wraps its own and `measure`, `width_px` are not used."""
    cut = (lambda t: wrap_like_the_game(font, t)) if font is not None else (lambda t: HI.wrap_text(t, width_px, measure))
    if e.type != HI.BATTLE_TYPE: return cut(e.text)
    out = []
    for l in HI.battle_lines(e): out.extend(cut(l))
    return out


class HistoryView:
    def __init__(self, pause):
        self.P = pause; self.J = pause.J
        self.tab = O_DIALOGUES; self.elements = []
        self.pos = 0.0                                                  # scroll position, in pixels: 0 = all the way down (the most recent visible), larger = older (see scroll_offset and the reference point)
        self.selected = 0                                                    # selected message (golden arrow, Enter key): selected by up / down, by a click or, with the mouse, by hovering (see draw_all)
        self.hc = self.hv = 0.0; self.step = Box.STEP                  # height of the content, of the list window (pixels) and of a text line (pixels), measured at the last frame; before the first frame: nothing to scroll
        self.center_target = None                                             # element to bring to the middle of the view as soon as the list is measured (go_to)
        self.starts = []; self.ends = []                               # top of the first box and bottom of the last box of each element, pixels from the top of the content (measured at the last frame; empty until the list is measured)
        self.zones = []; self.star_zones = []; self.play_zones = []; self.trash_zones = []; self.tab_zones = []; self.bar = None; self.dragging_bar = None
        self.clear_zone = None                                          # "Clear all" plate
        self.zone_ret = None
        self.favorites_only = self._read_filter(); self.filter_zone = None  # "Favorites only" checkbox: checked? (saved setting); its on-screen area (click)
        self.drag = None                                               # drag in the list: [start y, start offset, moved?]
        self._spr = {}; self._lines = {}; self._layout = None; self._prev_s = None
        self._box = None; self._box_layout = None; self._wins = {}              # standard dialogue box (Box) and the two game message windows used to draw its frame (with / without tab)
        self.clock = time.monotonic
        self.rewind = None; self.rewind_zones = {}; self._rw_lines = {}           # battle rewind in progress (battle_rewind.Replay), its buttons' areas ('speed', 'quit'), its wrapped lines
        self.notice = None                                                        # (text, until): short message at the bottom of the list ("this battle cannot be replayed")

    # ---- data
    def enter(self, tab=O_DIALOGUES):
        """On opening the page: reloads the list, all the way down on the most recent element (then it follows the game: `follow_game`)."""
        self.tab = tab if 0 <= tab < len(TABS) else O_DIALOGUES
        self.dragging_bar = None; self.drag = None; self._lines.clear(); self.rewind = None; self.notice = None
        self.favorites_only = self._read_filter()
        h = getattr(self.J, 'history', None)
        if h is not None and hasattr(h, 'refresh'): h.refresh()          # (favorites are stored by key: their text is requested again from the game, see History.refresh)
        self.reload()

    def reload(self, keep=False):
        h = getattr(self.J, 'history', None)
        self.elements = h.entries(TABS[self.tab][1], self.favorites_only) if h is not None else []
        n = len(self.elements); self._layout = None; self.center_target = None; self.starts = []; self.ends = []
        if keep: self.selected = max(0, min(n - 1, self.selected))
        else: self.pos = 0.0; self.selected = max(0, n - 1)
        self.zones = []; self.star_zones = []; self.play_zones = []; self.trash_zones = []

    def follow_game(self):
        """The game runs behind the window and may write to the history (a dialogue, the end of a battle). Called every frame: when the view is all the way down (nothing is hidden further down), the list is replaced by the
        up-to-date list; the selected message stays the same (recognized by its object), except if it was the last one: the selection then follows the most recent. When reading further up, or when a drag or the bar is in progress, the list does not move
        (the reading does not jump); it updates as soon as we return to the bottom. -> True if the list changed."""
        h = getattr(self.J, 'history', None)
        if h is None or self.rewind is not None or self.scroll_offset() > 0.5 or self.drag is not None or self.dragging_bar is not None: return False
        el = h.entries(TABS[self.tab][1], self.favorites_only); anc = self.elements
        if len(el) == len(anc) and all(a is b for a, b in zip(el, anc)): return False
        cur = self.current_item(); follow = cur is None or self.selected >= len(anc) - 1
        self.elements = el; n = len(el); self._layout = None; self.center_target = None; self.starts = []; self.ends = []; self.zones = []; self.star_zones = []; self.play_zones = []; self.trash_zones = []; self.pos = 0.0
        i = None if follow else next((k for k, e in enumerate(el) if e is cur), None)
        self.selected = max(0, n - 1) if i is None else i
        return True

    def change_tab(self, i):
        i %= len(TABS)
        if i != self.tab: self.tab = i; self.reload()

    # ---- "Favorites only" checkbox: its state is a setting (history_favorites_only), kept from one session to the next
    def _read_filter(self):
        try: return self.J.reg['history_favorites_only'] is True
        except Exception: return False

    def _write_filter(self, on):
        """Saves the checkbox state in the settings (settings.json, immediately: an abrupt shutdown does not lose it). An error never prevents checking or unchecking."""
        try: reg = self.J.reg; reg['history_favorites_only'] = bool(on); reg.store()
        except Exception: pass

    def toggle_filter(self):
        """Checks or unchecks "Favorites only" (applies to both tabs, saved in the settings). The selected element, if it is in the new list, stays selected (and the view recenters on it); otherwise we go to the most recent."""
        cur = self.current_item(); lookup_key = cur.lookup_key() if cur is not None else None
        self.favorites_only = not self.favorites_only; self._write_filter(self.favorites_only); self.reload()
        if lookup_key is not None:
            for i in range(len(self.elements) - 1, -1, -1):
                if self.elements[i].lookup_key() == lookup_key: self.go_to(i); break
        return self.favorites_only

    def current_item(self):
        return self.elements[self.selected] if 0 <= self.selected < len(self.elements) else None

    def star(self, i=None):
        """Toggles the star of element i (the current element by default); -> True if the star is now solid. Unstarred, a favorite leaves the favorites at once: from "Favorites only"
        it leaves the list, the selection staying at its place."""
        h = getattr(self.J, 'history', None)
        if h is None: return False
        e = self.current_item() if i is None else (self.elements[i] if 0 <= i < len(self.elements) else None)
        if e is None: return False
        on = h.toggle_favorite(e)
        if not on and self.favorites_only: self.selected = self.elements.index(e) if e in self.elements else self.selected; self.reload(keep=True)
        return on

    def delete(self, i=None):
        """The trash of element i (the current element by default, Suppr key): it leaves the history at once (its replay too). A favorite's trash is grayed and does nothing. -> True if deleted."""
        h = getattr(self.J, 'history', None)
        e = self.current_item() if i is None else (self.elements[i] if 0 <= i < len(self.elements) else None)
        if h is None or e is None or h.is_favorite(e) or not h.remove(e): return False
        self.selected = min(self.selected, max(0, len(self.elements) - 2)); self.reload(keep=True)
        return True

    def ask_clear(self):
        """"Clear all": three choices, the dialogues, the battles or both (the favorites stay), with no Yes / No (choosing is the confirmation; Esc / right click: nothing).
        The open tab's choice is preselected."""
        buttons = [(caption, (lambda kind=kind: self.clear_all(kind))) for caption, kind in CLEAR_CHOICES]
        self.P.popup = dict(title=tr(CLEAR_QUESTION), model=CLEAR_QUESTION, values=(), detail=tr(CLEAR_DETAIL), buttons=buttons, choice=self.tab)

    def clear_all(self, kind=None):
        h = getattr(self.J, 'history', None)
        if h is None: return 0
        n = h.clear(kind); self.reload()
        return n

    def leave(self):
        """The window is left completely (Pause.back from this page, Pause.shutdown): a battle rewind in progress ends. Changing tab or filter is not leaving."""
        self.rewind = None

    # ---- battle rewind: the battle's messages replayed at their pace; only the speed button and a button to quit
    def open_rewind(self, i=None):
        """Opens the rewind of battle i (the selected element by default). A battle recorded has no messages: a short notice says so. -> True if the rewind is open."""
        e = self.current_item() if i is None else (self.elements[i] if 0 <= i < len(self.elements) else None)
        if e is None or e.type != HI.BATTLE_TYPE: return False
        f = getattr(self.J, 'start_battle_replay', None)
        if callable(f) and getattr(e, 'replay', None) and f(e): return True           # the real replay; without one (battle from before), its messages
        if not e.log: self.notice = (NO_REWIND, self.clock() + NOTICE_SECONDS); return False
        self.selected = self.elements.index(e); self.rewind = BR.Replay(e, self.clock); self._rw_lines = {}
        return True

    def close_rewind(self):
        """Back to the list, on the same battle."""
        self.rewind = None

    def speed(self):
        try: return self.J.reg['battle_speed']
        except Exception: return 1.0

    def cycle_speed(self):
        """The same "Battle speed" setting and cycle as in battle (Manual -> Normal -> Fast -> Very fast)."""
        f = getattr(self.J, 'change_battle_speed', None)
        if callable(f): f(); return
        try: self.J.reg['battle_speed'] = RG.next_battle_speed(self.J.reg['battle_speed']); self.J.reg.store()
        except Exception: pass

    def _rewind_key(self, symbol, action):
        K = pyglet.window.key
        if symbol in (K.ESCAPE, K.BACKSPACE) or action == 'B': self.close_rewind()
        elif action == 'battle_speed': self.cycle_speed()
        elif symbol in (K.RETURN, K.ENTER, K.SPACE) or action in ('A', 'menu'): self.rewind.advance(self.speed())
        return True

    # ---- continuous scrolling (no page, no notch: the position is a number of pixels)
    def span(self):
        """Distance (pixels) the view can go up from the bottom: 0 when the whole list fits in the window."""
        return max(0.0, self.hc - self.hv)

    def scroll_offset(self):
        """Actual offset of the view (pixels): the position clamped to the scroll range."""
        return min(max(self.pos, 0.0), self.span())

    def page_px(self): return max(self.step, self.hv - 2 * self.step)

    def _visible_elements(self, fully_visible_only):
        n = len(self.elements)
        if not n or len(self.starts) != n: return []
        return visible_elements(self.starts, self.ends, self.hc, self.hv, self.scroll_offset(), fully_visible_only)

    def _bring_into_view(self, fully_visible_only=False):
        """The selected message must be in the window: otherwise (the list scrolled without it: wheel, bar, drag, page), it is the nearest visible message (the first if it is above the window, the last if it is
        below). `fully_visible_only`: only fully visible messages count (failing that, those that are partly visible). -> True if the selected message changed."""
        v = self._visible_elements(fully_visible_only) or (self._visible_elements(False) if fully_visible_only else [])
        if not v or self.selected in v: return False
        self.selected = v[0] if self.selected < v[0] else v[-1]; return True

    def _show(self, i):
        """Scrolls by the minimum needed to show message i in full (nothing if the list is not measured yet: the view will settle as soon as it is)."""
        if len(self.starts) != len(self.elements): self.center_target = i; return
        self.pos = offset_to_see(self.starts, self.ends, self.hc, self.hv, self.scroll_offset(), i)

    def move_by(self, d):
        if self.rewind is not None: return
        self._move_by(d)

    def _move_by(self, d):
        """Up / down: the message d ranks further (negative: older, toward the top of the screen), clamped to the list; the view scrolls only if this message is not fully visible, by the minimum necessary. Repeated by Pause.do_update while the key is held."""
        n = len(self.elements)
        if not n: return
        if not self._bring_into_view(): self.selected = max(0, min(n - 1, self.selected + int(d)))          # (a selected message pushed out of the window by the wheel or the bar: this press replaces it with the nearest visible message, without advancing one more rank)
        self._show(self.selected)

    def to_top(self):
        if self.elements: self.selected = 0; self.pos = self.span()
    def to_bottom(self):
        if self.elements: self.selected = len(self.elements) - 1; self.pos = 0.0

    def scroll_by(self, px):
        """Mouse (wheel, bar, drag): the view goes up by `px` pixels toward the older ones (positive) or down toward the recent ones (negative), clamped to the scroll range."""
        self.pos = min(self.span(), max(0.0, self.scroll_offset() + px))

    def go_to(self, i):
        """Selects element i; the view recenters on it as soon as the list is measured (next draw)."""
        n = len(self.elements)
        if not n: return
        self.selected = max(0, min(n - 1, i)); self.center_target = self.selected

    # ---- inputs
    def key_press(self, symbol, modifiers=0):
        K = pyglet.window.key; P = self.P; action = self.J.reg.action_of(symbol)
        P.mouse_mode = False
        if self.rewind is not None: return self._rewind_key(symbol, action)
        if symbol in (K.ESCAPE, K.BACKSPACE) or action == 'B': P.back(); return True
        if action == 'up': self.move_by(-1); P._repeat(symbol, 'v', -1)          # (the keys of "Controls", no more fixed arrows)
        elif action == 'down': self.move_by(1); P._repeat(symbol, 'v', 1)
        elif symbol == K.PAGEUP or action == 'L': self.move_by(-PAGE_MESSAGES)                  # (3 messages per press, like the arrows but bigger; no more window page on the keyboard)
        elif symbol == K.PAGEDOWN or action == 'R': self.move_by(PAGE_MESSAGES)
        elif symbol == K.HOME: self.to_top()
        elif symbol == K.END: self.to_bottom()
        elif action == 'cam_left': self.change_tab(self.tab - 1)          # (the camera keys change the tab, looping; the movement keys only go through the messages)
        elif action == 'cam_right': self.change_tab(self.tab + 1)
        elif symbol == K.DELETE: self.delete()                                                # (the selected element goes, like its trash)
        elif symbol == K.F or action == 'map': self.toggle_filter()                          # (F, or the Map key: "Favorites only")
        elif action == 'A' and TABS[self.tab][1] == 'battles': self.open_rewind()                   # (Space / A: the play button of the selected battle, for the keyboard and the gamepad; Enter keeps the star)
        elif symbol in (K.RETURN, K.ENTER) or action in ('menu', 'A'): self.star()
        return True

    def wheel(self, sy):
        """One wheel notch = WHEEL_STEP text lines, toward the older ones when the wheel is scrolled up (a fine, constant step; proportional to the movement for touchpads)."""
        self.P.mouse_mode = True
        if self.rewind is not None: return
        self.scroll_by(max(-5.0, min(5.0, float(sy))) * WHEEL_STEP * self.step)

    def hovered(self, x, y):
        P = self.P; p = P.mouse_pos; P.mouse_pos = (x, y)
        if p is None or abs(x - p[0]) + abs(y - p[1]) < 3: return
        P.mouse_mode = True

    @staticmethod
    def _inside(z, x, y): return z is not None and z[0] <= x <= z[2] and z[1] <= y <= z[3]

    def click(self, x, y, button):
        M = pyglet.window.mouse; P = self.P
        P.mouse_mode = True; P.mouse_pos = (x, y)
        if self.rewind is not None:
            z = self.rewind_zones
            if button == M.RIGHT or self._inside(z.get('quit'), x, y): self.close_rewind()
            elif self._inside(z.get('speed'), x, y): self.cycle_speed()
            else: self.rewind.advance(self.speed())
            return
        if button == M.RIGHT: P.back(); return
        if self._inside(self.zone_ret, x, y): P.back(); return
        for z in self.tab_zones:
            if self._inside(z, x, y): self.change_tab(z[4]); return
        if self._inside(self.filter_zone, x, y): self.toggle_filter(); return
        if self._inside(self.clear_zone, x, y): self.ask_clear(); return
        b = self.bar
        if b and b['x0'] <= x <= b['x1'] and b['y0'] <= y <= b['y1']:
            if y > b['ptop']: self.scroll_by(self.step)                                 # up arrow: one line toward the older ones
            elif y < b['pbot']: self.scroll_by(-self.step)
            elif b['thumb'][0] <= y <= b['thumb'][1]: self.dragging_bar = b['thumb'][1] - y
            elif y > b['thumb'][1]: self.scroll_by(self.page_px())                       # track above the thumb: one page toward the older ones
            else: self.scroll_by(-self.page_px())
            return
        for z in self.star_zones:
            if self._inside(z, x, y): self.selected = z[4]; self.star(z[4]); return
        for z in self.play_zones:
            if self._inside(z, x, y): self.selected = z[4]; self.open_rewind(z[4]); return          # the play button: the ONLY way to replay a battle with the mouse
        for z in self.trash_zones:
            if self._inside(z, x, y): self.selected = z[4]; self.delete(z[4]); return
        pressed = None
        for (x0, y0, x1, y1, i) in self.zones:
            if x0 <= x <= x1 and y0 <= y <= y1: self.selected = i; pressed = i; break
        self.drag = [y, self.scroll_offset(), False, pressed]

    def release(self, x, y, button):
        self.dragging_bar = None; self.drag = None

    def drag_to(self, x, y):
        if self.rewind is not None: return
        b = self.bar
        if self.dragging_bar is not None:
            if not b: self.dragging_bar = None; return
            free = b['ptop'] - b['pbot'] - b['th']
            if free > 0:
                from_top = max(0.0, min(1.0, (b['ptop'] - (y + self.dragging_bar)) / free)) * (b['n'] - b['visible'])      # the scrollbar thumb gives the distance from the top of the content
                self.pos = min(self.span(), max(0.0, self.span() - from_top))
            return
        d = self.drag
        if d is None: return
        if not d[2] and not EN.is_drag(0, y - d[0]): return                         # (Windows' drag threshold)
        d[2] = True
        self.pos = min(self.span(), max(0.0, d[1] + (d[0] - y)))                    # the content follows the pointer, pixel by pixel (the pointer goes down: the list goes down, we move back toward the oldest)

    # ---- drawing
    def _bm(self):
        r = getattr(self.J, 'ui_render', None)
        return r.texts.bitmap if r is not None and getattr(r, 'texts', None) is not None else None

    def _bmm(self):
        """The game's message font (that of the engine's text canvas: all the game's glyphs, with its placement and wrapping rules) for the box text; None if it was not extracted (SE-GARRIR is kept)."""
        r = getattr(self.J, 'ui_render', None); t = getattr(r, 'texts', None) if r is not None else None
        return getattr(t, 'messages', None)

    def _text_width(self, bm, text, sc, size_value):
        if bm: return bm.width_px(text) * sc
        return self.P._label(text, size_value).content_width

    def _line(self, bm, text, x, ybase, sc, clr, size_value):
        """A text line whose baseline is at ybase: the game's bitmap font (one texture per line, tinted), otherwise the system font."""
        if not text.strip(): return
        if '$' in text and not hasattr(bm, 'wrap_text'): text = text.replace('$', '')          # (the patch's break point; the message font already leaves it out, the others would draw it)
        if bm:
            tex, w, h, base = bm.line(text)
            lookup_key = (text, clr); sp = self._spr.get(lookup_key)
            if sp is None or sp.image is not tex:
                if len(self._spr) > 600: self._spr.clear()
                sp = self._spr[lookup_key] = pyglet.sprite.Sprite(tex); sp.color = clr[:3]
            sp.update(x=x - bm.PAD * sc, y=ybase - (h - base) * sc, scale=sc); sp.draw()
        else:
            label = self.P._label(text, size_value, tuple(clr) + (255,)); label.x = x; label.y = ybase; label.draw()

    def _game_box(self):
        """Standard dialogue box (dimensions from the original layout if it is loaded); cached."""
        r = getattr(self.J, 'ui_render', None); ml = getattr(r, 'ml', None)
        if self._box is None or self._box_layout is not ml: self._box = Box.from_ml(ml) if ml is not None else Box(); self._box_layout = ml
        return self._box

    def _pages_of(self, bm, e, B, s, size_value):
        """Pages of an element: list of lists of text rows (3 rows at most, a battle's header included). Cached (key: element, scale)."""
        lookup_key = (e.n, e.type, int(s * 100))
        r = self._lines.get(lookup_key)
        if r is None:
            if len(self._lines) > 4000: self._lines.clear()
            if bm: mes = lambda t: bm.width_px(t) * B.text_scale
            else: mes = lambda t: self.P._label(t, size_value).content_width * 0.9 / s
            battle = e.type == HI.BATTLE_TYPE
            r = self._lines[lookup_key] = paginate(rows_of(e, mes, B.text_width(), self._bmm()), battle, MAX_BATTLE_LINES if battle else B.LINES)
        return r

    def _star(self, cx, cy, radius, solid):
        """Favorite star: golden when the element is a favorite, gray and hollow otherwise."""
        if solid:
            pyglet.shapes.Star(cx, cy, radius, radius * 0.45, 5, rotation=0, color=STAR + (255,)).draw()
        else:
            pyglet.shapes.Star(cx, cy, radius, radius * 0.45, 5, rotation=0, color=GRAY + (255,)).draw()
            pyglet.shapes.Star(cx, cy, radius * 0.6, radius * 0.27, 5, rotation=0, color=EMPTY_STAR + (255,)).draw()

    def _play(self, cx, cy, radius):
        """Play button of a battle: a white triangle pointing right, like the arrows of the battle speed button, with a dark outline."""
        a, b, c = (cx - radius * 0.6, cy - radius * 0.8), (cx - radius * 0.6, cy + radius * 0.8), (cx + radius * 0.85, cy)
        o = radius * 0.22
        pyglet.shapes.Triangle(a[0] - o, a[1] - o * 1.4, b[0] - o, b[1] + o * 1.4, c[0] + o * 1.6, c[1], color=(20, 20, 20)).draw()
        pyglet.shapes.Triangle(*a, *b, *c, color=WHITE).draw()

    def _trash(self, cx, cy, radius, hot, off=False):
        """Trash of an element: a small bin (lid, handle, body with two grooves), gray; red when hovered; dark gray for a favorite (`off`)."""
        c = (TRASH_OFF if off else TRASH if hot else GRAY) + (255,); d = (20, 20, 20, 255); r = radius
        pyglet.shapes.Rectangle(cx - r * 0.62, cy - r * 0.95, r * 1.24, r * 1.35, color=d).draw()
        pyglet.shapes.Rectangle(cx - r * 0.52, cy - r * 0.85, r * 1.04, r * 1.15, color=c).draw()                   # body
        pyglet.shapes.Rectangle(cx - r * 0.85, cy + r * 0.45, r * 1.7, r * 0.3, color=c).draw()                     # lid
        pyglet.shapes.Rectangle(cx - r * 0.25, cy + r * 0.75, r * 0.5, r * 0.22, color=c).draw()                    # handle
        for gx in (-0.2, 0.2): pyglet.shapes.Rectangle(cx + r * gx - r * 0.05, cy - r * 0.68, r * 0.1, r * 0.82, color=d).draw()

    def _clear_width(self, bm, sc, size_value, k):
        return 14 * k + 18 * k + 9 * k + self._text_width(bm, tr(CLEAR_CAPTION), sc, size_value) + 14 * k

    def _clear(self, bm, sc, size_value, asc, k, fx, ty, th):
        """"Clear all" plate: to the right of "Favorites only", a trash and the label; its area (click) is kept in `clear_zone`."""
        P = self.P; fw = self._clear_width(bm, sc, size_value, k); zone = (fx, ty, fx + fw, ty + th); self.clear_zone = zone
        over = (P._hovered(zone) if hasattr(P, '_hovered') else False) and P.mouse_mode
        self._plate(fx, ty, fw, th, k, over)
        self._trash(fx + 14 * k + 9 * k, ty + th / 2, 10 * k, over)
        self._line(bm, tr(CLEAR_CAPTION), fx + 14 * k + 18 * k + 9 * k, ty + th / 2 - (asc * 0.37 if bm else 6 * k), sc, WHITE, size_value)

    def _filter_width(self, bm, sc, size_value, k):
        """Width of the plate of the "Favorites only" checkbox: margin, box, margin, small star, label, margin."""
        return 14 * k + 18 * k + 9 * k + 2 * 8 * k + 7 * k + self._text_width(bm, tr(FILTER_CAPTION), sc, size_value) + 14 * k

    def _filter(self, bm, sc, size_value, asc, k, fx, ty, th):
        """"Favorites only" checkbox: a plate at the height of the tabs, to the right of the last tab (the tabs + checkbox group is centered in the window), with the box, a small star and the label;
        golden when checked. Its area (click) is kept in `filter_zone`."""
        P = self.P; cb = 18 * k; rs = 8 * k
        fw = self._filter_width(bm, sc, size_value, k)
        zone = (fx, ty, fx + fw, ty + th); self.filter_zone = zone
        over = (P._hovered(zone) if hasattr(P, '_hovered') else False) and P.mouse_mode
        self._plate(fx, ty, fw, th, k, over)
        on = self.favorites_only; clr = GOLD if on else WHITE
        bx, by = fx + 14 * k, ty + (th - cb) / 2
        pyglet.shapes.Rectangle(bx, by, cb, cb, color=(0, 0, 0)).draw()
        for (xa, ya, xb, yb) in ((bx, by, bx + cb, by), (bx, by + cb, bx + cb, by + cb), (bx, by, bx, by + cb), (bx + cb, by, bx + cb, by + cb)):
            pyglet.shapes.Line(xa, ya, xb, yb, thickness=max(1.5, 1.6 * k), color=clr + (255,)).draw()
        if on:                                                                      # the check mark (two strokes)
            pyglet.shapes.Line(bx + cb * 0.2, by + cb * 0.5, bx + cb * 0.42, by + cb * 0.22, thickness=max(2.0, 2.6 * k), color=GOLD + (255,)).draw()
            pyglet.shapes.Line(bx + cb * 0.42, by + cb * 0.22, bx + cb * 0.84, by + cb * 0.82, thickness=max(2.0, 2.6 * k), color=GOLD + (255,)).draw()
        ex = bx + cb + 9 * k + rs; ey = ty + th / 2
        pyglet.shapes.Star(ex, ey, rs * 1.15, rs * 0.5, 5, rotation=0, color=(STAR if on else GRAY) + (255,)).draw()
        self._line(bm, tr(FILTER_CAPTION), ex + rs + 7 * k, ty + th / 2 - (asc * 0.37 if bm else 6 * k), sc, clr, size_value)

    def _plate(self, x, y, w, h, k, chosen):
        J = self.J; r = getattr(J, 'ui_render', None)
        if r is not None and r.plate(x, y, w, h, (J.width, J.height), chosen, corner=14 * k): return
        HM.plate(x, y, w, h, k, chosen, None)

    def _box_window(self, has_tab, extra=0):
        """Game message window (ui_menu.MessageWindow) that draws a box's frame: with the name tab (frameData 191) or without (192), without the canvas or the end-of-page cursor; None if the original layout
        is not loaded (the box is then drawn with a simple frame). `extra`: text lines in addition to the 3 of the game's box (a battle): the frame (without tab) is lengthened accordingly (stretch_border)."""
        lookup_key = (has_tab, int(extra) if not has_tab else 0)
        f = self._wins.get(lookup_key)
        if f is None:
            f = False
            r = getattr(self.J, 'ui_render', None); ml = getattr(r, 'ml', None)
            if ml is not None and getattr(ml, 'message', None):
                try:
                    g = UM.MessageWindow(ml); g.select_language(0, 0, False, 'x' if has_tab else '')
                    if g.with_name == has_tab:
                        g.N['canvas']['act'] = False; g.N['cursor']['act'] = False; f = g
                        if lookup_key[1] > 0: g.N['frame']['vtx'] = stretch_border(g.N['frame']['vtx'], lookup_key[1] * Box.STEP)
                except Exception: f = False
            self._wins[lookup_key] = f
        return f or None

    def _draw_box(self, B, bx, by, s, k, name_str, bm, size_value, extra=0):
        """Frame of the box whose bottom-left corner is (bx, by), at scale s: the game's frame (and the name tab with its text, as the game places them), otherwise a simple frame. Always the same: the selected message is neither
        grayed nor lightened (it only carries the small arrow, see draw_all)."""
        J = self.J; r = getattr(J, 'ui_render', None); f = self._box_window(bool(name_str), extra) if r is not None else None
        done = False
        if f is not None:
            try:
                if name_str: f.N['speaker']['text']['text'] = name_str
                r.draw_all([f], bx - (B.win[0] + B.x0) * s, by - (B.win[2] + B.z0) * s, s, (J.width, J.height)); done = True
            except Exception: self._wins[(bool(name_str), int(extra) if not name_str else 0)] = False
        if not done:                                                      # (fallback: the menu's translucent black frame and, for a name, a small frame stuck at the top left)
            HM.border(bx + 4 * s, by + 4 * s, (B.WIDTH - 8) * s, (B.UP + extra * B.STEP - 8) * s, k, background=(0, 0, 0), opacity=HM.GAME_OPACITY)
            if name_str:
                HM.border(bx + 4 * s, by + (B.UP + extra * B.STEP - 6) * s, (B.TAB_L - 8) * s, (B.TAB_H + 2) * s, k, background=(0, 0, 0), opacity=HM.GAME_OPACITY)
                sc = s * B.text_scale if bm else 1.0; lw = self._text_width(bm, name_str, sc, size_value)
                self._line(bm, name_str, bx + (B.NAME_X - 0.0) * s - lw / 2, by + (B.UP + extra * B.STEP + 7) * s, sc, WHITE, size_value)

    def _measure(self, bm, B, s, k, size_value, hv):
        """Lays out THE WHOLE list in a column (arrange: a dialogue at the height of the game's dialogue box, whether the text fits on 1, 2 or 3 rows, and the name tab, on the first box of a dialogue with a name, is added above it; a battle has as many lines as its text requires, three at least: box_lines), for scale s and a list window of height hv (pixels). The layout never depends on the scroll position. Updates the scroll geometry (content height,
        window height, line height), keeps the proportional position when the scale changes, recenters the element requested by `go_to`, clamps the position and keeps the elements' edges (starts, ends) for keyboard navigation.
        -> boxes: (element, box, number of boxes, top, tab top, frame top, text rows); top = pixels from the top of the content."""
        els = self.elements; n = len(els)
        lookup_key = (id(els), n, int(s * 100), int(k * 100), bm is not None, self._bmm() is not None)
        if self._layout is None or self._layout[0] != lookup_key:
            pages = [self._pages_of(bm, e, B, s, size_value) for e in els]
            ent = [(len(pg), e.type == HI.TYPE_DIALOGUE and bool(e.name_str), [B.top_for(box_lines(page, j == 0, e.type == HI.BATTLE_TYPE)) * s for j, page in enumerate(pg)]) for pg, e in zip(pages, els)]
            boxes, starts, ends, hc = arrange(ent, B.UP * s, B.TAB_H * s, ELEMENT_SPACING * k, PAGE_SPACING * k, ENTRIES_MARGIN * k)
            self._layout = (lookup_key, [(i, p, num, h, hn, hb, pages[i][p]) for (i, p, num, h, hn, hb) in boxes], starts, ends, hc)
        boxes, starts, ends, hc = self._layout[1:]
        self._geometry(starts, ends, hc, hv, B.STEP * s, s)
        return boxes

    def _geometry(self, starts, ends, hc, hv, step, s):
        """Pure part of _measure (tested without font or GL): the list is `hc` pixels tall (starts / ends: top of the first box and bottom of the last box of each element), the list window `hv`, a text line `step`,
        at scale s. Keeps the proportional position when the scale changes, recenters the element requested by `go_to`, clamps the position and keeps the elements' edges for keyboard navigation."""
        n = len(starts)
        if self._prev_s and abs(s - self._prev_s) > 1e-6: self.pos *= s / self._prev_s                 # window resized: the view stays at the same place in the list
        self._prev_s = s; self.hc, self.hv, self.step = hc, float(hv), step
        if self.center_target is not None:
            i, self.center_target = self.center_target, None
            if 0 <= i < n: self.pos = min(self.span(), max(0.0, hc - (starts[i] + ends[i]) / 2.0 - self.hv / 2.0)); self.selected = i
        self.starts, self.ends = list(starts), list(ends)
        self.pos = min(self.span(), max(0.0, self.pos))
        self.selected = max(0, min(n - 1, self.selected)) if n else 0

    def _slice(self, x, y, w, h):
        """Scissor rectangle (glScissor) on the rectangle (x, y, w, h) of the window (window pixels: scaled to the frame buffer on a high-density screen): whatever overflows the list is clipped, like scrolling text.
        -> True if the scissor is active (to be closed with glDisable(GL_SCISSOR_TEST)); False if it could not be set up (the clipped boxes are then not drawn)."""
        try:
            W, H = self.J.width, self.J.height; fb = self.J.get_framebuffer_size() if hasattr(self.J, 'get_framebuffer_size') else (W, H)
            rx, ry = fb[0] / float(max(1, W)), fb[1] / float(max(1, H))
            gl.glEnable(gl.GL_SCISSOR_TEST); gl.glScissor(int(max(0, x * rx)), int(max(0, y * ry)), int(max(1, round(w * rx))), int(max(1, round(h * ry))))
            return True
        except Exception:
            return False

    def draw_all(self, place=None):
        """The history window: centered on the whole screen, or (`place` = (x, top, width, k, height)) in the right window of the Esc menu, next to its root (pause.py: two windows); the menu has drawn
        the veil then. Returns its frame (x0, y0, x1, y1)."""
        if self.rewind is not None: return self._draw_rewind()
        J = self.J; P = self.P; W, H = J.width, J.height; k = place[3] if place else max(0.75, H / 900.0)
        gl.glDisable(gl.GL_DEPTH_TEST); gl.glEnable(gl.GL_BLEND); gl.glBlendFunc(gl.GL_SRC_ALPHA, gl.GL_ONE_MINUS_SRC_ALPHA)
        if place is None: veil = pyglet.shapes.Rectangle(0, 0, W, H, color=(0, 0, 0)); veil.opacity = 90; veil.draw()
        bm = self._bm(); B = self._game_box(); s = B.scale_factor(H, place[2] + 40 * k if place else W, k)          # s: pixels per interface unit = those of a game dialogue box (in the right window: reduced to fit in it)
        su = max(0.8, min(2.4, H / 700.0)) if bm else 1.0; size_value = 17 * k                  # su: one game font pixel = su screen pixels (title, tabs, help); size_value: system font (fallback)
        sc = s * B.text_scale if bm else 1.0; size_b = 20 * s                               # same for the box text: as in the game (1.105 units per font pixel)
        fm = self._bmm()                                                                       # box text: the game's message font when available (one pixel of its canvas = one interface unit), otherwise SE-GARRIR
        if fm is not None: sc = s * fm.SCALE; text_baseline = B.base_msg
        else: fm = bm; text_baseline = B.base
        asc = (bm.ascent * su) if bm else 18 * k
        kb = 1.1 * k; bw, bh = 64 * kb, 55.5 * kb
        lgs = [self._text_width(bm, tr(name_str), su, size_value) + 44 * k for name_str, _ in TABS]; tw = max(lgs + [120 * k]); gap = 10 * k
        tabs_width = tw * len(TABS) + gap * (len(TABS) - 1); fw = self._filter_width(bm, su, size_value, k); cw = self._clear_width(bm, su, size_value, k)
        line_width = tabs_width + 14 * k + fw + 14 * k + cw                                         # the tab row: the tabs, the "Favorites only" checkbox, "Clear all"
        pw = min(W - 20 * k, max(B.WIDTH * s + B.MARGINS * k, line_width + 2 * 34 * k)); h = H - 2 * 30 * k - bh - 10 * k
        x0 = (W - pw) / 2; y1 = (H + h + bh + 10 * k) / 2
        if place: x0, y1, pw, h = place[0], place[1], place[2], place[4]          # (right window: its place and size, the same frame as the other pages of the menu)
        y0 = y1 - h
        HM.border(x0, y0, pw, h, k, background=(0, 0, 0), opacity=HM.GAME_OPACITY)                # as transparent as the other game windows
        title_screen = tr('settings.history')
        wt = self._text_width(bm, title_screen, su * 1.25, size_value * 1.3)
        self._line(bm, title_screen, x0 + (pw - wt) / 2, y1 - 24 * k - asc * 1.25, su * 1.25, WHITE, size_value * 1.3)
        # tabs: the buttons of the Keyboard / Gamepad row of "Controls" (pause._tab_buttons): the open tab lit, gold outline and text
        th = 34 * k; ty = y1 - 100 * k; self.tab_zones = []                      # (below the title: its plates must not cover it)
        tx = x0 + (pw - line_width) / 2
        for i, (name_str, lookup_key) in enumerate(TABS):
            zx = tx + i * (tw + gap); zone = (zx, ty, zx + tw, ty + th); self.tab_zones.append(zone + (i,))
            over = (P._hovered(zone) if hasattr(P, '_hovered') else False) and P.mouse_mode
            HM.plate(zx, ty, tw, th, k, chosen=i == self.tab or over, outline=GOLD if i == self.tab else None)
            name_str = tr(name_str); lf = self._text_width(bm, name_str, su, size_value); self._line(bm, name_str, zx + (tw - lf) / 2, ty + th / 2 - (asc * 0.37 if bm else 6 * k), su, GOLD if i == self.tab else WHITE, size_value)
        self._filter(bm, su, size_value, asc, k, tx + tabs_width + 14 * k, ty, th)                  # "Favorites only" checkbox (to the right of the tabs)
        self._clear(bm, su, size_value, asc, k, tx + tabs_width + 14 * k + fw + 14 * k, ty, th)
        # help (one or two lines, depending on the window width)
        helptext = [tr('menus.up_down_previous_next_message'), tr('menus.mouse_wheel_scroll'), tr('menus.camera_keys_tab'), tr('menus.enter_favorite'), tr('menus.delete_delete')] + ([tr('menus.space_play_button_replay_battle')] if TABS[self.tab][1] == 'battles' else []) + [tr('menus.f_favorites_only')] + [tr('menus.esc_close')]
        max_line_width = pw - 24 * k; measure_help = lambda t: self._text_width(bm, t, su * 0.72, size_value * 0.72)
        help_lines = []; cur = ''
        for a in helptext:
            cand = a if not cur else cur + '     ' + a
            if cur and measure_help(cand) > max_line_width: help_lines.append(cur); cur = a
            else: cur = cand
        help_lines.append(cur)
        helptext_step = (bm.leading * su * 0.72) if bm else 17 * k
        # list area: the box (game size) on the left, the star column to its right, the scrollbar at the edge
        group = B.WIDTH * s + 44 * k; lx0 = x0 + (pw - group) / 2; lx1 = lx0 + group; ly1 = ty - 14 * k; ly0 = y0 + 40 * k + (len(help_lines) - 1) * helptext_step
        self.zones = []; self.star_zones = []; self.play_zones = []; self.trash_zones = []; self.bar = None
        n = len(self.elements)
        if not n:
            self.hc = self.hv = 0.0; self.pos = 0.0; self._layout = None
            msg = tr((EMPTY_FAVORITES if self.favorites_only else EMPTY_MESSAGES)[TABS[self.tab][1]])
            vl = wrap_words(msg, lambda t: self._text_width(bm, t, su, size_value), pw - 40 * k)                 # the message fits in the window: split into several centered lines (it used to overflow the frame when long)
            step_v = (bm.leading * su) if bm else 28 * k; y_v = (ly0 + ly1) / 2 + (len(vl) - 1) * step_v / 2
            for j, l in enumerate(vl): self._line(bm, l, x0 + (pw - self._text_width(bm, l, su, size_value)) / 2, y_v - j * step_v, su, GRAY, size_value)
        else:
            mouse = P.mouse_mode; hv = ly1 - ly0
            boxes = self._measure(bm, B, s, k, size_b, hv)
            screen_top = ly0 + self.hc - round(self.scroll_offset())                      # y coordinate of the top of the content (integer position: the text keeps the same drawing at each position); the content is stuck to the bottom when it is shorter than the window
            sliced = self._slice(x0, ly0, pw, hv)                              # everything that overflows the list is clipped
            dragging = self.drag is not None and self.drag[2]
            try:
                views = []; top_of = {}
                for b in boxes:                                                    # only the boxes that touch the list window are drawn (from the oldest, at the top, to the most recent)
                    (i, p, np_, topmost, hn, hb, rows) = b; yb = screen_top - topmost - hn - hb; yt = yb + hb + hn
                    if yt <= ly0 or yb >= ly1 or (not sliced and (yb < ly0 or yt > ly1)): continue
                    views.append((b, yb, yt)); top_of[i] = min(top_of.get(i, p), p)       # (topmost page shown of each element: the golden arrow is drawn there only once)
                    if mouse and self.dragging_bar is None and not dragging and P._pointer_in((lx0, max(yb, ly0), lx1, min(yt, ly1))): self.selected = i      # with the mouse, the hovered message is the selected message (selected before drawing: a single arrow)
                for ((i, p, np_, topmost, hn, hb, rows), yb, yt) in views:
                    e = self.elements[i]; name_str = e.name_str if (e.type == HI.TYPE_DIALOGUE and p == 0 and e.name_str) else None
                    zone = (lx0, max(yb, ly0), lx1, min(yt, ly1)); self.zones.append(zone + (i,))                      # (the area of a clipped box does not extend past the list window: no click on the tabs or the help)
                    extra = max(0, box_lines(rows, p == 0, e.type == HI.BATTLE_TYPE) - B.LINES)                # lines in addition to the game box (a battle)
                    self._draw_box(B, lx0, yb, s, k, name_str, bm, size_b, extra)                      # game frame (+ tab and name): no graying on hover or on selection
                    if i == self.selected and p == top_of[i]: P._cursor(x0 + 4 * k, yb + hb / 2, min(hb * 0.7, 28 * k))      # the selected message (keyboard or mouse): the small arrow, and nothing else
                    rank = 0
                    if e.type == HI.BATTLE_TYPE and p == 0:                                # header: the battle outcome on the left, the game time on the right
                        base = yb + hb - text_baseline(0) * s; self._line(fm, tr(HI.OUTCOME_CAPTION.get(e.outcome, '')), lx0 + B.TEXT_X * s, base, sc, GOLD, size_b)
                        ht = game_time(e.t); self._line(fm, ht, lx0 + (B.WIDTH - 14) * s - self._text_width(fm, ht, sc * 0.8, size_b * 0.8), base, sc * 0.8, HELPTEXT, size_b * 0.8); rank = 1
                    for l in rows:
                        self._line(fm, l, lx0 + B.TEXT_X * s, yb + hb - text_baseline(rank) * s, sc, WHITE, size_b); rank += 1
                    rs = 11 * k; ex = lx0 + B.WIDTH * s + 22 * k; ey = yb + hb - (B.BASE_1 - 7) * s; gap_b = 2.6 * rs     # the element's buttons, in the column to the right of its first box:
                    if p == 0:                                                           # star level with the 1st line, then play (a battle), then the trash
                        buttons = [('star', ey)]
                        if e.type == HI.BATTLE_TYPE and (e.replay or e.log): buttons.append(('play', ey - gap_b))
                        buttons.append(('trash', ey - gap_b * len(buttons)))
                        for kind, by in buttons:
                            z = (ex - rs * 1.3, max(by - rs * 1.3, ly0), ex + rs * 1.3, min(by + rs * 1.3, ly1))
                            if z[1] >= z[3]: continue
                            off = kind == 'trash' and J.history.is_favorite(e)                      # (a favorite's trash is grayed, inactive)
                            hot = mouse and not off and P._pointer_in(z); r_b = rs * (1.15 if hot else 1.0)
                            if kind == 'star': self.star_zones.append(z + (i,)); self._star(ex, by, r_b, J.history.is_favorite(e))
                            elif kind == 'play': self.play_zones.append(z + (i,)); self._play(ex, by, r_b)
                            elif off: self._trash(ex, by, r_b, False, True)
                            else: self.trash_zones.append(z + (i,)); self._trash(ex, by, r_b, hot)
                    if np_ > 1:                                                          # "1/2" at the bottom of the column: the box is part of a sequence (simple label)
                        t = '%d/%d' % (p + 1, np_); self._line(bm, t, ex - self._text_width(bm, t, su * 0.72, size_value * 0.72) / 2, yb + 8 * k, su * 0.72, HELPTEXT, size_value * 0.72)
            finally:
                if sliced: gl.glDisable(gl.GL_SCISSOR_TEST)
            if self.hc > self.hv + 0.5: self.bar = P._scroll_bar(x0 + pw - 14 * k, ly1, ly0, self.hc, self.hv, self.span() - self.scroll_offset(), k, self.dragging_bar is not None)      # proportional thumb, continuous position (distance from the top of the content)
        for j, l in enumerate(help_lines):                                          # help and back button
            text_line_width = self._text_width(bm, l, su * 0.72, size_value * 0.72); self._line(bm, l, x0 + (pw - text_line_width) / 2, y0 + 14 * k + (len(help_lines) - 1 - j) * helptext_step, su * 0.72, HELPTEXT, size_value * 0.72)
        bx = x0 + pw - bw - 8 * k; by = y0 - 8 * k - bh; self.zone_ret = (bx, by, bx + bw, by + bh)
        P._back_button(bx, by, bw, bh, P._hovered(self.zone_ret))
        if self.notice is not None:                                                  # ("this battle cannot be replayed", for a few seconds)
            if self.clock() > self.notice[1]: self.notice = None
            else:
                t = tr(self.notice[0]); tw_ = self._text_width(bm, t, su * 0.8, size_value * 0.8); ny = ly0 + 10 * k
                nx = x0 + (pw - tw_) / 2; pyglet.shapes.Rectangle(nx - 10 * k, ny - 8 * k, tw_ + 20 * k, (asc * 0.8 if bm else 14 * k) + 16 * k, color=(0, 0, 0)).draw()
                self._line(bm, t, nx, ny, su * 0.8, GOLD, size_value * 0.8)
        return (x0, y0, x0 + pw, y1)

    def _rewind_rows(self, i, text, fm, B, s):
        """Lines of message i of the rewind, wrapped like the game (whole text: the typing reveals them without words jumping from one line to the next). Cached."""
        key = (id(self.rewind), i, int(s * 100)); r = self._rw_lines.get(key)
        if r is None:
            bm = self._bm()
            r = self._rw_lines[key] = (wrap_like_the_game(fm, text) if fm is not None else HI.wrap_text(text, B.text_width(), (lambda t: bm.width_px(t) * B.text_scale) if bm else len))
        return r

    def _draw_rewind(self):
        """Rewind screen: the battle's messages in a game message box (REWIND_LINES lines, the newest at the bottom), the outcome and time above, the speed button (the battle's arrows) and the back
        button below. Nothing else: no command, no menu."""
        J = self.J; P = self.P; W, H = J.width, J.height; k = max(0.75, H / 900.0); r = self.rewind; speed = self.speed()
        r.tick(speed)
        gl.glDisable(gl.GL_DEPTH_TEST); gl.glEnable(gl.GL_BLEND); gl.glBlendFunc(gl.GL_SRC_ALPHA, gl.GL_ONE_MINUS_SRC_ALPHA)
        veil = pyglet.shapes.Rectangle(0, 0, W, H, color=(0, 0, 0)); veil.opacity = 170; veil.draw()
        bm = self._bm(); B = self._game_box(); s = B.scale_factor(H, W, k)
        su = max(0.8, min(2.4, H / 700.0)) if bm else 1.0; size_value = 17 * k; size_b = 20 * s
        fm = self._bmm(); wrap_font = fm
        if fm is not None: sc = s * fm.SCALE; base = B.base_msg
        else: fm = bm; sc = s * B.text_scale if bm else 1.0; base = B.base
        bw = B.WIDTH * s; hb = B.top_for(REWIND_LINES) * s; bx = (W - bw) / 2; by = H * 0.42 - hb / 2
        title = '%s  —  %s  %s' % (tr(REWIND_TITLE), tr(HI.OUTCOME_CAPTION.get(r.e.outcome, '')), game_time(r.e.t))
        wt = self._text_width(bm, title, su * 1.1, size_value * 1.1); self._line(bm, title, (W - wt) / 2, by + hb + 40 * k, su * 1.1, WHITE, size_value * 1.1)
        self._draw_box(B, bx, by, s, k, None, bm, size_b, REWIND_LINES - B.LINES)
        lines = []
        for i, (name, text, n) in enumerate(r.shown()):
            for row in self._rewind_rows(i, text, wrap_font, B, s):
                if n <= 0: break
                lines.append(row[:n]); n -= len(row) + 1
        for j, l in enumerate(lines[-REWIND_LINES:]): self._line(fm, l, bx + B.TEXT_X * s, by + hb - base(j) * s, sc, WHITE, size_b)
        # the two buttons, under the box: speed on the left (the battle's plate and arrows), back on the right
        u = H / 800.0; sw, sh = 118.0 * u, 60.0 * u; gap = 16 * k
        sx, sy = bx, by - gap - sh; zs = (sx, sy, sx + sw, sy + sh)
        self._plate(sx, sy, sw, sh, k, P._pointer_in(zs)); HM.speed_arrows(sx, sy, sw, sh, speed)
        kb = 1.1 * k; rw, rh = 64 * kb, 55.5 * kb; rx, ry = bx + bw - rw, by - gap - rh; zq = (rx, ry, rx + rw, ry + rh)
        P._back_button(rx, ry, rw, rh, P._pointer_in(zq))
        self.rewind_zones = {'speed': zs, 'quit': zq}
        ks = (J.reg['keys'].get('battle_speed') or [None])[0] if hasattr(J.reg, '__getitem__') else None
        help_ = '     '.join(([tr('menus.speed') % tr(RG.key_name(ks))] if ks else []) + [tr('menus.enter_click_next_message'), tr('menus.esc_quit')])
        if r.finished(): help_ = tr(REWIND_END) + '     ' + help_
        hw = self._text_width(bm, help_, su * 0.72, size_value * 0.72); self._line(bm, help_, (W - hw) / 2, sy - 30 * k, su * 0.72, HELPTEXT, size_value * 0.72)
