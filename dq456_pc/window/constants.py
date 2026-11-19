"""Window constants: camera, interface, world map, battle, sprites (values read from the original game or chosen for the port)."""
import math, os
import numpy as np
from dq456_pc.core import engine as ENGINE
from dq456_pc import games as GM


BTN_SAVES = 8         # button number of the "Sauv. cloud" box of the start menu (type 53): the port puts "Saves" there
BTN_LANGUAGE = 12     # the port's language plate of the start menu, between "License" and "Saves" (ui_menu.LANGUAGE_BUTTON): never sent to the engine
SFX_BUTTON = 300               # sound effect of a menu button press (played by Unity, MenuPortItem.Update)
SFX_PADS = 0x810         # gamepad keys whose button plays SFX_BUTTON on press (MenuPortItem.Update: `m_gamepad & 0x810`): A (0x10) and action (0x800); B (0x20), back (0x400), arrows (1, 2, 4, 8) and zone 0x80 are silent
SFX_PREVIEW = 316                # test sound effect for the volumes (Son page of the Esc menu): floor damage (CommonWalkDamage::checkWalk), short and unrelated to the interface
COMMON_SFX = (300, 301, 302, 303, 304, 305, 306, 307, 308, 309, 310, 402, 409, 412)       # decoded from the start in a background task
MODE_PP = 4                   # last mode of the "Shader" menu (0 originals, 1 EPX x8, 4 pixel perfect: see settings.MODES_SPRITES): pixel perfect (sharp texels without any softening; world map at an integer scale, camera and sprites aligned on the pixels)
# Town camera, read in SceneCamera.Update / Global.CameraInitParams[0] (see docs/engine-patches.md):
ASPECT_PORTRAIT = 0.5625      # SceneCamera.ASPECT_DEF: the original is designed for a 450 x 800 portrait screen; Unity fixes the HORIZONTAL field of view (fov x 4/3) and derives the height from it
ORTHO_HALF_WIDTH = 128.53125      # DQ V / VI, SceneCamera.SystemInit: s_DSSAOrthoCamera (orthographic, at (0, 0, 100), facing +Z) has orthographicSize = 128.53125 / aspect: the phone shows x from -128.5 to +128.5
RESOLUTIONS = ((1280, 720), (1600, 900), (1920, 1080), (2560, 1440), (3840, 2160))
WINDOW_MARGIN = 100           # pixels at 100%: title bar, borders and taskbar around the drawing area
TOWN_FOV_DEFAULT = 9.5           # nominal fov of mode 0 (field) as long as the engine sends none (packet 11)
TOWN_NEAR, TOWN_FAR = 5.0, 100.0
ENDING_CHAPTER = 9                  # StoryStatus chapter during the ending (ev09 sets it; never reached in normal play)
ENDING_FRAMING = {'mqout': (5.2, 11.0)}      # ending scene -> (extra pitch in degrees, nominal fov): in 16:9 the window shows the phone's SHORT side up (12.7 degrees instead of 22.5), so the balloon hanging above the wall of `mqout` (the old man and the pink-haired girl look at it) fell out of the top of the screen; the camera is raised and widened a little (the characters stay in view), scaled down to nothing as the window gets taller (see CameraMixin._ending_framing)
DIST_ADJ_TOWN = ENGINE.SCENE_DISTANCE_ADJUST          # SceneCamera.s_distanceAdjust (.cctor): after LookAt, the camera advances by 4 units along its axis
LOOK_DOWN_DEFAULT = ENGINE.SCENE_LOOK_DOWN                 # SceneCamera.s_lookDownAdjust (.cctor): the camera raises its pitch by 0.2 degree
EDGE_CORRECTION_DEFAULT = 0.0     # sprite edge correction (see Game._edge_correction): 0 = the game's original panel (default), 1 = rebuilt on screen (vertical edges)
SPRITE_L, SPRITE_H, SPRITE_SCALE = 24, 32, 0.036             # town panel 0.864 x 1.152, the game's (Chara: mesh4 0.48 x 0.64, localScale 1.8 x s, s = 1.0 on 99.5 % of the maps; was 0.045, x 1.25)
UI_ZOOM = 1.12            # magnification of the game windows (the original portrait column exactly fills the window height); reduced to 1 if a group of windows no longer fits on the screen
CB_MSG_BOTTOM = -338.0         # battle: bottom edge of the message frame = bottom edge of the main frame of the command menus (Combattre / Attaquer...)
CB_ZONE_MENUS = (-402.0, -144.0)       # battle: area taken by the command menus (Fuir / back button included); used to keep the same interface scale as the messages
MSG_BOTTOM = -362.0           # field message window moved down: bottom edge of the frame (interface units), like the battle messages
YESNO_BOX_SPACING = 1.0        # Yes/No (type 1): VISIBLE space between the bottom edge of the Yes / No stack and the top edge of the dialogue box (the stack is placed on its top right corner; 1 unit, like between Oui and Non; before: 4 units between the mesh cells, i.e. 8.5 visible)
TITLE_MAP = ENGINE.TITLE_MAP         # title screen map (sky, logo, island, dragon: a scene without a hero whose camera the game sets by itself; see _town_camera)
EXTENDED_SKIES = {'dq4': {'dpout': ('dpoutenk',), 'ev09': ('e9km1',)},         # maps whose sky plane (objects whose name contains these words) is extended on both sides by symmetry (player's choice: "extend the sky"): planes designed for the portrait screen left a large black corner on the left (ev09) or two (dpout, dungeon exit) in 16/9
                  'dq5': {'ev17': ('ev17km',)},
                  'dq6': {'e02din1': ('e01d5dt', 'e02dt3', 'e02wt03', 'e02km01a', 'e02km01b', 'e02stkm'), 'e21din1': ('e21sky', 'e21kgkm'), 'e15din1': ('e12sky02',), 'e12din2': ('e12sky02',)}}.get(GM.profile().key, {})      # (per game: the three games reuse the same map names; DQ V's title: its cloud layers stop inside a 16:9 window;
                                                                                                    #  DQ VI's title: its sky, the world map and the sea under it stop inside the window, more on the right; so do the cloud planes of its credits
                                                                                                    #  (e02km01a / b) and the haze layers above the world map (e02stkm))
                                                                                                    #  e21din1 (the flight in the golden sky): its sky is 24 units wide and its cloud layers little more, the camera backs away until black bands
                                                                                                    #  stand on both sides of a 16:9 window; e12din2 / e15din1: the sky plane seen from the foot of the cliff stops inside the window
CENTERED_WINDOWS = (54, 55)      # pre-game window types (StartMenuSelect: list of logs; StartNameEntry: gender choice) that the viewer centers on the screen
CH_PX, CH_ATLAS = 16.0, 64                                                  # world map: pixels per tile, tiles per atlas row
# world map water animation (the game's Field.UpdatePattern): 5 patterns; the displayed tile is the number + the pattern offset, which advances every 17 frames
CH_PATTERN_END = np.array([326, 403, 940, 1195, 1260, 1713])                  # end (exclusive) of each tile number range (Field.m_patternCheck)
CH_PATTERN_NUM = np.array([0, 1, 2, 0, 3, 4, 0])                              # pattern of each range (0 = fixed tile); the last value is used beyond the last range
CH_PATTERN_STEP = (0, 76, 4, 64, 4)                                            # offset added at each step, per pattern (Field.m_patternInfo.acc)
CH_PATTERN_LIMIT = (0, 608, 96, 512, 96)                                        # the offset falls back to 0 as soon as it reaches this limit (.limit)
CH_PATTERN_PERIOD = 17
# DQ V / VI: no water patterns on the Unity side (the engine animates its own tile numbers); a tile sent is atlas cell (bits 0-11) | orientation << 12 (FieldSet, the native function that
# Field.SetIndexList calls: for each orientation, the texture point of each corner of the quad, 0 / 1 / 2 = left (top) edge, middle, right (bottom) edge of the cell). Corners in the order of
# the port's quads (NW, NE, SE, SW); orientations 8 and 9 show a half of the cell; any other one is drawn as 0.
CH_ORIENT_V2 = np.array([[(0, 0), (2, 0), (2, 2), (0, 2)], [(2, 0), (0, 0), (0, 2), (2, 2)], [(0, 0), (0, 2), (2, 2), (2, 0)], [(0, 2), (0, 0), (2, 0), (2, 2)],
                         [(2, 2), (0, 2), (0, 0), (2, 0)], [(2, 0), (2, 2), (0, 2), (0, 0)], [(0, 2), (2, 2), (2, 0), (0, 0)], [(2, 2), (2, 0), (0, 0), (0, 2)],
                         [(0, 2), (1, 2), (1, 1), (0, 1)], [(1, 1), (2, 1), (2, 0), (1, 0)]] + [[(0, 0), (2, 0), (2, 2), (0, 2)]] * 6, np.float32) / 2.0
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
CB_FOV_NOMINAL, CB_NEAR, CB_FAR, CB_YOFFSET, CB_SCENERY_SCALE = 48.0, 0.25, 500.0, 0.04, 6.0      # battle: Global.CameraInitParams[1] of the original Unity (nominal field of view; Unity multiplies it by 4/3 and applies it to the horizontal of a 4/3 view)
_cb = [float(x) for x in os.environ.get('DQ_CB', '0,0').split(',')]
CB_MIRROR_X, CB_DEC_Z = int(_cb[0]), _cb[1]      # (trials) left/right mirror; scenery offset on z
CB_CAP = 1536       # vertices reserved per monster (fixed-size lists)
CH_ICONS_DQ4 = {0: (0, 512, 48, 32), 1: (96, 512, 48, 32), 2: (192, 512, 48, 48), 3: (288, 512, 41, 32), 4: (384, 512, 41, 32), 5: (480, 512, 25, 31),
             6: (544, 512, 25, 31), 7: (608, 512, 40, 32), 8: (704, 512, 24, 24), 9: (768, 512, 32, 32), 10: (832, 512, 40, 32), 11: (928, 512, 24, 40),
             12: (0, 448, 32, 46), 13: (64, 448, 26, 28), 14: (128, 448, 41, 39), 15: (224, 448, 27, 42), 16: (288, 448, 48, 48), 17: (384, 448, 40, 32),
             19: (544, 448, 64, 58), 20: (640, 448, 41, 39)}   # world map place icons (FieldSymbol.s_symbols: 21 rectangles; number 18 is empty in the atlas)
# DQ V: FieldSymbol.s_symbols has 42 rectangles (its static constructor), given here whole (a transparent margin draws nothing)
CH_ICONS_V2 = {'dq5': {0: (0, 288, 64, 32), 1: (64, 288, 64, 54), 2: (128, 288, 64, 64), 3: (192, 288, 48, 32), 4: (240, 288, 48, 32), 5: (288, 288, 32, 32), 6: (320, 288, 32, 32),
                       7: (352, 288, 48, 32), 8: (400, 288, 48, 32), 9: (448, 288, 32, 32), 10: (480, 288, 32, 32), 11: (528, 288, 48, 32), 12: (576, 288, 32, 16), 13: (608, 288, 32, 64),
                       14: (640, 288, 32, 64), 15: (688, 288, 32, 32), 16: (720, 288, 48, 32), 17: (768, 288, 48, 32), 18: (816, 288, 48, 64), 19: (864, 288, 48, 64), 20: (912, 288, 16, 32),
                       21: (944, 288, 16, 32), 22: (976, 288, 16, 32), 23: (0, 224, 32, 32), 24: (48, 224, 32, 64), 25: (96, 224, 32, 32), 26: (144, 224, 64, 64), 27: (224, 224, 64, 64),
                       28: (288, 224, 64, 64), 29: (352, 224, 48, 32), 30: (400, 224, 64, 32), 31: (464, 224, 32, 32), 32: (496, 224, 32, 32), 33: (528, 224, 32, 32), 34: (16, 64, 16, 32),
                       35: (48, 64, 16, 32), 36: (80, 64, 16, 32), 37: (0, 128, 32, 32), 38: (32, 128, 32, 32), 39: (128, 128, 64, 64), 40: (0, 96, 32, 32), 41: (80, 112, 32, 32)},
               # DQ VI: 53 rectangles in its own 512 x 512 texture `symbol` (Field/symbol), as (u0, v0, u1, v1) fractions; the mesh is (u1 - u0) x (v1 - v0) x 512 px (FieldSymbol.ChangeMesh);
               # number 52 (top right corner of the texture) is empty
               'dq6': {0: (0, 512, 64, 64), 1: (64, 512, 64, 64), 2: (128, 512, 64, 64), 3: (192, 512, 64, 64), 4: (256, 512, 64, 32), 5: (320, 512, 64, 32), 6: (384, 512, 64, 32),
                       7: (448, 512, 64, 32), 8: (0, 448, 32, 32), 9: (32, 448, 32, 32), 10: (64, 448, 32, 32), 11: (96, 448, 32, 32), 12: (128, 448, 32, 32), 13: (160, 448, 48, 32),
                       14: (208, 448, 32, 32), 15: (240, 448, 32, 64), 16: (272, 448, 32, 64), 17: (304, 448, 32, 32), 18: (336, 448, 32, 32), 19: (368, 448, 48, 64), 20: (416, 448, 16, 32),
                       21: (448, 448, 32, 32), 22: (480, 448, 32, 32), 23: (0, 384, 32, 64), 24: (48, 384, 32, 64), 25: (96, 384, 64, 64), 26: (160, 384, 64, 64), 27: (224, 384, 64, 64),
                       28: (288, 384, 32, 64), 29: (336, 384, 32, 32), 30: (368, 384, 32, 32), 31: (400, 384, 32, 32), 32: (432, 384, 32, 32), 33: (464, 384, 32, 32), 34: (0, 320, 64, 64),
                       35: (64, 320, 16, 32), 36: (80, 320, 16, 16), 37: (96, 320, 48, 32), 38: (144, 320, 48, 32), 39: (192, 320, 48, 32), 40: (240, 320, 48, 32), 41: (288, 320, 32, 32),
                       42: (320, 320, 32, 32), 43: (352, 320, 64, 64), 44: (416, 320, 32, 32), 45: (448, 320, 32, 32), 46: (480, 320, 32, 32), 47: (0, 256, 32, 32), 48: (32, 256, 32, 32),
                       49: (64, 256, 32, 32), 50: (96, 256, 32, 32), 51: (128, 256, 32, 32)}}
CH_ICONS = CH_ICONS_V2.get(GM.profile().key, CH_ICONS_DQ4)        # (ox, bottom, w, h) in the icon texture (CH_ICON_TEXTURE), as above
CH_ICON_TEXTURE = {'dq6': ('symbol', 512)}.get(GM.profile().key, (None, 1024))      # texture of the place icons (None: the field atlas) and its size in pixels
SCENERY_BIAS = 4.0            # scenery: depth offset (in smallest depth units) between two groups drawn one after the other; 24 bits: 4 units = 2e-7 of the depth range, invisible for a real relief
ORIGINAL_GUTTER = 2                 # original sheets: 2 px gutter (repeated edges) around each cell, like the HD sheets: filtering no longer catches a bit of the neighboring cell
HD_GUTTER, HD_LEVELS = 4, 2      # HD sprites (x8 enlargement, see hd.py): 4 px margin, 2 mipmap levels
FONTS = ('Segoe UI', 'Arial', 'DejaVu Sans', 'Liberation Sans')
EDGE_ACTIONS = ('menu', 'chat', 'map', 'extra', 'L', 'R')       # actions whose press is detected (rising edge)
BTN_TALK, BTN_MENU, BTN_CHAT, BTN_MAP = 0x100, 0x800, 0x400, 0x1000     # arg2 of GameUpdate: talk / examine (exactly 0x100), command menu, party chat, map
GROUP_SLOTS = 10      # world map: slots 0 to 9 = party members (hero in 0); 10 to 12 = vehicles (boat, balloon...)

def button_sfx(pad):
    """True if pressing a menu button of gamepad key `pad` plays SFX_BUTTON in the original game (A and action only). The keyboard follows the same rule as the finger."""
    return bool(pad & SFX_PADS)
CLOSE_MENU_STEPS = 120             # engine steps at most to close the game's menu behind "Settings" (Divers list, then root menu: two back presses, a few steps each)
