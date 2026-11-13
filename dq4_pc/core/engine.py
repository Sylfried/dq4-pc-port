"""The game engine (libdq4core.so, ARM64) running in an emulator + decoding of what it asks of Unity."""
import os, re, struct, zipfile, unicorn
import numpy as np
from dq4_pc.core import emu_core as T
from dq4_pc.core import game_priority as PJ
from dq4_pc.core import lying_pose as PC
from dq4_pc.core import encounters as RE
from dq4_pc.core.pktlog import PacketLog
from dq4_pc.core.legacy_state import OLD_ATTRIBUTES, renamed_attributes as _renamed_attributes, renamed_dict_keys as _renamed_dict_keys, renamed_interface_keys as _renamed_interface_keys     # noqa: F401 (names of the savestates recorded before the switch to English; OLD_ATTRIBUTES is read through this module by the tests)
from dq4_pc.core.history import Sensor
from dq4_pc.world.fbx import AnimPlayer
from dq4_pc.battle.battle_history import BattleSensor
from dq4_pc.render import capture_effects as EF
from dq4_pc.persistence.write_dir import atomic_write
from dq4_pc.menus.message_font import MessageFont

FIELD_SCALE = (0.25, 4.0)               # bounds of the world map scale (packet 30; the engine only sends 1.0 to 1.25: the bound only serves to discard an outlier value)
CUR_I, CUR_F = 0x258278, 0x258280          # write cursors (integers / floats) in the library
PART_INITIAL = 0x3                         # start menu (GameStartPart: log list, creation, deletion, license)
PART_TOWN = 0xc                         # town, dungeon, tower (3D scenery)
PART_BATTLE = 0xd
PART_FIELD = 0xe                         # FieldPart: world map
PART_CASINO = 0xf                        # Global::startCasino: slot machine (map ev05) and poker (map ev04), windows of types 44-48
PART_BESTIARY = 0x10                    # Global::startBook: monster book (window of type 28); keeps the town map
TITLE_MAP = 'ev01'                       # title screen map (sky, logo, island, dragon: scene without a hero)
MINIGAME_PARTS = (PART_CASINO, PART_BESTIARY)        # engine "full screen" parts that draw their elements with dynamic meshes (packets 21 / 22) using their own camera
MSGDBG = bool(os.environ.get('DQ_MSGDBG'))     # (test) log of the engine message states
FBXLOG = bool(os.environ.get('DQ_FBXLOG'))     # (test) log of packets 32 (title dragon: position, rotation, color, sequence)
GLOBAL_PTR = 0x23d438                       # Global singleton
RESOURCE_NAME = 0x258290                    # name of the map resource requested from Unity (e.g. m/ma/in/mak1f1)
SCREEN_STATE = 0xd8                           # Global+0xd8: copy, on every GameUpdate, of the first integer of the output buffer (state word shared with Unity); its bit 1 = "screen effect in progress" (Global::IsScreenEffectEnd waits for it to drop)
G_IS_AMAZON = 0x24f684                      # engine byte g_isAmazon: at 1, the "Sauv. cloud" cell of the start menu does not exist
# Name of a monster's copy of a character (MsgVar::extract_var: the string chosen by the language index through the byte offsets at 0xc9190, ";" = the place of the name;
# languages 1, 3, 4 put it before the name, 0 and 2 after). The French texts run as language 1, whose prefix is the English "copy of ;": replaced in memory by the French patch's own words.
COPY_PREFIX = 0xc9170
COPY_PREFIX_EN = b'copy of ;\x00\xec\x9d'      # (+ the first 2 bytes of the Korean string that follows: language 2, never read by the French texts)
COPY_PREFIX_FR = b"double de ;\x00"         # the words of the French patch for these copies (monster names of `b1002000.mpt`: "double de ;Ragnar", "double de Kiryl", "double d'Alina")
COPY_ELISION = b"double d'"                    # before a vowel, as the patch writes "double d'Alina" (hook at MsgVar::extract_var + COPY_NAME_DONE)
COPY_NAME_DONE = 0xb8                          # MsgVar::extract_var + 0xb8 (`ldrb w8, [x20, #0x12]`): the name has just been written after the prefix, x19 = its start
LDRB_W8_X20_12 = 0x39404a88
NAMES_MSG = 'assets/msg/en/b1002000.mpt'   # monster names with their articles ("@2" = definite article): "le", "la", "l'" in the French texts, "the" in the English ones
MSG_RETURN_TITLE = 0xcba2f                     # message identifier of the "Revenir a l'ecran titre" box of the original "Parametres" (TownMenu_OPERATION_SETTING::menuUpdate + 0x1c8: `mov w1, #0xba2f ; movk w1, #0xc, lsl` then TownMenu_MESSAGE::addMessage(int)): b0834000.mpt, 834095
MESSAGE_RESULT = 0x10                        # TownMenu_MESSAGE + 0x10: box answer (1 = Yes, 2 = No; reset to 0 on opening); read by TownMenu_OPERATION_SETTING::menuUpdate (state 5)
BATTLE_EFFECT = 4                            # packet 34 (cmd_screen_effect): value & 0xf = 4, Capture.BattleEffect (the screen chunks fall)
BATTLE_EFFECT_FRAMES = 57                    # Capture.BattleEffect: the counter goes from 0 to divY (56) inclusive, one game frame each
BLACK_SCREEN_MAX = 1800                       # frames (30 Hz) of black screen after the start of a journey (Capture.Tabi) before giving up waiting for the arrival (safeguard: the game always launches it, well before)
LOADING_COVERED = 0.9                    # opacity (0 to 1) of a fade plane from which the screen is "covered": a map load that arrives then is shown only once the scene is in place (State.loading)
LOADING_MIN, LOADING_PLACEMENT, LOADING_MAX = 1, 2, 6      # engine frames after packet 0: at least 1 (the engine places the camera and characters on the next frame, on 529 maps), 2 at most to wait for the visible characters' positions, 6: safeguard (never a longer wait)
LOAD_WAIT_MAX = 240                    # frames (30 Hz) of black screen before giving up waiting for the battle scene to load
BATTLE_ENTRY_WINDOW = 12                  # frames after a battle scene loads (packet 0, bit 8) during which a fade launched by the engine is the battle arrival fade (State.battle_transition)
BATTLE_RETURN_WINDOW = 12                  # frames after leaving the battle part during which a fade launched by the engine is the fade back to the map
TRANSITION_GUARD = 8                        # frames during which the battle transition stays "in progress" after one of its fades ends (the engine changes scene 1 to 3 frames later, then launches the next fade)
LIB_APK = 'lib/arm64-v8a/libdq4core.so'
EXIT_COUNTDOWN = 0x258254                  # library byte read by Global::NativeExec: countdown (in frames) of the exit sound effect; startTown, startField, ChangeGamePart, startFirstTown and startDebugTown arm it to 15 when the game leaves a town or the world map,
                                            # NativeExec decrements it every frame and, at 0, calls TownSystem::playTownExitSE / FieldSystem::playFieldExitSE
                                            # (sound effect 305: only if the old scene is still alive, its byte 0 = 1); see Engine._exit_countdown

# keys (mask sent to GameUpdate): up, down, left, right checked; A/B to be confirmed
UP, DOWN, LEFT, RIGHT, A, B = 0x1, 0x2, 0x4, 0x8, 0x10, 0x20
SCROLL_MANUAL = 4                       # OptionStatus.battleSpeed 4: battle messages turned by hand (BattleAutoFeed: -1)
CAM_G, CAM_D = 0x10, 0x20                  # on a town field, bits 4 and 5 of the held keys are not A / B but the game's camera buttons (window::NormalControl::checkCamera reads (Global + 0xe0) >> 4 & 3): 1 turns left,
                                           # 2 right, 3 (both) returns the camera to north; the engine itself applies limits, locks and scenes (TownPlayerManager::setCameraRot)
                                           # and rotates the walking directions and the sprite rows
CAM_STEP = 360.0 * 0x200 / 65536.0          # degrees of a game camera rotation (TownCamera::rotateL / rotateR: 0x200 out of 65536 per turn), one per engine step while the button is held: 84.4 degrees per second
ROT_CAM_RIGHT, ROT_CAM_LEFT, ROT_CAM_NORTH, ROT_CAM_FINISHED = 1, 2, 3, 4      # CAMERA_ROT_TYPE: TownPlayerManager + 0x698 (requested rotation, waiting for the next setCameraRot); 3 / 4 = return to north in progress / finished
OBJ_MESSAGE = 0x252330                     # SDrawCTRL object (message text canvas) in the library
CANVAS_L, CANVAS_H = 512, 512            # texture of Unity's message canvas (MenuMessage: Texture2D(512, 512)); the engine writes to it in a loop
SHORTS_STACK = 4096                         # actual size allocated for the message queue (Unity announces 1089)
MSG_ACTIVE, MSG_STATE, MSG_CURRENT, MSG_END, MSG_SPEED = 0x25238e, 0x25238c, 0x2523cc, 0x2523ce, 0x2523b0      # ui_MsgLoop: message open (byte), state (1 reading a code, 2 writing the letters, 3 / 5 waiting for a key), index of the current letter and of the end of line, letters per frame / 4 of the window type
MSG_PAUSE = 6                            # ui_MsgLoop state between two pages while the engine waits before the next one (measured: 90 frames after a level-up jingle, before "X passe au niveau N !")
UI_MSGLOOP_WRITE = 0x128                # ui_MsgLoop + 0x128: `sxth w20, w8` after `lsl w8, w8,` (state 2: number of letters written in this frame)
SXTH_W20_W8 = 0x13003d14
BATTLE_MANUAL = 4                          # OptionStatus.battleSpeed: 0 to 3 = wait of 12 / 22 / 32 / 42 frames between two battle messages (BattleAutoFeed::setMessageSpeed), 4 = no automatic advance
FADE_FLAG, PLAYER_LOCKED_FLAG = 0x1, 0x4        # Global.Flag (shared state word, Engine.flags): a fade is in progress; the game has locked the player (event, scene: Global.PLAYER_LOCK)
ENCOUNT_BREW_END = 0x1c0                   # Encount::brew() + 0x1c0: `mov x0, x19`, start of the common tail (the random group is complete in Encount + 0x34 (4 monster numbers) and + 0x44 (4 counts))
ENCOUNT_BREW_RET = 0x200                   # ... and the `ret` that closes the function
MOV_X0_X19, RET = 0xaa1303e0, 0xd65f03c0
ENCOUNT_MONSTERS, ENCOUNT_COUNTS = 0x34, 0x44
HAVESTATUS_LEVELUP_END = 0x3f8             # status::HaveStatus::levelup(bool) + 0x3f8: `tbz w20,, ...` (w20 = the argument; true: the character regains all their HP and MP, their max HP/max MP having just been recalculated)
MENU_MANAGER, OPENED_MENUS, MENU_GIFT_EXP, MENU_GIFT_EXP_STATE, MENU_GIFT_EXP_WAIT = 0x252078, 8, 0x24c730, 0x30, 2      # MenuManager: pointer to the manager (at +8, up to 8 open menus, one pointer each); gMaterielMenu_EXTRA_PRESENT_EXP (experience gift): state at +0x30, 2 = last wait (see awaits_touch)
TBZ_W20_0 = 0x36000094
RET_A64 = 0xd65f03c0
PLAYTIME_MOV_W1, PLAYTIME_BL, PLAYTIME_STUB, PLAYTIME_GOT, MOV_W1_2 = 0x14, 0x20, 0x227d90, 0x240968, 0x52800041
PLAYTIME_STUB_WORDS = (0xb00000d0, 0xf944b611, 0x9125a210, 0xd61f0220)      # the 4 instructions of the PLT stub 0x227d90
# Global::NativeExec + 0x14: `mov w1,`; + 0x20: `bl GameStatus::addPlayTime` (via the PLT stub 0x227d90: x0 = status::g_Game, w1 = 2, void):
# once per engine step, +2 units (1/60 s) of play time
MAGIC_CHARSELECT_BL, MAGIC_WITHOUT_TARGET_BL, MAGIC_EXECUSE_STUB = 0x428, 0x188, 0x2269c0      # TownMenu_MAGIC_CHARSELECT::menuUpdate + 0x428 and TownMenu_MAGIC_ROOT::useMagicNoTarget + 0x188: `bl UseAction::execUse` (via the PLT stub 0x2269c0) of the field Magic menu
MAGIC_MP, MAGIC_RESULT, MAGIC_ACTION = 0x7e, 0x210, 0x1d8        # PlayerStatus + 0x7e: current MP; UseActionParam + 0x210: list of result messages (ends with 0), + 0x1d8: action number
MAGIC_HEAL_SOUND, SUB_W8_W8_C4 = 0x100, 0x51031108          # TownMenu_MAGIC_CHARSELECT::menuUpdate + 0x100: `sub w8, w8, #0xc4` (w8 = action number; if the result is <= 2, it is a healing spell and the engine plays sound effect 501, `playSe(0x1f5)`, whatever its effect)
MAGIC_TARGET_COUNT, MAGIC_LOOP_END = 0x257f84, 0x2e0       # gTownMenuItemUseManager + 0xaa: number of targets whose result the engine displays (and for which it plays the healing sound effect, once each); useMagicNoTarget + 0x2e0: exit of this loop
MSG_NOTHING_HAPPENS = 0xc3d6b             # identifier of the engine message "Mais rien ne se passe." (failure field of the action table: Resurrection, Antipoison, Sifflet...); serves as an engine version marker (action 201): it is no longer displayed by the no-effect spells rule
MSG_NOTHING_OCCURS = 0xc3d6d          # identifier of the engine message "Mais il ne se passe rien." (the one Evac' puts in param + MAGIC_RESULT outside a dungeon; measured: field 5 of the action table gives 0xaae7e for action 204, but it is not the displayed message): official text displayed by the "spell that costs MP with no effect" rule
MESSAGE_BUFFER = 0x2582c0                      # g_current_fld+0x50 : pointer to GameUpdate's input buffer (c.inp), the list of Unity -> engine messages: 0 = camera, 1 = end of animation, terminated by a negative integer (GameUpdate resets it to -1 on exit)
STAFF_TEX = (1, 2)                          # identifiers given to the engine for the end credits' two textures (what Texture2D.GetNativeTexturePtr returns in Unity: any distinct numbers other than 0)
STAFF_SIZE = 512                            # side of those textures (the engine reads it from the first integer of the message)
ANIM_DURATION = 18                            # frames (30 Hz) before telling the engine that an object animation (door...) is finished
ORIGIN_AFTER = 3                            # frames after its creation after which an animated character without a position is placed at the origin (see State.apply, packet 13)


class Silent:
    def __init__(self): self.lines = []
    def __call__(self, *a):
        self.lines.append(' '.join(str(x) for x in a)); del self.lines[:-200]


class GameCore(T.Core):
    """Core + saves: reads from a real folder, persistent writes (never into the originals)."""
    read_folder = None
    write_folder = None

    def h_fopen(self, path, mode, *a):
        p = self.read_cstr(path).decode('latin-1'); m = self.read_cstr(mode).decode()
        mm = re.search(r'(data\d+\.dat)$', p)
        if mm and os.environ.get('DQ_SAVEDBG'): print('fopen %s mode %s' % (p, m), flush=True)           # (test) when the engine opens a save file
        if mm:
            name_str = mm.group(1)
            if 'w' in m or 'a' in m:
                r = super().h_fopen(path, mode, *a)
                if r: self.files[r]['persist'] = os.path.join(self.write_folder, name_str)
                return r
            for d in (self.write_folder, self.read_folder):
                if d and os.path.exists(os.path.join(d, name_str)):
                    self.real_files[p] = os.path.join(d, name_str); break
        return super().h_fopen(path, mode, *a)

    write_failures = None                    # save files the engine could not write (list of sentences, read and emptied by the window: small message + log)
    written_saves = None                     # adventure logs written since the history last looked (numbers 1..9: data<n>.dat), read and emptied by History

    atomic_write = staticmethod(atomic_write)                  # (persistence/write_dir.py: shared with the save import)

    read_only = False                        # a battle replay is being played: the engine's save files are not written (a replay must not change the real game)

    def h_fclose(self, h, *a):
        f = self.files.get(h)
        if f and f.get('persist') and not self.read_only:
            ex = self.atomic_write(f['persist'], bytes(f['d']))
            mm = re.search(r'data(\d+)\.dat$', f['persist'])
            if ex is None and mm:
                if self.written_saves is None: self.written_saves = []
                self.written_saves.append(int(mm.group(1)))
            if ex is not None:                # the engine continues (it thinks it wrote, as before): the window warns the player
                if self.write_failures is None: self.write_failures = []
                self.write_failures.append('%s : %r' % (os.path.basename(f['persist']), ex))
        return super().h_fclose(h, *a)


class State:
    """What Unity would know on screen: decoding of the engine's packets."""
    fade_speed = 1.0                        # fades to black last 1 / fade_speed of their original duration: FIXED at 1 (game duration), no longer a player setting (tests vary it)
    sepia = False                              # packet 1 (cmd_map_effect_sepia: FldObject.calculateExecSepia): the town scenery switches to the `Custom/fld_*_sepia` shaders (flashbacks) until the next map load; class attribute: a savestate recorded does not have this attribute
    field_scale = 1.0                        # packet 30, integer < 0: Field.SetScale(scale): the world map's orthographic camera sees scale x more of the field (balloon: 1.0 to 1.25, sent again every frame by FieldData::setOffset); class attribute: a savestate recorded does not have this attribute
    screen_effect = None                         # packet 34, values 3 (journey), 5 (lamp), 6 (Riremito): Capture class effect in progress {'n': frames elapsed, 'duration': engine frames, 'frames': original MoveNext calls, 'kind', 'inverse', 'morning'} (see Engine._start_screen_effect); class attribute: a savestate recorded does not have this attribute
    black_screen = None                          # end of a journey's departure (Capture.Tabi: both layers go to alpha 0, the game camera stays cut off): {'n': frames elapsed} as long as the screen stays black, until the end of the arrival (see Engine._screen_effect)
    floats = ()                             # packet 30, integer >= 0: Field.SetFloatingObject(slot): this character's panel (the balloon: slot 12) is enlarged by `field_scale` (Field.FloatingObject.SetScale), so it keeps its on-screen size when the field is seen from farther away; its shadow is not touched
    def __init__(self):
        self.game_map = None; self.cam_pos = None; self.cam_target = None; self.cam_rot = None
        self.symbols = {}                            # world map: icons (packet 29) idx -> {genre, x, y (top-left corner in px), alpha, visible}
        self.models = {}; self.meshes = {}       # battle: slot -> model id (texture m<id>); slot -> dynamic mesh (packet 22)
        self.mesh_state = {}                           # battle: slot -> {'shader', 'vis', 'col', 'off'} (packets 21, 23, 24, 25, 26: MeshChara on the Unity side)
        self.cam_near = None; self.cam_far = None; self.cam_yoff = None; self.cam_free = False; self.cam_down = None      # packet 11: near, far, yOffset (None = Global.CameraInitParams values), free camera (no target), lookDownAdjust (None = 0.2 from SceneCamera's .cctor)
        self.cam_fov = None                           # packet 11 (camera_sub): nominal field of view in degrees (Unity multiplies it by 4/3, SceneCamera.Update); None = battle value (48)
        self.pad_blink = False                     # packet 19 with a slot >= 16 (TouchPad.SetPadBlink): the game makes the central disc of the D-pad blink (orange ball and halo) as long as an action is possible / awaited; icon number < 0 = end
        self.icons = {}                              # packets 19/20 (Riseup): slot (0..15) -> {'id' (32 x 32 cell of the MenuTexture sheet), 'pos', 'alpha'}: "!" bubble above a character
        self.sprites = {}; self.loaded_maps = 0; self.object_cmds = []; self.background = (0.0, 0.0, 0.0); self.top_background = None; self.bottom_background = None       # background: average of the two tints of packet 8; top_background / bottom_background: tints of the top and bottom of the screen (BackColor, gradient; None = no packet 8); object_cmds: orders on map objects (packets 2 to 5 and 7), emptied by the window: (kind, object, values...)
        self.part = 0; self.field = None        # game part (0xc town, 0xe world map); world map: tiles to display
        self.meshes_seen = set()                # battle: slots whose mesh (packet 22) arrived in THIS frame: Unity draws in immediate mode, no packet = nothing on screen (blinking of a hit received, defeated monster)
        self.fade = self._fade_plane(); self.background_fade = self._fade_plane()      # Fade.FadePlane: current opacity, target opacity, step per frame, remaining frames, color, frames spent fully black. TWO planes (Fade.l_fade, bit 14 of packet 9's integer = Fade.l_targetLayer): 0 = "FadeForMenu" (shader Custom/FrontFade, Overlay queue: in front of everything, windows and messages included); 1 = "FadeForBG" (Custom/BackFade, Background queue: in front of the scene, behind the windows)
        self.sounds = []; self.music = None       # packets 35/36/37: pending sound orders (type, value), emptied by the window every frame; last requested music (None = stop)
        self.effect = None                         # battle start screen effect in progress: {'n': frames elapsed} (the engine waits for it to end, see Engine._battle_effect)
        self.loading = None                    # map load (packet 0) while the screen is covered by a fade: {'n': engine frames since packet 0, 'cam': packet 10 received since} as long as the scene is not in place; the window then draws only the fade (see update_loading)
        self.fade_ratio = (-99, 1.0)             # last fade to black launched by the engine: (engine frame, played duration / original duration); 1.0 = game duration (see Engine._exit_countdown)
        self.entry_window = 0; self.return_window = 0; self.transition_guard = 0      # battle transition (see battle_transition): remaining frames of the "battle arrival" window, of the "return to the map" window, of the guard between two fades
        self.load_wait = None                # {'base': number of scene loads already seen, 'n': frames waited}: black screen until the battle scene has arrived
        self.world = None                         # entire world map read from the engine: {'ids': tiles (H x L) after animation, 'l', 'h'}; None outside the world map
        self.tint = (1.0, 1.0, 1.0)             # packet 33 (cmd_map_color_rate): scenery tint (FldObject.m_color, or Field.SetColor on the world map): multiplies the color of each scenery material (except "tz_" textures: lamps, candles, waves); 1, 1, 1 = neutral
        self.sleeping_height = 0.0                          # packet 17 (Chara.SetSleepNear): body height of lying characters (Y component of s_lieOffset, static of Chara: it survives map changes); 0 as long as the engine has sent nothing
        self.fbx = {}; self.image = 0             # animated 3D models (packets 31 / 32: the title dragon): slot -> {'id', 'vis', 'pos', 'rot', 'scl', 'col', 'anim': [(engine frame, sequence number, force)]}; frame: number of the current engine step (filled in by Engine.step)

    @staticmethod
    def _fade_plane(): return {'a': 0.0, 'end': 0.0, 'step': 0.0, 'n': 0, 'col': (0.0, 0.0, 0.0), 'black': 0, 'battle': False}      # 'battle': battle transition fade (game duration, see battle_transition)

    def __setstate__(self, d):                  # states recorded before the two fade planes (and before the switch to English: see OLD_ATTRIBUTES)
        self.__dict__.update(_renamed_dict_keys(_renamed_attributes(d))); self.__dict__.setdefault('background_fade', self._fade_plane()); self.__dict__.setdefault('fbx', {}); self.__dict__.setdefault('image', 0); self.__dict__.setdefault('tint', (1.0, 1.0, 1.0)); self.__dict__.setdefault('loading', None); self.__dict__.setdefault('sleeping_height', 0.0); self.__dict__.setdefault('top_background', None); self.__dict__.setdefault('bottom_background', None)
        self.__dict__.setdefault('entry_window', 0); self.__dict__.setdefault('return_window', 0); self.__dict__.setdefault('transition_guard', 0); self.__dict__.setdefault('fade_ratio', (-99, 1.0))

    def fade_in_progress(self): return self.fade['n'] >= 1 or self.background_fade['n'] >= 1      # Fade.FadePlane.CheckFade: remaining frames > 0 on one of the two planes

    def battle_transition(self):
        """Is the game in a battle transition: start screen effect (the "cascade"), black screen waiting for the scene, battle arrival and exit fades, fade back to the map (and the 1 to 3 frames
        between two of these fades)? its duration in frames follows "Transition speed" (State._fade, Engine._start_battle_effect) like any fade; its clock stays the game's for the cascade and, on the return to the
        map, while the player is locked or between two fades (Game._speed_factor: as soon as the player is free, accelerated walking and the accelerator take effect), whereas "Battle speed" acts from the end of the cascade (black screen, arrival fade, messages) up to and including the end fade."""
        return (self.effect is not None or self.load_wait is not None or self.transition_guard > 0
                or (self.fade['n'] >= 1 and bool(self.fade.get('battle'))) or (self.background_fade['n'] >= 1 and bool(self.background_fade.get('battle'))))

    def tick_transition(self):
        """One game frame (after tick_fade): the windows and the battle transition guard run down."""
        if self.entry_window > 0: self.entry_window -= 1
        if self.return_window > 0: self.return_window -= 1
        if self.transition_guard > 0: self.transition_guard -= 1

    def apply(self, packets, read_name):
        self.meshes_seen = set()
        covered = max(self.fade['a'], self.background_fade['a']) >= LOADING_COVERED; do_load = False; cam_view = False      # screen already covered by a fade at the time of the map load?
        for t, a, f in packets:
            if t == 0:
                do_load = True; cam_view = False
                if a and a[0] & 0x100: self.entry_window = BATTLE_ENTRY_WINDOW          # battle scene (cmd_fld_load, bit 8): the fade launched right after is the battle arrival fade
                self.game_map = read_name(); self.loaded_maps += 1; self.sprites.clear(); self.background = (0.0, 0.0, 0.0); self.top_background = self.bottom_background = None; self.models.clear(); self.meshes.clear(); self.mesh_state.clear(); self.object_cmds = [('map',)]; self.cam_rot = None; self.cam_fov = None; self.cam_near = None; self.cam_far = None; self.cam_yoff = None; self.cam_free = False; self.symbols.clear(); self.icons.clear(); self.fbx.clear(); self.tint = (1.0, 1.0, 1.0); self.field_scale = 1.0; self.floats = (); self.sepia = False      # new map: fresh FldObject, white m_color (FldObject.init_fld); the engine sends the map tint again after packet 0
            elif t == 1: self.sepia = True           # cmd_fld_color (D12C98) = cmd_map_effect_sepia: no argument; FldObject.calculateExecSepia (CDD9E0) replaces the shader of each scenery material with "<name>_sepia" (not the characters')
            elif t == 8 and len(f) >= 6:
                self.background = tuple((f[i] + f[i + 3]) / 2 for i in range(3))     # clear color: average of the two tints (fallback, off-screen rendering); the background itself is a vertical gradient
                self.top_background = tuple(float(f[i]) for i in range(3)); self.bottom_background = tuple(float(f[i + 3]) for i in range(3))      # cmd_back_color (RVA 0xD14F44): 6 floats -> BackColor.SetColor(top, bottom, 0) (0xCC43F8): top = vertices 0 and 1 of the full screen quadrilateral, bottom = vertices 2 and 3
            elif t == 33 and len(f) >= 3:           # cmd_map_color_rate (D14E44): r, g, b; FldObject.m_color = (r, g, b, 1) (town and battle scenery: FldObject.update_material_color, every frame, Material.color = _OrgColor (1, 1, 1, alpha) x m_color, except materials whose texture has "tz_" in its name); on the world map: Field.SetColor (tiles and symbols)
                self.tint = (float(f[0]), float(f[1]), float(f[2]))
            elif t == 27:                           # cmd_field_load: Field.Init, fresh material (white color); the engine sends the world map tint afterwards
                self.tint = (1.0, 1.0, 1.0); self.field_scale = 1.0; self.floats = ()          # (Field.Init resets the original camera size; the engine registers the balloon (packet 30, slot 12) right after, on every world map load)
            elif t == 30 and a:                     # cmd_field_scale (D12794): integer >= 0 = Field.SetFloatingObject(Chara of this slot); integer < 0 = Field.SetScale(float)
                if a[0] >= 0:
                    if a[0] not in self.floats: self.floats = self.floats + (a[0],)
                elif f and 0.0 < f[0] < 1e6: self.field_scale = min(max(float(f[0]), FIELD_SCALE[0]), FIELD_SCALE[1])         # (FieldData::setOffset: 1 + offset / 128, offset <= 32: from 1.00 to 1.25)
            elif t == 28 and len(a) >= 4:           # FieldData::drawBlock: 16x16 tile window of the world map (cols x rows) around the camera
                self.field = {'x0': a[0], 'y0': a[1], 'cols': a[2], 'tiles': a[4:4 + a[3]], 'cam': (f[0], f[1]) if len(f) >= 2 else None}
            elif t == 29 and a:                     # FieldData::draw_symbol: idx | genre << 8 + [x, y, alpha]; 0x8000 | idx = hide; 0xc000 | idx = show again
                v = a[0]; i = v & 0xff
                if v & 0xc000 == 0xc000:
                    if i in self.symbols: self.symbols[i]['visible'] = True
                elif v & 0x8000:
                    if i in self.symbols: self.symbols[i]['visible'] = False
                elif len(f) >= 3: self.symbols[i] = {'kind': (v >> 8) & 0x7f, 'x': f[0], 'y': f[1], 'alpha': f[2], 'visible': True}
            elif t == 12 and len(a) >= 2:
                if a[1] >= 0: self.sprites[a[0]] = {'id': a[1], 'pos': None, 'col': (1, 1, 1, 1), 'pose': 0, 'dir': 0, 'visible': True, 'scale': 1.0, 'created': self.image}
                else: self.sprites.pop(a[0], None)
            elif t == 14 and len(a) >= 2:           # cmd_chara_on_off: Chara.SetVisible(value != 0) = Renderer.enabled of the character (and its shadow)
                if a[0] in self.sprites: self.sprites[a[0]]['visible'] = a[1] != 0
            elif t == 16 and a:                     # cmd_chara_sleep_pose (D132FC): character = v & 0xff; bits 8-9: Chara.SetSleepPose(bit 8); bit 10: Chara.SetSleepDir(v >> 12) (see lying_pose.py)
                v = a[0]; s = self.sprites.get(v & 0xff)
                if s is not None:
                    if v & 0x300:
                        s['sleeping'] = bool(v & 0x100)
                        if s['sleeping']: s['sleeping_rot'] = (0.0, 0)          # SetSleepPose(true): quadrant 0, identity rotation (the direction follows in the same packet)
                    if v & 0x400: s['sleeping_rot'] = PC.packet_direction(v)
            elif t == 17 and len(a) >= 2:           # cmd_chara_sleep_near (D133E4): (defNear, offset); Chara.SetSleepNear: height of the lying body
                self.sleeping_height = PC.packet_height(a[1])
            elif t == 18 and a:                     # cmd_chara_pose (D13474): v = character | number << 8: Chara.SetTexture(number) = the character changes sprite sheet (TownCharacterDraw::changePose)
                s = self.sprites.get(a[0] & 0xff)
                if s is not None and (a[0] >> 8) >= 0: s['id'] = (a[0] >> 8) | (s['id'] & 4096)
            elif t == 15 and a:                     # cmd_chara_shadow (D13150): character = v & 0xff; bits 8-9: shadow visible (bit 8); bits 10-11: separate shadow (bit 10); bit 12: shadow position (3 floats,
                v = a[0]; s = self.sprites.get(v & 0xff)        # SetShadowPosition); bit 13: opacity (SetShadowAlpha); bit 14: shadow position on the world map (SetFieldShadowPosition)
                if s is not None:
                    fl = list(f)
                    if v & 0x300: s['shadow'] = bool(v & 0x100)
                    if v & 0xc00: s['shadow_separate'] = bool(v & 0x400)
                    if v & 0x1000 and len(fl) >= 3: s['shadow_pos'] = tuple(fl[:3]); fl = fl[3:]
                    if v & 0x2000 and fl: s['shadow_alpha'] = float(fl[0]); fl = fl[1:]
                    if v & 0x4000 and len(fl) >= 3: s['shadow_field'] = tuple(fl[:3])          # SetFieldShadowPosition: (x, y, height) in map pixels; the balloon: 32 pixels (2 tiles) south of its feet
            elif t == 19 and len(a) >= 2 and a[0] >= 16:            # cmd_rise_icon_load with a slot >= 16: not a bubble, the D-pad blinking (TouchPad.SetPadBlink); number < 0 = stop
                self.pad_blink = a[1] >= 0
            elif t == 19 and len(a) >= 2 and 0 <= a[0] < 16:        # cmd_rise_icon_load: slot, icon number (< 0 = release); Riseup object, Custom/Riseup material on the MenuTexture sheet
                if a[1] >= 0: self.icons[a[0]] = {'id': a[1], 'pos': None, 'alpha': 1.0}
                else: self.icons.pop(a[0], None)
            elif t == 20 and a and len(f) >= 4:     # cmd_rise_icon: slot; x, y, z (SetPosition) then alpha (Material.color = 1, 1, 1, alpha)
                ic = self.icons.get(a[0])
                if ic is not None: ic['pos'] = tuple(f[:3]); ic['alpha'] = f[3]
            elif t == 9 and a:                      # cmd_fade: duration in frames = v & 0x7ff; bit 12: fade out to a color (otherwise fade in); bit 11: color r, g, b as floats; bit 13: white (otherwise black); bit 14: background plane "FadeForBG" (behind the windows; otherwise plane "FadeForMenu", in front of everything: see State._fade)
                self._fade(a[0], f)
            elif t == 5 and a:                      # cmd_fld_common_anim: object = v & 0xffff, common animation number = v >> 16 (FldObject.SetCommonAnimation)
                self.object_cmds.append(('anim', a[0] & 0xffff, (a[0] >> 16) & 0xffff))
            elif t == 6 and a and 0 <= a[0] < 0x1000:   # cmd_fld_event_anim: event animation number (FEAN, FldObject.SetEventAnimation); >= 0x1000: SetCameraNo(v & 0x3fff), no visible effect (scene cameras come from packets 10 and 11)
                self.object_cmds.append(('event', a[0]))
            elif t == 7 and a:                      # cmd_fld_on_off: object = v & 0xffff, flag = v >> 16 (SetMapObjOnOff: non-zero flag = object hidden)
                self.object_cmds.append(('onoff', a[0] & 0xffff, (a[0] >> 16) & 0xffff))
            elif t == 2 and a:                      # cmd_fld_alpha: object = v & 0xffff, level (0..31) = v >> 16 & 0xff (SetMapObjAlpha: opacity = level / 31)
                self.object_cmds.append(('alpha', a[0] & 0xffff, (a[0] >> 16) & 0xff))
            elif t == 3 and a and len(f) >= 3:      # cmd_fld_pos: object; x, y, z
                self.object_cmds.append(('pos', a[0] & 0xffff, tuple(f[:3])))
            elif t == 4 and a and len(f) >= 2:      # cmd_fld_rot: object; rotation x, y (z = 0)
                self.object_cmds.append(('rot', a[0] & 0xffff, tuple(f[:2])))
            elif t == 10 and a:
                if do_load: cam_view = True
                elif self.loading is not None: self.loading['cam'] = True
                fl = list(f)
                if a[0] & 1 and len(fl) >= 3: self.cam_pos = tuple(fl[:3]); fl = fl[3:]
                if a[0] & 2 and len(fl) >= 3: self.cam_target = tuple(fl[:3]); fl = fl[3:]
                if a[0] & 4 and len(fl) >= 3: self.cam_rot = tuple(fl[:3])        # battle: rotation (pitch, yaw, roll) in degrees
            elif t == 21 and len(a) >= 2:           # DSSAObject::send_unity_load(slot, model id); id < 0 = release
                if a[1] >= 0:
                    self.models[a[0]] = a[1]
                    self.mesh_state[a[0]] = {'shader': 3 if a[1] > 999 else 1, 'visible': True, 'col': (1.0, 1.0, 1.0), 'off': (0.0, 0.0)}      # MeshChara..ctor: shader 1 (DssaMonster0) except id > 999 (DssaCharaTransparent); white color
                else: self.models.pop(a[0], None); self.meshes.pop(a[0], None); self.mesh_state.pop(a[0], None)
            elif t == 31 and len(a) >= 2:           # cmd_fbx_load: slot, model number ("fbx/c<number>", FbxObject); < 0 = release. The model is created hidden, scale 1, and turned by Euler(0, 180, 0): NativeManager.cmd_fbx_load ends with FbxObject.SetRotation(0, 180, 0) (0xD13610). A packet 32 with bit 14 replaces that rotation (the title dragon); the battle spells never send one, so they are seen from that side
                if a[1] >= 0: self.fbx[a[0]] = {'id': a[1], 'visible': False, 'pos': (0.0, 0.0, 0.0), 'rot': (0.0, 180.0, 0.0), 'scl': (1.0, 1.0, 1.0), 'col': (1.0, 1.0, 1.0, 1.0), 'anim': []}
                else: self.fbx.pop(a[0], None)
            elif t == 32 and a:                     # cmd_fbx: slot = v & 0xff; bits 8-9: visibility (bit 8 = visible); 10: force the animation; 11: scale (3 floats); 12: color (4); 13: position (3); 14: rotation, degrees (3); 15: animation (one integer: sequence)
                v = a[0]; m = self.fbx.get(v & 0xff); fl = list(f)
                if FBXLOG: print('FBX frame %d packet 32: v=%#x ints=%s floats=%s' % (self.image, v & 0xffff, list(a[1:]), [round(x, 4) for x in fl]), flush=True)         # (test) DQ_FBXLOG=1: all packets 32 (position, rotation, scale, color, sequence)
                if m is not None:
                    if v & 0x300: m['visible'] = bool(v & 0x100)
                    if v & 0x800 and len(fl) >= 3: m['scl'] = tuple(fl[:3]); m['scl_set'] = True; fl = fl[3:]          # (scl_set: until then Unity keeps the prefab's localScale; the window uses it for the screen pictures)
                    if v & 0x1000 and len(fl) >= 4: m['col'] = tuple(fl[:4]); m['col_set'] = True; fl = fl[4:]          # (FbxObject.SetColor: Material.color of all its materials; until then each material keeps its own)
                    if v & 0x2000 and len(fl) >= 3: m['pos'] = tuple(fl[:3]); fl = fl[3:]
                    if v & 0x4000 and len(fl) >= 3: m['rot'] = tuple(fl[:3]); fl = fl[3:]
                    if v & 0x8000 and len(a) >= 2: m['anim'].append((self.image, int(a[1]), bool(v & 0x400)))
            elif t == 23 and len(a) >= 2:           # cmd_mesh_on_off: slot, visible
                if a[0] in self.mesh_state: self.mesh_state[a[0]]['visible'] = bool(a[1])
            elif t == 24 and a:                     # cmd_mesh_shader: slot | shader number << 8 (0 Chara, 1 DssaMonster0, 2 DssaMonster1, 3 DssaCharaTransparent)
                if (a[0] & 0xff) in self.mesh_state: self.mesh_state[a[0] & 0xff]['shader'] = a[0] >> 8
            elif t == 25 and a and len(f) >= 3:     # cmd_mesh_color: slot; r, g, b (Material.color, alpha 1)
                if a[0] in self.mesh_state: self.mesh_state[a[0]]['col'] = tuple(f[:3])
            elif t == 26 and a and len(f) >= 2:     # cmd_mesh_tex_offset: slot; u, v (Material.SetTextureOffset)
                if a[0] in self.mesh_state: self.mesh_state[a[0]]['off'] = tuple(f[:2])
            elif t == 11 and a:        # cmd_camera_sub: bit 0 near, 1 far, 2 fov, 4 yOffset, 5 lookDownAdjust (one float each, in bit order), 7 free camera (s_targetCamera = false)
                k = 0
                for bit, name_str in ((0, 'cam_near'), (1, 'cam_far'), (2, 'cam_fov'), (4, 'cam_yoff'), (5, 'cam_down')):
                    if a[0] >> bit & 1 and k < len(f):
                        v = f[k]; k += 1
                        setattr(self, name_str, min(max(v, 0.0), 78.0) if name_str == 'cam_fov' else v)       # SceneCamera.SetFOV2: clamped to 78
                if a[0] & 128: self.cam_free = True
            elif t == 22 and len(a) >= 2:           # dynamic mesh: [slot, vertex count, colors (1 byte/vertex, 4 per integer), indices...] + floats [x, y, z, (u, v, x, y, z) * vertex count]
                nv = a[1]; nc = (nv + 3) // 4; idx = a[2 + nc:]
                if len(f) >= 3 + 5 * nv and idx:
                    v = [f[3 + 5 * i:8 + 5 * i] for i in range(nv)]
                    self.meshes[a[0]] = {'pos': tuple(f[:3]), 'v': v, 'idx': list(idx), 'col': list(a[2:2 + nc])}       # col: one byte per quad (4 vertices), 255 = opaque
                    self.meshes_seen.add(a[0])
            elif t in (35, 36, 37) and a:           # cmd_se_play / cmd_se_stop / cmd_bgm (Sound.PlaySE, StopSE, PlayBGM; value >= 4096 = StopBGM)
                self.sounds.append((t, a[0]))
                if t == 37: self.music = a[0] if 0 <= a[0] < 4096 else None
            elif t == 13 and a:
                fl = list(f); flags = a[0]; s = self.sprites.get(flags & 0x7ff)
                if s is None: continue
                if flags & 0x800 and fl:                # cmd_chara (D12EA8): bit 11 = Chara.SetScale(scale): Transform.localScale = 1.8 x scale on the character's panel (not on its shadow)
                    if s['pos'] is not None: s['scale'] = float(fl[0])      # (a character's 1st update, the one that places it, carries a throwaway starting value: 0.0253 to 0.08 then 1.0 in one frame; observed on 529 maps, 1062 characters: ignored)
                    fl = fl[1:]
                if flags & 0x1000: s['col'] = tuple(fl[:4]); fl = fl[4:]
                if flags & 0x2000 or flags & 0x8000: s['pos'] = tuple(fl[:3]); fl = fl[3:]      # 0x8000: same position, world map version (pixels)
                if flags & 0x4000 and len(a) > 1:
                    s['pose'] = a[1] & 0xff; s['dir'] = (a[1] >> 8) & 0xff
                    if s['pos'] is None and self.image - s.get('created', 0) >= ORIGIN_AFTER: s['pos'] = (0.0, 0.0, 0.0)       # the engine only sends a position if it differs from the one it believes is already set (its record of the character: (0, 0, 0)):
                                                                          # an animated character that has not received one after a few frames is at the origin (Chara created at (0, 0, 0) by Unity); mqtf3, mom2f1, msm1f1, slot 8: the NPC
                                                                          # in the middle of the room was not drawn. (The others' positions arrive 1 frame after creation: no one-frame appearance at the origin.)
        if do_load:         # map load: drawing held back (see update_loading) if the screen is covered, either by a fade already there or by the fade-in launched with this load (it restarts from opacity 1)
            if covered or any(fd['a'] >= LOADING_COVERED and fd['end'] == 0.0 and fd['n'] >= 1 for fd in (self.fade, self.background_fade)): self.loading = {'n': -1, 'cam': cam_view}
            else: self.loading = None

    def _fade(self, v, f):
        """Fade.SetFadeIn / SetFadeOutBlack / SetFadeOutWhite / SetFadeOutColor (FadePlane.Command): fade-out = toward opacity 1 from the current opacity;
        fade-in = the plane starts again from opacity 1 toward 0 (Unity starts from the plane's current opacity: the same thing after a completed fade-out). Duration <= 1 frame: immediate."""
        script = bool(v & PJ.SCRIPT_FADE_MARK)                                          # fade launched by a game script command (mark set by Engine._fade_hooks): its duration is the script's
        d = v & 0x7ff; fd = self.background_fade if v & 0x4000 else self.fade; fd['black'] = 0      # bit 14: Fade.l_targetLayer (NativeManager.cmd_fade D14D10), the plane that receives the command
        fd['battle'] = self.part == PART_BATTLE or self.entry_window > 0 or self.return_window > 0        # battle fade (arrival in the scene, exit, return to the map): mark for battle_transition (its duration follows "Transition speed" like any fade to black)
        d0 = d
        if not v & (0x800 | 0x2000): d = PJ.fade_duration(d, State.fade_speed, script)       # shorter fade to black (map change, battle arrival, battle end, return to the map): "Transition speed" setting (not for a script fade)
        self.fade_ratio = (self.image, (d / d0) if d0 > 1 and v & 0x1000 else 1.0)      # shortened fade to black: the engine's exit sound effect countdown follows (Engine._exit_countdown)
        if v & 0x1000:
            fd['col'] = tuple(f[:3]) if v & 0x800 and len(f) >= 3 else ((1.0, 1.0, 1.0) if v & 0x2000 else (0.0, 0.0, 0.0))
            fd['end'] = 1.0
            if d <= 1: fd['a'] = 1.0; fd['n'] = 0; fd['step'] = 0.0
            else: fd['step'] = (1.0 - fd['a']) / d; fd['n'] = d
        else:
            fd['end'] = 0.0
            if d <= 1: fd['a'] = 0.0; fd['n'] = 0; fd['step'] = 0.0
            else: fd['a'] = 1.0; fd['step'] = -1.0 / d; fd['n'] = d

    def sharp_black_fade(self):
        """Fade.SetFadeOutBlack(0) on plane 0 (in front of everything): opaque, black, immediately (end of the lamp and Riremito effects); it stays that way until a fade-in started by the engine."""
        fd = self.fade; fd['black'] = 0; fd['col'] = (0.0, 0.0, 0.0); fd['end'] = 1.0; fd['a'] = 1.0; fd['n'] = 0; fd['step'] = 0.0; fd['battle'] = False

    def current_fade_in(self, frames):
        """Fade.SetFadeIn(frames) on plane 0 (arrival of a trip, Capture.Tabi): from the plane's CURRENT opacity to 0, in `frames` equal steps (FadePlane.Command, IN): no visible effect if the plane is transparent, and
        the "fade in progress" bit of Global.Flag stays raised for `frames` frames (CheckFade), as in the game."""
        fd = self.fade; fd['black'] = 0; fd['end'] = 0.0; fd['step'] = -fd['a'] / frames; fd['n'] = frames

    def update_loading(self):
        """End of the drawing hold after a map load (once per engine frame, after `apply`). The viewer has seen only packet 0 (new scenery) at the load frame: camera of the previous scene,
        characters without a position, no tint and no object orders; the engine sends the camera (packet 10) and the positions (packet 13) on the next frame (59 maps tried, 529 maps counted: always the offset of 1).
        While `loading` exists, the window draws only the fade planes (black of the covered screen) and the fade-ins are suspended (`tick_fade`): the game's fade keeps its full duration, it just starts
        one frame later, on a complete scene. Ready: at least LOADING_MIN frames, camera received, and visible characters all placed (at most LOADING_PLACEMENT waiting frames); safeguard LOADING_MAX."""
        ch = self.loading
        if ch is None: return
        ch['n'] += 1                                                       # engine frames since the load (0 at the load frame: own count, no frame difference: a loaded state can reset the frame counter to zero)
        places = all(sp['pos'] is not None for sp in self.sprites.values() if sp.get('visible', True))
        world = self.part != PART_FIELD or self.field is not None      # world map: also wait for its tiles (packet 28)
        if ch['n'] >= LOADING_MAX or (ch['n'] >= LOADING_MIN and world and ch['cam'] and (places or ch['n'] >= LOADING_PLACEMENT)): self.loading = None

    def tick_fade(self):
        """FadePlane.Update: once per game frame, for each of the two planes. Safeguard (front plane only): a screen that stays fully black for more than 6 s (fade-in started by Unity itself, not by the engine) is reopened;
        the background plane has none: the engine keeps it black by itself (chapter title, 160 frames) and reopens it with a command."""
        for fd, guard in ((self.fade, True), (self.background_fade, False)):
            if self.loading is not None and fd['end'] == 0.0 and fd['n'] >= 1: continue      # drawing held back after a load: a fade-in only starts with the scene in place
            if fd['n'] >= 1:
                fd['n'] -= 1
                if fd['n'] < 1:
                    fd['a'] = fd['end']
                    if fd.get('battle') and fd['end'] >= 1.0: self.transition_guard = TRANSITION_GUARD      # battle black exit finished: the engine changes scene within 1 to 3 frames, then launches the fade-in; the clock must not change between the two
                else: fd['a'] += fd['step']
            if guard and fd['a'] >= 0.999 and fd['n'] < 1:
                fd['black'] += 1
                if fd['black'] > 180: fd['end'] = 0.0; fd['step'] = -1.0 / 15; fd['n'] = 15; fd['black'] = 0
            else: fd['black'] = 0


DBG = bool(os.environ.get('DQ_UIDBG'))


class Interface:
    """What the Unity interface remembers of the engine's messages: one window per port (list of texts, cursor, open or not).
    Messages of a port (after the first byte = number of arguments): [1,..] opens; [7,0] closes; [11,line,column] announces
    that the port's next message is the text of that cell; [4,i] cursor on line i; [12,line,x] and [10,..] settings."""
    def __setstate__(self, state): self.__dict__.update(_renamed_interface_keys(_renamed_attributes(state)))

    staff = None               # end credits (port of category 3, Unity's StaffrollPort): {'port', 'live', 'visible', 'offset', 'ready', 'float_next'}; None before the first (old savestates have no such attribute)

    def __init__(self):
        self.f = {}; self.waiting = {}; self.order = 0
        self.msg = {'type': 0, 'y': 0, 'feed': False, 'shake': 0, 'speaker': '', 'speaker_pending': False}      # message window (port 1): window type, canvas scroll, end-of-page cursor, speaker name ("qui"); qui_att: the next packet on the port carries this name
        self.damage = []           # damage numbers to make hop on the monsters: (monster, height, damage), emptied by the viewer
        self.system = []          # port 0 messages addressed to the host: (code, arguments...); 999 = quit (MenuPortSendQuit), 6 = portal, 4 / 5 = volumes, 7 = name size, 8 = gamepad
        self.obs = None            # optional observer (viewer): open_menu(port, type), shutdown(port), param_int/param_str/code/selection

    def win(self, port):
        if port not in self.f: self.f[port] = {'cells': {}, 'visible': False, 'cur': 0, 'order': 0, 'indicators': {}, 'type': None, 'act': False, 'req': False, 'draw': False, 'force': False, 'ign': False, 'sv': True}
        return self.f[port]

    def apply(self, entries):
        if DBG:
            for port, a in entries:
                if port in (0, 1) or port >= 12: print('MSG frame %s port %d %s' % (getattr(self, 'image', '?'), port, a[:10]), flush=True)
        for port, a in entries:
            st = self.staff
            if st is not None and st['live'] and port == st['port']:                         # StaffrollPort.NoticeReceive: [1] then a float (two shorts, low one first) = the offset of the two textures' V coordinate (+1/256 per frame = 2 pixels)
                if len(a) == 1 and a[0] == 1: st['float_next'] = True
                elif len(a) == 2 and st['float_next']: st['float_next'] = False; st['offset'] = struct.unpack('<f', struct.pack('<HH', a[0] & 0xffff, a[1] & 0xffff))[0]
                continue
            if port == 1:                                       # message window: drawn from the engine's canvas; MenuMessage.NoticeReceive: 0 type, 1 cursor, 2 shake, 3 scroll, 4 speaker name
                if self.msg['speaker_pending']:                         # [4, 1] announced a name: the next packet on the port is its text (one integer per character, like the menu cell texts)
                    self.msg['speaker_pending'] = False; self.msg['speaker'] = ''.join(chr(v & 0xffff) for v in a if v).strip()
                    continue
                if len(a) >= 2:
                    c, v = a[0], a[1]
                    if c == 0: self.msg['type'] = v
                    elif c == 1: self.msg['feed'] = (v & 0xffff) == 1
                    elif c == 3: self.msg['y'] = v
                    elif c == 4:                                # [4, 0]: no name (frame without tab); [4, 1]: the name follows (frame with tab, only for the field window: MenuMessage.NoticeReceive, command 4)
                        if (v & 0xffff) != 0: self.msg['speaker_pending'] = True
                        else: self.msg['speaker'] = ''
                continue
            if port == 0:
                if len(a) >= 2 and a[0] == 0: self.system.append(tuple(a[1:]))
                if len(a) >= 2 and 2 <= a[0] < 32:
                    if a[1] == 3:
                        self.win(a[0])['sv'] = bool(a[2]) if len(a) > 2 else True                  # [window, 3, visible]: MenuPort.SetVisible
                        if self.staff is not None and self.staff['port'] == a[0]: self.staff['visible'] = bool(a[2]) if len(a) > 2 else True
                    elif a[1] == 2:                                                                # [window, 2]: closed
                        f = self.win(a[0]); f['act'] = f['visible'] = False; f['closed'] = True          # (the engine's stop messages can set "act" again: "ferme" stays until the next creation)
                        if self.staff is not None and self.staff['port'] == a[0]: self.staff['live'] = self.staff['visible'] = False
                        if self.obs: self.obs.shutdown(a[0])
                    elif a[1] == 1 and len(a) >= 4:                                                # [window, 1, category, type]: creates a menu of the given type (MenuPortItemTable.Make_*)
                        if a[2] == 3: self.staff = {'port': a[0], 'live': True, 'visible': False, 'offset': 0.0, 'ready': False, 'float_next': False}          # category 3 = StaffrollPort (1 = MenuPortItem, 2 = MenuMessage)
                        f = self.win(a[0]); f['type'] = a[3]; f['cells'] = {}; f['indicators'] = {}; f['cur'] = 0; f['ints'] = {}; f['layout'] = None; f['lists'] = {}; f['next_list'] = None
                        f['act'] = f['req'] = f['draw'] = f['force'] = f['ign'] = False; f['sv'] = True; f['visible'] = False; f['pending'] = None; f['plates'] = {}; f['n_codes'] = {}; f['closed'] = False
                        if self.obs: self.obs.open_menu(a[0], a[3])
                continue
            f = self.win(port)
            if f.get('closed'):                                  # MenuPortSystem.internalUpdate (D10A54): [port, 2] destroys the element (`s_ports[port] = null`), the port messages received afterwards (same frame: ports 12 to 31 are read after port 0)
                self.waiting.pop(port, None)                    # no longer have a recipient (`if (item != null) item.NoticeReceive`); before, the end of the log list (5, 6, 4) reopened the closed window for one frame: purple "simple" box
                continue
            if f['type'] == 43:                                 # Make_BattleHoppingNumber: [12, 0, 0] then [monster, height, damage] (BattleMenu_setHoppingNumbers)
                if f.get('damage_pending'):
                    f['damage_pending'] = False
                    if len(a) >= 3: self.damage.append(tuple(a[:3]))
                    continue
                if len(a) >= 3 and a[0] == 12: f['damage_pending'] = True; continue
            if port in self.waiting:                            # text of the announced cell
                lookup_key = self.waiting.pop(port); txt = ''.join(chr(v & 0xffff) for v in a if v); f['cells'][lookup_key] = txt
                if self.obs: self.obs.param_str(port, lookup_key[0], lookup_key[1], txt)
                continue
            if f.get('next_list') is not None:                      # map window (type 25): the list of numbers that follows the engine's codes 3 (discovered places) and 5 (veil) (MenuPort.Receive of the Make_CityMap functions), not a command
                f.setdefault('lists', {})[f['next_list']] = [v & 0xffff for v in a]; f['next_list'] = None
                continue
            if f['type'] == 31 and f.get('pending'):               # monster plate: messages that follow a code > 0 (name, then [x, y, ...])
                i, stage = f['pending']
                if stage == 'name': f['plates'][i]['name'] = ''.join(chr(v & 0xffff) for v in a if v); f['pending'] = (i, 'params')
                else:
                    f['plates'][i]['params'] = list(a); f['pending'] = None
                    if self.obs and hasattr(self.obs, 'plate'): self.obs.plate(port, i, f['plates'][i]['name'], f['plates'][i]['params'], f['plates'][i]['code'])
                continue
            if not a: continue
            cmd = a[0]
            if cmd != 7 and not f['act']: f['act'] = True; f['force'] = True       # MenuPortItem.NoticeReceive: first command -> parts activated, drawing forced
            if cmd == 11 and len(a) >= 3: self.waiting[port] = (a[1], a[2])
            elif cmd == 1:
                if port >= 12: f['cells'] = {}; f['indicators'] = {}; f['cur'] = 0; f['ints'] = {}; f['lists'] = {}; f['next_list'] = None           # dynamic window: fresh content
                self.order += 1; f['order'] = self.order
            elif cmd == 2 and len(a) >= 3: f['grid'] = tuple(a[1:4])                 # setItemMenu: columns, rows, number of cells of the engine's cursor
            elif cmd == 6: f['inp'] = True                                              # input request (every frame while the menu waits for a key)
            elif cmd == 5: f['req'] = True                                             # draw request: the engine resends it every frame as long as the window must be visible
            elif cmd == 7: f['act'] = False                                            # stop: parts deactivated
            elif cmd == 8 and len(a) >= 2: f['ign'] = (a[1] & 0xffff) != 0            # ignore draw requests (always visible)
            elif cmd == 4 and len(a) >= 2:
                f['cur'] = a[1]
                if self.obs: self.obs.selection(port, a[1])
            elif cmd == 10 and len(a) >= 5:                    # setItemParamInt [id, no, low, high]: 32-bit value
                v = (a[3] & 0xffff) | ((a[4] & 0xffff) << 16); v = v - (1 << 32) if v & 0x80000000 else v
                f.setdefault('ints', {})[(a[1], a[2])] = v                                   # kept to replay the window (savestates)
                if self.obs: self.obs.param_int(port, a[1], a[2], v)
            elif cmd == 12 and len(a) >= 3:
                f['indicators'][a[1]] = a[2]; f.setdefault('n_codes', {})[a[1]] = f.get('n_codes', {}).get(a[1], 0) + 1          # number of times each code has arrived (the title: TapToStart.CountReset = code 0 of port 12)
                if f['type'] == 25 and a[1] in (3, 5): f['next_list'] = a[1]               # ICityMap: code 3 = discovered places (x + 256 y, one per number), code 5 = veil (16 numbers: one bit per 10 x 10 pixel unexplored block)
                if f['type'] == 31 and a[1] < 4 and a[2] >= 1:                                  # MonsterNamePlate.ReceiveParameters(code >= 1)
                    f.setdefault('plates', {})[a[1]] = {'code': a[2]}; f['pending'] = (a[1], 'name')
                elif f['type'] == 31 and a[1] == 5:                                             # plate layout (number of plates)
                    f['layout'] = a[2]
                    if self.obs and hasattr(self.obs, 'arrange'): self.obs.arrange(port, a[2])
                elif self.obs: self.obs.code(port, a[1], a[2])

        for f in self.f.values():                              # MenuPortItem.Update: visible as long as the engine requests drawing every frame
            if not f['ign']:
                if f['force']: f['force'] = False; f['draw'] = f['req']
                elif f['draw'] != f['req']: f['draw'] = f['req']
            f['req'] = False; f['input'] = f.get('inp', False); f['inp'] = False
            f['visible'] = f['act'] and f['sv'] and (f['draw'] or f['ign'])

    def visible_ones(self):
        return sorted(((p, f) for p, f in self.f.items() if f['visible'] and f['cells']), key=lambda x: x[1]['order'])


def starts_with_vowel(name):
    """Does this name (UTF-8 bytes, ";" break markers ignored) start with a vowel, accented or not (A, E, I, O, U, Y)? For the French elision of a copy's name."""
    import unicodedata
    t = name.replace(b';', b'').decode('utf-8', 'replace')
    return bool(t) and unicodedata.normalize('NFD', t[0])[0].upper() in 'AEIOUY'


class Engine:
    end_roll = None                          # end of the game started by start_the_end: 'credits' (until isStaffRollEnd), 'the end' (until isEndTheEnd), None
    input_log = None                         # battle being recorded for its replay: one (held, decl, menu messages, scroll_mode, menu that had the input) per step, None = not recording (History starts and stops it)
    _menus_this_step = ()
    ignored_types = ()                       # (window) window types the viewer replaces by its own control (arena "Quit", type 71): they never have the input (active_menu, input_menus)
    hold_messages = False                    # (window) a jingle or the victory fanfare plays in battle: the battle messages wait (write_scroll_mode)
    _hold_saved = None                       # value of the message speed before the hold (-1: an imposed value, given back by scroll_mode)
    _menu_active = None                      # port of the menu that waits for the keys when the first menu message of this step is sent (recorded with the step: the replay sends a choice only to that menu)
    battle_intro = False                     # a battle's entry cascade has just started (set by _start_battle_effect, read and cleared by History: the replay of a battle starts from there)

    def record_inputs(self, on):
        """Starts (True) or stops (False) the recording of the inputs; -> the steps recorded so far (the list is kept by the caller)."""
        log = self.input_log
        self.input_log = [] if on else None; self._menus_this_step = []; self._menu_active = None
        return log

    def __init__(self, apk_folder, read_folder, write_folder, language=1):
        self.log = Silent()
        self.missing_hooks = []               # settings / hooks that the engine of THIS apk did not let install (see _record_missing); the window announces them once (Game._report_missing_hooks)
        lib = zipfile.ZipFile(os.path.join(apk_folder, 'split_config.arm64_v8a.apk')).read(LIB_APK)
        pack = os.path.join(apk_folder, 'split_UnityDataAssetPack.apk')
        self.apk_data = pack
        GameCore.read_folder, GameCore.write_folder = read_folder, write_folder
        c = self.core = GameCore(lib, T.ApkFs([pack]), self.log, real_files={'/dq/assets.apk': pack})
        self.french_texts = self._french_texts(pack)
        self.E = c.export; self.L = c.LIB_BASE
        self._widen_symbols()
        if not c.run_init(): raise RuntimeError('C++ constructors failed')
        c.call(self.E('DevInit'), c.cstr('/dq/assets.apk'), c.cstr('/dq/'), language)
        self.buf1, self.buf2 = c.malloc(0x2000), c.malloc(0x2000)          # interface <-> engine message queues (allocated by the caller)
        c.call(self.E('MenuPortInit'), 32, self.buf1, 129, self.buf2, 1089)
        BUFFER_SIZE = 0x40000
        c.inp, c.outp, c.outf, c.strb = c.malloc(BUFFER_SIZE), c.malloc(BUFFER_SIZE), c.malloc(BUFFER_SIZE), c.malloc(0x10000)
        c.call(self.E('GameInit'), c.inp, c.outp, c.outf, c.strb)
        c.mem_w(self.L + G_IS_AMAZON, b'\x01')              # start menu: no "Sauv. cloud" (Google Play Games / Square Enix server absent on PC); the original removes the same cell for the Amazon version
        self.patch_copy_prefix()
        self.pk = PacketLog(c)
        self.state = State()
        self.msgs_ui = []                        # engine -> interface messages (menus), last frame
        self.ui = Interface()                    # menu windows remembered
        self.frames = 0; self._countdown = 0; self._countdown_armed = -99; self._countdown_done = True      # exit sound effect countdown (see _exit_countdown)
        # map object animations (doors...): the engine waits for Unity to finish them (bit0 of byte +0x14 of the entry)
        self.anims = []                          # [(due frame, object index)]
        self.anim_duration = None                   # (object, number) -> frames before the common animation ends (given by the window, from the map data); None = ANIM_DURATION
        self.fldobj = 0
        self.fbx_clips = None                       # 3D model number -> {clip: {'dur', 'wrap'}} (provided by the window); None in the function = model not yet read; function absent = no known animation (immediate end)
        self._messages_sent = False
        self.fbx_playing = []                       # NativeManager.m_anim_list (3D model animations launched by packet 32): slots, in launch order
        self.msg_visible = False                 # message window displayed? (MenuPort::SetVisible on the message port)
        def _sv(uc, a, sz, u):
            port = uc.reg_read(c.XREG[0]) & 0xffffffffffff
            if port and port == struct.unpack('<Q', c.mem(self.L + OBJ_MESSAGE + 0x30, 8))[0]:
                self.msg_visible = bool(uc.reg_read(c.XREG[1]) & 0xff)
                if not self.msg_visible: self._text_accumulator = 0.0; self.ui.msg['speaker'] = ''; self.ui.msg['speaker_pending'] = False        # MenuMessage.SetVisible(false) clears the name text (m_who)
        hv = c.export('_ZN8MenuPort10SetVisibleEb')
        c.uc.hook_add(unicorn.UC_HOOK_CODE, _sv, None, hv, hv)
        self.fielddata = 0; self._grid = None; self._grid_frame = -999
        self.back_to_title_state = None            # return to title: None, 'requested' (to be launched at the next step) or 'dialog' (the game's Yes / No box is waiting for the answer); see request_return_to_title
        self.request_pause = False               # the player chose "Settings" in the Miscellaneous menu: the viewer opens its Pause menu (see _divert_params)
        self._divert_params()
        def _fd(uc, a, sz, u): self.fielddata = uc.reg_read(c.XREG[0]) & 0xffffffffffff          # FieldData::drawBlock(this): the object that holds the world map
        hfd = c.export('_ZN9FieldData9drawBlockEv')
        c.uc.hook_add(unicorn.UC_HOOK_CODE, _fd, None, hfd, hfd)
        def _sca(uc, a, sz, u): self.fldobj = uc.reg_read(c.XREG[0])
        uc_hook = c.export('_ZN9FLDObject18SetCommonAnimationEii')
        c.uc.hook_add(unicorn.UC_HOOK_CODE, _sca, None, uc_hook, uc_hook)
        self._text_hooks()
        self._fade_hooks()
        self._level_hooks()
        self._forced_monster_hooks()
        self._copy_name_hooks()
        self._game_time_hooks()
        self._magic_hooks()
        self.sensor = Sensor(self)             # dialogue history: hook on TextBuffer::cat (installed before the first frame: Unicorn keeps the blocks already translated)
        self.battle_sensor = BattleSensor.for_(self)       # battle history: read-only hooks (defeated enemies, gold, experience; see battle_history.py)
        if not self.sensor.active: self._record_missing("dialogue history: hook not installed, the history will stay empty")
        if not self.battle_sensor.active: self._record_missing("battle history: hooks not installed, the battle history will stay empty")
        for _ in range(3): self.step(0, 0)       # the title runs for a few frames (cursors initialized)
        self._create_canvas()

    def _flush_tb(self, what):
        """Flushes the blocks already translated by Unicorn after a hook that rewrites code has been placed (`ctl_flush_tb`). Without this flush, a block translated BEFORE the placement keeps running as is and the hook
        has no effect. The call was inside a `try/except: pass`: if a version of Unicorn no longer exposed it, the setting stopped working **silently**. Now it is reported, like any missing hook."""
        try: self.core.uc.ctl_flush_tb()
        except Exception as ex: self._record_missing('%s: ctl_flush_tb unavailable (%s): the setting may have no effect until the engine retranslates this code' % (what, ex))

    def _record_missing(self, text):
        """A setting or a hook could not be installed (different engine instruction: another APK version). The game continues with the original behavior; the line goes to the console and to `missing_hooks`
        (without duplicates: reapply_fixes passes through here again after a savestate is loaded), from there the window notes it in window_errors.log and warns the player with an on-screen message."""
        print(text, flush=True)
        if text not in self.missing_hooks: self.missing_hooks.append(text)

    def _text_hooks(self):
        """Text speed of dialogues and scrolling in battles (player settings, Esc menu).
        - Text: ui_MsgLoop writes, on every engine frame (30 Hz), `speed x 4` letters (speed = word at MSG_SPEED, copy of the window type's array: 1 for dialogues, 100 for battle windows that
          display their line all at once). A hook on `sxth w20, w8` replaces this number with the setting's (`text_speed`, letters per frame, fractions accumulated; 4 = like the game: the hook does nothing).
        - Battles: BattleAutoFeed reads OptionStatus.battleSpeed (g_Option + 5, the game's "Message speed" option, saved in the save file) on every message: `scroll_mode` (None = nothing is touched)
          is written at that address before each frame; a change made by the player in the game's Settings window (setBattleSpeed called from TownMenu_OPERATION_SETTING::menuUpdate) is
          reported to `scroll_callback(value)` (loading a save, for its part, goes through Profile::deliverDATA_PARTY and triggers nothing)."""
        c = self.core
        self.text_speed = 4.0; self._text_accumulator = 0.0
        self.scroll_mode = None; self.scroll_callback = None; self._scroll_origin = None
        try:
            a = c.export('_Z10ui_MsgLoopv')
            if a and struct.unpack('<I', c.mem(a + UI_MSGLOOP_WRITE, 4))[0] == SXTH_W20_W8:        # other engine version: nothing is touched
                def _vt(uc, ad, sz, u):
                    game = uc.reg_read(c.XREG[8]) & 0xffff                                  # letters the engine is about to write (window speed word x 4)
                    v = PJ.letters_per_frame(self.text_speed, game)                      # player setting only while the game is at its standard speed (4); any other value (100 for battle windows, speed set by the game) is the game's own
                    if v == game: return                                                    # game speed: unchanged (also when the setting is "as in the game", 4)
                    self._text_accumulator += v; n = int(self._text_accumulator); self._text_accumulator -= n
                    uc.reg_write(c.XREG[8], min(n, 4000))
                c.uc.hook_add(unicorn.UC_HOOK_CODE, _vt, None, a + UI_MSGLOOP_WRITE, a + UI_MSGLOOP_WRITE)
            else: self._record_missing('text speed: unexpected ui_MsgLoop, setting has no effect')
        except Exception as ex: self._record_missing('text speed not installed: %s' % (ex,))
        try:
            sb = c.export('_ZN6status12OptionStatus14setBattleSpeedEc'); mu = c.export('_ZN26TownMenu_OPERATION_SETTING10menuUpdateEv')
            if sb and mu:
                def _sb(uc, ad, sz, u):
                    if self.scroll_mode is not None and self.scroll_callback is not None and mu <= uc.reg_read(c.XREG[30]) < mu + 0x400: self.scroll_callback(uc.reg_read(c.XREG[1]) & 0xff)
                c.uc.hook_add(unicorn.UC_HOOK_CODE, _sb, None, sb, sb)
        except Exception as ex: self._record_missing('battle text scrolling: hook not installed: %s' % (ex,))
        try:                                                                  # kerning of letter pairs that are too far apart (MessageFont.kern)
            put = c.export('_ZN9SDrawCTRL7PutCharEt')
            if not put: raise ValueError('SDrawCTRL::PutChar not found')
            font = MessageFont(data=zipfile.ZipFile(self.apk_data).read('assets/English.font')); last = {}          # last[canvas] = (line, write position after the last glyph, its code)
            def _kern(uc, ad, sz, u):
                obj = uc.reg_read(c.XREG[0]); code = uc.reg_read(c.XREG[1]) & 0xffff
                adv = font.advance(code)
                if adv is None: last.pop(obj, None); return                   # space, tab, line break, "$": the next glyph is the first of a word
                x, y = struct.unpack('<2H', c.mem(obj + 0x46, 4)); before = last.get(obj)
                if before is not None and before[:2] == (y, x):                    # glyph placed right after the previous one (on the same line, no space)
                    k = font.kern(before[2], code)
                    if k: x -= k; c.mem_w(obj + 0x46, struct.pack('<H', x))
                last[obj] = (y, x + adv, code)
            c.uc.hook_add(unicorn.UC_HOOK_CODE, _kern, None, put, put); self._flush_tb('text kerning')
        except Exception as ex: self._record_missing('text kerning not installed: %s' % (ex,))

    def _level_hooks(self):
        """Option "HP and MP restored on level up" (`level_heal`, false = like the game). Every level-up goes through `HaveStatus::levelup(bool)`: it recalculates the stats, then, if the argument is true
        (the case of `debugLevelup`), sets HP and MP back to their maximum (`tbz w20,` at +0x3f8: HP <- max HP, MP <- max MP). A hook on that instruction forces the bit when the option is active; the rest of the calculation is the game's."""
        c = self.core; self.level_heal = False
        try:
            a = c.export('_ZN6status10HaveStatus7levelupEb')
            if not a or struct.unpack('<I', c.mem(a + HAVESTATUS_LEVELUP_END, 4))[0] != TBZ_W20_0:
                self._record_missing('HP/MP on level up: unexpected HaveStatus::levelup, option has no effect'); return
            def _heal(uc, ad, sz, u):
                if self.level_heal: uc.reg_write(c.XREG[20], uc.reg_read(c.XREG[20]) | 1)
            c.uc.hook_add(unicorn.UC_HOOK_CODE, _heal, None, a + HAVESTATUS_LEVELUP_END, a + HAVESTATUS_LEVELUP_END)
            self._flush_tb('HP/MP on level up')
        except Exception as ex: self._record_missing('HP/MP on level up: hook not installed: %s' % (ex,))

    def _forced_monster_hooks(self):
        """(test) `force_monster` (command line `--force-monster N`, 0 = off): every RANDOM encounter is a single monster N. `Encount::brew()` builds the group in `Encount + 0x34` (monster numbers) and `+ 0x44` (counts);
        a hook on the common tail (the group is complete there) replaces it. Scripted battles (bosses, events) do not go through `brew`, so they stay as they are."""
        c = self.core; self.force_monster = 0
        try:
            a = c.export('_ZN7Encount4brewEv')
            u32 = lambda x: struct.unpack('<I', c.mem(x, 4))[0]
            if not a or u32(a + ENCOUNT_BREW_END) != MOV_X0_X19 or u32(a + ENCOUNT_BREW_RET) != RET:
                self._record_missing('forced monster: unexpected Encount::brew, --force-monster has no effect'); return
            def _force(uc, ad, sz, u):
                if not self.force_monster: return
                p = uc.reg_read(c.XREG[19]) & 0xffffffffffff
                c.mem_w(p + ENCOUNT_MONSTERS, struct.pack('<4I', self.force_monster, 0, 0, 0)); c.mem_w(p + ENCOUNT_COUNTS, struct.pack('<4I', 1, 0, 0, 0))
            c.uc.hook_add(unicorn.UC_HOOK_CODE, _force, None, a + ENCOUNT_BREW_END, a + ENCOUNT_BREW_END)
            self._flush_tb('forced monster')
        except Exception as ex: self._record_missing('forced monster: hook not installed: %s' % (ex,))

    def _game_time_hooks(self):
        """Save play time on real time. The engine adds 2 units (1/60 s) per step (`GameStatus::addPlayTime(2)` in `Global::NativeExec`): at x1
        (30 steps per second) that is real time, but accelerated walking and fast battle make `a` times more steps per second and the play time (and the history timestamp, which reads it) runs `a` times too fast.
        `clock_speed` (written by the viewer before each step: acceleration factor of the game clock, walking AND battle; 1 = normal) > 1: the hook skips the call (returns directly to the next instruction, nothing
        else is touched: x0 and w1 are no longer used) for the fraction 1 - 1 / a of the steps (`Passer`), evenly. At 1 (or less, slowed down): the original game, identical."""
        c = self.core; self.clock_speed = 1.0; self.game_time = RE.Passer()
        try:
            f = c.export('_ZN6Global10NativeExecEv'); ad = c.export('_ZN6status10GameStatus11addPlayTimeEj')
            u32 = lambda a: struct.unpack('<I', c.mem(a, 4))[0]; u64 = lambda a: struct.unpack('<Q', c.mem(a, 8))[0]
            w = u32(f + PLAYTIME_BL) if f else 0
            stub = struct.unpack('<4I', c.mem(c.LIB_BASE + PLAYTIME_STUB, 16))                                  # (the PLT stub: adrp x16 ; ldr x17, [x16, #0x968] ; add x16, x16, #0x968 ; br x17: its entry in the address table, 0x240968, contains addPlayTime)
            if not f or not ad or u32(f + PLAYTIME_MOV_W1) != MOV_W1_2 or w & 0xfc000000 != 0x94000000 or f + PLAYTIME_BL + ((((w & 0x3ffffff) ^ 0x2000000) - 0x2000000) << 2) != c.LIB_BASE + PLAYTIME_STUB \
                    or stub != PLAYTIME_STUB_WORDS or u64(c.LIB_BASE + PLAYTIME_GOT) != ad:
                self._record_missing('play time: unexpected NativeExec, game speed changes how fast play time runs'); return
            def _tj(uc, a, sz, u):
                v = self.clock_speed
                if v <= 1.0: return                                                          # x1: the game as is
                p = self.game_time; p.factor = 1.0 / v
                if not p.allows(): uc.reg_write(unicorn.arm64_const.UC_ARM64_REG_PC, a + 4)       # call skipped
            c.uc.hook_add(unicorn.UC_HOOK_CODE, _tj, None, f + PLAYTIME_BL, f + PLAYTIME_BL)
            self._flush_tb('play time')
        except Exception as ex: self._record_missing('play time: hook not installed: %s' % (ex,))

    def _magic_hooks(self):
        """Spells of the Magic menu (outside battle) that cost MP but spend none: the engine spends MP only if the spell had an effect (`BaseAction::useMp`), but for heals it announces the success message anyway
        (the action table gives the same text for success and failure: "Les blessures de X guerissent !" at full HP). The Magic menu launches the spell through `UseAction::execUse` in two places (choosing a
        target: `TownMenu_MAGIC_CHARSELECT::menuUpdate`; group spell or no target: `TownMenu_MAGIC_ROOT::useMagicNoTarget`) then displays `param + 0x1f8` ("X lance le sort Y !") and the list `param + 0x210`.
        A hook before the call records the caster's MP, a hook after compares: if the spell costs MP (`excelParam` table), the MP has not dropped and the game announces its success message (fields 1 / 3 of the
        message table) or none, the list becomes the game's message "Mais il ne se passe rien." (`MSG_NOTHING_OCCURS`, only once, even for a group). The game's own failure messages (Rappel, Antipoison, Evac'...) and battle do not change.
        Sound effects (measured on the real engine): casting plays sound effect 306 (the same for all spells: it always remains); the result message then plays heal sound effect 501 (`menuUpdate` + 0x110, for actions 196 to 198: Premiers secours, Soins
        partiels, Soins complets, without checking whether the heal was used): when the spell had no effect, this second sound effect is cut (a single `sub` modified before the instruction: the comparison output becomes 3, above 2). A group spell with no effect already no longer plays it (empty target loop)."""
        c = self.core; self._magic = None; self._magic_mute = False; self._magic_without_effect = False
        try:
            cs, nt = c.export('_ZN25TownMenu_MAGIC_CHARSELECT10menuUpdateEv'), c.export('_ZN19TownMenu_MAGIC_ROOT16useMagicNoTargetEv')
            msg, exc = c.export('_ZN6status17BaseActionMessage12actionParam_E'), c.export('_ZN6status10excelParamE')
            u32 = lambda a: struct.unpack('<I', c.mem(a, 4))[0]; u64 = lambda a: struct.unpack('<Q', c.mem(a, 8))[0]
            def is_exec_use(a):                                                            # `bl` to the UseAction::execUse stub?
                w = u32(a); return w & 0xfc000000 == 0x94000000 and a + ((((w & 0x3ffffff) ^ 0x2000000) - 0x2000000) << 2) == c.LIB_BASE + MAGIC_EXECUSE_STUB
            sites = [(cs + MAGIC_CHARSELECT_BL, False), (nt + MAGIC_WITHOUT_TARGET_BL, True)] if cs and nt and msg and exc else []
            if not sites or not all(is_exec_use(a) for a, _ in sites) or u32(u64(msg) + 0x48 * 201 + 0x14) != MSG_NOTHING_HAPPENS:
                self._record_missing('ineffective spells: unexpected Magic menu, the success message is kept'); return
            def _before(uc, ad, sz, u):
                p = uc.reg_read(c.XREG[0]) & 0xffffffffffff; caster = u64(p); action = u32(p + MAGIC_ACTION)
                cost = c.mem(u64(exc + 0x70) + 0x48 * action + 0x3a, 1)[0]                  # UseAction::getUseMp
                self._magic = (p, caster, struct.unpack('<H', c.mem(caster + MAGIC_MP, 2))[0], cost, action) if caster and cost else None; self._magic_without_effect = False
            def place(group):
                def _after(uc, ad, sz, u):
                    m, self._magic = self._magic, None
                    if not m: return
                    p, caster, mp, cost, action = m
                    if struct.unpack('<H', c.mem(caster + MAGIC_MP, 2))[0] < mp: return        # MP spent: the spell had an effect
                    e = u64(msg) + 0x48 * action; r = u32(p + MAGIC_RESULT)
                    if r and r not in (u32(e + 4), u32(e + 0xc)): return                    # the game already has its failure message
                    c.mem_w(p + MAGIC_RESULT, struct.pack('<II', MSG_NOTHING_OCCURS, 0))
                    if not group: self._magic_without_effect = True                              # the healing sound effect of the next step is cut off (see _sound)
                    if group: c.mem_w(self.L + MAGIC_TARGET_COUNT, b'\x01'); self._magic_mute = True      # a single copy of the message (the engine shows it once per living target)
                return _after
            for (a, group) in sites:
                c.uc.hook_add(unicorn.UC_HOOK_CODE, _before, None, a, a); c.uc.hook_add(unicorn.UC_HOOK_CODE, place(group), None, a + 4, a + 4)
            def _end(uc, ad, sz, u):                                                       # exit from the target loop: no more healing sound effect pending (menuUpdate plays one per remaining target) if nothing happened
                if self._magic_mute: self._magic_mute = False; c.mem_w(self.L + MAGIC_TARGET_COUNT, b'\x00')
            c.uc.hook_add(unicorn.UC_HOOK_CODE, _end, None, nt + MAGIC_LOOP_END, nt + MAGIC_LOOP_END)
            if u32(cs + MAGIC_HEAL_SOUND) == SUB_W8_W8_C4:
                def _sound(uc, ad, sz, u):                                                   # before `sub w8, w8, #0xc4`: the spell had no effect -> w8 = 0xc7 (result 3 > 2): no healing sound effect
                    if self._magic_without_effect: self._magic_without_effect = False; uc.reg_write(c.XREG[8], 0xc7)
                c.uc.hook_add(unicorn.UC_HOOK_CODE, _sound, None, cs + MAGIC_HEAL_SOUND, cs + MAGIC_HEAL_SOUND)
            else: self._record_missing('ineffective spells: unexpected healing sound, it is kept')
            self._flush_tb('ineffective spells')
        except Exception as ex: self._record_missing('ineffective spells: hook not installed: %s' % (ex,))

    def _fade_hooks(self):
        """Fades started by a game SCRIPT command (fade_in / fade_out: `__cmd_fade_in::initialize`, `__cmd_fade_out::initialize`, which call Global::fadeIn / fadeOutBlack... then UnitySetFade with the script's duration,
        and themselves wait for that number of frames: `isEnd` counts the frames): packet 9 receives the PJ.SCRIPT_FADE_MARK mark, and State._fade does not shorten this fade ("transition
        transitions" setting: it applies to the engine's fades, map changes..., not to those a script has fixed). Without the mark, the shortened fade would leave the screen black until the end of the script's wait."""
        c = self.core; self._script_fade = False
        try:
            ini = [c.export('_ZN13__cmd_fade_in10initializeEPc'), c.export('_ZN14__cmd_fade_out10initializeEPc')]; usf = c.export('_Z12UnitySetFadei')
            if not all(ini) or not usf: self._record_missing('script fades: engine functions not found, setting applied to all fades'); return
            def end_of(a):                                                       # address after the `ret` of the function
                for k in range(80):
                    if struct.unpack('<I', c.mem(a + 4 * k, 4))[0] == 0xd65f03c0: return a + 4 * (k + 1)
                return None
            ends = [end_of(a) for a in ini]
            if None in ends or struct.unpack('<I', c.mem(usf + 8, 4))[0] != 0x5280012a:        # UnitySetFade: `mov w10,` (packet type) at +8; other engine version: nothing is touched
                self._record_missing('script fades: unexpected UnitySetFade, setting applied to all fades'); return
            def _entry(uc, ad, sz, u): self._script_fade = True
            def _exit(uc, ad, sz, u): self._script_fade = False
            def _packet(uc, ad, sz, u):
                if self._script_fade:
                    self._script_fade = False
                    uc.reg_write(c.XREG[0], (uc.reg_read(c.XREG[0]) & 0xffffffff) | PJ.SCRIPT_FADE_MARK)
            for a, f in zip(ini, ends):
                c.uc.hook_add(unicorn.UC_HOOK_CODE, _entry, None, a, a); c.uc.hook_add(unicorn.UC_HOOK_CODE, _exit, None, f - 4, f - 4)
            c.uc.hook_add(unicorn.UC_HOOK_CODE, _packet, None, usf, usf)
            self._flush_tb('script fades')                                  # (blocks already translated before the hooks)
        except Exception as ex: self._record_missing('script fades: hook not installed: %s' % (ex,))

    def _option(self, offset):
        """Address of a byte of status::g_Option (OptionStatus: +1 music volume, +2 sound effect volume (0 to 4), +5 battle message speed)."""
        ad = self.core.export('_ZN6status8g_OptionE')
        return (ad if ad else self.L + 0x25b564) + offset

    def game_options(self):
        """(music volume, sound effect volume, battle message speed) of the game's options (Settings window, saved in the save file)."""
        c = self.core
        return c.mem(self._option(1), 1)[0], c.mem(self._option(2), 1)[0], c.mem(self._option(5), 1)[0]

    def impose_scroll_mode(self, code):
        """Battle message scrolling imposed on every frame (code 0 to 3: wait of 12 / 22 / 32 / 42 frames, 4: manual); None: the game's value is returned (the one from the save, or chosen in its Settings)."""
        if code is None:
            if self.scroll_mode is not None and self._scroll_origin is not None: self.core.mem_w(self._option(5), bytes([self._scroll_origin]))
            self.scroll_mode = None; self._scroll_origin = None
        else:
            if self.scroll_mode is None: self._scroll_origin = self.game_options()[2]
            self.scroll_mode = int(code) & 0xff; self.core.mem_w(self._option(5), bytes([self.scroll_mode]))

    def write_scroll_mode(self):
        """Before each engine frame: the imposed value is written; if the game had set another one (loading a save or a savestate, Settings window), that is the one that will be returned.
        `hold_messages` (set by the window while a jingle or the victory fanfare plays in battle): the battle messages are put on "manual" (4) so that none moves on by itself; when it is
        lowered, the value from before comes back (the imposed one, or the game's own), without being taken for a change made by the game."""
        ad = self._option(5)
        if self.hold_messages:
            if self._hold_saved is None: self._hold_saved = -1 if self.scroll_mode is not None else self.core.mem(ad, 1)[0]
            self.core.mem_w(ad, bytes([SCROLL_MANUAL])); return
        if self._hold_saved is not None:
            saved, self._hold_saved = self._hold_saved, None
            if self.scroll_mode is None: self.core.mem_w(ad, bytes([saved])); return
            self.core.mem_w(ad, bytes([self.scroll_mode])); return
        if self.scroll_mode is None: return
        cur = self.core.mem(ad, 1)[0]
        if cur != self.scroll_mode: self._scroll_origin = cur
        self.core.mem_w(ad, bytes([self.scroll_mode]))

    def message_state(self):
        """(test) (open message, ui_MsgLoop state, current letter, end of line, window type speed)."""
        c = self.core; g = lambda off: struct.unpack('<H', c.mem(self.L + off, 2))[0]
        return c.mem(self.L + MSG_ACTIVE, 1)[0], g(MSG_STATE), g(MSG_CURRENT), g(MSG_END), g(MSG_SPEED)

    def reapply_fixes(self):
        """Puts back the fixes that the viewer places in the engine's memory (widened locations window, no "Sauv. cloud", "Settings" button, original walking speeds). Called after a savestate is loaded
        (savestates.apply): the library's original image is reloaded first, and a savestate recorded by a version that did not yet have a fix does not contain it. Each one is idempotent."""
        self._widen_symbols()
        self.core.mem_w(self.L + G_IS_AMAZON, b'\x01')
        self.reset_speeds()
        self.patch_params()
        self.patch_copy_prefix()
        self.back_to_title_state = None            # a savestate loaded during the return-to-title box: the box no longer exists (engine memory replaced)

    @staticmethod
    def _french_texts(pack):
        """True if the game's texts are French (the French patch): the first monster's definite article ("@2") is French. The engine itself does not know it (the French texts run as language 1, English)."""
        try:
            d = zipfile.ZipFile(pack).read(NAMES_MSG); i = d.find(b'@2')
            return i >= 0 and (d[i + 2:i + 5] in (b'le ', b'la ') or d[i + 2:i + 4] == b"l'")
        except Exception: return False

    def patch_copy_prefix(self):
        """French texts: the name of a monster's copy of a character ("copy of ;Alina": Le feutocopieur se transforme en portrait craché d'Alina) becomes "double de ;Kiryl", "double d'Alina", the
        words the French patch uses for these copies (its monster names). The English string is checked before writing; the 2 extra bytes overwrite the start of the Korean string (language 2, never
        read with these texts). English texts: nothing. Called again after a savestate is loaded (original library image)."""
        if not self.french_texts: return
        c = self.core; ad = self.L + COPY_PREFIX; cur = bytes(c.mem(ad, len(COPY_PREFIX_EN)))
        if cur == COPY_PREFIX_EN: c.mem_w(ad, COPY_PREFIX_FR)
        elif cur != COPY_PREFIX_FR: self._record_missing('copy name: unexpected string in MsgVar::extract_var, a monster\'s copy of a character keeps its original name')

    def _copy_name_hooks(self):
        """French texts: elision of the copy's name before a vowel ("double de ;Alina" -> "double d'Alina", as in the French patch's monster names). Hook at MsgVar::extract_var + 0xb8, where the name
        has just been written after the prefix (x19 = its start): the name is moved back 2 bytes and x19 follows it. Instruction checked, otherwise not installed (the name keeps "de")."""
        if not self.french_texts: return
        c = self.core
        try:
            a = c.export('_ZN6MsgVar11extract_varEPci')
            if not a or struct.unpack('<I', c.mem(a + COPY_NAME_DONE, 4))[0] != LDRB_W8_X20_12:
                self._record_missing("copy name: unexpected MsgVar::extract_var, no elision (double de Alina)"); return
            pre = COPY_PREFIX_FR[:-1]; n_pre = len(pre)
            def _elide(uc, ad, sz, u):
                x19 = uc.reg_read(c.XREG[19]) & 0xffffffffffff
                if bytes(c.mem(x19 - n_pre, n_pre)) != pre: return
                raw = bytes(c.mem(x19, 64)); name = raw[:raw.find(b'\x00')] if b'\x00' in raw else raw
                if not starts_with_vowel(name): return
                c.mem_w(x19 - n_pre, COPY_ELISION + name + b'\x00')
                uc.reg_write(c.XREG[19], x19 - n_pre + len(COPY_ELISION))
            c.uc.hook_add(unicorn.UC_HOOK_CODE, _elide, None, a + COPY_NAME_DONE, a + COPY_NAME_DONE)
            self._flush_tb('copy name')
        except Exception as ex: self._record_missing('copy name: elision hook not installed: %s' % (ex,))

    def _widen_symbols(self):
        """FieldData::drawSymbol shows the world map's locations (towns, caves...) only in the window of the original portrait screen around the hero
        (x from -192 to +448, y from -192 to +788 pixels, plus a margin): in 16/9 the locations at the sides appeared only once very close. The three constants of
        the function (add w22/w23/w24, w9, #imm) are raised to 1600 pixels: the window covers everything the viewer can show, even zoomed out."""
        c = self.core
        try:
            a = c.export('_ZN9FieldData10drawSymbolEv')
            words = [struct.unpack('<I', c.mem(a + dec, 4))[0] for dec in (0x44, 0x48, 0x4c)]
            if all(w & 0xffc003e0 == 0x11000120 and (w >> 10) & 0xfff == 1600 for w in words): return        # already widened (reapply_fixes)
            for w, imm in zip(words, (0xc0, 0x1c0, 0x314)):
                if w & 0xffc003e0 != 0x11000120 or (w >> 10) & 0xfff != imm:
                    self._record_missing('places window not widened: unexpected FieldData::drawSymbol, world map places only appear in the original window'); return        # other engine version: nothing is touched
            for dec in (0x44, 0x48, 0x4c):
                w = struct.unpack('<I', c.mem(a + dec, 4))[0]
                c.mem_w(a + dec, struct.pack('<I', (w & ~(0xfff << 10)) | (1600 << 10)))
        except Exception as ex:
            self._record_missing('places window not widened: %s' % (ex,))

    # TownMenu_OPERATION_ROOT::menuUpdate (list of the Miscellaneous menu): "cmp w8," (0x16ef28) followed by "b.ne" to the "unknown button" exit;
    # button 7 ("Settings") closes the menu and opens TownMenu_OPERATION_SETTING
    CMP_PARAMS = 0x16ef28

    def patch_params(self):
        """The "Settings" button of the Miscellaneous menu opens the viewer's Pause menu, not the game's original settings (volumes, speed, D-pad size, return to title): the comparison of the chosen button's number with 7
        is raised to 4095 (never equal: the engine treats the press as that of an unknown button, does not close the Miscellaneous menu and does not enter the "Settings" state). Without effect if already done or if the engine is another
        version. Called again after a savestate is loaded (savestates.apply puts back the library's original image)."""
        c = self.core; ad = c.LIB_BASE + self.CMP_PARAMS; w = struct.unpack('<I', c.mem(ad, 4))[0]
        if w == 0x71001d1f: c.mem_w(ad, struct.pack('<I', (w & ~(0xfff << 10)) | (0xfff << 10)))       # "cmp w8," -> "cmp w8,"
        elif w != 0x713ffd1f: self._record_missing("Settings button: unexpected comparison in the Misc menu, the button opens the game's original settings instead of the Pause menu")        # (0x713ffd1f = already patched)

    def _divert_params(self):
        """Patch of the "Settings" button (patch_params) and hook on the comparison: it raises `request_pause` when the chosen button is 7; the viewer then only has to open its Pause menu (Game.tick)."""
        c = self.core
        try:
            self.patch_params(); ad = c.LIB_BASE + self.CMP_PARAMS
            def _p(uc, a, sz, u):
                if uc.reg_read(c.XREG[8]) & 0xffffffff == 7: self.request_pause = True
            c.uc.hook_add(unicorn.UC_HOOK_CODE, _p, None, ad, ad)
        except Exception as ex:
            self._record_missing('Settings button not redirected: %s' % (ex,))

    def _create_canvas(self):
        c = self.core
        # text canvas of the messages: Unity creates it through a port message (width, height); the handler is called directly
        self.obj_msg = self.L + OBJ_MESSAGE
        shorts = [0]
        for v in (1, 0, CANVAS_L, CANVAS_H, 0): shorts += [v & 0xffff, (v >> 16) & 0xffff]
        mp = c.malloc(64); c.mem_w(mp, struct.pack('<%dH' % len(shorts), *shorts))
        c.call(self.E('_ZN9SDrawCTRL11CanvasSetupEPvPKs'), self.obj_msg, mp, label='CanvasSetup')

    def _global(self):
        return struct.unpack('<Q', self.core.mem(self.L + GLOBAL_PTR, 8))[0]

    def start_field(self):
        """(trial) forces the switch to the world map: Global::startField()."""
        self.core.call(self.E('_ZN6Global10startFieldEv'), self._global(), label='startField')

    def back_to_title(self):
        """Return to the title screen: the end of the "Return to title screen" button of the game's original Settings when "Yes" is answered (TownMenu_OPERATION_SETTING::menuUpdate, state 5): clears bank 4
        (autosave, killbank), closes the box, locks the player, then Global::startTitle() (30-frame fade to black started by UnitySetFade(0x101e), chapter 0, the next part is the title). To be
        invoked DURING a step (see _return_to_title_after): the fade packet must be read with those of the step, otherwise the fade is lost (the buffer is reset to zero at the next step) and the screen goes black at once."""
        c = self.core
        c.call(self.E('_ZN7profile8SaveLoad8killbankEib'), 4, 0, label='killbank')
        self._close_title_box()
        c.call(self.E('_ZN3cmn11GameManager12getSingletonEv'), label='getSingleton')
        c.call(self.E('_ZN3cmn13PlayerManager7setLockEb'), 1, label='setLock')
        c.call(self.E('_ZN6Global10startTitleEv'), self._global(), label='startTitle')

    def request_return_to_title(self):
        """Pause menu > "Return to title screen": opens the game's box (its text, Yes / No) at the next step, like the button of the original Settings. -> false if a request is already in progress.
        "No" closes the box and gives control back to the player; "Yes" launches back_to_title, with the game's fade. Both continuations are played by `_return_to_title_after`, after each GameUpdate.
        Only in towns and on the world map, the two parts where the original Settings menu exists and where the box responds (trial: in battle, the box opens but receives neither keys nor
        clicks, the battle command menu keeps control; not verified in shops and the casino games)."""
        if self.back_to_title_state is not None or self.state.part not in (PART_TOWN, PART_FIELD): return False
        self.back_to_title_state = 'requested'; return True

    def _title_box(self): return self.core.export('gTownMenu_MESSAGE')

    def _close_title_box(self):
        c = self.core; m = self._title_box()
        if m and c.call(self.E('_ZN8MenuBase6isOpenEv'), m, label='isOpen') & 1: c.call(self.E('_ZN8MenuBase5closeEv'), m, label='close')

    def _return_to_title_before(self):
        """Before GameUpdate: opens the box. Same sequence of calls as state 5 of the original Settings menu (menuUpdate + 0x1ac): openMessageForMENU, addMessage(0xCBA2F), setYesNo() (cursor on "Yes"),
        setYesNoSuperCancel(false); the player is locked as in the game's menu (PlayerManager::setLock(true), given back by "No")."""
        if self.back_to_title_state != 'requested': return
        c = self.core; m = self._title_box(); self.back_to_title_state = 'dialog'
        c.call(self.E('_ZN3cmn11GameManager12getSingletonEv'), label='getSingleton')
        c.call(self.E('_ZN3cmn13PlayerManager7setLockEb'), 1, label='setLock')
        c.call(self.E('_ZN16TownMenu_MESSAGE18openMessageForMENUEv'), m, label='openMessageForMENU')
        c.call(self.E('_ZN16TownMenu_MESSAGE10addMessageEi'), m, MSG_RETURN_TITLE, label='addMessage')
        c.call(self.E('_ZN16TownMenu_MESSAGE8setYesNoEv'), m, label='setYesNo')
        c.call(self.E('_ZN16TownMenu_MESSAGE19setYesNoSuperCancelEb'), m, 0, label='setYesNoSuperCancel')
        c.mem_w(m + MESSAGE_RESULT, bytes(4))                # the answer of a previous box does not count (MenuBase::menuBaseSetup resets it to 0 when the menu is added; here it may already be added: an NPC message in progress)

    def _return_to_title_after(self):
        """After GameUpdate, before the packets are read: the box's answer (TownMenu_MESSAGE + 0x10, as the original Settings menu's menuUpdate does). 2 = Non: the box is closed and control is
        given back (setLock(false), the inverse of the opening). 1 = Oui: back_to_title, in this step, therefore with its fade."""
        if self.back_to_title_state != 'dialog': return
        c = self.core; r = struct.unpack('<I', c.mem(self._title_box() + MESSAGE_RESULT, 4))[0]
        if r == 2:
            self.back_to_title_state = None; self._close_title_box()
            c.call(self.E('_ZN3cmn11GameManager12getSingletonEv'), label='getSingleton')
            c.call(self.E('_ZN3cmn13PlayerManager7setLockEb'), 0, label='setLock')
        elif r == 1:
            self.back_to_title_state = None; self.back_to_title()
        elif not c.call(self.E('_ZN8MenuBase6isOpenEv'), self._title_box(), label='isOpen') & 1:          # closed without an answer (the engine's scene took the box over: a message from more than one script, for example): the request is dropped, the player is released
            self.back_to_title_state = None
            c.call(self.E('_ZN3cmn11GameManager12getSingletonEv'), label='getSingleton')
            c.call(self.E('_ZN3cmn13PlayerManager7setLockEb'), 0, label='setLock')

    def start_the_end(self):
        """(test shortcut) The end of the game right away, in the order of the ending script of mlb1a: TownEndrollManager::setup (cmd_set_end_roll), the credits (the engine scrolls them until
        isStaffRollEnd), startTheEnd (cmd_the_end: the calligraphy "The End", meshes of packets 21 / 22), then back to the title screen (the script goes on with cmd_menu_save(2)). The steps are played by `_end_roll_after`,
        after each GameUpdate, so that the packets of startTheEnd are read with those of the step (called outside a step they were lost)."""
        c = self.core; tem = c.export('_ZN18TownEndrollManager11m_singletonE')
        c.call(c.export('_ZN18TownEndrollManager5setupEv'), tem, label='setup end roll')
        self.end_roll = 'credits'

    def story_chapter(self):
        """Current chapter of the story (StoryStatus +4): 1 to 6, 9 during the ending (set by `ev09`)."""
        c = self.core; return struct.unpack('<I', c.mem(c.export('_ZN6status7g_StoryE') + 4, 4))[0]

    def the_end_started(self):
        """TownEndrollManager::startTheEnd has been called (byte +0x43 of the manager): the credits are over, the calligraphy "The End" is being written. The viewer then stops showing the credits' last picture."""
        c = self.core; return c.mem(c.export('_ZN18TownEndrollManager11m_singletonE') + 0x43, 1)[0] == 1

    def _end_roll_after(self):
        """After GameUpdate: the end of the credits starts the end screen (what the ending script does after cmd_set_end_roll), the end of the end screen goes back to the title screen."""
        if self.end_roll is None: return
        c = self.core; tem = c.export('_ZN18TownEndrollManager11m_singletonE')
        if self.end_roll == 'credits' and c.call(c.export('_ZN18TownEndrollManager14isStaffRollEndEv'), tem, label='isStaffRollEnd') & 1:
            c.call(c.export('_ZN18TownEndrollManager11startTheEndEv'), tem, label='startTheEnd'); self.end_roll = 'the end'
        elif self.end_roll == 'the end' and c.call(c.export('_ZN18TownEndrollManager11isEndTheEndEv'), tem, label='isEndTheEnd') & 1:
            self.end_roll = None; self.back_to_title()

    def start_town(self, name_str):
        """(trial) loads a town or a dungeon: Global::startTown(name_str). Refuses a name without a map file (`assets/map/<name_str>.stg`): the original engine does not test it and crashes (null pointer in FldStage::getCameraLimitL),
        for example `za3f3`, an orphan map (`.map` and `.fld` in the graphics pack, no `.stg`)."""
        if self.core.fs is not None and self.core.fs.open('map/%s.stg' % name_str) is None: raise ValueError("unknown map: no file assets/map/%s.stg in the game data" % name_str)
        self.core.call(self.E('_ZN6Global9startTownEPKc'), self._global(), self.core.cstr(name_str.encode()), label='startTown')

    # walking speed of the hero (Fix32 per engine step, original values from libdq4core): towns (two variables), world map (Speed, plus the two local constants
    # 0x27520c and 0x275210 that FieldPlayer::move reads when moving diagonally). Running speeds up the engine clock (viewer, _loop), not these values;
    # they are put back to the original only when a savestate is loaded (see reset_speeds)
    ORIGIN_SPEEDS = (('_ZN16TownPlayerAction9walkSpeedE', 819), ('_ZN16TownPlayerAction10walkSpeed2E', 655), ('_ZN11FieldPlayer5SpeedE', 12288), (0x27520c, 8192), (0x275210, 8192))

    def reset_speeds(self):
        """Puts the hero's walking speeds back to their original values: a savestate recorded by an older version during a run contains them increased (running no longer touches them)."""
        c = self.core
        for n, base in self.ORIGIN_SPEEDS:
            ad = c.LIB_BASE + n if isinstance(n, int) else c.export(n)
            if ad: c.mem_w(ad, struct.pack('<i', base))

    def shops(self):
        """(current index, count) of the shops in the list of a town's map (TownImageMap::execute: two local statics, 0x2750c4 and 0x2750c8; the list is the type 24 window)."""
        c = self.core; b = c.LIB_BASE
        return struct.unpack('<hh', c.mem(b + 0x2750c4, 2) + c.mem(b + 0x2750c8, 2))

    def camera_town(self):
        """Camera of the original engine's towns (TownCamera, static object): (left limit, right limit, lock); limit = 0: free rotation, < 0: rotation forbidden, > 0: bounded angle (units of 1 / 4096 of a turn); lock: camera locked by an event."""
        c = self.core; ad = c.export('_ZN10TownCamera11m_singletonE')
        if ad is None: return 0, 0, False
        lg, ld = struct.unpack('<ii', c.mem(ad + 0x34, 8)); return lg, ld, bool(c.mem(ad + 0x3e, 1)[0])

    def camera_game(self):
        """State of the engine's TownCamera (static object), to know whether the game drives the camera: (lock +0x3e, target mode +0x48, viewpoint lock +0x40, movement in progress +0x43)."""
        c = self.core; ad = c.export('_ZN10TownCamera11m_singletonE')
        if ad is None: return 0, 0, 0, 0
        b = c.mem(ad + 0x3e, 6); return b[0], struct.unpack('<i', c.mem(ad + 0x48, 4))[0], b[2], b[5]

    def camera_wait(self):
        """Camera rotation that the game has just accepted (TownPlayerManager + 0x698, CAMERA_ROT_TYPE): ROT_CAM_RIGHT or ROT_CAM_LEFT as long as the button held at this step has not yet turned the camera (player lock, scene, location that forbids
        turning it: the game does not touch it and the value stays 0), ROT_CAM_NORD during the return to north."""
        c = self.core; ad = c.export('_ZN17TownPlayerManager11m_singletonE')
        return 0 if ad is None else struct.unpack('<i', c.mem(ad + 0x698, 4))[0]

    def camera_turn(self, direction, times):
        """`times` more rotations of the game's camera (direction: ROT_CAM_RIGHT or ROT_CAM_LEFT), each exactly that of one engine step (setCameraRotType then TownPlayerManager::setCameraRot: TownCamera::rotateL / rotateR, which clamps according to the limits
        of the location, and rotation of the party's direction so that the hero keeps his heading on screen). Used by the "Camera speed" setting (the game turns only one notch per step) and by the wheel click drag. Called after a step that took the button (camera_wait)
        : the rotations of this step ARE these `times` calls (the first consumes the one that the button put on hold)."""
        c = self.core; ad = c.export('_ZN17TownPlayerManager11m_singletonE')
        if ad is None: return
        a, b = self.E('_ZN17TownPlayerManager16setCameraRotTypeE15CAMERA_ROT_TYPE'), self.E('_ZN17TownPlayerManager12setCameraRotEv')
        for _ in range(times): c.call(a, ad, direction, label='camera'); c.call(b, ad, label='camera')

    def dpad_size(self):
        """The game's "D-pad size" option (g_pad_size): 0 Grande, 1 Moyenne (default), 2 Petite."""
        v = self.core.mem(self.core.LIB_BASE + 0x24a779, 1)[0]
        return v if v in (0, 1, 2) else 1

    def awaits_touch(self):
        """True when the experience gift menu (`MaterielMenu_EXTRA_PRESENT_EXP`, a mobile addition: the king of Burland in chapter 1) is open and in its last state: once the levels are shown, `menuUpdate` (state +0x30 = 2)
        waits for a trigger from the game's pad (`dss::g_Pad + 2`, filled by `Global::NativeExec` from the 2nd argument of `GameUpdate`: the screen tap, exactly 0x100, or the buttons 0x400 to 0x2000), before closing the menu and
        giving control back to the scenario. The A key of a message (0x10) never raises it: the window then sends the tap (see Game._entries). "Open": the menu is in the array of the `MenuManager` manager (its state stays at 2 after
        closing until the next creation)."""
        try:
            c = self.core; L = self.L
            ges = int.from_bytes(c.mem(L + MENU_MANAGER, 8), 'little')
            if not ges: return False
            menu = L + MENU_GIFT_EXP
            if not any(int.from_bytes(c.mem(ges + 8 + 8 * i, 8), 'little') == menu for i in range(OPENED_MENUS)): return False
            return c.mem(menu + MENU_GIFT_EXP_STATE, 1)[0] == MENU_GIFT_EXP_WAIT
        except Exception: return False

    def flags(self):
        """Global.Flag: first word of the engine's output (bit 3: touch gamepad present; 4 player lock, 0x20 map allowed, 0x40 interface locked...)."""
        return struct.unpack('<I', self.core.mem(self.core.outp, 4))[0]

    def _effect_flag(self, active):
        """Bit 1 of Global+0xd8: Unity (Capture.ScreenEffect) raises it at the start of a screen effect and lowers it at the end; the engine waits for it to drop."""
        ad = self.core.outp; v = struct.unpack('<I', self.core.mem(ad, 4))[0]
        self.core.mem_w(ad, struct.pack('<I', (v | 2) if active else (v & ~2)))

    def _start_battle_effect(self, before):
        """Packet 34 (value 4): the screen shatters into pieces (BATTLE_EFFECT_FRAMES frames) while the engine waits; then the screen stays black until the battle scene has loaded."""
        if self.state.effect is not None: return
        self.battle_intro = True                                                                   # (History takes the state the replay of this battle starts from)
        self.state.effect = {'n': 0, 'duration': PJ.fade_duration(BATTLE_EFFECT_FRAMES, State.fade_speed)}; self._effect_flag(True)      # the cascade follows "Transition speed" like the fades: 57 frames at x1, 57 / factor afterwards (the simulation advances 57 frames in total, see Game._draw_effect)
        if self.state.load_wait is None: self.state.load_wait = {'base': before, 'n': 0}

    def _battle_effect(self):
        """One game frame: advances the battle start effect, lowers the flag at the end (the engine resumes on the next frame); counts the loading wait."""
        ef = self.state.effect
        if ef is not None:
            ef['n'] += 1
            if ef['n'] >= ef.get('duration', BATTLE_EFFECT_FRAMES): self._effect_flag(False); self.state.effect = None
        ac = self.state.load_wait
        if ac is not None:
            ac['n'] += 1
            if ac['n'] > LOAD_WAIT_MAX + BATTLE_EFFECT_FRAMES: self.state.load_wait = None

    def _start_screen_effect(self, value):
        """Packet 34, values 3 (trip: ailes de Chimere), 5 (lamp: Ranaruta) and 6 (Riremito): Capture.ScreenEffect raises bit 1 of Global.Flag, which the engine waits for, and starts a coroutine that lasts
        EF.FRAMES[...] frames (63 to 64 at departure, 45 at the arrival of a trip); the window draws the effect (window/capture_effects.py), see _screen_effect. Bit 7 of the value: bReverse (trip: arrival) or bMorning
        (lamp: morning tint). Like the battle cascade, the effect follows "Transition speed" (fewer engine frames)."""
        kind = EF.KINDS.get(value & 0xf)
        if kind is None or self.state.screen_effect is not None: return
        bit7 = bool(value & 0x80); inverse = kind == 'tabi' and bit7; frames = EF.frames_of(kind, inverse)
        self.state.screen_effect = {'n': 0, 'duration': PJ.fade_duration(frames, State.fade_speed), 'frames': frames, 'kind': kind, 'inverse': inverse, 'morning': kind == 'lamp' and bit7}
        self._effect_flag(True)

    def _screen_effect(self):
        """One game frame: advances the Capture effect in progress. The immediate black (lamp, Riremito: Fade.SetFadeOutBlack(0)) and the fade-in of a trip's arrival (Fade.SetFadeIn(30)) are started at their call of
        MoveNext; at the end, the flag drops (the engine resumes on the next frame). End of a trip's departure: the screen stays black (State.black_screen) until the end of the arrival. The black screen is abandoned if it
        lasts too long (safeguard) or if the game returns to the title."""
        e = self.state
        if e.black_screen is not None:
            e.black_screen['n'] += 1
            if e.black_screen['n'] > BLACK_SCREEN_MAX or e.part == PART_INITIAL or e.game_map == TITLE_MAP: e.black_screen = None
        ef = e.screen_effect
        if ef is None: return
        ef['n'] += 1; kind = ef['kind']; calls = EF.calls_made(ef['n'], ef['duration'], ef['frames'])
        if kind in EF.BLACK_CALL and calls >= EF.BLACK_CALL[kind] and not ef.get('black'): ef['black'] = True; e.sharp_black_fade()
        if ef['inverse'] and calls >= EF.FADE_IN_CALL and not ef.get('fade_in'): ef['fade_in'] = True; e.current_fade_in(EF.FADE_IN)
        if ef['inverse'] and calls >= ef['frames']: e.black_screen = None            # last call of the arrival (state 4): the game's camera is given back to the game, the scene reappears
        if ef['n'] >= ef['duration']:
            self._effect_flag(False); e.screen_effect = None
            if kind == 'tabi' and not ef['inverse']: e.black_screen = {'n': 0}

    def _map_name(self):
        s = self.core.read_cstr(self.L + RESOURCE_NAME).decode('latin-1')
        return s.split('/')[-1]

    def step(self, held=0, decl=None):
        """One game frame. held = keys held down (walking); decl = keys that have just been pressed (buttons, menus).
        Screen fades are replayed in State (tick_fade). -> list of packets"""
        if decl is None: decl = held
        if self.end_roll is not None: held = decl = 0                      # the end of the game started by start_the_end: the keys do nothing (the real ending script has the player locked)
        if self.input_log is not None:                                  # what the viewer gives the engine at this step: keys, menu messages sent since the last step, imposed message speed, menu that had the input
            self.input_log.append((held, decl, self._menus_this_step, self.scroll_mode, self._menu_active)); self._menus_this_step = []; self._menu_active = None
        c = self.core
        w = struct.unpack('<I', c.mem(c.outp, 4))[0]            # bit 0: "a fade is in progress" (Fade.FadePlane.CheckFade: remaining frames > 0). The engine raises it itself when it starts a fade (UnitySetFade) then waits for it to drop
        w2 = (w | 1) if self.state.fade_in_progress() else (w & ~1)      # (Global::IsFadeEnd: inn, chapter titles, loading screen, menu openings, whistle...)
        if w2 != w: c.mem_w(c.outp, struct.pack('<I', w2))
        self._finish_anims(); self._finish_fbx_anims()
        self._battle_effect(); self._screen_effect()
        if os.environ.get('DQ_CALLHOP'):                                       # (test) "image:monstre:hauteur:degats,...": calls BattleMenu_setHoppingNumbers like the engine after a hit
            for spec in os.environ['DQ_CALLHOP'].split(','):
                im, ch, hh, nn = [int(x) for x in spec.split(':')]
                if self.frames == im: self.ui.image = self.frames; c.call(self.E('_Z27BattleMenu_setHoppingNumbersss'), ch, hh, nn, label='hop')
        self.pk.begin()
        if self.scroll_mode is not None or self.hold_messages or self._hold_saved is not None: self.write_scroll_mode()
        self._return_to_title_before()
        r = c.call(self.E('GameUpdate'), held, decl, label='GameUpdate')
        if self._messages_sent: c.mem_w(c.inp, struct.pack('<i', -1)); self._messages_sent = False          # Unity rewrites the list every frame: a message is only valid for the frame in which it is sent
        self._return_to_title_after(); self._end_roll_after()
        if MSGDBG: self._log_message()
        if r is None: raise RuntimeError('the engine stopped:\n' + '\n'.join(self.log.lines[-12:]))
        pkt = self.pk.packets()
        if os.environ.get('DQ_PKT') and self.state.part == PART_BATTLE:       # (test) log of the battle packets: frame, [(type, ints...)]
            with open(os.environ['DQ_PKT'], 'a') as fj:
                fj.write('%d %s\n' % (self.frames, [(t, a[:2]) if t != 22 else (22, a[0], a[1], [round(x, 2) for x in f[:3]], [round(min(f[3 + 5 * i + 2] for i in range(a[1])), 2), round(max(f[3 + 5 * i + 2] for i in range(a[1])), 2), round(min(f[3 + 5 * i + 3] for i in range(a[1])), 2), round(max(f[3 + 5 * i + 3] for i in range(a[1])), 2)]) for t, a, f in pkt if t not in (12, 13, 14)]))
        if os.environ.get('DQ_PKTALL'):       # (temporary test) all packets except 22/28/29
            with open(os.environ['DQ_PKTALL'], 'a') as fj:
                for t, a, f in pkt:
                    if t not in (22, 28, 29): fj.write('%d p=%#x %d %s %s\n' % (self.frames, self.state.part, t, a[:6], [round(x, 3) for x in f[:6]]))
        self.ui.image = self.frames
        self._consume_messages()
        self._staffroll_after()
        for p in pkt:
            if p[0] == 5 and p[1]:
                d = self.anim_duration(p[1][0] & 0xffff, (p[1][0] >> 16) & 0xffff) if self.anim_duration else None
                self.anims.append((self.frames + (d or ANIM_DURATION), p[1][0] & 0xffff))
        before = self.state.loaded_maps
        self.state.image = self.frames
        self.state.apply(pkt, self._map_name)
        if self.state.loaded_maps > before: self._grid = None          # new map: the world grid is read again (never kept from before the load)
        if self.end_roll == 'the end': self.state.cam_free = True          # the end screen's camera: the engine sends a position and angles (free camera, as for the title); in the ending's own scene that mode is already on, in the shortcut's throne room it is not
        self.fbx_playing += [p[1][0] & 0xff for p in pkt if p[0] == 32 and p[1] and p[1][0] & 0x8000 and (p[1][0] & 0xff) in self.state.fbx]      # cmd_fbx : FbxObject.PlayAnimation puis m_anim_list.Add(emplacement | 0x1000)
        self._exit_countdown()
        for t, a, f in pkt:
            if t == 34 and a and (a[0] & 0xf) == BATTLE_EFFECT: self._start_battle_effect(before)
            elif t == 34 and a: self._start_screen_effect(a[0])
        ac = self.state.load_wait
        if ac is not None and self.state.effect is None and self.state.loaded_maps > ac['base']: self.state.load_wait = None      # the battle scene has arrived
        self.state.update_loading()
        self.state.tick_fade(); self.state.tick_transition()
        prev = self.state.part
        self.state.part = struct.unpack('<H', c.mem(self._global() + 0xee, 2))[0]
        if prev == PART_BATTLE and self.state.part != PART_BATTLE: self.state.return_window = BATTLE_RETURN_WINDOW      # end of battle: the fade-in that follows on the map is the return one (the game's duration)
        if self.state.part == PART_BATTLE and prev != PART_BATTLE and self.state.load_wait is None and self.state.loaded_maps <= before:
            self.state.load_wait = {'base': before, 'n': 0}      # battle without a screen effect (scenario...): the previous scene must not appear before the battle's scene has loaded
        if self.state.part != PART_FIELD: self.state.field = None; self.state.world = None
        else: self._read_world()
        self.frames += 1
        return pkt

    def _staffroll_after(self):
        """What Unity does for the credits' port (StaffrollPort): at the creation of the port two 512 x 512 RGBA textures are made and their identifiers sent to the engine (`512, id0, id1`, each integer in two shorts),
        then at each frame UnityRenderEvent(1) makes the engine upload the next rows of text into them (glTexSubImage2D, copied by the emulator into `ui.staff['tex']`)."""
        st = self.ui.staff
        if st is None or not st['live']: return
        c = self.core
        if not st['ready']:
            st['ready'] = True; st['tex'] = []
            for t in STAFF_TEX:
                img = np.zeros((STAFF_SIZE, STAFF_SIZE, 4), np.uint8); img[..., 3] = 255; st['tex'].append(img)
            self.send_menu(st['port'], STAFF_SIZE, 0, STAFF_TEX[0], 0, STAFF_TEX[1], 0)
        for t, img in zip(STAFF_TEX, st['tex']): c.gl_textures[t] = img                      # (also after a savestate has been loaded: the emulator's table is not in it)
        c.call(c.export('UnityRenderEvent'), 1, label='UnityRenderEvent')

    def _exit_countdown(self):
        """Map transition sound effect (door, exit, village entrance, stairs, world map <-> town): cause of its loss with the shortened fades ("Transition speed" x3 and above, marginal at x2).
        When the game leaves a town or the world map, it starts a 30-frame fade to black AND arms a 15-frame countdown (EXIT_COUNTDOWN); at 0, NativeExec calls playTownExitSE / playFieldExitSE, which play
        sound effect 305 only if the old scene is still alive. In the original game, the next map's loading happens only at the end of the fade (30 frames): the sound effect is requested at mid-fade. The viewer's shortened fade
        (State._fade) brings the loading before the 15 frames: the old scene is destroyed, the engine no longer requests anything (no packet 35). The countdown is therefore reset to the same proportion as the fade
        (played duration / original duration): the sound effect stays requested at mid-fade, the duration of the fade and that of the sound effect do not change. Without a shortened fade (ratio 1), nothing is touched."""
        c = self.core; b = c.mem(self.L + EXIT_COUNTDOWN, 1)[0]
        if b > self._countdown: self._countdown_armed = self.frames; self._countdown_done = False       # armed during this step (the engine has already decremented it once)
        self._countdown = b
        if self._countdown_done or b == 0 or b > 15: return
        im, r = self.state.fade_ratio
        if self.frames - self._countdown_armed > 2: self._countdown_done = True; return
        if im < self._countdown_armed - 2 or im > self.frames: return           # the fade of this exit has not (yet) arrived
        self._countdown_done = True
        if r < 1.0:
            num = max(1, int(round(b * r))); c.mem_w(self.L + EXIT_COUNTDOWN, bytes([num])); self._countdown = num

    def _log_message(self):
        """(test, DQ_MSGDBG=1) one line at each change of the message state: engine frame, state, letters written / letters of the line, window type speed."""
        o = self.game_options()
        if o != getattr(self, '_opt_vu', None): self._opt_vu = o; print('MSGDBG frame %d game options: music volume %d, sound effects volume %d, battle message speed %d (forced: %s)' % ((self.frames,) + o + (self.scroll_mode,)), flush=True)
        e = self.message_state()
        if (e[0], e[1], e[4]) != getattr(self, '_msg_vu', None) or (e[1] == 2 and e[2] == e[3]):
            self._msg_vu = (e[0], e[1], e[4]); print('MSGDBG frame %d active %d state %d letters %d/%d speed %d battle=%d' % ((self.frames,) + e + (self.state.part == PART_BATTLE,)), flush=True)

    def _read_world(self):
        """Entire world map (FieldData: CWorldMap +0x188 grid of 256 x 256 block numbers, block table +0x180 of 6 bytes,
        water animation offsets at addresses 0x275830/34/38). Same rule as FieldData::drawBlock (verified: 1300 tiles out of 1300).
        The engine sends only 25 columns around the hero; here we can draw around him as much as we want.
        Safeguards (the grid is cached for 30 frames, and `fielddata` is the pointer of the last drawBlock): the cache is dropped at each map load, and the result is checked against the
        tiles the engine itself sent (packet 28) in the same step: a grid that does not match (old or half-filled data) is read again, and if it still does not match the window gets `world = None`
        and draws the engine's own tiles, instead of a map of water."""
        c, fd = self.core, self.fielddata
        if not fd: self.state.world = None; return
        try:
            fresh = self._grid is None or self.frames - self._grid_frame >= 30
            for attempt in (0, 1):
                if fresh:
                    gp, = struct.unpack('<Q', c.mem(fd + 0x188, 8)); l, h = struct.unpack('<ii', c.mem(fd + 0x198, 8))
                    if not gp or not (0 < l <= 1024 and 0 < h <= 1024): self._grid = None; self.state.world = None; return
                    self._grid = np.frombuffer(c.mem(gp, l * h * 2), '<u2').reshape(h, l).astype(np.int32); self._grid_frame = self.frames
                tbl, = struct.unpack('<Q', c.mem(fd + 0x180, 8))
                ch = np.frombuffer(c.mem(tbl, 1024 * 6), np.uint8).reshape(1024, 6)
                b0, b1, b2 = (struct.unpack('<h', c.mem(self.L + a, 2))[0] for a in (0x275830, 0x275834, 0x275838))
                t = ch[:, 1]; s2 = np.ascontiguousarray(ch[:, 2:4]).view('<i2').ravel().astype(np.int32); s4 = np.ascontiguousarray(ch[:, 4:6]).view('<i2').ravel().astype(np.int32)
                tile = np.where(t == 0, s4 + b0, np.where(t == 0x18, s2 + b2, np.where(t == 8, s2 + b1, s2)))
                h, l = self._grid.shape
                ids = tile[(self._grid - 1) & 0x3ff]
                if self._world_matches(ids): self.state.world = {'ids': ids, 'l': l, 'h': h}; return
                if fresh: break                                       # read just now and still wrong
                fresh = True                                          # cached grid: read it again once
            self._grid = None; self.state.world = None
        except Exception:
            self._grid = None; self.state.world = None

    WORLD_MATCH = 0.9                          # share of the engine's own tiles (packet 28) that the grid read from memory must reproduce

    def _world_matches(self, ids):
        """Does the world map read from memory give, around the hero, the tiles the engine sent in packet 28 (same coordinates)? True when the engine sent none yet."""
        f = self.state.field
        if not f or not f.get('cols') or not f.get('tiles'): return True
        cols = f['cols']; t = np.asarray(f['tiles'], np.int32); rows = len(t) // cols
        if rows <= 0: return True
        h, l = ids.shape
        win = ids[(np.arange(f['y0'], f['y0'] + rows) % h)[:, None], (np.arange(f['x0'], f['x0'] + cols) % l)[None, :]]
        return float((win.ravel() == t[:rows * cols]).mean()) >= self.WORLD_MATCH

    def read_canvas(self):
        """Bitmap of the message text (height x width, 0-255 = opacity), or None if the canvas does not exist yet."""
        c = self.core
        buf = struct.unpack('<Q', c.mem(self.obj_msg + 0x10, 8))[0]
        if not buf: return None
        import numpy as np
        return np.frombuffer(c.mem(buf, CANVAS_L * CANVAS_H), np.uint8).reshape(CANVAS_H, CANVAS_L)

    def _consume_messages(self):
        """Does what the Unity interface would do: reads the messages that the engine has put for each port (menus, windows...)
        then empties the queue. Without this the queue grows endlessly and ends up overwriting the neighboring memory."""
        c = self.core
        b2 = self.buf2
        a = struct.unpack('<%dh' % SHORTS_STACK, c.mem(b2, 2 * SHORTS_STACK))
        out = []
        for port in range(32):
            idx = a[port] & 0xffff; guard = 0
            while 0 < idx < SHORTS_STACK - 2 and guard < 600:
                n = a[idx]
                if n < 0 or idx + n + 1 >= SHORTS_STACK: break
                out.append((port, a[idx + 1: idx + 1 + n]))
                idx = a[idx + 1 + n] & 0xffff; guard += 1
        self.msgs_ui = out
        self.ui.apply(out)
        c.mem_w(b2, b'\0' * 128 + struct.pack('<h', 65))              # heads/tails at 0, free pointer = 65

    def active_menu(self):
        """Port of the menu window that waits for keys (active and accepting input), or None."""
        c = self.core; L = self.L
        u = lambda a, n, sg=False: int.from_bytes(c.mem(a, n), 'little', signed=sg)
        base = u(L + 0x252098, 8); cnt = u(L + 0x252094, 2, True)
        if not base: return None
        cand = []
        for i in range(1, cnt):
            e = base + 0x20 * i
            port = u(e + 0x28, 2, True); this = u(e + 0x30, 8)
            if this and u(e + 0x38, 8) and port > 1 and u(this + 8, 1) == 1 and u(this + 0x50, 2):
                f = self.ui.f.get(port)
                if f and f['visible'] and f['cells'] and f.get('type') not in self.ignored_types: cand.append((f['order'], port))
        if not cand:                                 # otherwise: a menu whose input the engine requests (command 6 on every frame), even under a message: the Yes / No of a question
            cand = [(self.ui.f[p]['order'], p) for p in self.input_menus()]
        return max(cand)[1] if cand else None

    def input_menus(self):
        """All the menu ports whose input the engine requests (touch acts on each of them): the most recent first."""
        return sorted((p for p, f in self.ui.f.items() if p > 1 and f.get('input') and f['visible'] and f['cells'] and f.get('type') not in self.ignored_types), key=lambda p: -self.ui.f[p]['order'])

    def send_menu(self, port, *args):
        """What Unity does: drops a message [n, args...] into the engine<-interface queue of the port (menu keys/pointer)."""
        if os.environ.get('DQ_MENUDBG'): print('SEND frame %d port %d %s' % (self.frames, port, list(args)), flush=True)         # (test) interface -> engine messages
        if self.input_log is not None:                                                                    # (battle being recorded for its replay)
            if not self._menus_this_step: self._menu_active = self.active_menu()                         # (which menu the player was answering: the replay sends the choice to that one)
            self._menus_this_step.append((port,) + tuple(args))
        c = self.core
        a = list(struct.unpack('<%dh' % SHORTS_STACK, c.mem(self.buf1, 2 * SHORTS_STACK)))
        n = len(args); idx = a[64] or 65
        a[idx] = n
        for i, v in enumerate(args): a[idx + 1 + i] = v
        a[idx + n + 1] = 0
        if a[port]: a[a[32 + port]] = idx
        else: a[port] = idx
        a[32 + port] = idx + n + 1
        a[64] = idx + n + 2
        c.mem_w(self.buf1, struct.pack('<%dh' % SHORTS_STACK, *a))

    def params_message(self):
        """(number of visible lines - 1, height of a line, scroll) of the message canvas, as the engine holds them."""
        c = self.core; i16 = lambda ad: struct.unpack('<h', c.mem(ad, 2))[0]
        return i16(self.L + 0x2523a0), i16(self.obj_msg + 0x42), i16(self.obj_msg + 0x4a)

    def read_message(self):
        """Part of the canvas currently visible in the message window: n lines from the current scroll.
        -> (height x width) array of 0-255, or None."""
        a = self.read_canvas()
        if a is None: return None
        c = self.core
        i16 = lambda ad: struct.unpack('<h', c.mem(ad, 2))[0]
        lines = i16(self.L + 0x2523a0) + 1            # number of visible lines of the window (engine setting)
        lh = i16(self.obj_msg + 0x42)                  # height of a line (canvas pixels)
        scroll = i16(self.obj_msg + 0x4a)               # current scroll (the engine animates it by 8 pixels per frame)
        if not (1 <= lines <= 8 and 8 <= lh <= 64): lines, lh, scroll = 4, 28, -3
        import numpy as np
        h = lines * lh; top = max(0, scroll + 3)
        return a[(top + np.arange(h)) % a.shape[0]]                   # the canvas is circular (512 lines, REPEAT) and the engine's scroll grows without bound: like `ui_menu.select_language` (y & 0x1ff)

    def _finish_anims(self):
        c = self.core
        due = [a for a in self.anims if a[0] <= self.frames]
        if not due: return
        self.anims = [a for a in self.anims if a[0] > self.frames]
        table = struct.unpack('<Q', c.mem(self.fldobj + 8, 8))[0]
        for _, idx in due:
            ad = table + idx * 32 + 0x14
            c.mem_w(ad, bytes([c.mem(ad, 1)[0] & ~1]))

    def _finish_fbx_anims(self):
        """NativeManager.Update: for each 3D model animation in m_anim_list, FbxObject.IsEndAnimation (= not Animation.isPlaying); finished -> message (1, 0x1000 | slot) for the engine, which lowers
        ModelObject::motionFlag (setMotionEnd); without it ModelObject::isEnd stays false and the engine never hides or frees the model (spell effects: the image stayed on screen). A model freed in the meantime
        keeps its entry (m_model[slot] null: the entry is skipped). The clips come from the window (fbx_clips); model not yet read: we wait."""
        if not self.fbx_playing: return
        ends = []; keep = []; players = {}
        for slot in self.fbx_playing:
            m = self.state.fbx.get(slot)
            if m is None: keep.append(slot); continue
            if slot not in players:
                clips = self.fbx_clips(m['id']) if self.fbx_clips is not None else {}
                if clips is None: keep.append(slot); continue
                a = players[slot] = AnimPlayer(clips)
                for img, seq, force in m['anim']: a.play(seq, force, img)
                a.do_update(self.frames)
            a = players[slot]
            if a.cur is not None and not a._finished(a.cur, self.frames): keep.append(slot)
            else: ends.append(slot)
        self.fbx_playing = keep
        if ends:
            c = self.core; ad = struct.unpack('<Q', c.mem(self.L + MESSAGE_BUFFER, 8))[0]; self._messages_sent = True
            c.mem_w(ad, b''.join(struct.pack('<ii', 1, 0x1000 | s) for s in ends) + struct.pack('<i', -1))       # message type 1 = fin d'animation (identifiant >= 0x1000 : modele 3D, emplacement = identifiant & 0xff -> ModelObject::setMotionEnd)

    def catalog_status(self):
        """Mask of `getCatalogStatus`: bits 0-4 = valid bank, 5-9 = unreadable, 10-14 = corrupted, 15 = a file is missing."""
        return int(self.core.call(self.E('_ZN7profile8SaveLoad16getCatalogStatusEv'), label='getCatalogStatus')) & 0xffff

    def reread_savefiles(self):
        """After an import of saves: the engine reads the data1..5 / data9 files only when the start menu is created; it is made to read the catalog again (names, chapters, durations of the lists). -> new status mask."""
        for name_str in ('getCatalogView', 'getCatalogRecent'):
            self.core.call(self.E('_ZN7profile8SaveLoad%d%sEv' % (len(name_str), name_str)), label=name_str)
        return self.catalog_status()

    @staticmethod
    def initial_buttons_state(status):
        """What the engine sets when the start menu is created (`updateActiveDiary`): (a bank 0-2 contains data, bank 3 is valid, bank 4 is valid) -> grayed-out or absent buttons."""
        return (bool(status & 0x0007 or status & 0x00e0 or status & 0x1c00), bool(status & 0x0008), bool(status & 0x0010))

    def load_save(self, number):
        """number 1..5 -> reads data<number>.dat; the engine restarts the saved town"""
        r = self.core.call(self.E('_ZN7profile8SaveLoad8loadbankEi'), number - 1, label='loadbank')
        return bool(r)
