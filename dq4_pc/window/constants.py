"""Window constants: camera, interface, world map, battle, sprites (values read from the original game or chosen for the port)."""
import math, os
import numpy as np
from dq4_pc.core import engine as ENGINE


BTN_SAVES = 8         # button number of the "Sauv. cloud" box of the start menu (type 53): the port puts "Saves" there
BTN_LANGUAGE = 12     # the port's language plate of the start menu, between "License" and "Saves" (ui_menu.LANGUAGE_BUTTON): never sent to the engine
SFX_BUTTON = 300               # sound effect of a menu button press (played by Unity, MenuPortItem.Update)
SFX_PADS = 0x810         # gamepad keys whose button plays SFX_BUTTON on press (MenuPortItem.Update: `m_gamepad & 0x810`): A (0x10) and action (0x800); B (0x20), back (0x400), arrows (1, 2, 4, 8) and zone 0x80 are silent
SFX_PREVIEW = 316                # test sound effect for the volumes (Son page of the Esc menu): floor damage (CommonWalkDamage::checkWalk), short and unrelated to the interface
COMMON_SFX = (300, 301, 302, 303, 304, 305, 306, 307, 308, 309, 310, 402, 409, 412)       # decoded from the start in a background task
MODE_PP = 4                   # last mode of the "Shader" menu (0 originals, 1 EPX x8, 4 pixel perfect: see settings.MODES_SPRITES): pixel perfect (sharp texels without any softening; world map at an integer scale, camera and sprites aligned on the pixels)
# Town camera, read in SceneCamera.Update / Global.CameraInitParams[0] (see docs/engine-patches.md):
ASPECT_PORTRAIT = 0.5625      # SceneCamera.ASPECT_DEF: the original is designed for a 450 x 800 portrait screen; Unity fixes the HORIZONTAL field of view (fov x 4/3) and derives the height from it
RESOLUTIONS = ((1280, 720), (1600, 900), (1920, 1080), (2560, 1440), (3840, 2160))
WINDOW_MARGIN = 100           # pixels at 100%: title bar, borders and taskbar around the drawing area
TOWN_FOV_DEFAULT = 9.5           # nominal fov of mode 0 (field) as long as the engine sends none (packet 11)
TOWN_NEAR, TOWN_FAR = 5.0, 100.0
ENDING_CHAPTER = 9                  # StoryStatus chapter during the ending (ev09 sets it; never reached in normal play)
ENDING_FRAMING = {'mqout': (5.2, 11.0)}      # ending scene -> (extra pitch in degrees, nominal fov): in 16:9 the window shows the phone's SHORT side up (12.7 degrees instead of 22.5), so the balloon hanging above the wall of `mqout` (the old man and the pink-haired girl look at it) fell out of the top of the screen; the camera is raised and widened a little (the characters stay in view), scaled down to nothing as the window gets taller (see CameraMixin._ending_framing)
DIST_ADJ_TOWN = 4.0          # SceneCamera.s_distanceAdjust (.cctor): after LookAt, the camera advances by 4 units along its axis
LOOK_DOWN_DEFAULT = 0.2                 # SceneCamera.s_lookDownAdjust (.cctor): the camera raises its pitch by 0.2 degree
EDGE_CORRECTION_DEFAULT = 0.0     # sprite edge correction (see Game._edge_correction): 0 = the game's original panel (default), 1 = rebuilt on screen (vertical edges)
SPRITE_L, SPRITE_H, SPRITE_SCALE = 24, 32, 0.036             # town panel 0.864 x 1.152, the game's (Chara: mesh4 0.48 x 0.64, localScale 1.8 x s, s = 1.0 on 99.5 % of the maps; was 0.045, x 1.25)
UI_ZOOM = 1.12            # magnification of the game windows (the original portrait column exactly fills the window height); reduced to 1 if a group of windows no longer fits on the screen
CB_MSG_BOTTOM = -338.0         # battle: bottom edge of the message frame = bottom edge of the main frame of the command menus (Combattre / Attaquer...)
CB_ZONE_MENUS = (-402.0, -144.0)       # battle: area taken by the command menus (Fuir / back button included); used to keep the same interface scale as the messages
MSG_BOTTOM = -362.0           # field message window moved down: bottom edge of the frame (interface units), like the battle messages
YESNO_BOX_SPACING = 1.0        # Yes/No (type 1): VISIBLE space between the bottom edge of the Yes / No stack and the top edge of the dialogue box (the stack is placed on its top right corner; 1 unit, like between Oui and Non; before: 4 units between the mesh cells, i.e. 8.5 visible)
TITLE_MAP = ENGINE.TITLE_MAP         # title screen map (sky, logo, island, dragon: a scene without a hero whose camera the game sets by itself; see _town_camera)
EXTENDED_SKIES = {'dpout': ('dpoutenk',), 'ev09': ('e9km1',)}         # maps whose sky plane (objects whose name contains these words) is extended on both sides by symmetry (player's choice: "extend the sky"): planes designed for the portrait screen left a large black corner on the left (ev09) or two (dpout, dungeon exit) in 16/9
CENTERED_WINDOWS = (54, 55)      # pre-game window types (StartMenuSelect: list of logs; StartNameEntry: gender choice) that the viewer centers on the screen
CH_PX, CH_ATLAS = 16.0, 64                                                  # world map: pixels per tile, tiles per atlas row
# world map water animation (the game's Field.UpdatePattern): 5 patterns; the displayed tile is the number + the pattern offset, which advances every 17 frames
CH_PATTERN_END = np.array([326, 403, 940, 1195, 1260, 1713])                  # end (exclusive) of each tile number range (Field.m_patternCheck)
CH_PATTERN_NUM = np.array([0, 1, 2, 0, 3, 4, 0])                              # pattern of each range (0 = fixed tile); the last value is used beyond the last range
CH_PATTERN_STEP = (0, 76, 4, 64, 4)                                            # offset added at each step, per pattern (Field.m_patternInfo.acc)
CH_PATTERN_LIMIT = (0, 608, 96, 512, 96)                                        # the offset falls back to 0 as soon as it reaches this limit (.limit)
CH_PATTERN_PERIOD = 17
CH_SCALE = 51.84 * 0.48 / 24                                              # Chara.SetFieldMode: scale 28.8 x 1.8 = 51.84 on a 0.48 x 0.64 mesh: the hero is ~24.9 x 33.2 px (1.04 x the 24 x 32 sheet), flat on the map
# SCALE: the phone in portrait 16:9 shows a short side (width) and a long side (height, x 16/9); in landscape 16:9 the port shows the same two
# values swapped (long side across, short side up), i.e. the same part of the world as the phone; other window shapes keep this base whole (see helpers.portrait_base_height).
CH_PHONE_SHORT = 256.0 / CH_PX                                             # world map: Field.Init sets the orthographic half-width to 128 map pixels: the phone shows 16 tiles across (and 28.4 up in portrait)
TOWN_CAM_DIST = 39.55          # TownCamera: distance from the camera to its target (the hero), the same on every map (45 maps measured on the engine); minus DIST_ADJ_TOWN = the hero's depth
FIELD_HERO_SHARE = SPRITE_H * CH_SCALE / CH_PX / CH_PHONE_SHORT          # world map: the hero's height / the height of the 16:9 window (33.2 map pixels of 256: 0.1296)
TOWN_HERO_SHARE = SPRITE_H * SPRITE_SCALE / (2 * (TOWN_CAM_DIST - DIST_ADJ_TOWN) * math.tan(math.radians(TOWN_FOV_DEFAULT * 4.0 / 3.0) / 2))          # town, dungeon, tower: the same at the game's camera (0.1460)
# (the two shares differ by 1.126 as on the phone: the world map and the towns keep their own zoom; are canceled)
CH_GUTTER = 2                                                                 # world map: gutter (repeated pixels) around each 16 px tile in the copied atlas: no tile bleeds onto its neighbor when filtering
CH_CELL = 16 + 2 * CH_GUTTER
CAM_JUMP_TOWN = 1.5                                                         # town units per engine step: beyond that, the camera's target jumped (cut, map change): no interpolation
CAM_JUMP_ROT = 0.35                                                          # rotation of the camera around its target (game or player): as long as the camera's displacement relative to its target, from one step to the next, stays under this share of the distance (about 20 degrees), it is a rotation,
                                                                             # interpolated like the rest; beyond that (scene angle set all at once), it is a cut
CAM_DRAG_STEP = 6                                                           # wheel click drag: at most this many game rotations (ENGINE.CAM_STEP each) per engine step, so that the camera follows the pointer (506 degrees per second)
CAM_DRAG_MAX = 180.0                                                       # rotation requested with the mouse and not yet done: cap in degrees (a large drag does not make the camera turn for long after the release)
ENGINE_STEP = 1.0 / 30.0                                                     # the original engine runs at 30 Hz (Time.fixedDeltaTime of Boot)
FAST_STEP_BUDGET = float(os.environ.get('DQ_STEP_BUDGET', '0.030'))                                                   # maximum duration (s) of engine steps within a single displayed frame when walking is accelerated (walking speed x2 to x4, accelerator): beyond that, the game falls behind instead of freezing the frame
JINGLE_SKIP = 30.0                                                            # battle clock factor while a jingle plays and the engine waits before its message (MSG_PAUSE): the wait goes by in a few frames (FAST_STEP_BUDGET)
CB_FOV_NOMINAL, CB_NEAR, CB_FAR, CB_YOFFSET, CB_SCENERY_SCALE = 48.0, 0.25, 500.0, 0.04, 6.0      # battle: Global.CameraInitParams[1] of the original Unity (nominal field of view; Unity multiplies it by 4/3 and applies it to the horizontal of a 4/3 view)
_cb = [float(x) for x in os.environ.get('DQ_CB', '0,0').split(',')]
CB_MIRROR_X, CB_DEC_Z = int(_cb[0]), _cb[1]      # (trials) left/right mirror; scenery offset on z
CB_CAP = 1536       # vertices reserved per monster (fixed-size lists)
CH_ICONS = {0: (0, 512, 48, 32), 1: (96, 512, 48, 32), 2: (192, 512, 48, 48), 3: (288, 512, 41, 32), 4: (384, 512, 41, 32), 5: (480, 512, 25, 31),
             6: (544, 512, 25, 31), 7: (608, 512, 40, 32), 8: (704, 512, 24, 24), 9: (768, 512, 32, 32), 10: (832, 512, 40, 32), 11: (928, 512, 24, 40),
             12: (0, 448, 32, 46), 13: (64, 448, 26, 28), 14: (128, 448, 41, 39), 15: (224, 448, 27, 42), 16: (288, 448, 48, 48), 17: (384, 448, 40, 32),
             19: (544, 448, 64, 58), 20: (640, 448, 41, 39)}   # world map place icons (FieldSymbol.s_symbols: 21 rectangles; number 18 is empty in the atlas)
SCENERY_BIAS = 4.0            # scenery: depth offset (in smallest depth units) between two groups drawn one after the other; 24 bits: 4 units = 2e-7 of the depth range, invisible for a real relief
ORIGINAL_GUTTER = 2                 # original sheets: 2 px gutter (repeated edges) around each cell, like the HD sheets: filtering no longer catches a bit of the neighboring cell
HD_GUTTER, HD_LEVELS = 4, 2      # HD sprites (x8 enlargement, see hd.py): 4 px margin, 2 mipmap levels
FONTS = ('Segoe UI', 'Arial', 'DejaVu Sans', 'Liberation Sans')
EDGE_ACTIONS = ('menu', 'chat', 'map', 'L', 'R')       # actions whose press is detected (rising edge)
BTN_TALK, BTN_MENU, BTN_CHAT, BTN_MAP = 0x100, 0x800, 0x400, 0x1000     # arg2 of GameUpdate: talk / examine (exactly 0x100), command menu, party chat, map
ENDING_KING = ('caf2a', 36, 1.6)     # test shortcut: map of Bastione's throne room, sprite of its king (character 36), distance (town units) within which a talk is his
ENDING_OF_CHAPTER = {5: 1, 6: 2}     # the setting `test_ending_which` (chapter whose ending the shortcut plays: 5 = Psaro defeated, 6 = Aamon defeated, Psaro joins) -> argument of Engine.start_ending
GROUP_SLOTS = 10      # world map: slots 0 to 9 = party members (hero in 0); 10 to 12 = vehicles (boat, balloon...)

def button_sfx(pad):
    """True if pressing a menu button of gamepad key `pad` plays SFX_BUTTON in the original game (A and action only). The keyboard follows the same rule as the finger."""
    return bool(pad & SFX_PADS)
CLOSE_MENU_STEPS = 120             # engine steps at most to close the game's menu behind "Settings" (Divers list, then root menu: two back presses, a few steps each)
