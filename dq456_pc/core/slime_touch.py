"""Dragon Quest V's Slime Touch: what Unity's SlimeTouchPort, SlimeTouchBehaviour and CgController do with the mini-game's port (menu port of category 5).

The engine draws the game itself (the board, the slimes, the score) with meshes of the orthographic layer (packet MESH_ORTHO) and its own windows. Unity adds:
- the "CG" animations, Resources prefabs `SlimeTouch/<name>` on the orthographic layer (layer 11): 1 = the countdown and "START" (`start_p`), 2 = "GAME OVER" (`gameover_p`),
  3 = sweat drops (`ase_p`, a loop), 4 to 7 = the four target boards (`board_p`, the clips "Take 001" to "Take 006"; their second material shows `board/slime`, `board/bes` or
  `board/metal`). CgController.Setup shifts each board by (number - 4) x 42 units in x (the other CGs keep their prefab's place);
- eight touch boxes (BoxCollider, 40 x 30 units, at BOXES), hit by a ray of the orthographic camera.

Messages of the engine (SlimeTouchPort.NoticeReceive): [0, on] touch boxes on / off; [1, cg] draw that CG this frame (it only advances while drawn); [2, id, cg, track] play: a board
(id 8 to 11 = board id - 4, cg 4 to 6 = its picture, track = the clip "Take <track + 1>"), otherwise the CG `cg`.
Messages to the engine: [0, box] (a touch in a box, while the boxes are on); after each frame (CgController.Update) the set of CGs playing: [1, set] when it changed, [2, set] when some
have just ended.
While the port exists, the scene camera is off and the orthographic camera clears its view to black (SlimeTouchPort's constructor).
"""

PORT_CATEGORY = 5                            # [port, 1, category, type] on port 0: MenuPortSystem creates a SlimeTouchPort
FILES = {1: 'start_p', 2: 'gameover_p', 3: 'ase_p', 4: 'board_p', 5: 'board_p', 6: 'board_p', 7: 'board_p'}          # CgController.cgInfo (prefixed by DATA_PATH "SlimeTouch/")
ONCE, LOOP = 1, 2                            # WrapMode
WRAP = {1: ONCE, 2: ONCE, 3: LOOP, 4: ONCE, 5: ONCE, 6: ONCE, 7: ONCE}
FIRST_BOARD, NORMA0 = 4, 8                   # CgController.SLIME_CG_norma0, NORMA0
BOARD_PICTURES = ('board/slime', 'board/bes', 'board/metal')          # CgController.tex (cg 4, 5, 6 of a board's play message)
X_STEP = 42.0                                # CgController.Setup: a board's position.x += (cg - 4) x 42 (cg >= 4 only)
BOXES = ((-68.0, -75.0), (1.0, -75.0), (72.0, -75.0), (-28.0, -114.0), (31.0, -114.0), (-68.0, -155.0), (1.0, -155.0), (68.0, -155.0))          # SlimeTouchBehaviour.boxInfo: centers
BOX_HALF = (20.0, 15.0)                      # half of its size (40 x 30)
FRAME = 1.0 / 30.0                           # one engine step
UP, DOWN, LEFT, RIGHT = 0x1, 0x2, 0x4, 0x8   # the engine's key bits (engine.UP...)
DIRECTIONS = {UP | LEFT: 0, UP: 1, UP | RIGHT: 2, LEFT: 3, RIGHT: 4, DOWN | LEFT: 5, DOWN: 6, DOWN | RIGHT: 7}          # keys / gamepad: the box on that side of the board (3 above, 2 beside, 3 below)


def prefab(cg):
    """Resources name of a CG's prefab."""
    return 'SlimeTouch/' + FILES[cg]


def new(port, clips):
    """State of a new port (SlimeTouchPort constructor: SlimeTouchBehaviour.Awake, CgController.Setup). clips(cg) -> {clip name: length in seconds}, or None if the prefab is unknown.
    Each CG: its clip, its time, playing or not (Setup plays each default clip at speed 0: "playing", frozen at its start)."""
    st = {'port': port, 'live': True, 'touch': False, 'draw': 0, 'play': 0, 'sent': 0, 'shown': 0, 'cg': {}, 'picture': {}}
    for cg in FILES:
        c = clips(cg) if clips else None
        names = sorted(c) if c else []
        st['cg'][cg] = {'lengths': dict(c or {}), 'clip': names[0] if names else None, 't': 0.0, 'playing': bool(names)}
    return st


def notice(st, a):
    """SlimeTouchPort.NoticeReceive."""
    if not a: return
    k = a[0]
    if k == 0 and len(a) >= 2: st['touch'] = (a[1] & 0xffff) != 0                    # SlimeTouchBehaviour.SetTouchState
    elif k == 1 and len(a) >= 2 and 1 <= a[1] <= 7: st['draw'] |= 1 << a[1]          # CgController.Draw
    elif k == 2 and len(a) >= 4: norma_set(st, a[1], a[2], a[3])


def norma_set(st, ident, cg, track):
    """CgController.NormaSet: plays a CG (Animation.Play: a clip already playing goes on, one that has ended starts again from its beginning; frozen until drawn)."""
    if ident & ~3 == NORMA0:
        if track > 5 or not FIRST_BOARD <= cg <= FIRST_BOARD + 2: return
        board = ident - FIRST_BOARD
        st['picture'][board] = BOARD_PICTURES[cg - FIRST_BOARD]          # the board's second material gets that picture
        c = st['cg'][board]; name_str = 'Take %03d' % (track + 1)
        if c['clip'] != name_str or not c['playing']: c['clip'] = name_str; c['t'] = 0.0          # (Animation.clip = that clip, Play: another clip was playing, it starts from 0)
        c['playing'] = True
        st['play'] |= (1 << board) | 0x80000000                          # (bit 31: a [1, set] message even when the board was already playing)
    elif 1 <= cg <= 7:
        c = st['cg'][cg]
        if not c['playing']: c['t'] = 0.0
        c['playing'] = c['clip'] is not None
        st['play'] |= 1 << cg


def update(st, dt=FRAME):
    """One frame (SlimeTouchBehaviour.Update -> CgController.Update, then Unity's animation step): which CGs are shown, the messages for the engine, the animations advance.
    -> list of messages ([1, set] or [2, set])."""
    finished = 0
    for cg in range(1, 8):
        b = 1 << cg
        if st['play'] & b and not st['cg'][cg]['playing']: finished |= b          # Animation.isPlaying false: that CG has ended
    shown = st['draw']; st['draw'] = 0; st['shown'] = shown
    out = []
    if st['play'] == st['sent']:
        if finished:
            st['play'] = (st['play'] & ~finished) & 0x7fffffff; out.append([2, st['play']]); st['sent'] = st['play']
    else:
        st['play'] = (st['play'] & ~finished) & 0x7fffffff; out.append([1, st['play']]); st['sent'] = st['play']
    for cg in range(1, 8):                                                # the animation step: speed 1 while drawn, 0 otherwise
        c = st['cg'][cg]
        if not (shown & (1 << cg)) or not c['playing']: continue
        c['t'] += dt
        length = c['lengths'].get(c['clip'], 0.0)
        if WRAP[cg] == LOOP: c['t'] = c['t'] % length if length > 0 else 0.0
        elif c['t'] >= length: c['playing'] = False; c['t'] = 0.0          # WrapMode.Once: stops and goes back to its first frame
    return out


def touch(st, x, y):
    """A touch at (x, y) in orthographic units: the first box hit while the boxes are on -> the message [0, box] for the engine, else None."""
    if not st['live'] or not st['touch']: return None
    for i, (cx, cy) in enumerate(BOXES):
        if abs(x - cx) <= BOX_HALF[0] and abs(y - cy) <= BOX_HALF[1]: return [0, i]
    return None


def shown(st):
    """The CGs drawn this frame: [(cg, prefab name, clip, time, board picture or None, x shift)]."""
    out = []
    for cg in range(1, 8):
        if not st['shown'] & (1 << cg): continue
        c = st['cg'][cg]
        out.append((cg, prefab(cg), c['clip'], c['t'], st['picture'].get(cg), (cg - FIRST_BOARD) * X_STEP if cg >= FIRST_BOARD else 0.0))
    return out


def box_of_direction(mask):
    """The box that a held direction (engine key mask, diagonals included) points at, or None."""
    return DIRECTIONS.get(mask & (UP | DOWN | LEFT | RIGHT))


def window_to_layer(x, y, width, height, half_height):
    """Window pixel (from the bottom left) -> orthographic units, the middle of the window = (0, 0), `half_height` units from the middle to the top edge."""
    k = height / 2.0 / half_height
    return (x - width / 2.0) / k, (y - height / 2.0) / k
