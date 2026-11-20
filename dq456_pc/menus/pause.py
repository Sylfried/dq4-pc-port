"""Esc menu: resume, savestates, display, sound, commands (speeds, keys, interface), back to the title screen.

While the menu is open the game KEEPS running behind it, on all pages, without receiving any key or click (no pause in any menu; the scene stays displayed, darkened). Navigation: arrows or the configured up / down / left / right / A / B keys,
Enter / Space = confirm, Esc / Backspace = back, mouse (hover, click, right click or "back" button at the bottom right of the window = back, wheel, scrollbar).
Two selection modes: with the keyboard, the gold cursor (fixed) in front of the line; with the mouse, nothing is outlined: as with touch on mobile, the plate (or the button) under the pointer darkens and lights up again when it leaves.
Settings are saved in settings.json. Black windows, gold cursor and back button: those of the game menus (MenuTexture and Button sheets)."""
import math, os, sys, time
import numpy as np
import pyglet
from pyglet import gl
from dq456_pc.persistence import settings as RG
from dq456_pc.persistence import savestates as SS
from dq456_pc.persistence import pad_inputs as PI
from dq456_pc.persistence import game_rules as GR
from dq456_pc.randomizer import seed as SD
from dq456_pc import language as LG
from dq456_pc import games as GM
from dq456_pc.language import N_, tr
from dq456_pc.world import hd as HD
from dq456_pc.menus import sheets as SH
from dq456_pc.menus import hud_mobile as HM
from dq456_pc.window import inputs as EN
from dq456_pc.menus import ui_history as UH
from dq456_pc.menus import prompts as PR
from dq456_pc.core import engine as ENGINE

SAVESTATE_COUNT = 9                 # savestate slots (keys 1 to 9)
REPEAT_DELAY, REPEAT_STEP = 0.40, 0.07
# Game text palette (MenuPortItemTable: white, yellow, red, gray); black windows framed in white and buttons in the style of the mobile game's command menu
# (see hud_mobile.border and hud_mobile.plate)
GOLD = (255, 235, 4, 255); WHITE = (255, 255, 255, 255); GRAY = (128, 128, 128, 255); HELPTEXT = (170, 170, 170, 255); RED = (255, 80, 80, 255)
HEADING = (146, 140, 112, 255); HEADING_RULE = (72, 69, 54)          # group subheadings of the drop-down lists ("Touch screen", "Dialogue"...): dull golden gray, smaller; gold (GOLD) is reserved for the current value
HEADING_SIZE = 0.76                                                   # (fraction of the size of the values)


def heading_style(fs):
    """(size, color) of a drop-down list group subheading: smaller than the values and a dull golden gray, never gold (gold marks the current value)."""
    return fs * HEADING_SIZE, HEADING
YELLOW = GOLD[:3]; LIGHT = (236, 236, 232)
NO_DEFAULT = object()                                  # "no default value" (None and False are possible values)
BLACK = (0, 0, 0)                                  # background of the menu windows: black, with the opacity of the windows of the other menus (hud_mobile.GAME_OPACITY, measured on the game windows)
CELL_WIDTH, CELL_SPACING = 180.0, 10.0       # "Controls" menu: width of a key cell and gap between the two (at 900 px high, multiplied by k); two cells (they were 150 wide, three of them)
BAR_WIDTH = 12.0                                 # scrollbar
CURSOR = (194, 297, 238, 328)                    # gold cursor of the game menus in the MenuTexture sheet (x0, y0, x1, y1; DQ IV's places: the interface block is lower in DQ V / VI, see _sliced_tex)
DPAD = (50, 291, 61, 301)                        # the game's red cross (clear a key)
BACK_ICON = (352, 224, 384, 256)               # icon of the game's back button (cell 11 of the icon row)
LIST_OPACITY = 0.94                             # an open drop-down list: its background hides the lines it covers (the other windows keep the game's 68 %)
WIDTH_SW, HEIGHT_SW = 46.0, 24.0                    # Yes / No toggle: size at 900 px high (multiplied by k)
INDENT = 28.0                                        # shift to the right of a line under another one (`indent`: the notched lines under "Difficulty"), at 900 px high (multiplied by k)
HELP_H = 96.0                                        # two windows: height of the help zone at the bottom of the right frame (3 lines), at 900 px high (multiplied by k)
HERO_SHEETS = (100, 103)                             # the hero's sprite sheets (h100 male, h103 female): the pictures of the gender page of a new game
FRONT_ROW = 4; WALK = (2, 1, 0, 1); WALK_STEP = 0.1    # facing the camera (row 4 of 8), walking: the poses the engine sends in a town, 3 frames of 1/30 s each (on the world map: 6)
SPRITE_SIZE = 0.75                                    # gender page: the heroes at 3/4 of the largest whole multiple that fits
GENDER_HINT = 'new_game.gender_hero_new_game   new_game.left_right_choose'          # (help of the gender page)
DEVICE_ROW = 48.0                                    # "Controls": height of the Clavier / Manette row, centered just under the page's title (fixed: the lines scroll under it)
GAME_SIZE = 1.0                                  # scale of the texts in the game font (relative to the system fonts)
MSAA_CHOICES = (0, 2, 4, 8)
# mouse gestures on the field ("Controls" page, read-only: these are not keys): (gesture, effect); the camera only turns left / right and recenters
KEY_SIDE = {'LSHIFT': N_('keys.key_side_left'), 'RSHIFT': N_('keys.key_side_right'), 'LCTRL': N_('keys.key_side_left'), 'RCTRL': N_('keys.key_side_right')}          # "Controls": the keys that exist on both sides share their picture; a small word beside it says which one (Alt and Alt Gr have pictures of their own: no word)
MOUSE_GESTURES = ((N_('controls.hold_middle_click_move'), N_('controls.rotates_camera')),
                 (N_('controls.middle_click'), N_('controls.recenters_camera')))          # (French texts, translated as they are drawn)
# interface editor: names of the game windows (Make_* functions of MenuPortItemTable; 'boutons' = buttons and D-pad of the screen, 'msg' = dialogues) and groupings
# of the "Interface to edit" list. A game window appears there only if it has a mesh to adjust (RG.REMOVED_WINDOWS: game launch, network, windows without a mesh);
# an unknown window goes into "Other".
WINDOW_NAMES = {'buttons': N_('interface.screen_buttons_d_pad'), 'vehicle_button': N_('interface.vehicle_button'), 'speed_button': N_('interface.battle_speed_button'), 'msg': N_('interface.dialogue_messages'), 'YesNo': N_('interface.yes_no'), 'Chapter': N_('interface.chapter_title'),
                 'RootMenu': N_('interface.main_menu'), 'LeftCharaList': N_('interface.character_list'), 'TargetCharaList': N_('interface.character_selection'), 'Money': N_('interface.gold'), 'Pageing': N_('interface.page_arrows'),
                 'ItemList': N_('interface.item_list'), 'ItemInfo': N_('interface.item_info'), 'OperationItemList': N_('interface.item_actions'),
                 'Status': N_('interface.character_status'), 'Chapter2Status': N_('interface.chapter_2_status'), 'MemberShift': N_('interface.party_order'), 'MemberShiftButton': N_('interface.party_order_buttons'),
                 'NameButton': N_('interface.miscellaneous_button_list'), 'BCInfo': N_('interface.quick_save'), 'Senreki': N_('interface.adventure_log'), 'MonsterEncyclopedia': N_('interface.bestiary'),
                 'CityMap': N_('interface.map_overview_town_world'), 'WorldLargeMap': N_('interface.map_large_world_map'), 'MapButton': N_('interface.map_mode_back_buttons'), 'ShopMap': N_('interface.map_shop_list'),
                 'BattleUpStatus': N_('interface.battle_party_banner'), 'BattleRoot': N_('interface.battle_main_menu'), 'BattleAction': N_('interface.battle_actions'), 'BattleTarget': N_('interface.battle_targets'), 'BattleGo': N_('interface.battle_go_ahead'),
                 'BattleIM': N_('interface.battle_items_spells'), 'BattleInfo': N_('interface.battle_party_info'), 'BattleEnemyTarget': N_('interface.battle_enemy_target'), 'BattlePartyTarget': N_('interface.battle_ally_target'),
                 'BattleChangeButton': N_('interface.battle_change'), 'BattleChangeInfo': N_('interface.battle_change_info'),
                 'ShopRoot': N_('interface.shop_menu'), 'ShopBuy': N_('interface.shop_buy'), 'ShopBuyInfo': N_('interface.shop_item_info'), 'ShopSellItemList': N_('interface.shop_sell'), 'ShopSellItemInfo': N_('interface.shop_sell_info'),
                 'TorunekoMiseban': N_('interface.torneko_s_shop'), 'BankDeposit': N_('interface.bank_deposit'), 'BankDraw': N_('interface.bank_withdraw'), 'ChurchRoot': N_('interface.church_menu'), 'ChurchWork': N_('interface.church_services'),
                 'Casino_CoinShop': N_('interface.casino_coins'), 'Casino_GiftList': N_('interface.casino_prizes'), 'Casino_GiftTarget': N_('interface.casino_recipient'), 'Casino_Slot': N_('interface.casino_slot_machine'), 'Casino_Poker': N_('interface.casino_poker'),
                 'Casino_FightStadiumSelect': N_('interface.casino_arena_selection'), 'Casino_FightStadiumBet': N_('interface.casino_arena_bet'), 'Casino_FightStadiumCoin': N_('interface.casino_arena_coins')}
INTERFACE_GROUPS = ((N_('interface.touch_screen'), ('buttons', 'vehicle_button')),
                     (N_('interface.dialogue'), ('msg', 'YesNo', 'Chapter')),
                     (N_('interface.game_menu'), ('RootMenu', 'LeftCharaList', 'TargetCharaList', 'Money', 'Pageing')),
                     (N_('interface.items'), ('ItemList', 'ItemInfo', 'OperationItemList')),
                     (N_('interface.party_status'), ('Status', 'Chapter2Status', 'MemberShift', 'MemberShiftButton')),
                     (N_('interface.miscellaneous'), ('NameButton', 'BCInfo', 'Senreki', 'MonsterEncyclopedia')),
                     (N_('interface.maps'), ('CityMap', 'WorldLargeMap', 'MapButton', 'ShopMap')),
                     (N_('save_states.battle'), ('speed_button', 'BattleUpStatus', 'BattleRoot', 'BattleAction', 'BattleTarget', 'BattleGo', 'BattleIM', 'BattleInfo', 'BattleEnemyTarget', 'BattlePartyTarget', 'BattleChangeButton', 'BattleChangeInfo')),
                     (N_('interface.shops_bank'), ('ShopRoot', 'ShopBuy', 'ShopBuyInfo', 'ShopSellItemList', 'ShopSellItemInfo', 'TorunekoMiseban', 'BankDeposit', 'BankDraw')),
                     (N_('interface.churches'), ('ChurchRoot', 'ChurchWork')),
                     (N_('interface.casino'), ('Casino_CoinShop', 'Casino_GiftList', 'Casino_GiftTarget', 'Casino_Slot', 'Casino_Poker', 'Casino_FightStadiumSelect', 'Casino_FightStadiumBet', 'Casino_FightStadiumCoin')))
OWN_INTERFACES = (RG.SCREEN_TARGET, 'msg', RG.SPEED_TARGET, RG.VEHICLE_TARGET)         # editor interfaces that are not Make_* windows of the engine: buttons and D-pad of the screen, dialogues, battle speed button, DQ VI's vehicle button
HUD_TARGETS = (RG.SCREEN_TARGET, RG.SPEED_TARGET, RG.VEHICLE_TARGET)          # editor interfaces made of on-screen buttons (hud_mobile.editor_names), placed by dragging them
LEGACY_LOCATIONS = {'Carte du monde': 'save_states.world_map', 'Combat': 'save_states.battle'}     # location of a savestate written by an older version (French text instead of a key)
HEADER = '#'                                                    # value of a drop-down list that is a group subheading ("#Dialogues"): never chosen, skipped by the cursor
WITHOUT_EDITING = RG.REMOVED_WINDOWS
LONG_PRESS_DELAY = float(os.environ['DQ_LONG_PRESS']) if os.environ.get('DQ_LONG_PRESS') else None      # editor panel: press held without moving (seconds) before it lifts; None = Windows' click / hold limit (inputs.system_click; 0.35 s before)
DOUBLE_CLICK_DELAY = float(os.environ.get('DQ_DOUBLE_CLICK', '0.50'))        # double click on the title bar: default delay (seconds) between the START of the first press and that of the second, when the system does not provide it (Windows default: 500 ms)
RECT_DOUBLE_CLICK = (4, 4)                                       # default double-click rectangle (pixels, centered on the first press; Windows default: 4 x 4)


def system_double_click():
    """System double-click setting, re-read at each press: (delay in seconds, width, height in pixels of the rectangle around the first press). Windows: GetDoubleClickTime and SM_CXDOUBLECLK / SM_CYDOUBLECLK (the
    "Double-click speed" slider of the Windows Mouse panel); the environment variable DQ_DOUBLE_CLICK (seconds) forces the delay; without Windows, the Windows defaults (0.5 s, 4 x 4)."""
    delay, (w, h) = DOUBLE_CLICK_DELAY, RECT_DOUBLE_CLICK
    if sys.platform == 'win32':
        try:
            import ctypes; u = ctypes.windll.user32
            if not os.environ.get('DQ_DOUBLE_CLICK'): delay = max(0.05, u.GetDoubleClickTime() / 1000.0)
            w, h = max(1, int(u.GetSystemMetrics(36))), max(1, int(u.GetSystemMetrics(37)))
        except Exception: pass
    return delay, w, h

SELECTION_BORDER = (255, 235, 130)                               # yellow frame of the element chosen in the editor preview (the same as that of the screen buttons: hud_mobile.py)
HIDDEN_WORDS = (N_('interface.hidden_feminine'), N_('interface.hidden_masculine'))                             # label of a hidden element in the editor preview: feminine (window, D-pad), masculine (buttons)


class Pause:
    new_game = False; draft_seed = None; hero_gender = None; randomizer_on = False          # "new game" panel (rules of the game about to start), its seed code, the hero's gender (0 male, 1 female, None not chosen yet), randomizer mode: see open_menu

    def __init__(self, game):
        self.J = game; self.hist = UH.HistoryView(self); self.opened = False; self.stack = []; self.selected = {}; self.capture = None; self.message = None; self.controls_pad = False; self.zones_device = []
        self.zones = []; self.zones_off = []; self.bars = {}; self.zones_val = {}; self.zones_col = (0.0, 0.0); self.minis = {}; self.rep = None; self.wants_thumbnail = False; self.mini_tex = None; self.confirmed = None
        self.panel_border = None                          # (x0, y0, x1, y1) of the frame drawn in the last frame (button placement: a click outside the frame grabs a button)
        self.default_zones = {}; self.zones_mute = {}          # line -> (x0, y0, x1, y1) of the "default value" button of the sliders; of the "mute" button of the lines of the "Sound" page
        self.dragging = None; self.entry = None            # slider held by the mouse (line number); value being typed [line, text]
        self.open_dropdown = None; self.zones_pop = []          # open drop-down list [line, hovered value]; zones of its values (x0, y0, x1, y1, number)
        self.pos_sw = {}; self.t_sw = time.time(); self.dt_sw = 0.0         # toggles: button position (0 = No, 1 = Yes) per label, for the animation
        self._pol = None; self._caps = {}                 # families of the game font (None: not searched yet); height of capitals per size

        self.rep_pos = None                               # (screen, line) on which the repeat of a held key started
        self.begin = {}; self.seen_selected = {}; self.has_bar = None; self.dragging_bar = None      # scroll: first visible line per screen, last selection seen (the view follows it when it changes), scrollbar drawn, grab of the scrollbar thumb
        self.zone_ret = None; self.on_back = False; self.zones_eff = {}                      # back button (x0, y0, x1, y1), pointer over it; (line, column) -> "clear the key" cross
        self._pil = {}; self._img = {}                    # game sheets (PIL) and textures of the menu sprites
        self.mouse_mode = False; self.mouse_pos = None   # mouse selection (the plate under the pointer darkens, as with touch on mobile) or keyboard selection (gold cursor); last pointer position
        self.popup = None; self.zones_popup = []                                          # Yes / No modal window: {'title', 'detail', 'yes', 'choice' (0 Yes, 1 No)}; zones of its buttons
        self.folded = False; self.fold_zone = None; self.tt = None                          # interface editor: collapsed panel; title bar (collapse / expand); line hovered since (key, instant) for the tooltip
        self.list_bar = None; self.dragging_entries = None; self.entries_top = None; self.entries_cur_seen = None      # drop-down list: scrollbar, grab of the thumb, first visible value
        self.target = 'buttons'; self.drag = None; self.rect_preview = None           # interface editor: modified element ('boutons', 'msg' or Make_* name of a game window); move in progress (start x, y, start offset)
        self.pan_pos = None; self.pan_pressed = None; self.pan_click_t = 0.0; self.pan_click_pos = None; self.pan_fold_at = None             # interface editor, movable panel: top right corner (x, y) after a move (for the length of the session; None = original position, computed from the chosen interface);
        self.list_border = None; self.pan_dim = None                                    # press in progress on the title bar {t0, x, y, dx, dy, long (lifted: follows the pointer), double}; instant of the last short press (double click); frame of the open drop-down list
        self.dims = {}; self.anc = {}                    # two windows: sizes of the root and of the widest page per (width, height, language); buttons of the lines per page at the previous frame
        self.left_zones = []; self.page_rect = None      # two windows: zones of the root lines and frame of the page open on the right

    def _label(self, text, size_value, color=WHITE, translate=True):
        """Label in the game font (GMaruGoPro-M, cache/ui_font.otf, registered on the first call); failing that, the system fonts. `translate` False: the text as it is (a language's own name)."""
        if self._pol is None:
            self._pol = ()
            f = os.path.join(self.J.args.cache, 'ui_font.otf')
            if os.path.exists(f):
                try: pyglet.font.add_file(f); self._pol = ('FOT-GMaruGo Pro', 'FOT-GMaruGo Pro M', 'GMaruGoPro-M')
                except Exception as ex: print('game font not loaded:', ex, flush=True)
        own = LG.language_of_name(text) if isinstance(text, str) else None          # (a language's own name: written with that language's fonts)
        return self.J._lbl(tr(text) if translate else text, size_value * (1.0 if not self._pol else GAME_SIZE), color, LG.font_families(self._pol, own))          # (any text drawn by the pages goes through translation; a text without a translation stays as is)

    # ---- game menu sprites
    def _sheet(self, name_str):
        """Game texture sheet (cache/<name>, PIL RGBA); None if it is absent."""
        f = self._pil.get(name_str)
        if f is None:
            try:
                f = SH.pil(self.J.args.cache, name_str)          # (decoded once, shared with the menus and the field buttons)
            except Exception: f = False
            self._pil[name_str] = f
        return f or None

    def _tex_pil(self, im, lookup_key):
        """Texture (linear filter) of a PIL RGBA image, kept under `lookup_key`."""
        t = self._img.get(lookup_key)
        if t is None:
            a = np.asarray(im.convert('RGBA'))
            t = pyglet.image.ImageData(im.width, im.height, 'RGBA', np.ascontiguousarray(a[::-1]).tobytes(), pitch=im.width * 4).get_texture()
            gl.glBindTexture(t.target, t.id); gl.glTexParameteri(t.target, gl.GL_TEXTURE_MIN_FILTER, gl.GL_LINEAR); gl.glTexParameteri(t.target, gl.GL_TEXTURE_MAG_FILTER, gl.GL_LINEAR)
            self._img[lookup_key] = t
        return t

    def _sliced_tex(self, lookup_key, name_str, box):
        """Texture of a piece of the sheet `name_str` (box x0, y0, x1, y1), color of the transparent pixels propagated by one pixel (no dark fringe when filtering); None if the sheet is missing."""
        t = self._img.get(lookup_key)
        if t is None:
            f = self._sheet(name_str)
            if f is None: return None
            from PIL import Image
            if name_str == 'ui_MenuTexture.png': dy = SH.interface_dy(self.J); box = (box[0], box[1] + dy, box[2], box[3] + dy)          # (the game's interface block: DQ V / VI have it 352 px lower)
            t = self._tex_pil(Image.fromarray(HD._dilate(np.array(f.crop(box)), 1)), lookup_key)
        return t

    @staticmethod
    def _restore_blend():
        """pyglet's shapes turn off alpha blending at the end of their drawing: it is turned back on before a texture."""
        gl.glEnable(gl.GL_BLEND); gl.glBlendFunc(gl.GL_SRC_ALPHA, gl.GL_ONE_MINUS_SRC_ALPHA)

    def _pointer_in(self, z):
        """Is the mouse pointer in zone z (x0, y0, x1, y1)? Only in mouse mode: with the keyboard, nothing is hovered."""
        return bool(self.mouse_mode and self.mouse_pos is not None and z is not None and self._inside(z, *self.mouse_pos))

    def _hovered(self, z):
        """Hovered and active zone: like _pointer_in, except under a modal window (Yes / No window, open drop-down list, waiting for a key) which keeps the hover for itself."""
        return self.popup is None and self.open_dropdown is None and self.capture is None and self._pointer_in(z)

    def _cursor(self, x, yc, topmost):
        """Gold cursor of the game menus (pointing right), `topmost` pixels high, at the left at x, vertically centered at yc; it stays fixed."""
        t = self._sliced_tex('cursor', 'ui_MenuTexture.png', CURSOR)
        dx = 0.0
        if t is None:
            pyglet.shapes.Triangle(x, yc + topmost / 2, x, yc - topmost / 2, x + topmost * 0.7, yc, color=YELLOW).draw(); return
        e = topmost / float(CURSOR[3] - CURSOR[1]); self._restore_blend(); t.blit(x + dx, yc - topmost / 2, width=(CURSOR[2] - CURSOR[0]) * e, height=topmost)

    def _back_button(self, x, y, w, h, pushed):
        """Back button of the game menus: button-window of the Button sheet (nine pieces, 32 px corners reduced by half, pressed version at 96 px to the right) and its back arrow icon."""
        from PIL import Image
        lookup_key = ('retour', int(w), int(h), bool(pushed)); t = self._img.get(lookup_key); w, h = int(round(w)), int(round(h))
        if t is None:
            f = self._sheet('ui_Button.png')
            if f is not None:
                src = f.crop((96 if pushed else 0, 0, 96 + (96 if pushed else 0), 96)); c = max(2, int(round(w / 4.0)))
                im = Image.new('RGBA', (w, h)); xs = (0, c, w - c, w); ys = (0, c, h - c, h); sx = (0, 32, 64, 96)
                for i in range(3):
                    for j in range(3): im.paste(src.crop((sx[i], sx[j], sx[i + 1], sx[j + 1])).resize((xs[i + 1] - xs[i], ys[j + 1] - ys[j]), Image.LANCZOS), (xs[i], ys[j]))
                t = self._tex_pil(im, lookup_key)
        ic = self._sliced_tex('ic_retour', 'ui_MenuTexture.png', BACK_ICON)
        self._restore_blend()
        if t is not None: t.blit(x, y)
        else: self._plate(x, y, w, h, w / 64.0, pushed)
        if ic is not None:
            e = 62.4 / 64.0 * w; ic.blit(x + (w - e) / 2, y + (h - e) / 2, width=e, height=e)

    # ---- opening / closing
    FROZEN_PAGES = ()                                 # pages that stop the game behind them: NONE (no menu pauses the game; the history and the "Quit" question used to stop it). The game runs behind all pages, with no key or click (see Window.tick)

    SHARP_PAGES = ('interface', 'display')          # pages where the game stays sharp behind the menu: the interface editor places elements on it, Affichage shows its settings on it

    def blurs_game(self):
        """Is the game blurred behind the menu? Yes on every page (root, Sound, Controls, Save states, Quit, history...), except SHARP_PAGES."""
        return self.screen_page not in self.SHARP_PAGES

    def freezes_game(self):
        """Is the game stopped behind the menu? No, on no page (root "Settings", settings, history, "Quit" question): the game runs, it receives no input. It stays true only for a page added to FROZEN_PAGES (empty: see the rule above)."""
        return self.opened and self.screen_page in self.FROZEN_PAGES

    def open_menu(self, page=None, new_game=False, side=None):
        """`new_game`: the panel of a new game, at its name entry (title_screen._update_name_entry): Display (open), Sound, Controls, Difficulty, Randomizer, Cheats, the hero's name and gender,
        "Start the adventure"; its back button (or Esc at its root) goes back to the start menu. The game's rules start at their default (game_rules.GAME_KEYS: difficulty, cheats);
        display, sound and controls are the application's, the same for every game: shown as they are."""
        if self.opened: return
        self.new_game = new_game; self.draft_seed = None; self.hero_gender = None; self.randomizer_on = False          # (a seed is drawn only when the randomizer mode is turned on)
        ne = getattr(self.J, 'name_entry', None)
        if new_game and ne is not None: ne.on_ok = self._focus_start          # (Enter after typing the name on the keyboard: the cursor goes to "Start the adventure")
        if new_game:                                    # (the rules of the new game at their default: difficulty, cheats)
            GR.reset(self.J.reg)
            if hasattr(self.J, 'apply_all'): self.J.apply_all()
            elif hasattr(self.J, 'apply_game'): self.J.apply_game()
        self.opened = True; self.stack = ['root']; self.selected = {}; self.capture = None; self.message = None; self.confirmed = None; self.popup = None; self.folded = False; self.tt = None; self.begin = {}; self.seen_selected = {}; self.dragging_bar = None
        self.wants_thumbnail = True; self.minis = {}; self.rep = None; self.dragging = None; self.entry = None; self.open_dropdown = None
        self.mouse_mode = False; self.mouse_pos = getattr(self.J, 'mouse', None); self.drag = None; self.pan_pressed = None; self.pan_fold_at = None; self.pan_click_pos = None
        self.dims = {}; self.left_zones = []; self.page_rect = None
        self._guard().keyboard(self.mouse_pos)                    # the selection is by keyboard as long as the pointer has not really moved (cumulative offset from its opening point: inputs.MouseGuard)
        if page: self.stack = [page]; self.selected[page] = 2           # directly opens this page (exit question: "No" preselected, "No" or Esc close everything)
        if new_game: side = 'display'
        if side: self.stack = ['root', side]; self.selected['root'] = next((i for i, x in enumerate(self._entries_root()) if x.get('page') == side), 0)          # (Esc in the game: the page last open; a new game: Display, its first line)
        self.J.pause_game(True)
        if page == 'history' or (side == 'history' and not page): self.hist.enter()

    def shutdown(self, leaving=True):
        """Closes the menu. `leaving` False: it is closed for a moment and will be put back as it was (a battle replay): the history is not left (its battle rewind stays)."""
        if not self.opened: return
        if leaving and not self.new_game and len(self.stack) >= 2 and self.stack[0] == 'root' and self.stack[1] in RG.SETTINGS_PAGES: self.J.reg['settings_page'] = self.stack[1]          # (the menu opens on it next time)
        if 'history' in self.stack and leaving: self.hist.leave()                  # (closing the menu from the history: its battle rewind ends)
        self.new_game = False
        ne = getattr(self.J, 'name_entry', None)
        if ne is not None: ne.on_ok = None
        self.opened = False; self.capture = None; self.popup = None; self.dragging = None; self.entry = None; self.open_dropdown = None; self.J.reg.store(); self.J.pause_game(False)
        if self.mini_tex is not None:
            try: self.mini_tex.delete()
            except Exception: pass
            self.mini_tex = None

    @property
    def screen_page(self): return self.stack[-1]

    def view_state(self):
        """What the menu shows (its pages, the selected lines, the history's tab, element and scroll): to put it back as it was after a battle replay. None when it is closed."""
        if not self.opened: return None
        v = self.hist; el = v.elements[v.selected] if 0 <= v.selected < len(v.elements) else None
        return {'stack': list(self.stack), 'selected': dict(self.selected), 'tab': v.tab, 'element': el, 'pos': v.pos}

    def restore_view(self, view):
        """Opens the menu again exactly as `view_state` saw it (the history list is read again: the element is found again by its object)."""
        if view is None: return
        self.open_menu(); self.stack = list(view['stack']); self.selected = dict(view['selected'])
        if 'history' in self.stack:
            v = self.hist; v.enter(view['tab'])
            if view['element'] in v.elements: v.selected = v.elements.index(view['element']); v.pos = view['pos']

    def close_all(self):
        """Esc: the menu closes at once, whatever is open in it (a key waited for, a typed value, a question, a list); a new game's panel goes back to the start menu."""
        self.capture = None; self.entry = None; self.popup = None; self.open_dropdown = None
        if self.screen_page == 'interface': self.drag = None; self.pan_pressed = None; self.pan_fold_at = None; self.pan_click_pos = None          # (end of interface editing, as with back)
        if self.new_game: self._cancel_new_game()
        else: self.shutdown()

    def _side_by_side(self):
        """The root and its page are drawn side by side (two windows: _two_panels)."""
        J = self.J
        try: return self._two_panels(J.width, J.height, max(0.75, J.height / 900.0)) is not None
        except Exception: return False

    def back(self):
        """One step back (Backspace, B, the right click, the back button). From a page drawn beside the root of the game's menu, the menu closes: the root alone, with nothing on
        its right, is never shown (Q / R, the previous / next page keys, go from page to page)."""
        if len(self.stack) == 2 and self.stack[0] == 'root' and not self.new_game and self._side_by_side(): self.close_all(); return
        if self.screen_page == 'interface': self.J.reg.store(); self.drag = None; self.pan_pressed = None; self.pan_fold_at = None; self.pan_click_pos = None                # end of interface editing
        if self.screen_page == 'history': self.hist.leave()
        if len(self.stack) > 1: self.stack.pop()
        elif self.new_game: self._cancel_new_game()
        else: self.shutdown()

    # ---- screen entries: list of dicts {'t': 'act'|'choice'|'slider'|'key'|'sep', 'l': label, 'v': displayed value, 'ok', 'minus', 'plus', 'off'}
    PAGE_ENTRIES = {'root': '_entries_root', 'display': '_entries_display', 'interface': '_entries_interface', 'sound': '_entries_sound', 'difficulty': '_entries_difficulty', 'randomizer': '_entries_randomizer', 'cheats': '_entries_cheats', 'controls': '_entries_commands',
                    'states': '_entries_savestates', 'quit': '_entries_quit', 'history': '_entries_history', 'achievements': '_entries_achievements', 'name': '_entries_name', 'gender': '_entries_gender'}      # page identifier (string) -> method that gives its lines
    def _entries(self):
        return getattr(self, self.PAGE_ENTRIES[self.screen_page])()

    def _entries_history(self): return []                                     # (page drawn by ui_history.HistoryView: no menu line)

    def _entries_name(self): return []                                        # (page drawn by the name entry, name_entry.NameEntry: no menu line)

    def _entries_gender(self): return []                                      # (page drawn by _draw_gender: no menu line)

    def last_page(self):
        """The page the menu opens on: the one open on the right when it was last closed (setting `settings_page`, the same for every game), Display the first time or when that page
        cannot be opened now (the history while the game has control)."""
        p = self.J.reg['settings_page'] if 'settings_page' in getattr(self.J.reg, 'v', {}) else 'display'
        e = next((x for x in self._entries_root() if x.get('page') == p), None)
        return p if e is not None and not self._inactive(e) else 'display'

    def _go(self, name_str):
        def va():
            self.stack.append(name_str)
            if name_str == 'quit': self.selected[name_str] = 2        # "No" preselected
            if name_str == 'controls': self.controls_pad = getattr(self.J, 'last_device', '') == 'gamepad'          # (the keys of the device the menu was opened with)
        return va

    def _entries_root(self):
        if self.new_game:                                  # panel of a new game: the application's settings, the game's rules, the hero's name (the game's name entry, drawn on the right) and gender, then the start
            ready = self._hero_ready()                     # ("Start the adventure" grayed as long as the hero has no name or no gender)
            return [dict(t='act', l='menu.display', ok=self._go('display'), sub=True, page='display'),
                    dict(t='act', l='menu.sound', ok=self._go('sound'), sub=True, page='sound'),
                    dict(t='act', l='menu.controls', ok=self._go('controls'), sub=True, page='controls'),
                    dict(t='act', l='menu.difficulty', ok=self._go('difficulty'), sub=True, page='difficulty'),
                    dict(t='act', l='menu.randomizer', ok=self._go('randomizer'), sub=True, page='randomizer'),
                    dict(t='act', l='menu.cheats', ok=self._go('cheats'), sub=True, page='cheats'),
                    dict(t='act', l='new_game.hero_name', ok=self._go('name'), sub=True, page='name', hint='new_game.name_hero_new_game'),
                    *([] if ENGINE.ENGINE_V2 else [          # (DQ V / VI: the hero is a boy, the game asks no gender)
                        dict(t='act', l='new_game.hero_gender', ok=self._go('gender'), sub=True, page='gender', hint='new_game.gender_hero_new_game')]),
                    dict(t='act', l='new_game.start_adventure', ok=self._start_adventure, off=lambda: not self._hero_ready(), hint='new_game.rules_saved_with_game' if ready else 'new_game.choose_name_gender_first')]
        return [dict(t='act', l='menu.resume', ok=self.shutdown),
                dict(t='act', l='menu.display', ok=self._go('display'), sub=True, page='display'),
                dict(t='act', l='menu.sound', ok=self._go('sound'), sub=True, page='sound'),
                dict(t='act', l='menu.controls', ok=self._go('controls'), sub=True, page='controls'),
                dict(t='act', l='menu.save_states', ok=self._go('states'), sub=True, page='states'),
                dict(t='act', l='menu.history', ok=lambda: (self.hist.enter(), self._go('history')()), sub=True, page='history', off=lambda: not getattr(self.J, 'history_possible', lambda: True)(),
                     hint='menu.only_available_when_control_character'),
                dict(t='act', l='menu.achievements', ok=self._go('achievements'), sub=True, page='achievements'),
                dict(t='act', l='menu.difficulty', ok=self._go('difficulty'), sub=True, page='difficulty'),
                dict(t='act', l='menu.cheats', ok=self._go('cheats'), sub=True, page='cheats'),
                dict(t='act', l='menu.randomizer', ok=self._go('randomizer'), sub=True, page='randomizer'),
                dict(t='act', l='menu.return_title_screen', ok=self._return_to_title, off=lambda: not getattr(self.J, 'back_to_title_possible', lambda: True)(),
                     hint='menu.only_available_towns_world_map'),          # (the menu closes, the game opens its Yes / No box: the only way back to the game's title)
                dict(t='act', l='menu.quit_game', ok=self._quit_game, page='quit',          # (no chevron, even though the line opens the Yes / No confirmation)
                     hint='menu.closes_game_settings_history_saved')]          # same Yes / No confirmation page as the start menu (page 'quitter', "No" preselected); "Yes" -> Game.quit_game: on_close then exit

    def _choice(self, label, value_list, get, set_, off=False, default=NO_DEFAULT, restore_default=None, is_default=None):
        """Value entry: Yes / No = toggle (confirming or clicking toggles it; left = No, right = Yes); any other choice, even with two values = drop-down list
        (confirming or clicking opens it; left / right go to the previous / next value). `off`: the line cannot be modified in the current state (see _inactive: grayed, neither chosen nor hovered nor clicked).
        `default`: original value of the setting (round "default value" button to the right of the line, Delete / Home); `restore_default` / `is_default`: instead, for a setting handed back to the game (function that restores it, function that says whether it is)."""
        sw = len(value_list) == 2 and all(isinstance(v, bool) for v in value_list)
        def step(d):
            i = (value_list.index(get()) + d) % len(value_list) if get() in value_list else 0
            i = self._outside_header(value_list, i, d)
            set_(value_list[i])
        def fix_value(x):
            if get() != x: set_(x)
        if sw: minus, plus, ok = (lambda: fix_value(False)), (lambda: fix_value(True)), (lambda: set_(not get()))
        else: minus, plus, ok = (lambda: step(-1)), (lambda: step(1)), (lambda: step(1))
        d = dict(t='choice', l=label, vals=value_list, v=lambda: self._value_name(label, get()), minus=minus, plus=plus, ok=ok, off=off, get=get, set=set_, sw=sw, as_list=not sw)
        if restore_default is not None: d['default'] = restore_default; d['is_default'] = is_default or (lambda: False)
        elif default is not NO_DEFAULT: d['default'] = lambda: fix_value(default); d['is_default'] = lambda: get() == default
        return d


    @staticmethod
    def _inactive(entry):
        """The line cannot be modified in the current state (`off`: a boolean, or a function re-read on each call; the entries are redone every frame anyway: a line grayed out by another value
        becomes active again as soon as this value changes). An inactive line is grayed out entirely (label, value, arrow, round button, cell); it is neither chosen (the gold cursor and the arrows skip it), nor hovered
        (no darkened plate), nor clicked, nor confirmed, nor adjusted (left / right, Delete, Home); only its tooltip (`helptext`, if it has one) remains. Applies to all line types on all pages."""
        o = entry.get('off'); return bool(o() if callable(o) else o)

    def _active(self, entry):
        """Line that the cursor can choose: neither a subheading (or information line), nor an inactive line."""
        return entry['t'] != 'sep' and not self._inactive(entry)

    @staticmethod
    def _header(v):
        """True if the value of a drop-down list is a group subheading ("#Dialogues")."""
        return isinstance(v, str) and v[:1] == HEADER

    def _outside_header(self, vals, i, d):
        """Index of the first value that is not a subheading, starting from i in the direction d."""
        n = len(vals)
        for _ in range(n):
            if not self._header(vals[i]): break
            i = (i + (1 if d >= 0 else -1)) % n
        return i

    def _value_name(self, label, v):
        if label == 'interface.interface_edit': return self.target_name(v)
        if label == 'language.title' and v != 'system': return LG.NAMES.get(v, v)          # (the languages added while the game runs too)
        n = self.names.get(label, {}).get(v)
        if n is not None: return n
        if isinstance(v, bool): return N_('common.yes') if v else N_('common.no')
        return '%d x %d' % v if isinstance(v, tuple) else str(v)

    def _curs(self, label, get, apply, minimum, maximum, step, step_f, fmt, mult=1.0, default=None):
        """Numeric slider from `minimum` to `maximum` (values rounded to `step`, arrows: `step_f`). Clicking on the value or confirming allows typing it on the keyboard: `mult` = factor between the internal
        value and the one that is displayed and typed (100 for percentages). `default`: original value of the setting ("default value" button to the left of the slider, Delete key)."""
        def pose(v): apply(min(maximum, max(minimum, round(round(v / step) * step, 4))))
        d = dict(t='slider', l=label, v=lambda: fmt(get()), fraction=lambda: (get() - minimum) / (maximum - minimum), minus=lambda: pose(get() - step_f), plus=lambda: pose(get() + step_f),
                 set_fraction=lambda f: pose(minimum + f * (maximum - minimum)), set_value=lambda x: pose(x / mult), raw_value=lambda: ('%g' % round(get() * mult, 2)))
        if default is not None: d['default'] = lambda: pose(default); d['is_default'] = lambda: abs(get() - default) < step / 2
        return d

    names = {
        'language.title': {'system': N_('language.system')},          # (each language: its own name, LG.NAMES, drawn as it is: _value_name)
        'display.shader': {0: N_('common.none'), 1: 'EPX x8', 4: 'Pixel perfect'},
        'display.antialiasing': {0: N_('common.none'), 2: 'x2', 4: 'x4', 8: 'x8'},
        'display.supersampling': {1.0: N_('common.none'), 1.5: N_('display.x1_5'), 2.0: 'x2'},
        'controls.action': {'create': N_('save_states.create_save_state'), 'load': N_('save_states.load_save_state'), 'delete': N_('save_states.delete_a_save_state')},
    }
    names['display.text_speed'] = {0.5: N_('display.very_slow'), 1.0: N_('display.slow'), 2.0: N_('display.fairly_slow'), 4.0: N_('common.normal'), 8.0: N_('common.fast'), 16.0: N_('common.very_fast'), 4000.0: N_('display.instant')}      # (French names, translated as they are drawn: `_value_name` returns data)
    names['display.filter'] = {'none': N_('common.none'), 'sepia': N_('display.sepia'), 'gray': N_('display.black_white'), 'vivid': N_('display.vivid_colors'), 'soft': N_('display.soft_colors'), 'warm': N_('display.warm'), 'cool': N_('display.cool')}
    names['new_game.hero_gender'] = {0: N_('new_game.male'), 1: N_('new_game.female')}                         # (the words of the game's own choice: Masculin / Féminin)
    names['randomizer.items_setting'] = {0: N_('randomizer.items_unchanged'), 1: N_('randomizer.items_shuffled'), 2: N_('randomizer.items_random')}          # (randomizer/items.py: UNCHANGED, SHUFFLED, RANDOM)
    names['randomizer.loot_setting'] = {0: N_('randomizer.loot_unchanged'), 1: N_('randomizer.loot_random')}                                            # (randomizer/items.py: LOOT_UNCHANGED, LOOT_RANDOM)
    names['randomizer.encounters_setting'] = {0: N_('randomizer.encounters_unchanged'), 1: N_('randomizer.encounters_shuffled'), 2: N_('randomizer.encounters_random')}     # (randomizer/encounters.py: UNCHANGED, SHUFFLED, RANDOM)
    names['randomizer.bosses_setting'] = {0: N_('randomizer.bosses_unchanged'), 1: N_('randomizer.bosses_shuffled'), 2: N_('randomizer.bosses_random')}      # (randomizer/encounters.py: UNCHANGED_BOSSES, SHUFFLED_BOSSES, RANDOM_BOSSES)
    names['controls.battle_speed'] = RG.BATTLE_SPEED_NAMES                                                    # "Manual", "Normal", "Fast", "Very fast" (never x1, x2, x3)

    def _entries_display(self):
        J, R = self.J, self.J.reg
        def set_(k, f=None):
            def s(v):
                R[k] = v
                if f: f(v)                 # (the settings are saved when the menu closes)
            return s
        def set_language(v):
            LG.select_language(v)
            if J.language_pending(): self._info(N_('language.reload_language_at_menu_close') if J.on_title() else N_('language.reload_language_at_title'))          # (the APKs are read when the game starts; it starts again on the title screen)
        lang = self._choice('language.title', list(LG.CHOICES), lambda: R['language'], set_('language', set_language), off=self.new_game, default=RG.DEFAULT['language'])          # (above "Fullscreen"; applies immediately; grayed in a new game's panel: the reload it needs would drop the game being started)
        lang['hint'] = 'language.tool_language_hint   language.system_language_hint   language.game_language_hint'
        win = self._choice('display.fullscreen', [False, True], lambda: J.is_fullscreen, J.set_full_screen)          # (toggle: the old setting; F11 and Alt + Enter do the same thing; no "default value" button: windowed (No) is only the setting's default, settings.DEFAULT)
        win['hint'] = 'display.fullscreen_borderless_window_resolution_screen   display.f11_alt_enter_switches_between'
        msaa = self._choice('display.antialiasing', list(MSAA_CHOICES), lambda: R['msaa'], set_('msaa'), default=RG.DEFAULT['msaa'])
        if J.post.max_msaa is not None and R['msaa'] > J.post.max_msaa: msaa['hint'] = tr('display.limited_x_graphics_card') % J.post.max_msaa          # (former red note: now only a tooltip)
        pct = lambda v: '%d %%' % round(v * 100)
        def slider(label, key, minimum=0.0, maximum=1.0, step=0.01, step_f=0.05): return self._curs(label, lambda: R[key], lambda v: R.__setitem__(key, v), minimum, maximum, step, step_f, pct, 100.0, default=RG.DEFAULT[key])
        contrast = slider('display.contrast', 'contrast'); contrast['hint'] = 'display.contrast_game_picture_not_windows   display.0_as_original_game   display.100_twice_contrast'
        color_filter = self._choice('display.filter', list(RG.COLOR_FILTERS), lambda: R['color_filter'], set_('color_filter'), default=RG.DEFAULT['color_filter'])
        color_filter['hint'] = 'display.colors_game_picture_not_windows   display.none_as_original_game'
        # (this order; no "Resolution" line; "Battle speed" is on the Controls page; "Filter" just above "Shader"; no "Motion blur" line)
        return [lang, win,
                self._curs('display.brightness', lambda: R['brightness'], lambda v: R.__setitem__('brightness', v), 0.5, 1.5, 0.05, 0.1, pct, 100.0, default=RG.DEFAULT['brightness']),
                contrast, color_filter,
                self._choice('display.shader', list(RG.MODES_SPRITES), lambda: J.mode, set_('sprite_mode', J.set_mode), default=RG.DEFAULT['sprite_mode']),
                slider('display.vignette_effect', 'vignette'),
                slider('display.edge_blur', 'edge_blur'),          # (just under the vignette, same places)
                self._curs('display.sharpness', lambda: R['sharpness'], lambda v: R.__setitem__('sharpness', v), 0.0, 1.0, 0.05, 0.1, pct, 100.0, default=RG.DEFAULT['sharpness']),
                msaa,
                self._choice('display.supersampling', [1.0, 1.5, 2.0], lambda: R['render_scale'], set_('render_scale'), default=RG.DEFAULT['render_scale']),
                self._text_speed(),          # (here since then; "Battle speed" is in Commandes, under its key)
                dict(t='act', l='menu.interface', ok=self._go('interface'), sub=True)]          # (on-screen interface editor: buttons, dialogues, game windows; at the very end of the list)

    # ---- interface editor: screen buttons, dialogue window and game windows (size, position, display)
    def targets(self):
        """Values of the "Interface to edit" list: the editable elements by group (INTERFACE_GROUPS), each group preceded by its subheading ("#Dialogues"); only the game windows that have a layout appear there."""
        names = self.J.window_names(); out = []; seen = set()
        for title_screen, ids in INTERFACE_GROUPS:
            l = [i for i in ids if (i in OWN_INTERFACES and (i != RG.VEHICLE_TARGET or GM.profile().key == 'dq6')) or i in names]; seen.update(ids)          # (the vehicle button: DQ VI only)
            if l: out += [HEADER + title_screen] + l
        remainder = sorted((n for n in names if n not in seen and n not in RG.REMOVED_WINDOWS), key=lambda n: n.lower())
        return out + ([HEADER + N_('controls.other')] + remainder if remainder else [])

    def target_name(self, c):
        return c[len(HEADER):] if self._header(c) else WINDOW_NAMES.get(c, c)

    def _ov(self):
        """[size, x offset, y offset] of the chosen element (game window)."""
        return self.J.reg['interface_windows'].get(self.target) or list(RG.default_window(self.target))

    def _set_ov(self, i, v):
        d = dict(self.J.reg['interface_windows']); o = list(self._ov()); o[i] = v
        if self.target not in RG.DEFAULT['interface_windows'] and all(abs(a - b) < 1e-6 for a, b in zip(o, RG.DEFAULT_WINDOW)): d.pop(self.target, None)          # (a window that has its own default size keeps its entry, even at 100%)
        else: d[self.target] = [round(o[0], 4), round(o[1], 4), round(o[2], 4)]
        self.J.reg['interface_windows'] = d

    def _set_target(self, v):
        """Chosen interface to modify: for dialogues, a new random test message."""
        if v != self.target and v == 'msg': self.J.new_sample()
        self.target = v

    def _visible(self, c):
        """Is interface c displayed on screen? Buttons and D-pad: 'boutons' setting; game window: absent from the list of hidden interfaces. Each interface has its own setting."""
        if c == RG.SPEED_TARGET: return bool(self.J.reg['speed_button'])
        if c == RG.VEHICLE_TARGET: return bool(self.J.reg['vehicle_button'])
        return bool(self.J.reg['buttons']) if c == RG.SCREEN_TARGET else c not in self.J.reg['interface_hidden']

    def _set_visible(self, c, v):
        R = self.J.reg
        if c == RG.SCREEN_TARGET: R['buttons'] = v; return
        if c == RG.SPEED_TARGET: R['speed_button'] = v; return
        if c == RG.VEHICLE_TARGET: R['vehicle_button'] = v; return
        l = [n for n in R['interface_hidden'] if n != c]
        if not v: l.append(c)
        R['interface_hidden'] = l

    def _entries_interface(self):
        """"Interface" page: first the interface to modify (list by groups), then its display (specific to each interface), then its settings."""
        R = self.J.reg; c = self.target
        e = [self._choice('interface.interface_edit', self.targets(), lambda: self.target, self._set_target),
             self._choice('interface.show_interface_screen', [True, False], lambda: self._visible(self.target), lambda v: self._set_visible(self.target, v), default=True)]
        if c == RG.SCREEN_TARGET:
            e.append(self._curs('interface.button_size', lambda: R['buttons_size'], lambda v: R.__setitem__('buttons_size', v), 0.5, 2.0, 0.05, 0.1, lambda v: '%d %%' % round(v * 100), 100.0, default=RG.DEFAULT['buttons_size']))
            e.append(self._choice('interface.show_d_pad', [True, False], lambda: R['dpad'], lambda v: R.__setitem__('dpad', v), default=RG.DEFAULT['dpad']))
            e.append(self._curs('interface.d_pad_size', lambda: R['dpad_size'], lambda v: R.__setitem__('dpad_size', v), 0.5, 2.0, 0.05, 0.1, lambda v: '%d %%' % round(v * 100), 100.0, default=RG.DEFAULT['dpad_size']))
            e.append(self._choice('interface.show_camera_rotation_bar', [True, False], lambda: R['rotation_bar'], lambda v: R.__setitem__('rotation_bar', v), default=RG.DEFAULT['rotation_bar']))
        elif c == RG.VEHICLE_TARGET:                                                 # DQ VI's vehicle button: its size; its position is set by dragging it
            e.append(self._curs('interface.button_size_one', lambda: R['vehicle_button_size'], lambda v: R.__setitem__('vehicle_button_size', v), 0.5, 2.0, 0.05, 0.1, lambda v: '%d %%' % round(v * 100), 100.0, default=RG.DEFAULT['vehicle_button_size']))
        elif c == RG.SPEED_TARGET:                                                   # battle speed button: its size; its position is set by dragging it (or "Put back under the battle box")
            e.append(self._curs('interface.button_size_one', lambda: R['speed_button_size'], lambda v: R.__setitem__('speed_button_size', v), 0.5, 2.0, 0.05, 0.1, lambda v: '%d %%' % round(v * 100), 100.0, default=RG.DEFAULT['speed_button_size']))
            if HM.speed_anchor(): e.append(dict(t='act', l='interface.put_back_under_battle_box', ok=lambda: R.__setitem__('speed_button_pos', []), hint='interface.button_goes_back_attached_bottom'))
            else: e.append(dict(t='act', l='interface.put_back_left_edge', ok=lambda: R.__setitem__('speed_button_pos', []), hint='interface.button_goes_back_left_edge'))
        else:
            e += [self._curs('interface.size', lambda: self._ov()[0], lambda v: self._set_ov(0, v), 0.5, 2.0, 0.05, 0.1, lambda v: '%d %%' % round(v * 100), 100.0, default=RG.default_window(self.target)[0]),
                  self._curs('interface.horizontal_position', lambda: self._ov()[1], lambda v: self._set_ov(1, v), -0.5, 0.5, 0.01, 0.05, lambda v: '%+d %%' % round(v * 100), 100.0, default=RG.default_window(self.target)[1]),
                  self._curs('interface.vertical_position', lambda: self._ov()[2], lambda v: self._set_ov(2, v), -0.5, 0.5, 0.01, 0.05, lambda v: '%+d %%' % round(v * 100), 100.0, default=RG.default_window(self.target)[2])]
        e += [self._choice('interface.snap_grid', [True, False], lambda: R['buttons_snap'], lambda v: R.__setitem__('buttons_snap', v), default=RG.DEFAULT['buttons_snap']),            # (for all interfaces)
              self._choice('interface.show_grid', [True, False], lambda: R['editor_grid'], lambda v: R.__setitem__('editor_grid', v), default=RG.DEFAULT['editor_grid'])]
        this_ = dict(t='act', l='interface.restore_interface', ok=self._reset_this)
        this_['hint'] = ('interface.restores_buttons_d_pad_as   interface.game_windows_battle_speed_button' if c == RG.SCREEN_TARGET
                         else 'interface.restores_battle_speed_button_as   interface.other_interfaces_do_not_change' if c == RG.SPEED_TARGET
                         else 'interface.restores_vehicle_button_as   interface.other_interfaces_do_not_change' if c == RG.VEHICLE_TARGET
                         else 'interface.restores_window_as_game_display   interface.other_interfaces_do_not_change')
        all_entry = dict(t='act', l='interface.restore_all_interfaces', ok=self._reset_all, hint='interface.restores_all_interfaces_as_game')
        e += [this_, all_entry, dict(t='act', l='interface.finish', ok=self.back)]
        return e

    def _reset_this(self):
        """"Restore this interface": the chosen interface goes entirely back to its original state (RG.Settings.reset_interface: position, size, display and all its options, and it alone).
        Nothing else to do: the preview and the game re-read the settings every frame."""
        self.J.reg.reset_interface(self.target)

    def _reset_all(self):
        """"Restore all interfaces": all the interfaces and the editor's options (grid, snapping) back to their default (RG.Settings.reset_interfaces), and the panel returns to its original place."""
        self.J.reg.reset_interfaces(); self.pan_pos = None

    def _set_sound(self, lookup_key, category=None):
        """Sound setting (toggle or volume): saves the value, applies it immediately to the sounds playing, and for a volume plays a test sound effect (the music, however, plays during the page)."""
        def place(v):
            self.J.reg[lookup_key] = v; self.J.apply_mix()
            if category and not isinstance(v, bool): self.J.preview_sound(category)
        return place

    def _sound_line(self, lib, vol_key, category, active, helptext):
        """Line of the "Sound" page: the name of the sound, its volume bar (and its value), the mute button (`active` = (read, write) the toggle of the sound), the "default" button (original volume and sound restored).
        Keyboard: up / down changes line, left / right adjusts the volume, Enter mutes or restores the sound, Delete or Home resets the line to its default."""
        R = self.J.reg; read, write = active; place = self._set_sound(vol_key, category); default = RG.DEFAULT[vol_key]
        d = self._curs(lib, lambda: R[vol_key], place, 0.0, 1.0, 0.01, 0.05, lambda v: '%d %%' % round(v * 100), 100.0)
        def do_toggle():
            write(not read()); self.J.apply_mix()
            if read(): self.J.preview_sound(category)                                                 # (the sound comes back: it is heard)
        def reset():
            write(True); place(default)                                                       # original volume AND sound restored
        d.update(active=read, ok=do_toggle, default=reset, is_default=lambda: abs(R[vol_key] - default) < 0.005 and read(), hint=helptext)
        return d

    def _entries_sound(self):
        """One line per sound (sound.CATEGORIES, plus the sound in general): name | volume bar | mute button | "default" button; no more sections."""
        J, R = self.J, self.J.reg
        def lookup_key(c): return (lambda: R[c]), self._set_sound(c)
        gen = (lambda: J.sound.active, lambda v: (J.set_sound(v), R.__setitem__('sound', v)))
        return [self._sound_line('sound.general', 'master_volume', 'general', gen, 'sound.all_game_s_sound_multiplies   sound.game_keeps_running_behind_menu'),
                self._sound_line('sound.music', 'music_volume', 'music', lookup_key('music_enabled'), 'sound.background_music_maps_towns_battles   sound.when_muted_keeps_playing_silently   sound.volume_changes_current_music_right'),
                self._sound_line('sound.jingles_fanfares', 'jingle_volume', 'jingles', lookup_key('jingles_enabled'), 'sound.short_tunes_played_only_once   sound.volume_can_heard_next_fanfare'),
                self._sound_line('sound.sound_effects', 'sfx_volume', 'effects', lookup_key('sfx_enabled'), 'sound.game_sound_effects_battles_spells   sound.not_including_interface_sounds_line   sound.test_sound_effect_plays_when'),
                self._sound_line('menu.interface', 'interface_volume', 'interface', lookup_key('interface_enabled'), 'sound.beep_message_pages_menu_button   sound.button_sound_plays_when_change')]

    def _text_speed(self):
        """"Text speed" (dialogue writing), on the Display page, just above the Interface button."""
        J, R = self.J, self.J.reg
        vt = self._choice('display.text_speed', list(RG.TEXT_SPEEDS), lambda: R['text_speed'], lambda v: (R.__setitem__('text_speed', v), J.apply_text()), default=RG.DEFAULT['text_speed'])
        vt['hint'] = 'display.speed_which_dialogues_written_letters   display.normal_same_as_original_game'
        return vt

    def _battle_speed(self):
        """"Battle speed" (Manuel, Normal, Rapide, Tres rapide: engine clock during battles and scrolling of battle messages), on the Controls page just under the key that changes it (on the Display page before)."""
        J, R = self.J, self.J.reg
        cb = self._choice('controls.battle_speed', list(RG.BATTLE_SPEEDS), lambda: R['battle_speed'], J.set_battle_speed, default=RG.DEFAULT['battle_speed'])
        cb['hint'] = 'controls.battles_only_animations_follow_one   controls.manual_normal_speed_advance_each   controls.music_sound_effects_keep_their   controls.can_also_set_middle_battle'
        return cb

    def _entries_difficulty(self):
        """Page "Difficulty" (formerly a tab of "Extras", formerly "Modifiers", "Changes", "Game"), right below "Controls" in the root menu, then "Randomizer" and "Cheats": HP and MP restored,
        the difficulty level and its 6 notched lines. Everything is as in the original game by default."""
        J, R = self.J, self.J.reg
        sn = self._choice('difficulty.hp_mp_restored_level_up', [True, False], lambda: R['level_up_heal'], lambda v: (R.__setitem__('level_up_heal', v), J.apply_game()), default=RG.DEFAULT['level_up_heal'])
        sn['hint'] = 'difficulty.when_character_gains_level_they   difficulty.no_as_original_game_leveling'
        sb = self._choice('difficulty.hp_mp_restored_battle_end', [True, False], lambda: R['battle_end_heal'], lambda v: (R.__setitem__('battle_end_heal', v), J.apply_game()), default=RG.DEFAULT['battle_end_heal'])
        sb['hint'] = 'difficulty.after_each_battle_members_standing   difficulty.no_as_original_game_battle'
        lo, hi = RG.RATES[0], RG.RATES[-1]; leveled = lambda: R['difficulty'] != RG.DIFFICULTY_CUSTOM          # (a difficulty level sets the notched lines and grays them; Custom: by hand)
        def set_difficulty(v):
            was = R['difficulty']; R['difficulty'] = v = int(round(v))
            if v != RG.DIFFICULTY_CUSTOM: rates = RG.difficulty_rates(v)
            elif was != RG.DIFFICULTY_CUSTOM: rates = {k: RG.DEFAULT[k] for k in RG.RATE_KEYS}          # (moving to Custom: every notched line back to its default, "Normal"; staying on it changes nothing)
            else: rates = {}
            for k, r in rates.items(): R[k] = r
            J.apply_game()
        sd = self._curs('difficulty.difficulty_level', lambda: R['difficulty'], set_difficulty, 0, RG.DIFFICULTY_CUSTOM, 1, 1, lambda v: RG.DIFFICULTY_NAMES.get(int(v), N_('difficulty.dragon')), default=RG.DEFAULT['difficulty'])
        sd['hint'] = 'difficulty.difficulty_sets_notched_options   difficulty.custom_each_option_by_hand   difficulty.dragon_as_original_game'
        sd['notches'] = [n / RG.DIFFICULTY_CUSTOM for n in RG.DIFFICULTIES]; sd['notch_names'] = [RG.DIFFICULTY_NAMES[n] for n in RG.DIFFICULTIES]
        def rate(label, key, hint):                     # 5 notches: Much less (x0.5), Less (x0.75), Normal (x1), More (x1.25), Much more (x1.5); only their names are shown
            c = self._curs(label, lambda: R[key], lambda v: (R.__setitem__(key, v), J.apply_game()), lo, hi, 0.25, 0.25, lambda v: RG.RATE_NAMES.get(v, N_('common.normal')), default=RG.DEFAULT[key])
            c['hint'] = hint + '   difficulty.normal_as_original_game_rewards' + ('   difficulty.set_by_difficulty_choose_custom' if leveled() else ''); c['off'] = leveled
            c['notches'] = [(v - lo) / (hi - lo) for v in RG.RATES]; c['notch_names'] = [RG.RATE_NAMES[v] for v in RG.RATES]; c['indent'] = 1; return c          # (under "Difficulty": shifted)
        sx = rate('difficulty.experience_gained', 'exp_rate', 'difficulty.experience_won_battle_multiplied')
        sg = rate('difficulty.gold_gained', 'gold_rate', 'difficulty.gold_won_battle_multiplied')
        sc = rate('difficulty.casino_tokens_won', 'casino_rate', 'difficulty.casino_tokens_won_multiplied')
        sp = rate('difficulty.damage_taken_party', 'party_damage_rate', 'difficulty.damage_hits_spells_party_multiplied')
        se = rate('difficulty.damage_taken_enemies', 'enemy_damage_rate', 'difficulty.damage_hits_spells_enemies_multiplied')
        sf = rate('difficulty.encounter_rate', 'encounter_rate', 'difficulty.random_battles_more_less_often')          # (set even without random encounters: it is kept for when they come back)
        return [sn, sb, sd, sx, sg, sc, sp, se, sf]

    def _entries_randomizer(self):
        """Page "Randomizer" (in the root, under "Difficulty"). New game: the randomizer mode (No by default: the original game, no seed), then, when it is on, the seed drawn when it was
        turned on, which can be typed or pasted (it sets the whole page) or drawn again (the settings stay), then the settings, which the seed code carries (randomizer/seed.py): changing
        one changes the code, not its random number. "Safety" heads them. During a game: its seed (Enter copies it, to reuse it in another game) and its settings, which no longer change;
        a game without the randomizer has none."""
        if self.new_game:
            def set_on(v):
                self.randomizer_on = bool(v)
                if v and self.draft_seed is None: self.draft_seed = SD.new_code()
            mode = self._choice('randomizer.randomizer_mode', [True, False], lambda: self.randomizer_on, set_on, default=False); mode['hint'] = 'randomizer.yes_randomizer_game_seed   randomizer.no_original_game_randomizer'
            if not self.randomizer_on: return [mode]
            lines = [mode, dict(t='act', l='randomizer.seed', v=lambda: self.draft_seed, ok=self._start_text_entry, hint='randomizer.seed_sets_whole_page   randomizer.type_paste_seed   randomizer.round_button_new_seed',
                                text_entry=dict(chars=set(SD.ALPHABET + 'OIL-'), max=20, set=self._type_seed, prompt='randomizer.type_paste_seed'),
                                default=self._new_seed, is_default=lambda: False)]          # (the round button on the right of the seed, or Home: a new seed, the settings kept)
            return lines + self._randomizer_settings(lambda: self.draft_seed, self._set_draft_option)
        gr = getattr(self.J, 'game_rules', None); code = gr.seed() if gr is not None else None
        if not code: return [dict(t='sep', l=N_('randomizer.game_without_randomizer'), gray=True)]
        return [dict(t='act', l='randomizer.seed', v=lambda: code, ok=lambda: self._copy_seed(code), hint='randomizer.enter_copies_seed')] + self._randomizer_settings(lambda: code, None)

    RANDOMIZER_SETTINGS = (('safety', 'randomizer.safety', 'randomizer.safety_yes   randomizer.safety_no'),
                           ('items', 'randomizer.items_setting', 'randomizer.items_where   randomizer.items_shuffled_hint   randomizer.items_random_hint'),
                           ('loot', 'randomizer.loot_setting', 'randomizer.loot_where   randomizer.loot_random_hint'),
                           ('encounters', 'randomizer.encounters_setting', 'randomizer.encounters_where   randomizer.encounters_shuffled_hint   randomizer.encounters_random_hint'),
                           ('single_enemy', 'randomizer.single_enemy_setting', 'randomizer.single_enemy_yes   randomizer.single_enemy_no'),
                           ('boss_encounters', 'randomizer.boss_encounters_setting', 'randomizer.boss_encounters_yes   randomizer.boss_encounters_no'),
                           ('bosses', 'randomizer.bosses_setting', 'randomizer.bosses_where   randomizer.bosses_shuffled_hint   randomizer.bosses_random_hint'),
                           ('two_bosses', 'randomizer.two_bosses_setting', 'randomizer.two_bosses_yes   randomizer.two_bosses_no'))
    YES_NO_SETTINGS = ('safety',)                                           # (value 0 = Yes)
    NO_YES_SETTINGS = ('single_enemy', 'boss_encounters', 'two_bosses')     # (value 0 = No)
    NEEDS = {'single_enemy': ('encounters', 2)}                             # a setting that only acts with another one's value (grayed otherwise): one enemy, with random encounters "Random"

    def _randomizer_settings(self, code, set_option):
        """The settings of the Randomizer page, read from the seed code `code()`; `set_option` (key, value) None: shown only (during a game, the settings no longer change)."""
        def get(k):
            p = SD.parse(code() or '')
            return p['options'].get(k, 0) if p else 0
        lines = []
        for k, label, hint in self.RANDOMIZER_SETTINGS:
            off = set_option is None
            if not off and k in self.NEEDS: off = lambda k=k: get(self.NEEDS[k][0]) != self.NEEDS[k][1]
            if k in self.YES_NO_SETTINGS: e = self._choice(label, [True, False], lambda k=k: get(k) == 0, lambda v, k=k: set_option(k, 0 if v else 1), off=off, default=True if set_option else NO_DEFAULT)
            elif k in self.NO_YES_SETTINGS: e = self._choice(label, [True, False], lambda k=k: get(k) == 1, lambda v, k=k: set_option(k, 1 if v else 0), off=off, default=False if set_option else NO_DEFAULT)
            else: e = self._choice(label, list(range(len(self.names[label]))), lambda k=k: get(k), lambda v, k=k: set_option(k, v), off=off, default=0 if set_option else NO_DEFAULT)
            e['hint'] = hint; lines.append(e)
        return lines

    def _set_draft_option(self, k, v):
        """A setting of the page changed: the seed code changes with it (same random number)."""
        p = SD.parse(self.draft_seed or '')
        if p is not None: self.draft_seed = SD.new_code(dict(p['options'], **{k: v}), p['number'])

    def _new_seed(self):
        """"New seed": another random number, the page's settings kept."""
        p = SD.parse(self.draft_seed or ''); self.draft_seed = SD.new_code(p['options'] if p else None)

    def _hero_ready(self):
        ne = getattr(self.J, 'name_entry', None)
        return bool(ne is not None and ne.text) and (self.hero_gender is not None or ENGINE.ENGINE_V2)

    def _open_root_page(self, page):
        self.stack = ['root', page]; self.selected['root'] = next((i for i, x in enumerate(self._entries_root()) if x.get('page') == page), 0)

    def _start_adventure(self):
        """"Start the adventure": the rules are kept for the game the engine creates and the name and gender are sent to it (without a name or a gender yet: its page opens; the line is grayed then)."""
        ne = getattr(self.J, 'name_entry', None)
        if ne is None or not ne.text: self._open_root_page('name'); return
        if self.hero_gender is None and not ENGINE.ENGINE_V2: self._open_root_page('gender'); return
        if hasattr(self.J, 'game_rules'): self.J.game_rules.prepare(GR.snapshot(self.J.reg, self.draft_seed if self.randomizer_on else None))          # (kept until the engine gives the game its ID; no seed: a game without the randomizer)
        name_str = ne.text; ne.handed = True; self.new_game = False; self.shutdown(); self.J._name_entry_ok(name_str, self.hero_gender)          # (the game then asks the gender: answered by the port)

    def _focus_start(self):
        """Enter after typing the name on the keyboard: the gender page if it is not chosen yet, otherwise back to the panel's list, on "Start the adventure"."""
        if self.hero_gender is None and not ENGINE.ENGINE_V2: self._open_root_page('gender'); return
        self.stack = ['root']; self.selected['root'] = next((i for i, x in enumerate(self._entries_root()) if x.get('l') == 'new_game.start_adventure'), 0)

    def _cancel_new_game(self):
        """The panel's back button (or Esc at its root): back to the start menu, like Back on the game's name entry (no rules kept)."""
        ne = getattr(self.J, 'name_entry', None)
        if ne is not None: ne.handed = True
        self.new_game = False; self.shutdown()
        if hasattr(self.J, '_name_entry_back'): self.J._name_entry_back()

    def _start_text_entry(self):
        """Typing the text of the chosen line (its `text_entry`: allowed characters, length, function that receives the text)."""
        self.entry = [self.selected.get(self.screen_page, 0), '']

    def _type_seed(self, text):
        p = SD.parse(text)
        if p is None: self._info(N_('randomizer.invalid_seed'), True); return
        self.draft_seed = p['code']

    def _copy_seed(self, code):
        f = getattr(self.J, 'set_clipboard_text', None)
        if f is None: return
        try: f(code); self._info(N_('randomizer.seed_copied'))
        except Exception: pass

    def _entries_cheats(self):
        """Page "Cheats" (in the root, under "Randomizer"): "Random encounters" (No: none while walking; "Encounter rate", on the "Difficulty" page, stays settable)."""
        J, R = self.J, self.J.reg
        sr = self._choice('difficulty.random_encounters', [True, False], lambda: R['random_encounters'], lambda v: (R.__setitem__('random_encounters', v), J.apply_game()), default=RG.DEFAULT['random_encounters'])
        sr['hint'] = 'difficulty.no_random_battle_walking   difficulty.yes_as_original_game_encounters'
        return [sr]

    def _entries_achievements(self):
        """"Achievements" page (in the root, under "Cheats"): none yet."""
        return [dict(t='sep', l=N_('menu.no_achievement_yet'), gray=True)]

    def _key_row(self, action):
        """Line of an action: three cells (main key, secondary key, gamepad input); Delete clears the chosen cell, the round button (or Home) restores the original keys and input."""
        R = self.J.reg
        def default():
            lost = R.reset_to_default(action); lost.append(R.reset_pad(action))
            for a in dict.fromkeys(a for a in lost if a): self._info(N_('controls.default_key_removed_from'), False, dict(RG.ACTIONS)[a])
            R.store()
        return dict(t='key', l=dict(RG.ACTIONS)[action], act=action, v=[RG.key_name(n) for n in R['keys'][action]] + [R['gamepad'].get(action)], keys=list(R['keys'][action]), default=default,
                    is_default=lambda: R.is_default_binding(action) and R.is_default_pad(action))          # (v[2]: the gamepad input name or names, drawn according to the connected controller; keys: the key names, for their pictures)

    def _entries_commands(self):
        """Sections (subheadings): movement (keys), "Camera" (left / right keys, mouse, direction; a single group), speeds (key and accelerator multiplier: slider from x1 to x4; then the "Change battle speed" key), game actions, others (special key, info); then the key reset."""
        R = self.J.reg; T = self._key_row
        def speed_accel_cursor(lib, lookup_key, minimum, maximum):
            return self._curs(lib, lambda: R[lookup_key], lambda v: R.__setitem__(lookup_key, v), minimum, maximum, 0.1, 0.5, lambda v: 'x%.2f' % v, 1.0, default=RG.DEFAULT[lookup_key])
        def inverse(lib, lookup_key, helptext):
            d = self._choice(lib, [False, True], lambda: R[lookup_key], lambda v: R.__setitem__(lookup_key, v), default=RG.DEFAULT[lookup_key]); d['hint'] = helptext; return d
        edit = T('modifier'); edit['hint'] = 'controls.digit_loads_save_state   controls.shift_undoes_last_save_state'
        accel = T('accel'); accel['hint'] = 'controls.held_down_speeds_up_walking   controls.no_effect_battle   ' + self.KEY_HELPTEXT
        info = T('info'); info['hint'] = 'controls.shows_hides_top_right_screen   ' + self.KEY_HELPTEXT
        speed_accel = speed_accel_cursor('controls.accelerator_multiplier', 'accel_speed', 1.0, 4.0); speed_accel['hint'] = 'controls.multiplies_walking_speed_while_accelerator   controls.nightfall_x_times_faster_as   controls.random_encounters_x_times_more   controls.battles_do_not_use_they'
        key_battle = T('battle_speed'); key_battle['hint'] = 'controls.goes_from_manual_normal_fast   controls.also_works_middle_battle_setting   ' + self.KEY_HELPTEXT
        return [dict(t='sep', l='controls.movement'),
                T('up'), T('down'), T('left'), T('right'),
                dict(t='sep', l='controls.camera'),
                *[dict(T(a), hint='controls.rotates_camera_around_hero_towns   controls.both_arrow_keys_together_recenters   controls.mouse_hold_middle_click_move   controls.middle_click_recenters_camera   controls.menus_previous_next_character_tab   ' + self.KEY_HELPTEXT) for a in ('cam_left', 'cam_right')],
                *[dict(t='sep', l=g, v=e) for g, e in MOUSE_GESTURES],          # (read-only: information lines, neither chosen nor clickable)
                inverse('controls.invert_left_right', 'camera_invert_lr', 'controls.camera_moved_mouse_hold_middle   controls.no_dragging_right_rotates_like   controls.keyboard_arrow_keys_do_not'),          # (under the mouse lines: it reverses the mouse drag)
                dict(t='sep', l='controls.speeds'),
                accel, speed_accel, key_battle, self._battle_speed(),          # ("Battle speed" under its key)
                dict(t='sep', l='controls.game_actions'),
                T('A'), T('menu'), T('B'), T('map'), T('chat'), *([T('extra')] if GM.profile().key == 'dq6' else []),          # (vehicle command: DQ VI only, see core/pad_modes.py)
                dict(t='sep', l='controls.other'),
                edit, info,
                dict(t='act', l='controls.restore_default_keys', ok=lambda: (R.default_keys(), R.store()))]


    @staticmethod
    def _state_date(date):
        """':05' -> '31/10/2026 19:21:05' in French, ':05' in English (name of a savestate: its saving date and time; day/month/year reads backwards for an English-speaking
        reader, "03/11" would be March 11 there: the year-month-day order leaves no doubt)."""
        try: return time.strftime(tr('save_states.date_format'), time.strptime(date, '%Y-%m-%d %H:%M:%S'))          # (each language's own date format)
        except Exception: return ''

    @staticmethod
    def _readable_location(inf):
        """Location of the state only if it means something to a player (the technical name of a map, like "mak1f1", is not shown)."""
        location = inf.get('location', ''); location = LEGACY_LOCATIONS.get(location, location)
        return location if location in ('save_states.world_map', 'save_states.battle') else ''

    def _entries_savestates(self):
        """Savestates: one line per slot. Confirming or clicking a slot that holds a state opens, beside it, the list of what to do with it (load it, create a new one over it, delete it: through
        a confirmation window); an empty slot receives a new state at once."""
        e = []
        for n in range(1, SAVESTATE_COUNT + 1):
            inf = self.J.state_info(n)
            if inf: lib = self._state_date(inf[0].get('date')) or 'save_states.no_date'; val = self._readable_location(inf[0])
            else: lib = 'save_states.empty'; val = ''
            do = lambda a, n=n: {'create': self._save, 'load': self._load, 'delete': self._request_deletion}[a](n)
            e.append(dict(t='slot', l=lib, v=val, n=n, off=False, vals=['load', 'create', 'delete'] if inf else ['create'], list_label='controls.action', get=lambda: None, set=do,
                          ok=(lambda n=n, full=bool(inf): self._open_list() if full else self._save(n))))
        return e

    def _entries_quit(self):
        return [dict(t='sep', l='common.sure'), dict(t='act', l='common.yes', ok=self.J.quit_game), dict(t='act', l='common.no', ok=self.back)]

    def _quit_game(self):
        """"Quit the game": where the game's box answers (towns, world map), the menu closes and the box asks the game's own question (Game.ask_quit, message b0834000.mpt#96: French or English
        with the game), Yes / No; elsewhere, the Yes / No page of the menu (and the start menu's "Quit" keeps it)."""
        if getattr(self.J, 'back_to_title_possible', lambda: False)() and hasattr(self.J, 'ask_quit'): self.shutdown(); self.J.ask_quit()
        else: self._go('quit')()

    def _return_to_title(self):
        """"Return to title screen": the menu closes (the game resumes) and the engine opens the original box of the game's "Settings" button (game text, Yes / No); what follows (Yes: fade then title, No: back to the game)
        is the engine's job (Engine.request_return_to_title)."""
        self.shutdown(); self.J.back_to_title()

    # ---- actions
    def _info(self, model, error=False, *value_list):
        """Information message (4 seconds, above the frame): `model` is a key whose text has placeholders (%d, %s) if there are `value_list`. `message[0]` is the full text in the language of the moment; the display (`_message_text`) translates the model BEFORE putting
        the values in (English does not have the same word order), and also translates the values that are texts of the tool (name of an action, name of a key)."""
        self.message = (tr(model) % tuple(tr(v) for v in value_list) if value_list else tr(model), time.time(), error, model, value_list)

    def _message_text(self):
        """The information message in the language of the tool ('' if there is none, or if it is more than 4 seconds old)."""
        m = self.message
        if not m or time.time() - m[1] >= 4.0: return ''
        return tr(m[3]) % tuple(tr(v) for v in m[4]) if m[4] else tr(m[3])

    def _save(self, n):
        try:
            self.J.save_state(n, self.J._png_thumbnail(self.mini_tex))
            self.minis.pop(n, None); self._info(N_('save_states.save_state_stored_slot'), False, n)
        except Exception as ex:
            self._info(N_('save_states.could_not_save_state_r'), True, ex)

    def _load(self, n):
        try:
            self.J.load_state(n); self.shutdown()
        except SS.OtherLanguage as ex:
            self._ask_language(n, ex.language)
        except SS.OtherEngine:
            self._info(N_('save_states.state_was_saved_other_apk'), True)
        except Exception as ex:
            self._info(N_('save_states.could_not_load_state_r'), True, ex)

    def _ask_language(self, n, language):
        """The state was saved with another game version (`language`: the language of its APK folder): a Yes / No window offers to switch the game to that language and load it (the game restarts
        in that language, the "Language" setting follows; No: nothing changes)."""
        model = N_('language.switch_game_language_load_state'); name = LG.language_name(language)
        self.popup = dict(title=tr(model) % name, model=model, values=(name,), detail=tr('language.state_was_saved_language_version') % name,
                          yes=lambda: (self.shutdown(), self.J.reload_game(language, n)), choice=1)

    def _request_deletion(self, n):
        """Delete state n: a modal window asks for confirmation ("No" preselected)."""
        inf = self.J.state_info(n); date = self._state_date(inf[0].get('date')).strip() if inf else ''
        model = N_('save_states.delete_save_state_n')
        self.popup = dict(title=tr(model) % n, model=model, values=(n,), detail=date, yes=lambda: self._delete(n), choice=1)          # (`model` + `value_list`: the title is translated before the number is put in, see _draw_popup)

    def _popup_key(self, symbol, action):
        K = pyglet.window.key; p = self.popup; n = len(p.get('buttons') or ()) or 2
        if symbol in (K.ESCAPE, K.BACKSPACE) or action == 'B': self.popup = None
        elif action in ('left', 'up', 'cam_left'): p['choice'] = (p['choice'] - 1) % n
        elif action in ('right', 'down', 'cam_right'): p['choice'] = (p['choice'] + 1) % n
        elif symbol in (K.RETURN, K.ENTER, K.SPACE) or action == 'A': self._choose_popup(p['choice'])

    def _choose_popup(self, i):
        """Button i of the modal window: Yes (0) / No (1), or the i-th of its own `buttons` (a list of choices: choosing is the confirmation)."""
        p = self.popup
        if p and p.get('buttons'):
            self.popup = None
            if 0 <= i < len(p['buttons']): p['buttons'][i][1]()
        else: self._validate_popup(i == 0)

    def _validate_popup(self, yes):
        p, self.popup = self.popup, None
        if yes and p and p.get('yes'): p['yes']()

    def _delete(self, n):
        try:
            os.remove(self.J.state_path(n))
            t = self.minis.pop(n, None)
            if t is not None:
                try: t.delete()
                except Exception: pass
            self._info(N_('save_states.save_state_deleted'), False, n)
        except Exception as ex:
            self._info(N_('save_states.could_not_delete_state_r'), True, ex)

    # ---- keyboard keys
    def key_press(self, symbol, modifiers=0):
        """True if the key is consumed (the menu is open)."""
        K = pyglet.window.key; R = self.J.reg
        self.mouse_mode = False; self._guard().keyboard(self.mouse_pos)       # a key: back to keyboard selection (gold cursor), the pointer takes over again at the first real movement (or at the click)
        if symbol == K.ESCAPE: self.close_all(); return True                    # Esc: the whole menu closes, from any page or state (Backspace, B, the right click: one step back)
        if self.screen_page == 'history' and self.popup is None: return self.hist.key_press(symbol, modifiers)
        if self.screen_page == 'gender' and self.popup is None:                        # the gender page: left / right choose, Enter chooses the one under the cursor and goes back to the panel's list (on "Start the adventure" once the name is there too), Backspace goes back
            action = R.action_of(symbol)
            if symbol in (K.LEFT, K.RIGHT) or action in ('left', 'right'): self.hero_gender = 0 if (symbol == K.LEFT or action == 'left') else 1
            elif symbol in (K.RETURN, K.ENTER) or action == 'A':
                if self.hero_gender is None: self.hero_gender = 0
                if self._hero_ready(): self._focus_start()              # (name and gender chosen: on "Start the adventure")
                else: self.back()
            elif symbol == K.BACKSPACE or action == 'B': self.back()
            return True
        if self.screen_page == 'name' and self.popup is None:                          # the name page: its keyboard (Esc: back to the panel's list)
            if symbol == K.ESCAPE: self.back()
            elif hasattr(self.J, 'name_entry'): self.J.name_entry.key_press(symbol, modifiers)
            return True
        if self.capture is not None: self._capture(symbol); return True
        if self.entry is not None: self._entry_key(symbol, modifiers); return True
        action = R.action_of(symbol)
        if self.popup is not None: self._popup_key(symbol, action); return True
        if self.screen_page == 'interface' and symbol == K.TAB: self.folded = not self.folded; self.pan_fold_at = None; self.pan_click_pos = None; return True              # (editor: collapse / expand the panel)
        if self.screen_page == 'interface' and self.folded and not (symbol in (K.ESCAPE, K.BACKSPACE) or action == 'B'): return True
        if self.open_dropdown is not None: self._list_key(symbol, action); return True
        if symbol in (K.ESCAPE, K.BACKSPACE) or action == 'B': self.back(); return True
        if action == 'info': self.J.set_info(not self.J.helptext); R['info'] = self.J.helptext; return True          # (the on-screen info key is set in "Controls")
        if self.screen_page == 'controls' and action in ('cam_left', 'cam_right'): self.switch_device(); return True          # camera keys: Clavier / Manette (rule: the camera keys change the section)
        if symbol == K.DELETE: self._delete_key(); return True
        if symbol == K.HOME: self._default(); return True
        if action in ('L', 'R') and self.stack and self.stack[0] == 'root' and len(self.stack) <= 2 and self._side_by_side(): self._cycle_root(-1 if action == 'L' else 1); return True          # previous / next line of the root (its page opens on the right)
        if action == 'up': self._move(-1); self._repeat(symbol, 'v', -1)          # (only the keys of "Controls"; the camera keys are left / right, as in the game's menus)
        elif action == 'down': self._move(1); self._repeat(symbol, 'v', 1)
        elif action in ('left', 'cam_left'): self._change_value(-1); self._repeat(symbol, 'h', -1)
        elif action in ('right', 'cam_right') and self.screen_page == 'root' and (self._current() or {}).get('page'): self._validate()          # root: right opens the page of the chosen line (drawn on its right), like Enter
        elif action in ('right', 'cam_right'): self._change_value(1); self._repeat(symbol, 'h', 1)
        elif symbol in (K.RETURN, K.ENTER, K.SPACE) or action == 'A': self._validate()
        return True

    def _repeat(self, symbol, direction, d):
        """A direction is held down: it will repeat (do_update) as long as it is held, on the line and screen where it started."""
        t = time.time(); self.rep = (symbol, t, t, direction, d); self.rep_pos = (self.screen_page, self.selected.get(self.screen_page, 0))

    def do_update(self):
        """Repeat of held directions, long press on the editor panel (called every frame). "Sound" page: the sounds play (the game is stopped) so that the volumes being adjusted can be heard."""
        S = self.J.sound; listening = self.screen_page == 'sound'
        if self.screen_page == 'history':
            if not getattr(self.J, 'history_possible', lambda: True)(): self.back()          # the game has taken control back (battle, dialogue, scene: the game runs behind the menu): the history is accessible only when the player has control of their character
            else: self.hist.follow_game()          # the game runs behind the history: what it writes there is added at the bottom of the list
        if listening != S.listening: S.listen(listening)
        if listening: S.tick()
        if self.pan_fold_at is not None and self.pan_pressed is None and time.time() >= self.pan_fold_at: self._fold_pending()          # single click on the title bar: the collapse happens when the double-click delay has elapsed without a second press
        a = self.pan_pressed
        if a is not None and not (a['long'] or a['double']) and time.time() - a['t0'] >= (LONG_PRESS_DELAY or EN.system_click()[0]): a['long'] = True          # press held without moving: the panel lifts (it will follow the pointer at the first movement)
        if not self.rep: return
        sym, t0, tl, direction, d = self.rep; t = time.time()
        if not self.J.key_list[sym]: self.rep = None; return
        if direction == 'h' and self.rep_pos != (self.screen_page, self.selected.get(self.screen_page, 0)): self.rep = None; return       # the selection has changed (mouse, other screen): the repeat stops, it must never touch another setting
        if t - t0 > REPEAT_DELAY and t - tl > REPEAT_STEP:
            self.rep = (sym, t0, t, direction, d)
            if direction == 'v': self._move(d)
            else: self._change_value(d)

    # ---- drop-down list
    def _open_list(self):
        i = self.selected.get(self.screen_page, 0); entry = self._entries()[i]; cur = entry['get']()
        self.open_dropdown = [i, entry['vals'].index(cur) if cur in entry['vals'] else 0]; self.entries_top = None; self.entries_cur_seen = None; self.dragging_entries = None

    def _entries_end(self, valid):
        d, self.open_dropdown = self.open_dropdown, None
        if not valid or d is None: return
        e = self._entries()
        if d[0] < len(e) and e[d[0]]['t'] in ('choice', 'slot') and not self._inactive(e[d[0]]) and not self._header(e[d[0]]['vals'][d[1]]): e[d[0]]['set'](e[d[0]]['vals'][d[1]])

    def _move_entries(self, d):
        e = self._entries()
        if self.open_dropdown[0] >= len(e) or e[self.open_dropdown[0]]['t'] not in ('choice', 'slot') or self._inactive(e[self.open_dropdown[0]]): self.open_dropdown = None; return
        vals = e[self.open_dropdown[0]]['vals']; n = len(vals); self.open_dropdown[1] = self._outside_header(vals, (self.open_dropdown[1] + d) % n, d)          # (the group subheadings are skipped)

    def _list_key(self, symbol, action):
        K = pyglet.window.key
        if symbol in (K.ESCAPE, K.BACKSPACE) or action == 'B': self._entries_end(False)
        elif action == 'up': self._move_entries(-1); self._repeat(symbol, 'v', -1)
        elif action == 'down': self._move_entries(1); self._repeat(symbol, 'v', 1)
        elif symbol == K.PAGEUP: self._move_entries(-7)
        elif symbol == K.PAGEDOWN: self._move_entries(7)
        elif symbol in (K.RETURN, K.ENTER, K.SPACE) or action == 'A': self._entries_end(True)

    def _set_top(self, t):
        """First visible value of the drop-down list (the scrollbar moves it without changing the highlighted value)."""
        b = self.list_bar
        if b: self.entries_top = max(0, min(int(t), b['n'] - b['visible']))

    def _click_entries_bar(self, x, y):
        b = self.list_bar; top = self.entries_top or 0
        if y > b['ptop']: self._set_top(top - 1)
        elif y < b['pbot']: self._set_top(top + 1)
        elif b['thumb'][0] <= y <= b['thumb'][1]: self.dragging_entries = b['thumb'][1] - y
        elif y > b['thumb'][1]: self._set_top(top - (b['visible'] - 1))
        else: self._set_top(top + (b['visible'] - 1))

    def _drag_entries_bar(self, y):
        b = self.list_bar
        if not b: self.dragging_entries = None; return
        free = b['ptop'] - b['pbot'] - b['th']
        if free > 0: self._set_top(round(max(0.0, min(1.0, (b['ptop'] - (y + self.dragging_entries)) / free)) * (b['n'] - b['visible'])))

    def _list_zone(self, x, y):
        for (x0, y0, x1, y1, j) in self.zones_pop:
            if x0 <= x <= x1 and y0 <= y <= y1: return j
        return None

    def _move(self, d):
        if self.screen_page == 'history': return self.hist.move_by(d)
        if self.open_dropdown is not None: self._move_entries(d); return
        e = self._entries(); n = len(e)
        if not n: return
        i = self.selected.get(self.screen_page, 0)
        for _ in range(n):
            i = (i + d) % n
            if self._active(e[i]): self.selected[self.screen_page] = i; break              # (subheadings and inactive lines are skipped; page with no active line: the selection does not move)

    def _current(self):
        """Chosen line, or None when it is inactive (no action reaches it: left / right, Delete, Home, Enter); a subheading gives way to the next line."""
        e = self._entries(); i = min(self.selected.get(self.screen_page, 0), len(e) - 1)
        if e and e[i]['t'] == 'sep':
            self._move(1); i = min(self.selected.get(self.screen_page, 0), len(e) - 1)
        return e[i] if e and e[i]['t'] != 'sep' and not self._inactive(e[i]) else None

    def _active_line(self, e, i):
        """Index of the line that the cursor must occupy: i if it is active, otherwise the first active line after it, then before it; i if no line is active (page with nothing to choose: the cursor is not drawn)."""
        for j in list(range(i, len(e))) + list(range(i - 1, -1, -1)):
            if self._active(e[j]): return j
        return i

    def _purge_inactive(self, e):
        """What held a line that became inactive stops: open drop-down list, slider held with the mouse, value being typed."""
        def inactive(i): return i is not None and 0 <= i < len(e) and e[i]['t'] != 'sep' and self._inactive(e[i])
        if self.open_dropdown is not None and inactive(self.open_dropdown[0]): self.open_dropdown = None
        if self.dragging is not None and inactive(self.dragging): self.dragging = None
        if self.entry is not None and inactive(self.entry[0]): self.entry = None

    def _change_value(self, d):
        if self.open_dropdown is not None: return
        entry = self._current()
        if not entry: return
        if entry['t'] in ('choice', 'slider'): (entry['minus'] if d < 0 else entry['plus'])()
        elif entry['t'] == 'key':
            c = self.selected.get('col', 0); self.selected['col'] = min(1, max(0, c + d))

    def _default(self):
        """Resets the slider, the choice or the keys of the chosen line to their original value."""
        entry = self._current()
        if entry and entry['t'] in ('slider', 'key', 'choice', 'act') and 'default' in entry: entry['default']()

    def _delete_key(self):
        """Delete: slider or choice -> original value; key -> the selected slot is cleared."""
        entry = self._current()
        if not entry: return
        if entry['t'] == 'key': self._clear_cell(entry['act'], self.selected.get('col', 0), self.controls_pad)
        else: self._default()

    def _validate(self):
        entry = self._current()
        if not entry: return
        if entry['t'] == 'key': self.capture = (entry['act'], self.selected.get('col', 0), self.controls_pad); return          # (the cell's device, keyboard or gamepad)
        if entry['t'] == 'slider' and 'ok' not in entry and not entry.get('notches'): self.entry = [self.selected.get(self.screen_page, 0), '']          # (a line of the "Sound" page has its 'ok': Enter mutes / unmutes the sound; the value is typed by clicking on it; a notched line's value is only its name, never typed)
        elif entry['t'] == 'choice' and entry.get('as_list'): self._open_list()
        elif 'ok' in entry: entry['ok']()

    def _device_row(self, x, y, w, h, k, fs, modal_now=False):
        """"Controls": the row above the column headers, fixed (the lines scroll under it), with two halves "Keyboard" and "Gamepad": the chosen one is lit (gold outline and text), the cells
        below show its keys or its buttons. A click on a half or a camera key (previous / next section) switches. Click zones: `zones_device`."""
        zones = self._tab_buttons(x, y, w, h, k, fs, (N_('controls.keyboard'), N_('controls.gamepad')), int(bool(self.controls_pad)), modal_now)
        self.zones_device += [z + (pad,) for z, pad in zip(zones, (False, True))]

    def _tab_buttons(self, x, y, w, h, k, fs, labels, chosen, modal_now=False):
        """Row of buttons side by side (Keyboard / Gamepad of "Controls"): the chosen one is lit (gold outline and text). Returns their zones (x0, y0, x1, y1)."""
        n = len(labels); bw = (w - CELL_SPACING * k * (n - 1)) / n; zones = []
        for i, label in enumerate(labels):
            hx = x + i * (bw + CELL_SPACING * k); zone = (hx, y, hx + bw, y + h); on = i == chosen; over = not modal_now and self._pointer_in(zone)
            HM.plate(hx, y, bw, h, k, chosen=on or over, outline=GOLD[:3] if on else None)
            lab = self._label(label, fs, GOLD if on else WHITE); lab.x = hx + (bw - lab.content_width) / 2; lab.y = y + h / 2 - self._cap(fs) / 2; lab.draw()
            zones.append(zone)
        return zones

    def _switch_side(self, j):
        """Two windows, a page open on the right: line j of the root (left) is chosen and confirmed: its page replaces the open one (Resume, Return to the title screen: their action; its own page: nothing)."""
        e = self._entries_root()
        if j >= len(e) or self._inactive(e[j]) or e[j].get('page') == self.screen_page: return
        self.entry = None; self.dragging = None; self.open_dropdown = None
        if self.screen_page == 'history': self.hist.leave()                       # (its battle rewind ends, as with Esc)
        self.stack = ['root']; self.selected['root'] = j; e[j]['ok']()

    def _cycle_root(self, d):
        """Q / R (previous / next page): the next line of the root that can be chosen, looping; a line with a page opens it on the right, another one (Resume, Return to the title
        screen, Start the adventure...) is only chosen, in the list."""
        e = self._entries_root(); ok = [i for i, x in enumerate(e) if x['t'] != 'sep' and not self._inactive(x)]
        if not ok: return
        cur = self.selected.get('root', 0); j = next((i for i in (ok if d > 0 else ok[::-1]) if (i > cur if d > 0 else i < cur)), ok[0] if d > 0 else ok[-1])
        if self.screen_page == 'history': self.hist.leave()
        self.entry = None; self.open_dropdown = None; self.stack = ['root']; self.selected['root'] = j
        if e[j].get('page') and e[j].get('sub'): e[j]['ok']()          # ("Quit the game" opens a question, not a page: only chosen)

    def open_history(self):
        """Opens the menu on the history (after a battle replay launched without the menu's state): the root on the left, the history on its right."""
        self.open_menu(); self.selected['root'] = next(i for i, x in enumerate(self._entries_root()) if x.get('page') == 'history'); self.hist.enter(); self.stack.append('history')

    def switch_device(self, pad=None):
        """"Controls": shows the keyboard keys or the gamepad buttons (`pad` None: the other one); a key being captured is cancelled."""
        self.controls_pad = (not self.controls_pad) if pad is None else bool(pad); self.capture = None

    def _family(self):
        """Family of the connected controller ('XB', 'PS', 'NS'): decides the logos and names of the gamepad cells."""
        g = getattr(self.J, 'gamepad', None)
        return g.family() if g is not None else 'XB'

    def _clear_cell(self, action, col, pad=False):
        """Empties a cell of the key lines (0 or 1), of the keyboard or (`pad`) of the gamepad."""
        R = self.J.reg
        if pad: R.unbind_pad(action, col)
        else: R.unbind(action, col)
        R.store()

    def _capture(self, symbol):
        K = pyglet.window.key; R = self.J.reg; action, col, pad = self.capture
        if symbol == K.ESCAPE: self.capture = None; return
        if symbol in (K.DELETE, K.BACKSPACE): self._clear_cell(action, col, pad); self.capture = None; return
        if pad:                                                # gamepad cell: waits for a gamepad input (Start is Esc: it cancels)
            if not PI.is_pad(symbol): return
            previous = R.bind_pad(action, PI.NAME[symbol], col); self.capture = None; R.store()
            if previous and previous != action: self._info(N_('controls.removed_from'), False, PI.text_label(PI.NAME[symbol], self._family()), dict(RG.ACTIONS)[previous].split(' :')[0])
            return
        if PI.is_pad(symbol): return          # the key cells take keyboard keys only
        if RG.name_of(symbol) in RG.RESERVED: self._info(N_('controls.key_reserved'), True, RG.key_name(RG.name_of(symbol))); return
        previous = R.bind(action, col, symbol); self.capture = None; R.store()
        if previous and previous != action: self._info(N_('controls.removed_from'), False, RG.key_name(RG.name_of(symbol)), dict(RG.ACTIONS)[previous].split(' :')[0])

    # ---- mouse
    def _zone(self, x, y):
        for (x0, y0, x1, y1, i) in self.zones:
            if x0 <= x <= x1 and y0 <= y <= y1: return i, (x - x0) / max(1.0, x1 - x0)
        return None, 0.0

    def _guard(self):
        """Keyboard / mouse memory of the window (Game.mouse_guard), or a separate one when the menu is tried without a window."""
        g = getattr(self.J, 'mouse_guard', None)
        if g is None: g = self.__dict__.setdefault('_garde_locale', EN.MouseGuard())
        return g

    def hovered(self, x, y):
        """The pointer moves. With the keyboard, the selection changes only if the pointer has moved more than EN.MOUSE_TOLERANCE pixels from where it was at the last key press (CUMULATIVE deviation: before, the test was on
        the change from one event to the next, and a mouse that sends movements of 1 to 2 pixels never took over again before a click or a very quick gesture); then the selection follows the pointer."""
        if self.screen_page == 'history' and self.popup is None: return self.hist.hovered(x, y)
        if self.screen_page == 'name' and self.popup is None: self.mouse_pos = (x, y); self.mouse_mode = True; return self.J.name_entry.hovered(x, y)
        if self.screen_page == 'gender' and self.popup is None: self.mouse_pos = (x, y); self.mouse_mode = True; return
        self.mouse_pos = (x, y)
        if self.pan_fold_at is not None and self.pan_pressed is None and not self._double_possible(x, y, time.time()): self._fold_pending()          # the pointer left the double-click rectangle: the single click is confirmed, the panel collapses / expands without waiting for the end of the delay
        if not self.mouse_mode and not self._guard().has_moved((x, y)): return          # the pointer has not really moved: the keyboard selection stays
        self.mouse_mode = True
        if self.popup is not None:
            for (x0, y0, x1, y1, i) in self.zones_popup:
                if x0 <= x <= x1 and y0 <= y <= y1: self.popup['choice'] = i
            return
        if self.capture is not None: return
        if self.open_dropdown is not None:
            j = self._list_zone(x, y)
            if j is not None: self.open_dropdown[1] = j
            return
        self.on_back = bool(self.zone_ret and self._inside(self.zone_ret, x, y))
        if self.on_back: return
        i, _ = self._zone(x, y)
        if i is not None: self.selected[self.screen_page] = i

    def output(self):
        """The pointer has left the window: nothing is hovered anymore."""
        self.mouse_pos = None; self.on_back = False; self.tt = None

    @staticmethod
    def _inside(z, x, y):
        return z[0] <= x <= z[2] and z[1] <= y <= z[3]

    def _set_view(self, start_idx):
        """First visible line of the current screen (the selection does not change: the view does not return to it as long as it does not move)."""
        b = self.has_bar
        if b: self.begin[self.screen_page] = max(b['base'], min(int(start_idx), b['base'] + b['n'] - b['visible']))

    def _click_bar(self, x, y):
        """Click on the scrollbar: arrows (one line), thumb (grabbed for dragging), bar track (one page)."""
        b = self.has_bar; start_idx = self.begin.get(self.screen_page, 0)
        if y > b['ptop']: self._set_view(start_idx - 1)
        elif y < b['pbot']: self._set_view(start_idx + 1)
        elif b['thumb'][0] <= y <= b['thumb'][1]: self.dragging_bar = b['thumb'][1] - y
        elif y > b['thumb'][1]: self._set_view(start_idx - (b['visible'] - 1))
        else: self._set_view(start_idx + (b['visible'] - 1))

    def _drag_bar(self, y):
        b = self.has_bar
        if not b: self.dragging_bar = None; return
        free = b['ptop'] - b['pbot'] - b['th']
        if free > 0: self._set_view(b['base'] + round(max(0.0, min(1.0, (b['ptop'] - (y + self.dragging_bar)) / free)) * (b['n'] - b['visible'])))

    def click(self, x, y, button):
        M = pyglet.window.mouse
        if self.screen_page in ('history', 'name', 'gender') and self.popup is None:
            j = next((z[4] for z in self.left_zones if self._inside(z[:4], x, y)), None) if button != M.RIGHT else None
            if j is not None: self.mouse_mode = True; self.mouse_pos = (x, y); self._switch_side(j); return          # (two windows: a line of the root, on the left of the history, of the name or gender page)
            if self.screen_page == 'gender':
                self.mouse_mode = True; self.mouse_pos = (x, y)
                if button == M.RIGHT: self.back()
                elif self.zone_ret and self._inside(self.zone_ret, x, y): self._cancel_new_game()
                else: self.hero_gender = next((g for g, z in self.gender_zones if self._inside(z, x, y)), self.hero_gender)
                return
            if self.screen_page == 'name':
                if self.zone_ret and self._inside(self.zone_ret, x, y) and button != M.RIGHT: self._cancel_new_game(); return
                return self.J.name_entry.click(x, y, button)
            return self.hist.click(x, y, button)
        self.mouse_mode = True; self.mouse_pos = (x, y)
        if self.pan_fold_at is not None and not self._double_possible(x, y, time.time()): self._fold_pending()          # any other press (elsewhere, too late): the pending single click collapses / expands immediately, it can no longer become a double click
        if self.capture is not None: self.capture = None; return
        if self.popup is None and self.open_dropdown is None and button != M.RIGHT:
            for (x0, y0, x1, y1, pad) in self.zones_device:
                if x0 <= x <= x1 and y0 <= y <= y1: self.switch_device(pad); return          # "Controls": Clavier / Manette row
        if self.popup is not None:                                    # confirmation window: a button confirms it, a right click or a click elsewhere closes it
            if button != M.RIGHT:
                for (x0, y0, x1, y1, i) in self.zones_popup:
                    if x0 <= x <= x1 and y0 <= y <= y1: self._choose_popup(i); return
            else: self.popup = None
            return
        if self.screen_page == 'interface' and self.fold_zone and self._inside(self.fold_zone, x, y) and button != M.RIGHT: self._press_bar(x, y); return          # panel title bar: short press = collapse / expand, long press = move, double click = original position
        if self.open_dropdown is not None:                                  # open drop-down list: a click on a value chooses it, a click elsewhere (or a right click) closes it
            b = self.list_bar
            if button != M.RIGHT and b and b['x0'] <= x <= b['x1'] and b['y0'] <= y <= b['y1']: self._click_entries_bar(x, y); return          # list scrollbar
            j = self._list_zone(x, y) if button != M.RIGHT else None
            c = self.list_border
            if j is not None: self.open_dropdown[1] = j; self._entries_end(True)
            elif button != M.RIGHT and c and c[0] <= x <= c[2] and c[1] <= y <= c[3]: pass          # (click on a subheading or on the list margin: it stays open)
            else: self.open_dropdown = None
            return
        if button == M.RIGHT:
            if self.entry is not None: self.entry = None
            else: self.back()
            return
        if self.zone_ret and self._inside(self.zone_ret, x, y):                    # back button (at the bottom right of the window; a new game: the panel's, back to the start menu)
            self.entry = None
            if self.new_game: self._cancel_new_game()
            else: self.back()
            return
        j = next((z[4] for z in self.left_zones if self._inside(z[:4], x, y)), None)
        if j is not None: self._switch_side(j); return                            # two windows, a page open: a click on a line of the root (left)
        i, f = self._zone(x, y)
        if self.screen_page == 'interface' and i is None and self.entry is None:       # editor: outside the panel, a click grabs the chosen element (a screen button, or the window shown in preview)
            c = self.panel_border
            if not (c and c[0] <= x <= c[2] and c[1] <= y <= c[3]):
                if self.target in HUD_TARGETS: self.J.hud.take(x, y, HM.editor_names(self.target))
                else: self.drag = (x, y, list(self._ov()), self.rect_preview)
            return
        if self.entry is not None:                                   # a click anywhere other than on the value being typed confirms it
            line = self.entry[0]; zv = self.zones_val.get(line)
            if i == line and zv and zv[0] <= x <= zv[1]: return
            self._end_entry(True)
        b = self.has_bar
        if b and b['x0'] <= x <= b['x1'] and b['y0'] <= y <= b['y1']: self._click_bar(x, y); return
        if i is None: return
        es = self._entries()
        if i >= len(es) or self._inactive(es[i]): return                                              # (line that became inactive since the last frame: the click does not reach it)
        self.selected[self.screen_page] = i; entry = es[i]
        bar = self.bars.get(i)
        zv = self.zones_val.get(i); zd = self.default_zones.get(i); zm = self.zones_mute.get(i)
        if entry['t'] == 'slider' and zm and self._inside(zm, x, y): entry['ok']()                           # mute button of the "Sound" page: mutes or restores the sound
        elif entry['t'] in ('slider', 'key', 'choice', 'act') and zd and zd[0] <= x <= zd[2] and zd[1] <= y <= zd[3]:       # round "default value" button (sliders, choices, original keys; the seed's: a new seed)
            if 'default' in entry: entry['default']()
        elif entry['t'] == 'slider' and bar and bar[0] - 6 <= x <= bar[1] + 6:       # slider: the held click drags it (drag)
            self.dragging = i; entry['set_fraction'](min(1.0, max(0.0, (x - bar[0]) / (bar[1] - bar[0]))))
        elif entry['t'] == 'slider' and zv and zv[0] - 8 <= x <= zv[1] + 8:     # click on the value: keyboard entry (not on a notched line: its value is only the notch's name)
            if not entry.get('notches'): self.entry = [i, '']
        elif entry['t'] == 'key':
            for c in range(2):
                ze = self.zones_eff.get((i, c))
                if ze and self._inside(ze, x, y): self.selected['col'] = c; self._clear_cell(entry['act'], c, self.controls_pad); return          # cross: clears the key of the cell
            col = 0 if x < self.zones_col[0] else 1; self.selected['col'] = col; self._validate()
        elif entry['t'] == 'slider' and 'ok' in entry: pass                                                  # line of the "Sound" page: a click next to the buttons does not mute the sound
        else: self._validate()

    @staticmethod
    def _snap(r, dx, dy, W, H):
        """Movement (dx, dy) of the window with frame r = (x0, y0, x1, y1), corrected so that one of its edges (or its middle) falls on a grid line (32 x 18 cells): the nearest one."""
        def step(a, b, g, d):
            best = None
            for p in (a, (a + b) / 2.0, b):
                c = round((p + d) / g) * g - (p + d)
                if best is None or abs(c) < abs(best): best = c
            return d + best
        return step(r[0], r[2], W / float(HM.COLS), dx), step(r[1], r[3], H / float(HM.LINES), dy)

    def _press_bar(self, x, y):
        """Press on the title bar of the editor panel (the gesture plays out in drag_to, do_update and release): the panel follows the pointer as soon as it leaves Windows' drag rectangle around the press point (inputs.is_drag) (drag
        right away, without waiting) or after a held press of LONG_PRESS_DELAY (it lifts); short press without moving = collapse / expand, once the double-click delay has elapsed without a second press; second short press
        within DOUBLE_CLICK_DELAY = return to the original position, with no folding at all."""
        t = time.time(); c = self.panel_border
        if not c: return
        if self.open_dropdown is not None: self.open_dropdown = None
        if self.entry is not None: self._end_entry(True)
        self.pan_pressed = dict(t0=t, x=x, y=y, dx=x - c[2], dy=y - c[3], long=False, double=self._double_possible(x, y, t))         # (dx, dy: offset of the pointer relative to the top right corner of the panel)

    def _double_possible(self, x, y, t):
        """Would a press at (x, y) at time t be the second of a double click, as Windows judges it: the first short press is less than GetDoubleClickTime old (since ITS START, not since its release) and the second
        falls in the SM_CXDOUBLECLK x SM_CYDOUBLECLK pixel rectangle centered on the first."""
        if self.pan_click_pos is None: return False
        delay, w, h = system_double_click()
        return 0.0 <= t - self.pan_click_t <= delay and abs(x - self.pan_click_pos[0]) <= w / 2.0 and abs(y - self.pan_click_pos[1]) <= h / 2.0

    def _fold_pending(self):
        """The folding of a single click on the title bar (interface editor) happens only once the double-click delay has elapsed: collapses / expands the panel and waits for nothing more (no effect if no click is pending)."""
        if self.pan_fold_at is None: return
        self.pan_fold_at = None; self.pan_click_pos = None; self.folded = not self.folded          # (the single click is confirmed: no more double click possible on it)

    def release(self, x, y, button):
        if self.screen_page == 'history': return self.hist.release(x, y, button)
        self.dragging = None; self.dragging_bar = None; self.dragging_entries = None
        a, self.pan_pressed = self.pan_pressed, None
        if a is not None and not a['long']:                                       # short press (no movement): a single click collapses / expands AFTER the double-click delay (see do_update); second press of a double click: original position, without collapsing or expanding
            if a['double']: self.pan_pos = None; self.pan_fold_at = None; self.pan_click_pos = None; self.pan_click_t = 0.0
            else:                                                                                  # single click: the double-click delay runs from the START of the press (like Windows); already elapsed at release (long press longer than this delay): collapses / expands right away
                self.pan_click_t = a['t0']; self.pan_click_pos = (a['x'], a['y']); self.pan_fold_at = a['t0'] + system_double_click()[0]
                if time.time() >= self.pan_fold_at: self._fold_pending()
        if self.screen_page == 'interface' and self.J.hud.taken is not None: self.J.hud.place(); self.J.reg.store()
        if self.drag is not None: self.drag = None; self.J.reg.store()

    def drag_to(self, x, y):
        """Mouse moved with the button held down: the held slider (or the scrollbar thumb) follows."""
        if self.screen_page == 'history': return self.hist.drag_to(x, y)
        a = self.pan_pressed
        if a is not None:                                                                    # editor panel: it follows the pointer as soon as the pointer has left the press point (the panel lifts, no collapse or double click), or after a held press
            if not a['long'] and EN.is_drag(x - a['x'], y - a['y']): a['long'] = True; a['double'] = False; self._fold_pending()          # a click immediately followed by a drag: the click collapses first, then the panel follows the pointer
            if a['long']: self.pan_pos = (x - a['dx'], y - a['dy'])
            return
        if self.dragging_entries is not None: self._drag_entries_bar(y); return
        if self.dragging_bar is not None: self._drag_bar(y); return
        if self.dragging is None:
            if self.screen_page == 'interface':
                if self.drag is not None:                              # game window: it follows the pointer (offset as a fraction of the screen), snapped to the grid if the setting is active
                    x0, y0, o, r0 = self.drag; W, H = self.J.width, self.J.height; dx, dy = x - x0, y - y0
                    if self.J.reg['buttons_snap'] and r0: dx, dy = self._snap(r0, dx, dy, W, H)
                    self._set_ov(1, max(-0.5, min(0.5, o[1] + dx / W))); self._set_ov(2, max(-0.5, min(0.5, o[2] + dy / H)))
                else: self.J.hud.move_to(x, y)
            return
        bar = self.bars.get(self.dragging); e = self._entries()
        if bar is None or self.dragging >= len(e) or e[self.dragging]['t'] != 'slider' or self._inactive(e[self.dragging]): self.dragging = None; return
        e[self.dragging]['set_fraction'](min(1.0, max(0.0, (x - bar[0]) / (bar[1] - bar[0]))))

    def _text_entry(self):
        """The `text_entry` of the line being typed (seed code), or None (a number)."""
        e = self._entries(); line = self.entry[0] if self.entry is not None else -1
        return e[line].get('text_entry') if 0 <= line < len(e) else None

    def text(self, t):
        """Characters typed while entering a value."""
        if self.entry is None: return
        spec = self._text_entry()
        if spec is not None:
            for c in t.upper():
                if c in spec['chars'] and len(self.entry[1]) < spec['max']: self.entry[1] += c
            return
        for c in t.replace(',', '.'):
            if (c.isdigit() or (c in '.-' and c not in self.entry[1])) and len(self.entry[1]) < 7: self.entry[1] += c

    def _entry_key(self, symbol, modifiers=0):
        K = pyglet.window.key
        if symbol == K.V and modifiers & (K.MOD_CTRL | K.MOD_COMMAND) and self._text_entry() is not None:          # Ctrl + V: paste (a seed code)
            f = getattr(self.J, 'get_clipboard_text', None)
            try: self.text((f() if f else '') or '')
            except Exception: pass
        elif symbol in (K.RETURN, K.ENTER): self._end_entry(True)
        elif symbol == K.ESCAPE: self._end_entry(False)
        elif symbol == K.BACKSPACE:
            if self.entry[1]: self.entry[1] = self.entry[1][:-1]
            else: self._end_entry(False)

    def _end_entry(self, valid):
        spec = self._text_entry(); line, txt = self.entry; self.entry = None
        if spec is not None:
            if valid and txt: spec['set'](txt)
            return
        if not valid or txt in ('', '-', '.'): return
        e = self._entries()
        if line < len(e) and e[line]['t'] == 'slider' and 'set_value' in e[line] and not self._inactive(e[line]):
            try: e[line]['set_value'](float(txt))
            except ValueError: pass

    def wheel(self, sy):
        if self.screen_page == 'history': return self.hist.wheel(sy)
        if self.popup is not None or (self.screen_page == 'interface' and self.folded): return
        b = self.has_bar
        if b and self.open_dropdown is None and b['n'] > b['visible']: self._set_view(self.begin.get(self.screen_page, 0) - 2 * (1 if sy > 0 else -1)); return      # scrolling list: the wheel scrolls the view (like the scrollbar)
        self._move(1 if sy > 0 else -1)                                    # (otherwise, reverse direction: wheel up = next line)

    # ---- drawing
    @staticmethod
    def _border(x, y, w, h, k):
        """Window in the style of the mobile game's menus: black background with the same opacity as the other menus, white frame drawn with five strokes, rounded transparent corners (hud_mobile.border)."""
        HM.border(x, y, w, h, k, background=BLACK, opacity=HM.GAME_OPACITY)

    def _plate(self, x, y, w, h, k, chosen=False, outline=None, grayed=False):
        """Background of a button: the game windows' plate (Button sheet, like "Heal all"), pressed (darkened) when it is selected or hovered. `outline` (colored outline): no longer used by the Pause page,
        kept for the pre-game screens (saves, name, license). `grayed`: inactive line, colorless and darkened plate (the game's gray shader). Without the original menus: drawn plate (hud_mobile), veiled if grayed."""
        r = getattr(self.J, 'ui_render', None); vp = (self.J.width, self.J.height)
        if r is not None and (r.plate(x, y, w, h, vp, chosen, grayed=True) if grayed else r.plate(x, y, w, h, vp, chosen)):
            if outline is not None: HM.outline(x, y, w, h, k, outline)
        else:
            HM.plate(x, y, w, h, k, chosen, outline)
            if grayed: v = pyglet.shapes.Rectangle(x + 2 * k, y + 2 * k, w - 4 * k, h - 4 * k, color=(24, 24, 24)); v.opacity = 140; v.draw()

    def _shapes(self, key, build):
        """Draws shapes built once for `key` (build(batch) -> the shapes, added to that batch): a menu that does not move draws the same ones every frame, and building them
        (sixteen shapes for a "default value" button, each one a buffer to fill) cost about 2 ms a button."""
        cache = self.__dict__.setdefault('_shape_cache', {})
        b = cache.get(key)
        if b is None:
            if len(cache) > 300: cache.clear()
            batch = pyglet.graphics.Batch(); b = cache[key] = (batch, build(batch))
        b[0].draw()

    def _sprite(self, key, make):
        """Draws a sprite made once for `key` (make() -> the sprite), like _shapes."""
        cache = self.__dict__.setdefault('_sprite_cache', {})
        spr = cache.get(key)
        if spr is None:
            if len(cache) > 300:
                for old in cache.values(): old.delete()
                cache.clear()
            spr = cache[key] = make()
        spr.draw()

    def _default_button(self, idx, x, y, c, is_default, selected, k, grayed=False):
        """Square "default value" button (arrow in a circle): bright when the value differs from the original, dull otherwise; darkens (75%, like a pressed game icon button) under the pointer.
        `grayed` (inactive line): dull, no click area or darkening."""
        z = (x - 3 * k, y - 3 * k, x + c + 3 * k, y + c + 3 * k)
        if not grayed: self.default_zones[idx] = z
        f = 0.75 if not grayed and self._hovered(z) else 1.0
        if grayed: is_default = True
        clr = tuple(int(a * f) for a in ((90, 90, 90) if is_default else LIGHT))
        def build(batch):
            back, front = pyglet.graphics.Group(order=0), pyglet.graphics.Group(order=1)          # (the translucent square under the arrow, as when they were drawn one after the other)
            r = pyglet.shapes.BorderedRectangle(x, y, c, c, border=max(1, int(2 * k)), color=(255, 255, 255), border_color=clr[:3], batch=batch, group=back); r.opacity = int((30 if is_default else 70) * f)
            cx, cy, ra = x + c / 2, y + c / 2, c * 0.28; t0, t1 = math.radians(55), math.radians(55 + 270)
            pts = [(cx + ra * math.cos(t0 + (t1 - t0) * i / 14), cy + ra * math.sin(t0 + (t1 - t0) * i / 14)) for i in range(15)]
            out = [r] + [pyglet.shapes.Line(a[0], a[1], b[0], b[1], thickness=max(1.5, 2 * k), color=clr[:3], batch=batch, group=front) for a, b in zip(pts, pts[1:])]
            ex, ey = pts[0]; tg = t0 - math.pi / 2                                       # arrowhead at the start of the arc
            h = c * 0.2
            out.append(pyglet.shapes.Triangle(ex + h * math.cos(tg), ey + h * math.sin(tg), ex + h * math.cos(tg + 2.4), ey + h * math.sin(tg + 2.4), ex + h * math.cos(tg - 2.4), ey + h * math.sin(tg - 2.4), color=clr[:3], batch=batch, group=front))
            return out
        self._shapes(('default', round(x, 2), round(y, 2), round(c, 2), clr, is_default, f, round(k, 4)), build)

    def _mute_button(self, idx, x, y, c, cut, k, grayed=False):
        """Square "mute" button of the "Sound" page: speaker and waves when the sound plays, grayed speaker crossed out with a red cross when it is muted; darkens (75%) under the pointer.
        `grayed` (inactive line): dull, no click area or darkening."""
        z = (x - 3 * k, y - 3 * k, x + c + 3 * k, y + c + 3 * k)
        if not grayed: self.zones_mute[idx] = z
        f = 0.75 if not grayed and self._hovered(z) else 1.0
        clr = tuple(int(a * f) for a in (GRAY[:3] if cut or grayed else LIGHT))
        r = pyglet.shapes.BorderedRectangle(x, y, c, c, border=max(1, int(2 * k)), color=(255, 255, 255), border_color=(90, 90, 90) if grayed else tuple(int(a * f) for a in LIGHT)); r.opacity = int((30 if grayed else 70) * f); r.draw()
        cy = y + c / 2; ep = max(1.5, 2 * k)
        x0 = x + c * 0.14; x1 = x + c * 0.32; x2 = x + c * 0.54                    # speaker box (x0 to x1), then the flaring cone (x1 to x2)
        pyglet.shapes.Rectangle(x0, cy - c * 0.13, x1 - x0, c * 0.26, color=clr).draw()
        pyglet.shapes.Triangle(x1, cy + c * 0.13, x1, cy - c * 0.13, x2, cy - c * 0.32, color=clr).draw(); pyglet.shapes.Triangle(x1, cy + c * 0.13, x2, cy + c * 0.32, x2, cy - c * 0.32, color=clr).draw()
        if cut:                                                                    # red cross in place of the waves
            rc = tuple(int(a * f) for a in RED[:3]); xc = x + c * 0.76; d = c * 0.14
            pyglet.shapes.Line(xc - d, cy - d, xc + d, cy + d, thickness=ep * 1.3, color=rc).draw(); pyglet.shapes.Line(xc - d, cy + d, xc + d, cy - d, thickness=ep * 1.3, color=rc).draw()
        else:
            for ra in (c * 0.17, c * 0.31):                                          # two waves (circle arcs) to the right of the cone
                pts = [(x2 - c * 0.04 + ra * math.cos(math.radians(a)), cy + ra * math.sin(math.radians(a))) for a in range(-50, 51, 10)]
                for p0, p1 in zip(pts, pts[1:]): pyglet.shapes.Line(p0[0], p0[1], p1[0], p1[1], thickness=ep, color=clr).draw()

    @staticmethod
    def _pill(x, yc, w, h, color):
        """Rectangle with rounded ends, vertically centered at yc."""
        r = h / 2
        for sh in (pyglet.shapes.Rectangle(x + r, yc - r, w - 2 * r, h, color=color), pyglet.shapes.Circle(x + r, yc, r, segments=24, color=color), pyglet.shapes.Circle(x + w - r, yc, r, segments=24, color=color)): sh.draw()

    def _switch(self, lookup_key, x, yc, active, selected, grayed, k):
        """Sliding switch (rounded track, round knob): gold when on, gray otherwise; the knob slides from one position to the other (short animation); gold outline if selected."""
        target = 1.0 if active else 0.0; p = self.pos_sw.get(lookup_key, target)                   # first appearance: no animation
        p = target if abs(target - p) < 0.02 else p + (target - p) * min(1.0, self.dt_sw * 16.0); self.pos_sw[lookup_key] = p
        w, h = WIDTH_SW * k, HEIGHT_SW * k; r = h / 2
        track = (30, 32, 36) if grayed else tuple(int(a + (b - a) * p) for a, b in zip((20, 22, 26), (225, 207, 3)))
        if selected and not grayed: e = max(1.5, 2 * k); self._pill(x - e, yc, w + 2 * e, h + 2 * e, LIGHT)
        self._pill(x, yc, w, h, track)
        pyglet.shapes.Circle(x + r + (w - 2 * r) * p, yc, r - 3 * k, segments=24, color=(128, 128, 128) if grayed else (255, 255, 255)).draw()

    def _thumbnail(self, n):
        """Texture of a savestate's thumbnail (None if there is none)."""
        if n in self.minis: return self.minis[n]
        t = None; inf = self.J.state_info(n)
        if inf and inf[1]:
            try:
                import io
                from PIL import Image
                import numpy as np
                im = Image.open(io.BytesIO(inf[1])).convert('RGBA'); a = np.asarray(im)
                t = pyglet.image.ImageData(im.width, im.height, 'RGBA', np.ascontiguousarray(a[::-1]).tobytes(), pitch=im.width * 4).get_texture()
            except Exception: t = None
        self.minis[n] = t
        return t

    def _scroll_bar(self, x1, ptop, pbot, n, vis, start_idx, k, active, base=0):
        """Scrollbar to the right of the list: up arrow, track, thumb, down arrow (top of the list at ptop, bottom at pbot). Returns the bar's geometry (for clicks)."""
        w = BAR_WIDTH * k; x0 = x1 - w; fl = 14 * k; th0, th1 = ptop - fl - 2 * k, pbot + fl + 2 * k          # track between the two arrows
        track = pyglet.shapes.Rectangle(x0, th1, w, th0 - th1, color=(34, 36, 42)); track.draw()
        th = max(26 * k, (th0 - th1) * vis / float(n)); f = start_idx / float(max(1, n - vis)); hau = th0 - f * (th0 - th1 - th)
        self._plate(x0, hau - th, w, th, k * 0.8, active or self._hovered((x0, hau - th, x1, hau)))                       # scrollbar thumb: darkened when held or hovered
        clr = LIGHT if n > vis else GRAY[:3]
        for yb, yt, tri_indices in ((ptop - fl, ptop, (x0 + 1.5 * k, ptop - fl + 3 * k, x1 - 1.5 * k, ptop - fl + 3 * k, (x0 + x1) / 2, ptop - 2 * k)), (pbot, pbot + fl, (x0 + 1.5 * k, pbot + fl - 3 * k, x1 - 1.5 * k, pbot + fl - 3 * k, (x0 + x1) / 2, pbot + 2 * k))):
            pyglet.shapes.Triangle(*tri_indices, color=tuple(int(a * 0.75) for a in clr) if n > vis and self._hovered((x0, yb, x1, yt)) else clr).draw()             # arrows: 75% under the pointer
        return dict(x0=x0 - 3 * k, x1=x1 + 3 * k, y0=pbot, y1=ptop, ptop=th0, pbot=th1, th=th, thumb=(hau - th, hau), n=n, visible=vis, base=base)

    def _dpad(self, x, y, c, dark=False, grayed=False):
        """The game's red cross (erase a key), of c pixels, bottom-left corner at (x, y); dark: at 75% (under the pointer, like a pressed game icon button); grayed: inactive line, dull cross."""
        t = self._sliced_tex('dpad', 'ui_MenuTexture.png', DPAD)
        if t is None: return
        self._restore_blend()
        if grayed: dark = True
        def make():
            spr = pyglet.sprite.Sprite(t, x=x, y=y); spr.scale_x = c / t.width; spr.scale_y = c * (DPAD[3] - DPAD[1]) / float(DPAD[2] - DPAD[0]) / t.height
            if dark: spr.color = (110, 110, 110) if grayed else (191, 191, 191); spr.opacity = 110 if grayed else 191
            return spr
        self._sprite(('cross', round(x, 2), round(y, 2), round(c, 2), dark, grayed), make)          # (a blit made and freed its own vertices every time: one cross per key cell, every frame)

    def _chevron(self, x, yc, k, grayed=False):
        """Chevron ">": the line opens another menu (gray when the line is inactive)."""
        for a, b in (((x - 4 * k, yc + 8 * k), (x + 4 * k, yc)), ((x + 4 * k, yc), (x - 4 * k, yc - 8 * k))):
            pyglet.shapes.Line(a[0], a[1], b[0], b[1], thickness=max(2.0, 2.6 * k), color=GRAY[:3] if grayed else (255, 255, 255)).draw()

    def _cap(self, fz):
        """Cap height (pixels) of a text of size `fz` (points, 96 dpi) in the game font: used to center a text vertically in its cell, whatever the font."""
        px = max(6, int(round(fz * 96.0 / 72.0))); c = self._caps.get(px)
        if c is None:
            c = 0.72 * px
            try:
                from PIL import ImageFont
                f = os.path.join(self.J.args.cache, 'ui_font.otf')
                c = float(-ImageFont.truetype(f if self._pol and os.path.exists(f) else 'DejaVuSans.ttf', px).getbbox('H', anchor='ls')[1])
            except Exception: pass
            self._caps[px] = c
        return c

    def _adjust(self, text, size_value, color, maxw):
        """Label for `text` that fits within `maxw` pixels (the size shrinks if needed)."""
        label = self._label(text, size_value, color)
        if label.content_width > maxw > 0: label = self._label(text, size_value * maxw / label.content_width, color)
        return label

    def _preview_elements(self):
        """Elements shown on screen for the chosen interface (on-screen buttons and D-pad, or the game window as a preview): [(x0, y0, x1, y1, mask, masculine)].
        `mask`: the element is not drawn in game: the whole interface hidden ("Show this interface on screen" = Non: buttons, D-pad, window) or, for the D-pad alone, "Show the D-pad" = Non.
        `masculine`: agreement of the "Hidden" label (buttons: "Hidden")."""
        R = self.J.reg
        if self.target in HUD_TARGETS:
            everything = not self._visible(self.target); out = []
            for n in HM.editor_names(self.target):
                x, y, w, h = self.J.hud.rect(n); out.append((x, y, x + w, y + h, everything or (n == HM.DPAD and not R['dpad']) or (n == HM.BAR and not R['rotation_bar']), n not in (HM.DPAD, HM.BAR)))
            return out
        return [tuple(self.rect_preview) + (not self._visible(self.target), False)] if self.rect_preview else []

    def _shown_rects(self):
        """Rectangles (x0, y0, x1, y1) shown on screen for the chosen interface (see _preview_elements)."""
        return [e[:4] for e in self._preview_elements()]

    def _origin_corner(self, pw, h, W, H, m):
        """Original position of the editor panel (top right corner): at the top right (the buttons are on the left, the D-pad at the bottom right); if that hides the chosen interface, the first of the other screen corners
        (top left, bottom right, bottom left) that does not hide it, otherwise the one that hides the least. Computed from the expanded panel's size (the collapsed panel does not change corner)."""
        pw, h = self.pan_dim or (pw, h); targets = self._shown_rects(); best = None
        for x1, y1 in ((W - m, H - m), (pw + m, H - m), (W - m, h + m), (pw + m, h + m)):
            r = (x1 - pw, y1 - h, x1, y1)
            sc = sum(max(0.0, min(r[2], q[2]) - max(r[0], q[0])) * max(0.0, min(r[3], q[3]) - max(r[1], q[1])) for q in targets)
            if sc <= 0: return x1, y1
            if best is None or sc < best[0]: best = (sc, x1, y1)
        return best[1], best[2]

    def _panel_pos(self, pw, h, W, H, k):
        """Top-left corner (x0, y1) of the interface editor panel: the player's position (after a long press and a drag, kept for the session) or the original position (_origin_corner),
        always brought back inside the screen."""
        x1, y1 = self.pan_pos if self.pan_pos is not None else self._origin_corner(pw, h, W, H, 22 * k)
        x1 = min(max(x1, pw + 4 * k), W - 4 * k); y1 = min(max(y1, h + 4 * k), H - 4 * k)
        return x1 - pw, y1

    def _preview(self):
        """Interface editor: the game stays visible; the chosen element is shown (on-screen buttons with their grid, or the game window as a preview, at its size and place); the other buttons stay on screen."""
        J = self.J; self.rect_preview = None
        if self.target in HUD_TARGETS: J.hud.draw_all(HM.editor_names(self.target), True, J.reg['editor_grid'])              # only the screen buttons (the game windows are not drawn during editing)
        else:
            veil = pyglet.shapes.Rectangle(0, 0, J.width, J.height, color=(0, 0, 0)); veil.opacity = 90; veil.draw()
            if J.reg['editor_grid']: HM.draw_grid(J.width, J.height)
            self.rect_preview = J.preview_interface(self.target)                                                    # only the chosen window (neither the other windows, nor the buttons)
        k = max(0.75, J.height / 900.0)
        for x0, y0, x1, y1, mask, masculine in self._preview_elements():                                           # element not displayed in game (the whole interface, or the D-pad alone): the preview stays visible so that it can be placed, but darkened and marked
            if not mask: continue
            v = pyglet.shapes.Rectangle(x0, y0, x1 - x0, y1 - y0, color=(0, 0, 0)); v.opacity = 150; v.draw()
            label = self._adjust(HIDDEN_WORDS[masculine], 20 * k, RED, max(x1 - x0 - 18 * k, 36 * k)); label.x = (x0 + x1) / 2 - label.content_width / 2; label.y = (y0 + y1) / 2 - label.content_height / 2
            dot = pyglet.shapes.Rectangle(label.x - 8 * k, label.y - 4 * k, label.content_width + 16 * k, label.content_height + 8 * k, color=(0, 0, 0)); dot.opacity = 200; dot.draw(); label.draw()          # (on a dark background: the text of the test message goes underneath)
            pyglet.shapes.Box(x0, y0, x1 - x0, y1 - y0, thickness=2, color=SELECTION_BORDER).draw()                  # the yellow selection frame stays as sharp as on a displayed element (the veil covered it)

    def draw_all(self):
        J = self.J; W, H = J.width, J.height; k = max(0.75, H / 900.0)
        editor = self.screen_page == 'interface'; hist = self.screen_page == 'history'
        two = None if editor or (hist and self.hist.rewind is not None) else self._two_panels(W, H, k)          # (the interface editor and a battle's rewind take the whole screen)
        if hist and two is None:
            self.left_zones = []; self.page_rect = None; self.hist.draw_all()
            if self.popup is not None: self._draw_popup(k, 18 * k, 13 * k, W, H)          # ("Clear all" asks first; the sizes of draw_all)
            return
        gl.glDisable(gl.GL_DEPTH_TEST); gl.glEnable(gl.GL_BLEND); gl.glBlendFunc(gl.GL_SRC_ALPHA, gl.GL_ONE_MINUS_SRC_ALPHA)
        if editor: self._preview()
        else:
            veil = pyglet.shapes.Rectangle(0, 0, W, H, color=(0, 0, 0)); veil.opacity = 90; veil.draw()
        t = time.time(); self.dt_sw = min(0.1, t - self.t_sw); self.t_sw = t               # (toggle animation)
        self.left_zones = []; self.page_rect = None
        if two is None: self._draw_page(self.screen_page); return
        xl, xr, top, wl, wr, kk, hb = two
        if self.screen_page == 'root':
            self._draw_page('root', 'left', (xl, top, wl), kk); self._border(xr, top - hb, wr, hb, kk)
            self._help_zone(xr, top - hb, wr, kk, self._described(self._entries_root(), self.selected.get('root', 0)))          # (the help of the root's line, in the empty frame)          # the root is chosen: its window alone, on the left (a page shows on its right only once opened: click, Enter, right)
        else:                                                                      # a page is open on the right: the root stays on the left, its line lit (a click on another line opens its page instead)
            self._draw_page('root', 'side', (xl, top, wl), kk); self.left_zones = list(self.zones)
            if hist:                                                               # (the history draws itself, in the right window's place and width)
                self.page_rect = self.hist.draw_all((xr, top, wr, kk, hb))
                if self.popup is not None: self._draw_popup(kk, 18 * kk, 13 * kk, W, H)
            elif self.screen_page == 'name':                                       # (the name entry of a new game, in the whole right frame: no help on that page)
                self._border(xr, top - hb, wr, hb, kk); self.page_rect = (xr, top - hb, xr + wr, top)
                self.J.name_entry.draw_all(0, 0, 1.0, place=(xr, top, wr, kk, hb))
            elif self.screen_page == 'gender': self._draw_gender(xr, top, wr, hb, kk)
            else: self.page_rect = self._draw_page(self.screen_page, 'right', (xr, top, wr, hb), kk)
        if self.new_game:                                                          # the panel's back button, under its right frame: back to the start menu, from any page
            kb = 1.1 * kk; bw, bh = 64 * kb, 55.5 * kb; bx = xr + wr - bw - 8 * kk; by = top - hb - 8 * kk - bh
            self.zone_ret = (bx, by, bx + bw, by + bh); self._back_button(bx, by, bw, bh, self._hovered(self.zone_ret))

    gender_zones = ()                                                         # gender page: [(gender, (x0, y0, x1, y1))], its two columns (label and character)

    def _hero_frame(self, gender, col, gray):
        """Texture of the hero facing the camera (row 4 of his sheet: HERO_SHEETS), column `col`; `gray`: colorless and darkened. None without the sheet (window without its data: tests)."""
        lookup_key = ('hero', gender, col, gray)
        if lookup_key not in self._img:
            sheet = getattr(self.J, '_original_sheet', lambda i: None)(HERO_SHEETS[gender]); t = None
            if sheet:
                w, h = sheet['geo']['width'], sheet['geo']['height']; a = sheet['arr'][FRONT_ROW * h:(FRONT_ROW + 1) * h, col * w:(col + 1) * w].copy()
                if gray: a[..., :3] = (a[..., :3].astype(np.float32) @ np.array([0.30, 0.59, 0.11], np.float32) * 0.55).astype(np.uint8)[..., None]
                t = pyglet.image.ImageData(w, h, 'RGBA', np.ascontiguousarray(a[::-1]).tobytes()).get_texture()
                gl.glBindTexture(t.target, t.id); gl.glTexParameteri(t.target, gl.GL_TEXTURE_MIN_FILTER, gl.GL_NEAREST); gl.glTexParameteri(t.target, gl.GL_TEXTURE_MAG_FILTER, gl.GL_NEAREST)
            self._img[lookup_key] = t
        return self._img[lookup_key]

    def _draw_gender(self, xr, top, wr, hb, kk):
        """The gender page of a new game, in the right frame: Masculin and Féminin side by side, the hero under each; the chosen one walks toward the camera (his walking poses, at the
        speed of a walk in a town), the other stands still, grayed (the sprite only: its label stays white). Nothing chosen yet: both stand still, grayed, the keyboard cursor on Masculin."""
        self._border(xr, top - hb, wr, hb, kk); self.page_rect = (xr, top - hb, xr + wr, top)
        tl = self._label(N_('new_game.hero_gender'), 24 * kk); tl.x = xr + (wr - tl.content_width) / 2; tl.y = top - 52 * kk; tl.draw()
        low = top - hb + HELP_H * kk; high = top - 78 * kk                    # (between the title and the help zone)
        bw, bh, gap = min(220 * kk, wr * 0.36), 52 * kk, 28 * kk
        n = max(1, int(min((high - low - bh - gap) * 0.7 / 32, wr * 0.22 / 24))) * SPRITE_SIZE          # (multiple of the sprite's pixels, drawn without smoothing)
        sw, sh = 24 * n, 32 * n; y_plate = (high + low + bh + gap + sh) / 2 - bh
        pose = WALK[int(time.time() / WALK_STEP) % len(WALK)]; zones = []
        for g in (0, 1):
            cx = xr + wr * (0.3 if g == 0 else 0.7); chosen = self.hero_gender == g
            z = (cx - bw / 2, y_plate - gap - sh, cx + bw / 2, y_plate + bh); zones.append((g, z))
            self._plate(cx - bw / 2, y_plate, bw, bh, kk, self._hovered(z))
            if (chosen or (self.hero_gender is None and g == 0)) and not self.mouse_mode: self._cursor(cx - bw / 2 - 30 * kk, y_plate + bh / 2, 28 * kk)
            self._restore_blend(); lb = self._label(self.names['new_game.hero_gender'][g], 20 * kk, GOLD if chosen else WHITE); lb.x = cx - lb.content_width / 2; lb.y = y_plate + bh / 2 - lb.content_height * 0.35; lb.draw()
            t = self._hero_frame(g, pose if chosen else 1, not chosen)
            if t is not None: self._restore_blend(); t.blit(cx - sw / 2, y_plate - gap - sh, width=sw, height=sh)
        self.gender_zones = zones
        self._help_zone(xr, top - hb, wr, kk, dict(hint=GENDER_HINT))

    SIDE_PAGES = ('states', 'display', 'sound', 'controls', 'difficulty', 'randomizer', 'cheats', 'achievements', 'quit')          # pages drawn on the right of the root (the history too, drawn by itself; the interface editor take the whole screen)

    def _two_panels(self, W, H, k):
        """Two windows side by side, like the System menu of Dragon Quest VII: the root on the left, the page opened from it on the right (nothing on the right before it is opened).
        Only from the root (a menu opened on a page stays one window). A screen too narrow for both (16:10, 4:3...) draws them smaller, down to 75 %; narrower still: one window.
        (left x, right x, top, left width, right width, scale k of the two windows, height of the right frame: the same for every page, empty at the root, its help zone at the bottom) or None."""
        if not self.stack or self.stack[0] != 'root' or self.screen_page not in ('root', 'history', 'name', 'gender') + self.SIDE_PAGES: return None
        key = (W, H, LG.current_language())
        if key not in self.dims:                                                   # (the right pages all take the width of the widest, their tops aligned: the windows do not move from one line to the next)
            kk = k; self.dims[key] = None
            for _ in range(4):
                wl, hl = self._draw_page('root', 'measure', k=kk); sizes = [self._draw_page(p, 'measure', k=kk) for p in self.SIDE_PAGES]
                wr = max(w for w, _ in sizes); total = wl + 24 * kk + wr
                if total <= W - 24 * kk: self.dims[key] = (kk, wl, wr, max([hl] + [h for _, h in sizes])); break
                kk *= (W - 24 * kk) / total * 0.995                              # (measured again at that size: the texts do not shrink exactly in proportion)
                if kk < 0.75 * k: break
        if self.dims[key] is None: return None
        kk, wl, wr, hb = self.dims[key]; gap = 24 * kk; hf = hb + HELP_H * kk          # (the right frame: the tallest page, then the help zone)
        xl = (W - wl - gap - wr) / 2; top = (H + hf + 55.5 * 1.1 * kk + 10 * kk) / 2          # (the block centered with the back button under it)
        return xl, xl + wl + gap, top, wl, wr, kk, hf

    WARM_FRESH = ('selected', 'begin', 'seen_selected', 'anc', 'bars', 'zones_val', 'default_zones', 'zones_mute', 'zones_eff', 'pos_sw', 'dims')      # state the warm-up's drawing fills in place: new empty ones, the originals put back after
    WARM_CACHES = ('_pol', '_caps', '_pil', '_img')                                # what the warm-up is for (with the window's text labels, Game._lbl): kept

    def warm_up(self):
        """Builds ahead what the menu's first opening needs, so that it no longer stalls (half a second here; the first Esc in the game, the new-game panel and its name page):
        some 500 text labels (the measure of the two windows reads every page) and the game font. Every page is drawn once at the window's size, in the game (the pages of the
        root) and in a new game (its pages and the name entry), under an empty scissor box: nothing reaches the screen. Then the menu's state is put back as it was.
        Called once, before the first game frame (the loading screen still shown); a later change of the window's size builds the labels of the new size at the next opening."""
        if self.opened: return
        J = self.J; W, H = J.width, J.height; k = max(0.75, H / 900.0)
        kept = {a: v for a, v in self.__dict__.items() if a not in self.WARM_CACHES}; failed = []
        gl.glEnable(gl.GL_SCISSOR_TEST); gl.glScissor(0, 0, 0, 0)
        try:
            for new in (False, True):
                for a in self.WARM_FRESH: setattr(self, a, {})
                self.new_game = new; self.stack = ['root']
                try: two = self._two_panels(W, H, k)
                except Exception as ex: failed.append(('root', ex)); continue
                if two is None: continue
                xl, xr, top, wl, wr, kk, hb = two
                for p in ('root',) + (('display', 'difficulty', 'randomizer', 'cheats', 'name') if new else self.SIDE_PAGES):
                    self.stack = ['root'] if p == 'root' else ['root', p]
                    try:
                        if p == 'root': self._draw_page('root', 'left', (xl, top, wl), kk); self._draw_page('root', 'side', (xl, top, wl), kk)
                        elif p == 'name': J.name_entry.draw_all(0, 0, 1.0, place=(xr, top, wr, kk, hb)); J.name_entry.zones = []
                        else: self._draw_page(p, 'right', (xr, top, wr, hb), kk)
                    except Exception as ex: failed.append((p, ex))
        finally:
            gl.glDisable(gl.GL_SCISSOR_TEST)
            self.__dict__.update(kept)
            for a in [a for a in self.__dict__ if a not in kept and hasattr(type(self), a)]: delattr(self, a)          # (new_game...: back to the class's value)
        if failed: print('menu warm-up: ' + ', '.join('%s (%s)' % (p, ex) for p, ex in failed), flush=True)

    def _draw_page(self, wdir, mode='single', place=None, k=None):
        """Draws the window of page `wdir`. `mode`: 'single' (the only window, centered); 'left' / 'right' (two windows: the one being used, at `place` = (x, top, width)); 'side' (the root on the left
        while a page is open on the right: its chosen line stays lit, no cursor nor help); 'measure' (nothing drawn:
        (width, height) of the window, thumbnail of the states included). `k`: scale (default: the screen's height / 900). Returns the frame (x0, y0, x1, y1)."""
        J = self.J; W, H = J.width, J.height; k = k or max(0.75, H / 900.0)
        editor = wdir == 'interface'; interactive = mode in ('single', 'left', 'right'); measure = mode == 'measure'
        e = self._entries() if wdir == self.screen_page else getattr(self, self.PAGE_ENTRIES[wdir])(); n = len(e)
        if editor and self.folded: e = []; n = 0                                           # collapsed editor panel: only the title bar remains
        if interactive: self._purge_inactive(e)
        i_selected = min(self.selected.get(wdir, 0), max(0, n - 1))
        if n and not measure and (wdir != 'quit' or e[i_selected]['t'] != 'sep'): i_selected = self.selected[wdir] = self._active_line(e, i_selected)          # (the selection skips subheadings and inactive lines, including when the screen opens or when the chosen line has just become inactive)
        n_f = 1 if e and e[0].get('set_fraction') is True else 0                                 # line fixed at the top (no page has one anymore): it does not scroll; (`fixe` of a slider is a function, not True: a page can start with a slider)
        fs, fst, fsp = 18 * k, 24 * k, 13 * k; pad = 30 * k
        titles = {'root': N_('menu.settings'), 'display': N_('menu.display'), 'sound': N_('menu.sound'), 'controls': N_('menu.controls'), 'interface': N_('menu.interface'), 'states': N_('menu.save_states'), 'quit': N_('menu.quit')}
        titles.update(difficulty=N_('menu.difficulty'), randomizer=N_('menu.randomizer'), cheats=N_('menu.cheats'), achievements=N_('menu.achievements'))
        if self.new_game: titles['root'] = N_('menu.game_rules')                # (the rules of a new game)
        with_mini = wdir == 'states'
        msg = self._message_text() if interactive else ''
        # heights: the back button is under the window; if the lines do not fit, they scroll (scrollbar on the right, in the margin)
        with_back = not editor and wdir not in ('root', 'quit') and not (self.new_game and mode != 'single')          # (no back button at the root: "Resume" closes the menu; nor on the "Quit the game?" question: its "No" goes back; a new game: the panel's own, see draw_all)
        kb = 1.1 * k; bw, bh = 64 * kb, 55.5 * kb; back_margin = bh + 10 * k if with_back else 0.0
        foot = 0.0                                          # (no more help line at the bottom: the help texts are tooltips; the information message is drawn above the frame)
        hmax = H - 2 * 36 * k - back_margin - (HELP_H * k if mode != 'single' else 0.0); h_title = 78 * k + (22 * k + DEVICE_ROW * k if wdir == 'controls' else 0.0)          # (Commandes: the column headers, and above them the Clavier / Manette row)
        if editor: h_title = 64 * k
        rh = max(34 * k, min(52 * k, (hmax - h_title - pad / 2 - foot) / max(1, n)))
        if editor: rh = 38 * k                                                    # compact panel
        elif wdir == 'controls': rh = 46 * k                                       # tall lines: the key cells do not touch the edges (the list scrolls)
        fs = min(fs, rh * 0.5)                                                     # tight lines: smaller text, so that it fits in the button
        h_title += n_f * rh
        n_s = n - n_f
        h = min(hmax, h_title + n_s * rh + pad / 2 + foot)
        visible_ones = max(1, int((h - h_title - pad / 2 - foot) / rh + 0.02)); has_bar = n_s > visible_ones
        if has_bar: h = h_title + visible_ones * rh + pad / 2 + foot                     # (the window closes on the last visible line)
        rdr = 56 * k                                                               # right margin of the line contents (buttons: 42 px margin on the left as on the right; the scrollbar is in the margin)
        # width: the longest label + room for the values / sliders / key cells
        lw = max([self._label(x['l'], fs).content_width + x.get('indent', 0) * INDENT * k for x in e if not (wdir == 'states' and x['t'] == 'slot')] + [0.0]); vw = 0.0       # (states: the date of the slots does not count, the window keeps the same size with or without a saved state; the date shrinks if needed)
        for x in e:
            if x['t'] == 'choice':
                tw = max(self._label(self._value_name(x['l'], v), fs).content_width for v in x['vals'])
                vw = max(vw, tw + 24 * k if x.get('as_list') else tw + 14 * k + WIDTH_SW * k)               # list: value + arrow; toggle: Yes / No then the toggle
            elif x['t'] == 'slider' and x.get('notch_names'):                                                # slider with notches: its short bar (90), the longest notch name and the "default value" button
                vw = max(vw, 14 * k + 90 * k + 14 * k + max(self._label(n, fs).content_width for n in x['notch_names']) + 40 * k)
        pw = max((300 if wdir == 'root' and mode != 'single' else 540) * k, 52 * k + lw + 40 * k + vw + rdr)          # (two windows: the root is narrower)
        if wdir in ('display', 'sound', 'controls', 'interface'): pw = max(pw, 52 * k + lw + 40 * k + 44 * k + 200 * k + 20 * k + 90 * k + rdr + (36 * k if wdir == 'sound' else 0.0))          # (sound: plus the mute button)
        if wdir == 'difficulty': pw = max(pw, 52 * k + lw + 40 * k + vw + rdr + 20 * k)
        if wdir == 'controls': pw = max(pw, 52 * k + lw + 30 * k + 40 * k + 2 * CELL_WIDTH * k + CELL_SPACING * k + rdr)
        wmini = 360 * k if with_mini else 0.0; gap = 24 * k if with_mini else 0.0
        if measure: return pw + gap + wmini, h
        if place is not None: pw = max(pw, place[2] - gap - wmini)                    # (two windows: the width of the widest page)
        x0 = (W - pw - wmini - gap) / 2; y1 = (H + h + back_margin) / 2
        if place is not None: x0, y1 = place[0], place[1]
        y0 = y1 - h; frame = (x0, y0, x0 + pw + gap + wmini, y1)          # (returned at the end: `gap` is reused below)
        fixed = mode == 'right' and place is not None and len(place) > 3; mx, my1, mw, mh = x0 + pw + gap, y1, wmini, h          # (mx...: the states' thumbnail box)
        if fixed:                                                                  # two windows: the right one keeps the same frame for every page (`place[3]`: its height), its content at the top
            y0 = y1 - max(place[3], h); frame = (x0, y0, x0 + pw + gap + wmini, y1)
            mx, my1, mh = x0 + pw, y1 - h_title + 3 * k, h - h_title - pad / 2 - 6 * k          # (the thumbnail inside the frame, beside the lines)
        if editor:                                                                 # collapsed: the title bar alone, to see the whole screen; position: the player's after a move, otherwise the original (see _panel_pos)
            if self.folded and self.pan_dim: pw = self.pan_dim[0]                       # collapsed: the title bar keeps the width of the expanded panel (it stays under the pointer: short press then double click)
            elif self.folded: pw = max(300 * k, self._label(titles['interface'], fst).content_width + 130 * k)
            else: self.pan_dim = (pw, h)
            x0, y1 = self._panel_pos(pw, h, W, H, k); y0 = y1 - h
        self.panel_border = (x0, y0, x0 + pw, y1) if editor else None
        self.fold_zone = (x0, y1 - h_title, x0 + pw, y1) if editor else None
        a_pan = self.pan_pressed if editor else None; lifted = bool(a_pan and a_pan['long'])          # press on the title bar: gold title; after the long press, the panel "lifts" (enlarged frame, gold outline)
        if lifted:
            g = 7 * k; self._border(x0 - g, y0 - g, pw + 2 * g, h + 2 * g, k)
            pyglet.shapes.Box(x0 - g, y0 - g, pw + 2 * g, h + 2 * g, thickness=max(2.0, 3 * k), color=GOLD[:3]).draw()
        else: self._border(x0, y0, frame[2] - x0 if fixed else pw, y1 - y0, k)
        e_t = self._label(titles.get(wdir, ''), fst, GOLD if (a_pan and not a_pan['double']) else WHITE); e_t.x = x0 + ((frame[2] - x0 if fixed else pw) - e_t.content_width) / 2; e_t.y = y1 - (44 if editor else 52) * k; e_t.draw()
        if editor:                                                                 # collapse / expand the panel: arrow in the title bar (up = collapse, down = expand)
            fx, fy = e_t.x + e_t.content_width + 26 * k, y1 - 32 * k                  # (stuck to the title: it follows it when the panel changes width)
            over = self.mouse_mode and self.mouse_pos and self._inside(self.fold_zone, *self.mouse_pos)
            clr = GOLD[:3] if over else (200, 200, 200)
            if self.folded: pyglet.shapes.Triangle(fx - 9 * k, fy + 5 * k, fx + 9 * k, fy + 5 * k, fx, fy - 6 * k, color=clr).draw()
            else: pyglet.shapes.Triangle(fx - 9 * k, fy - 5 * k, fx + 9 * k, fy - 5 * k, fx, fy + 6 * k, color=clr).draw()
        # view: the selection stays visible when it changes; otherwise the view moves only through the bar or the wheel
        start_idx = self.begin.get(wdir, n_f)
        if self.seen_selected.get(wdir) != i_selected:
            if i_selected >= n_f:
                if i_selected < start_idx: start_idx = i_selected
                elif i_selected >= start_idx + visible_ones: start_idx = i_selected - visible_ones + 1
            self.seen_selected[wdir] = i_selected
        begin = self.begin[wdir] = max(n_f, min(start_idx, max(n_f, n - visible_ones)))
        anc = self.anc.get(wdir, ({}, {}, {}))                                  # buttons of each line at the previous frame: under the pointer, it is the button that darkens, not the plate of the line
        self.zones = []; self.zones_off = []; self.bars = {}; self.zones_val = {}; self.default_zones = {}; self.zones_mute = {}; self.zones_eff = {}; self.zones_pop = []; lines = {}; self.has_bar = None; self.list_bar = None; self.list_border = None
        self.anc[wdir] = (self.default_zones, self.zones_mute, self.zones_eff)          # (per page: with two windows, the other one is drawn in between)
        xr = x0 + pw - rdr                                                        # right edge of the line contents
        cx2 = xr - 40 * k - CELL_WIDTH * k; cx1 = cx2 - CELL_SPACING * k - CELL_WIDTH * k; self.zones_col = (cx2 - CELL_SPACING * k / 2,)
        plx = x0 + 42 * k; plw = pw - 84 * k                                      # buttons: same margin on the left and on the right
        self.zones_device = []
        if wdir == 'controls':
            for c, cx in enumerate((cx1, cx2)):
                eh = self._label(tr('controls.button' if self.controls_pad else 'controls.key') % (c + 1), fsp, GRAY); eh.x = cx + (CELL_WIDTH * k - eh.content_width) / 2; eh.y = y1 - h_title + 6 * k; eh.draw()
            wrow = 2 * CELL_WIDTH * k + CELL_SPACING * k          # (centered just under the page's title)
            self._device_row(x0 + (pw - wrow) / 2, y1 - 62 * k - (DEVICE_ROW - 12) * k, wrow, (DEVICE_ROW - 12) * k, k, fs, modal_now=self.popup is not None or self.open_dropdown is not None or self.capture is not None)
        pos = []
        if n_f: pos.append((0, y1 - 66 * k))
        yy = y1 - h_title
        for idx in range(begin, min(n, begin + visible_ones)): pos.append((idx, yy)); yy -= rh
        mouse = self.mouse_mode; modal = self.popup is not None or self.open_dropdown is not None or self.capture is not None
        for idx, ytop in pos:
            entry = e[idx]; ybottom = ytop - rh; lines[idx] = (ybottom, ytop)
            ind = entry.get('indent', 0) * INDENT * k; px, pwl = plx + ind, plw - ind          # (a line under another one, `indent`: shifted to the right, its plate, label and cursor; the values stay right-aligned)
            off = entry['t'] != 'sep' and self._inactive(entry)                                       # inactive line (re-read every frame): the whole cell is grayed, never chosen or hovered, with no click zone
            if mouse:                                                                         # mouse: the line is darkened as long as the pointer is on it (and not on one of its buttons); there is no selection anymore when it leaves
                selected = (not modal and not off and entry['t'] != 'sep' and self._pointer_in((px, ybottom + 3 * k, px + pwl, ytop - 3 * k))
                       and not self._pointer_in(anc[0].get(idx)) and not self._pointer_in(anc[1].get(idx)) and not any(self._pointer_in(z) for (i_, c_), z in anc[2].items() if i_ == idx))
            else: selected = idx == i_selected and entry['t'] != 'sep' and not off                          # keyboard: the chosen line, with the gold cursor
            if mode == 'side' and idx == i_selected and not off: selected = True          # two windows: the root line whose page is open on the right stays lit
            if entry['t'] != 'sep': self._plate(px, ybottom + 3 * k, pwl, rh - 6 * k, k, selected, grayed=off)       # button background, like those of the mobile game's command menu: the plate darkens when chosen (keyboard) or hovered (mouse), without an outline
            if selected and not mouse and interactive: self._cursor(x0 + 6 * k + ind, ybottom + rh / 2, min(rh * 0.6, 26 * k))             # gold cursor of the game menus (keyboard selection)
            mute = entry['t'] == 'slider' and 'active' in entry and not entry['active']()                  # line of the "Sound" page whose sound is muted: name, value and gauge grayed
            clr = GRAY if off or mute else WHITE
            base = ybottom + rh / 2 - 0.45 * fs                                                  # text centered in the button
            lx = x0 + 52 * k + ind
            if entry['t'] == 'sep' and entry.get('v'):                                               # information line (mouse gesture): the gesture on the left, its effect on the right in gray, with no plate, no selection and no click zone
                label = self._label(entry['l'], fs, WHITE); label.x = lx; label.y = base; label.draw()
                ev = self._adjust(entry['v'], fs, GRAY, xr - 24 * k - (lx + label.content_width)); ev.x = xr - ev.content_width; ev.y = base; ev.draw()
                continue
            if entry['t'] == 'sep':                                                              # subheading: in the center of the window
                label = self._label(entry['l'], fs, GRAY if entry.get('gray') else GOLD); label.x = x0 + (pw - label.content_width) / 2; label.y = base; label.draw()          # (gray: a note, "nothing yet")
                self.zones.append((px, ybottom + 3 * k, px + pwl, ytop - 3 * k, idx))
                continue
            maxw_lab = 0.0                                                                    # width allowed for the label (0: no limit)
            if entry['t'] == 'slot':
                nu = self._label('%d' % entry['n'], fs, clr); nu.x = lx; nu.y = base; nu.draw(); lx += 44 * k
                maxw_lab = x0 + pw - 66 * k - (self._label(entry['v'], fsp * 1.2, GRAY).content_width + 12 * k if entry['v'] else 0.0) - lx           # (up to the location, on the right)
            lab = self._adjust(entry['l'], fs, clr, maxw_lab) if maxw_lab else self._label(entry['l'], fs, clr); lab.x = lx; lab.y = base; lab.draw()
            if entry['t'] == 'act' and entry.get('sub'): self._chevron(xr - 6 * k, ybottom + rh / 2, k, off)
            if entry['t'] == 'act' and 'v' in entry:                                                 # value of an action line (seed code): on the right; gold with a cursor while it is being typed
                typing = self.entry is not None and self.entry[0] == idx; xv = xr - (34 * k if 'default' in entry else 0.0)          # (a round button on its right: a new seed)
                txt = (self.entry[1] + ('_' if int(time.time() * 2) % 2 == 0 else ' ')) if typing else (entry['v']() or '')
                vl = self._label(txt, fs, GOLD if typing else clr); vl.x = xv - 24 * k - vl.content_width; vl.y = base; vl.draw()
                if not off: self.zones_val[idx] = (vl.x - 10 * k, xv)
                if 'default' in entry: self._default_button(idx, xr - 26 * k, ybottom + rh / 2 - 13 * k, 26 * k, entry['is_default'](), selected, k, off)
            xc = xr - (34 * k if entry['t'] == 'choice' and 'default' in entry else 0.0)                 # (space for the round "default value" button of the choices, on the right of the line)
            if entry['t'] == 'choice' and 'default' in entry: self._default_button(idx, xr - 26 * k, ybottom + rh / 2 - 13 * k, 26 * k, entry['is_default'](), selected, k, off)
            if entry['t'] == 'choice' and entry.get('as_list'):                                        # drop-down list: current value and small down arrow
                vl = self._label(entry['v'](), fs, clr); vl.x = xc - 24 * k - vl.content_width; vl.y = base; vl.draw()
                fx, fy = xc - 8 * k, ybottom + rh / 2
                pyglet.shapes.Triangle(fx - 7 * k, fy + 4 * k, fx + 7 * k, fy + 4 * k, fx, fy - 5 * k, color=GOLD[:3] if selected else clr[:3]).draw()
                if not off: self.zones_val[idx] = (vl.x - 10 * k, xc + 10 * k)
            elif entry['t'] == 'choice':                                                          # Yes / No toggle: the text of the value, then the toggle
                sw_x = xc - WIDTH_SW * k; active = bool(entry['get']())
                vl = self._label(entry['v'](), fs, clr if not active or off else GOLD); vl.x = sw_x - 14 * k - vl.content_width; vl.y = base; vl.draw()
                self._switch(entry['l'], sw_x, ybottom + rh / 2, active, selected and not mouse, off, k)
                if not off: self.zones_val[idx] = (vl.x - 10 * k, sw_x + WIDTH_SW * k + 10 * k)
            elif entry['t'] == 'slider':
                if self.entry is not None and self.entry[0] == idx: txt = (self.entry[1] + ('_' if int(time.time() * 2) % 2 == 0 else ' ')).rjust(3)
                else: txt = entry['v']()
                dm = 36 * k if 'active' in entry else 0.0                                         # space for the mute button ("Sound" page), between the value and the "default value" button
                dr = xr - 40 * k - dm                                                         # right edge of the value: the "default value" button is to its right
                vl = self._label(txt, fs, GOLD if self.entry is not None and self.entry[0] == idx else clr); vl.x = dr - vl.content_width; vl.y = base; vl.draw()
                bw_ = 200 * k; bx1 = dr - 90 * k - 20 * k; bx0 = bx1 - bw_; by = ybottom + rh / 2 - 5 * k
                if entry.get('notches'):                                                                 # slider with notches: a short bar, to the left of the longest notch name (the bars of two lines stay aligned)
                    bw_ = 90 * k; bx1 = dr - max(self._label(n, fs).content_width for x in e if x['t'] == 'slider' and x.get('notch_names') for n in x['notch_names']) - 14 * k; bx0 = bx1 - bw_          # (left of the longest notch name of the page: the bars line up)
                if not off: self.zones_val[idx] = (vl.x - 10 * k, dr + 10 * k); self.bars[idx] = (bx0, bx1)
                background = pyglet.shapes.Rectangle(bx0, by, bw_, 10 * k, color=(16, 18, 22)); background.draw()
                rem = pyglet.shapes.Rectangle(bx0, by, bw_ * max(0.0, min(1.0, entry['fraction']())), 10 * k, color=(110, 110, 104) if mute or off else YELLOW); rem.draw()            # (yellow gauge; gray when the sound is muted or the line inactive)
                for f in entry.get('notches', ()):                                                       # slider with notches ("Experience gained": Less, Normal, More): a mark under each one
                    pyglet.shapes.Rectangle(bx0 + bw_ * f - 1 * k, by - 6 * k, 2 * k, 22 * k, color=(150, 150, 150)).draw()
                cur = pyglet.shapes.Rectangle(bx0 + bw_ * max(0.0, min(1.0, entry['fraction']())) - 3 * k, by - 4 * k, 6 * k, 18 * k, color=(150, 150, 150) if off else (255, 255, 255)); cur.draw()
                if 'active' in entry: self._mute_button(idx, xr - 62 * k, ybottom + rh / 2 - 13 * k, 26 * k, mute, k, off)
                if 'default' in entry: self._default_button(idx, xr - 26 * k, ybottom + rh / 2 - 13 * k, 26 * k, entry['is_default'](), selected, k, off)
            elif entry['t'] == 'slot':
                if entry['v']: vl = self._label(entry['v'], fsp * 1.2, GRAY); vl.x = x0 + pw - 24 * k - 42 * k - vl.content_width; vl.y = base; vl.draw()
            elif entry['t'] == 'key':
                fam = self._family(); pad_mode = self.controls_pad
                slots = self.J.reg.pad_slots(entry['act']) if pad_mode else list(entry.get('keys') or [None, None])          # (the two keys, or the two gamepad inputs)
                for c, cx in enumerate((cx1, cx2)):
                    name_c = slots[c] if c < len(slots) else None
                    if pad_mode: txt = PI.text_label(name_c, fam) if name_c else RG.key_name(None); pics = [PR.pad_file(fam, name_c)] if name_c else []
                    else: txt = entry['v'][c]; pics = [PR.key_file(name_c)] if name_c else []          # (keys and inputs are drawn with their picture when there is one)
                    face = bool(pics) and all(pics)
                    capturing = self.capture == (entry['act'], c, pad_mode)
                    active = (selected and not mouse and self.selected.get('col', 0) == c) or capturing; empty = not name_c          # (chosen cell: by keyboard, or waiting for a key; with the mouse it is the plate that darkens)
                    if capturing: txt = '…'; face = False
                    if active: pyglet.shapes.Box(cx, ybottom + 5 * k, CELL_WIDTH * k, rh - 10 * k, thickness=max(1.0, 2 * k), color=GOLD[:3]).draw()          # chosen cell (keyboard) or waiting for a key: a gold outline; no black frame around the cells any more
                    zone_t = CELL_WIDTH * k - (0 if empty else 2 * 22 * k); fz = fs * 0.8                 # text centered in the cell (equal margins: the red cross is on the right, outside the text zone)
                    vl = self._label(txt, fz, GOLD if active else (GRAY if empty or off else WHITE))
                    if vl.content_width > zone_t - 8 * k: fz *= (zone_t - 8 * k) / vl.content_width; vl = self._label(txt, fz, GOLD if active else (GRAY if off else WHITE))
                    vl.x = cx + (CELL_WIDTH * k - vl.content_width) / 2; vl.y = ybottom + rh / 2 - self._cap(fz) / 2
                    if face:
                        word = self._label(KEY_SIDE[name_c], fz * 0.8, GOLD if active else (GRAY if off else WHITE)) if not pad_mode and name_c in KEY_SIDE else None          # (Shift, Ctrl, Alt: left or right)
                        ww = word.content_width + 4 * k if word else 0.0
                        side = rh + 4 * k; gap = 4 * k; npic = len(pics); side = min(side, (zone_t - 8 * k - ww - gap * (npic - 1)) / npic); x = cx + (CELL_WIDTH * k - (npic * side + gap * (npic - 1) + ww)) / 2          # (larger; the pictures have a transparent margin, the key itself stays inside the line)
                        for pic in pics:
                            def make(pic=pic, x=x):
                                logo = pyglet.sprite.Sprite(self._tex_pil(PR.image(pic), ('prompt', pic)), x=x, y=ybottom + (rh - side) / 2)
                                logo.scale = side / logo.image.width; logo.opacity = 110 if off else 255; return logo
                            self._sprite(('prompt', pic, round(x, 2), round(ybottom, 2), round(rh, 2), round(side, 2), off), make); x += side + gap
                        if word: word.x = x - gap + 4 * k; word.y = ybottom + rh / 2 - self._cap(fz * 0.8) / 2; word.draw()
                    else: vl.draw()               # (baseline: the middle of the height of the capitals on the middle of the cell)
                    if not empty and not capturing:
                        cc = 12 * k; cxx = cx + CELL_WIDTH * k - cc - 8 * k; ze = (cxx - 4 * k, ybottom + 9 * k, cx + CELL_WIDTH * k, ybottom + rh - 9 * k)
                        if not off: self.zones_eff[(idx, c)] = ze
                        self._dpad(cxx, ybottom + rh / 2 - cc * 0.45, cc, not off and self._hovered(ze), off)                  # (at 75% under the pointer; dull when the line is inactive)
                self._default_button(idx, xr - 26 * k, ybottom + rh / 2 - 13 * k, 26 * k, entry['is_default'](), selected, k, off)
            (self.zones_off if off else self.zones).append((px, ybottom + 3 * k, px + pwl, ytop - 3 * k, idx))          # (an inactive line has no zone: no hover, no click; its zone serves only for the tooltip)
        if has_bar: self.has_bar = self._scroll_bar(x0 + pw - 14 * k, y1 - h_title, y1 - h_title - visible_ones * rh, n_s, visible_ones, begin - n_f, k, self.dragging_bar is not None, n_f)
        # foot of the frame: help (centered, always inside the frame)
        if msg:
            em = self._adjust(msg, fsp * 1.1, RED if self.message[2] else GOLD, W - 24 * k); em.x = min(max(12 * k, x0 + (pw - em.content_width) / 2), W - em.content_width - 12 * k); em.y = min(H - 24 * k, y1 + 12 * k); em.draw()
        # back button, at the bottom right of the window
        self.zone_ret = None
        if with_back and interactive:
            bx = (frame[2] if fixed else x0 + pw) - bw - 8 * k; by = y0 - 8 * k - bh; self.zone_ret = (bx, by, bx + bw, by + bh)          # (under the right edge of the frame)
            self._back_button(bx, by, bw, bh, self._hovered(self.zone_ret))                    # (pressed version of the "Button" sheet under the pointer)
        # thumbnail of the hovered state
        if with_mini:
            self._border(mx, my1 - mh, mw, mh, k)
            if e and e[i_selected]['t'] == 'slot':
                n_e = e[i_selected]['n']; t = self._thumbnail(n_e); inf = J.state_info(n_e)
                if t is not None:
                    w_i = mw - 40 * k; h_i = w_i * t.height / t.width
                    spr = pyglet.sprite.Sprite(t, x=mx + 20 * k, y=my1 - 40 * k - h_i); spr.scale_x = w_i / t.width; spr.scale_y = h_i / t.height; spr.draw()
                    entries = []
                    if inf:
                        entries = [self._state_date(inf[0].get('date')) or 'save_states.no_date', self._readable_location(inf[0])]
                    for j, line in enumerate(entries):
                        el = self._label(line, fsp * 1.1, WHITE if j == 0 else GRAY); el.x = mx + (mw - el.content_width) / 2; el.y = my1 - 40 * k - h_i - 34 * k - j * 30 * k; el.draw()
                else:
                    el = self._label('save_states.empty_slot' if not inf else 'save_states.no_thumbnail', fs, GRAY); el.x = mx + (mw - el.content_width) / 2; el.y = my1 - mh / 2; el.draw()
        if fixed: self._help_zone(x0, y0, frame[2] - x0, k, self._described(e, i_selected))
        if not interactive: return frame
        if self.open_dropdown is not None and self.open_dropdown[0] in lines and self.open_dropdown[0] < n and e[self.open_dropdown[0]]['t'] in ('choice', 'slot'):          # (a slot: the list of what to do with it)
           
            self._draw_entries(e[self.open_dropdown[0]], lines[self.open_dropdown[0]], xr + 6 * k, k, fs)
        self._draw_tooltip(e, n, lines, plx, plw, k, fsp, W, H)
        self._draw_popup(k, fs, fsp, W, H)
        return frame

    # ---- tooltips (help on mouse hover) and modal window
    # (the help texts are French texts; `_helptext_lines` translates each sentence separated by three spaces, see the catalog texts_en\pause.py:
    # an assembled help text ("..." + KEY_HELPTEXT) is therefore translated sentence by sentence)
    KEY_HELPTEXT = 'controls.enter_change_key   controls.switch_slot   controls.delete_clear   controls.home_default_value_button_original   controls.camera_keys_keyboard_gamepad'
    SAVESTATES_HELPTEXT = N_('save_states.enter_click_slot_choose')          # (a slot: what confirming or clicking it does)

    def _line_helptext(self, entry):
        """Help text of a menu line ('   ' separates the tooltip lines); '' if there is none."""
        t = entry['t']
        if t != 'sep' and self._inactive(entry): return entry.get('hint') or ''                   # inactive line: no keyboard or mouse hint, only its own help (it says why)
        if t == 'key': return entry.get('hint') or self.KEY_HELPTEXT
        prefix = entry['hint'] + '   ' if entry.get('hint') and t != 'act' else ''          # text specific to the line, before the general hint
        if t == 'slider' and 'active' in entry: return prefix + 'sound.drag_volume   sound.enter_speaker_button_mute_unmute   common.click_value_type   sound.delete_default_value_button_reset'
        if t == 'slider' and entry.get('notches'): return prefix + 'common.drag_change_value   common.delete_default_value_button_default'          # (notches: the value is a name, not typed)
        if t == 'slider': return prefix + 'common.drag_change_value   common.click_value_type   common.delete_default_value_button_default'
        if t == 'choice':
            return prefix + ('common.enter_click_turn_off   common.left_arrow_no   common.right_arrow_yes' if entry.get('sw') else 'common.enter_click_open_list   common.previous_next_value') + ('   common.delete_round_button_default_value' if 'default' in entry else '')
        if t == 'act' and entry.get('hint'): return entry['hint']
        if t == 'slot': return self.SAVESTATES_HELPTEXT
        if self.screen_page == 'interface': return 'interface.drag_selected_item_place   interface.esc_right_click_finish   interface.tab_collapse_panel'
        return ''

    def _helptext_lines(self, text, maxw, fz):
        """Lines of a tooltip: split at triple spaces, then wrapped at width maxw. Each sentence (between two triple spaces) is translated BEFORE being wrapped to the width: a wrapped line is no longer a catalog sentence."""
        import re
        out = []
        for l in re.split(r'\s{3,}', text.strip()):
            out += LG.wrap(tr(l), maxw, lambda t: self._label(t, fz).content_width)          # (Japanese and Chinese: between characters too)
        return out

    def _described(self, e, i):
        """Line whose help the help zone shows: the one under the pointer (even an inactive one: its help says why), otherwise the chosen one."""
        if self.mouse_mode and self.mouse_pos:
            z = next((z for z in self.zones + self.zones_off if self._inside(z[:4], *self.mouse_pos)), None)
            if z is not None: return e[z[4]] if z[4] < len(e) else None
        return e[i] if e and 0 <= i < len(e) else None

    def _help_zone(self, x, y0, w, k, entry):
        """Help zone at the bottom of the right frame (two windows; like the description window of Dragon Quest VII's menus): the help of the line under the pointer or chosen,
        its sentences in one paragraph of up to 3 lines (no pop-up), under a thin separator."""
        import re
        fz = 14 * k; lh = fz * 1.6; hz = HELP_H * k; m = 30 * k
        pyglet.shapes.Line(x + m, y0 + hz, x + w - m, y0 + hz, thickness=max(1.0, k), color=(110, 110, 110)).draw()
        text = (entry.get('hint') or self._line_helptext(entry)) if entry else ''          # (the line's own description; the keys and the mouse only for a line without one: a key, a state slot)
        if not text: return
        lines = LG.wrap('  ·  '.join(tr(t) for t in re.split(r'\s{3,}', text.strip()) if t), w - 2 * m, lambda t: self._label(t, fz, translate=False).content_width)
        if len(lines) > 3: lines = lines[:3]; lines[-1] += ' …'
        y = y0 + hz - 14 * k - fz
        for l in lines: lab = self._label(l, fz, HELPTEXT, translate=False); lab.x = x + m; lab.y = y; lab.draw(); y -= lh

    def _draw_tooltip(self, e, n, lines, plx, plw, k, fsp, W, H):
        """The prompt for entering a value / capturing a key, under the selected line. (No more help bubble under the pointer: no pop-up; with two windows, the lines' help texts, `_line_helptext`, are in the help zone.)"""
        if self.popup is not None: self.tt = None; return
        fz = fsp * 1.05; text = ''; anchor = None
        i_selected = min(self.selected.get(self.screen_page, 0), max(0, n - 1))
        if self.capture is not None: text = tr('controls.press_gamepad_button' if self.capture[2] else 'controls.press_key') % tr(dict(RG.ACTIONS)[self.capture[0]]) + '   common.right_click_cancel   controls.delete_clear'; anchor = i_selected
        elif self.entry is not None:
            spec = self._text_entry(); anchor = self.entry[0]
            text = (spec['prompt'] if spec else 'common.type_value') + '   common.enter_confirm   common.right_click_cancel'
        elif self.open_dropdown is not None: self.tt = None; return
        else: self.tt = None
        if not text: return
        ls = self._helptext_lines(text, 520 * k, fz)
        if not ls: return
        ets = [self._label(l, fz, WHITE) for l in ls]; lh = fz * 1.65
        w = max(label.content_width for label in ets) + 28 * k; h = len(ets) * lh + 18 * k
        if anchor is not None and anchor in lines:                                   # hint: under the chosen line (above if there is no room)
            yb, yt = lines[anchor]; x = plx + 24 * k; y = yb - 8 * k - h
            if y < 8 * k: y = yt + 8 * k
        else:
            mx, my = self.mouse_pos; x = mx + 14 * k; y = my - 20 * k - h
            if y < 8 * k: y = my + 22 * k
        x = max(8 * k, min(x, W - w - 8 * k)); y = max(8 * k, min(y, H - h - 8 * k))
        HM.border(x, y, w, h, k * 0.5, 0.0, background=BLACK, opacity=0.94)
        for j, label in enumerate(ets): label.x = x + 14 * k; label.y = y + h - 9 * k - lh * (j + 1) + (lh - fz * 1.0) * 0.45; label.draw()

    def _draw_popup(self, k, fs, fsp, W, H):
        """Modal window: Yes / No (deleting a savestate: No is preselected), or a column of choices (`buttons`); the menu stays visible, darkened."""
        self.zones_popup = []
        p = self.popup
        if p is None: return
        veil = pyglet.shapes.Rectangle(0, 0, W, H, color=(0, 0, 0)); veil.opacity = 120; veil.draw()
        title_screen = tr(p['model']) % p['values'] if p.get('model') else p['title']
        label = self._label(title_screen, fs * 1.2, WHITE); ed = self._label(p['detail'], fsp * 1.15, GRAY) if p.get('detail') else None
        choices = [tr(c) for c, _ in p['buttons']] if p.get('buttons') else None
        bh = 46 * k; gap = 12 * k
        if choices:
            bw = max(self._label(c, fs).content_width for c in choices) + 70 * k
            w = max(bw + 80 * k, label.content_width + 80 * k, (ed.content_width + 80 * k) if ed else 0); h = 150 * k + len(choices) * (bh + gap)
            x, y = (W - w) / 2, (H - h) / 2
            places = [(x + (w - bw) / 2, y + 22 * k + (len(choices) - 1 - i) * (bh + gap)) for i in range(len(choices))]
        else:
            bw = 150 * k; w = max(2 * bw + 60 * k, label.content_width + 80 * k, (ed.content_width + 80 * k) if ed else 0); h = 200 * k
            x, y = (W - w) / 2, (H - h) / 2; choices = ['common.yes', 'common.no']
            places = [(x + w / 2 + (-bw - 14 * k if i == 0 else 14 * k), y + 28 * k) for i in range(2)]
        self._border(x, y, w, h, k)
        label.x = x + (w - label.content_width) / 2; label.y = y + h - 62 * k; label.draw()
        if ed: ed.x = x + (w - ed.content_width) / 2; ed.y = y + h - 92 * k; ed.draw()
        for i, (lib, (bx, by)) in enumerate(zip(choices, places)):
            selected = self._pointer_in((bx, by, bx + bw, by + bh)) if self.mouse_mode else p['choice'] == i                  # mouse: the button under the pointer darkens; keyboard: the chosen button, with the gold cursor
            self._plate(bx, by, bw, bh, k, selected)
            if selected and not self.mouse_mode: self._cursor(bx - 24 * k, by + bh / 2, min(bh * 0.6, 26 * k))
            lb = self._label(lib, fs, WHITE); lb.x = bx + (bw - lb.content_width) / 2; lb.y = by + bh / 2 - 0.45 * fs; lb.draw()
            self.zones_popup.append((bx, by, bx + bw, by + bh, i))

    def _draw_entries(self, entry, line, xd, k, fs):
        """Dropdown list of a choice: below the line (above if there is no room), current value in gold, golden cursor as in the game's menus; a scrollbar
        (arrows, thumb, click on the track, wheel = next value) when not all the values fit."""
        J = self.J; vals = entry['vals']; names = [self._value_name(entry.get('list_label', entry['l']), v) for v in vals]; cur = self.open_dropdown[1]; H = J.height; n = len(vals)
        ih = 36 * k; n_visible = max(1, min(n, 8, int((H - 40 * k) // ih)))
        has_bar = n > n_visible; lb = (BAR_WIDTH + 12) * k if has_bar else 0.0                          # space for the scrollbar, to the right of the values
        w = max(max(self._label(t, fs).content_width for t in names) + 90 * k + lb, 240 * k); h = n_visible * ih + 20 * k
        ybottom, ytop = line; y1 = ybottom - 4 * k; y0 = y1 - h
        if y0 < 8 * k: y1 = ytop + 4 * k; y0 = y1 - h
        if y0 < 8 * k: y0 = 8 * k; y1 = y0 + h
        x1 = xd; x0 = x1 - w
        HM.border(x0, y0, w, h, k, background=BLACK, opacity=LIST_OPACITY); self.list_border = (x0, y0, x1, y1)          # (nearly opaque: the lines under the list, their values and round buttons, do not show through it)
        if self.entries_top is None: self.entries_top = max(0, min(cur - n_visible // 2, n - n_visible)); self.entries_cur_seen = cur
        elif self.entries_cur_seen != cur:                                                         # the highlighted value has changed: the view follows it; otherwise only the bar or the wheel moves it
            if cur < self.entries_top or (cur - 1 < self.entries_top and cur > 0 and self._header(vals[cur - 1])): self.entries_top = cur - 1 if cur > 0 and self._header(vals[cur - 1]) else cur          # (the first choice of a group shows its subheading)
            elif cur >= self.entries_top + n_visible: self.entries_top = cur - n_visible + 1
            self.entries_cur_seen = cur
        top = self.entries_top = max(0, min(self.entries_top, n - n_visible))
        self.zones_pop = []; y = y1 - 10 * k
        for j in range(top, top + n_visible):
            yb = y - ih; current_item = vals[j] == entry['get']()
            if self._header(vals[j]):                                                          # group subheading: in the center of the list, in dull golden gray and smaller (gold is that of the current value), with no click zone
                size_i, clr_i = heading_style(fs); label = self._label(names[j], size_i, clr_i); label.x = x0 + (w - lb - label.content_width) / 2; label.y = yb + (ih - fs * 1.33) / 2 + 5 * k; label.draw()
                pyglet.shapes.Rectangle(x0 + 14 * k, yb + 3 * k, w - lb - 28 * k, max(1, int(k)), color=HEADING_RULE).draw(); y -= ih; continue
            if self.mouse_mode:                                                               # mouse: the value under the pointer is darkened (pressed plate), without an outline
                if self._pointer_in((x0 + 6 * k, yb, x1 - 6 * k - lb, yb + ih)): self._plate(x0 + 6 * k, yb + 2 * k, w - 12 * k - lb, ih - 4 * k, k * 0.8, True)
            elif j == cur: self._cursor(x0 + 8 * k, yb + ih / 2, 22 * k)                       # keyboard: gold cursor
            label = self._label(names[j], fs, GOLD if current_item else WHITE); label.x = x0 + 44 * k; label.y = yb + (ih - fs * 1.33) / 2 + 5 * k; label.draw()
            self.zones_pop.append((x0 + 6 * k, yb, x1 - 6 * k - lb, y, j)); y -= ih
        if has_bar: self.list_bar = self._scroll_bar(x1 - 8 * k, y1 - 10 * k, y0 + 10 * k, n, n_visible, top, k, self.dragging_entries is not None, 0)
        else: self.list_bar = None
