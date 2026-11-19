"""Gamepad inputs seen as extra "keys".

Each input of a controller (face button, shoulder, trigger, d-pad direction, stick direction) is a pseudo key code above any pyglet key code. The gamepad layer
(`window/gamepad.py`) sets `key_list[code]` and dispatches `on_key_press` / `on_key_release` with these codes, so that the game, the game's menus and the Esc menu read the gamepad
exactly as they read a keyboard key: through the action bindings of the "Controls" menu (third column, setting `manette`)."""
from dq456_pc.language import N_

PAD_BASE = 0x7F000000          # pseudo key codes start here (no pyglet key code is that high)

# (name, French label shown in the Controls menu: data, translated when drawn). Names follow the Xbox layout; other controllers are mapped by position (A = bottom button).
PAD_INPUTS = (
    ('PAD_UP', N_('settings.dpad_up')), ('PAD_DOWN', N_('settings.dpad_down')), ('PAD_LEFT', N_('settings.dpad_left')), ('PAD_RIGHT', N_('settings.dpad_right')),         # d-pad
    ('PAD_RS_UP', 'RS ↑'), ('PAD_RS_DOWN', 'RS ↓'), ('PAD_RS_LEFT', 'RS ←'), ('PAD_RS_RIGHT', 'RS →'),          # (RS = right stick; not translated, like the other names printed on a controller)
    ('PAD_A', 'A'), ('PAD_B', 'B'), ('PAD_X', 'X'), ('PAD_Y', 'Y'),
    ('PAD_LB', 'LB'), ('PAD_RB', 'RB'), ('PAD_LT', 'LT'), ('PAD_RT', 'RT'),
    ('PAD_BACK', 'Select'), ('PAD_START', 'Start'), ('PAD_L3', 'L3'), ('PAD_R3', 'R3'),
    ('PAD_TOUCH', N_('settings.touch_pad')),          # PlayStation touch pad click (DirectInput gives the click only, not the finger's position)
    ('PAD_LS_UP', 'LS ↑'), ('PAD_LS_DOWN', 'LS ↓'), ('PAD_LS_LEFT', 'LS ←'), ('PAD_LS_RIGHT', 'LS →'),          # left stick (its own inputs since the d-pad and the stick have a cell each; added at the end: the codes of the others do not move)
)
DPAD_OF_STICK = {'PAD_LS_UP': 'PAD_UP', 'PAD_LS_DOWN': 'PAD_DOWN', 'PAD_LS_LEFT': 'PAD_LEFT', 'PAD_LS_RIGHT': 'PAD_RIGHT'}
LABELS = dict(PAD_INPUTS)
SYMBOL = {name: PAD_BASE + i for i, (name, _) in enumerate(PAD_INPUTS)}
NAME = {code: name for name, code in SYMBOL.items()}
RESERVED = ('PAD_START',)          # Start opens the Esc menu (and closes it): like Esc, not reassignable

# Default binding of each action to a gamepad input (None: none; a list: several inputs). Families: 'XB' Xbox, 'PS' PlayStation, 'NS' Nintendo Switch. The inputs are
# positional, so PlayStation is Xbox's layout; on a Switch controller the bottom button is "B" and the right one "A" (Action = A on all three, as printed).
FAMILIES = ('XB', 'PS', 'NS')
_BASE = {
    'up': ['PAD_LS_UP', 'PAD_UP'], 'down': ['PAD_LS_DOWN', 'PAD_DOWN'], 'left': ['PAD_LS_LEFT', 'PAD_LEFT'], 'right': ['PAD_LS_RIGHT', 'PAD_RIGHT'],          # "Button 1": left stick, "Button 2": d-pad
    'cam_left': 'PAD_LB', 'cam_right': 'PAD_RB',          # camera: shoulders (LB / RB, L1 / R1, L / R); the right stick is the mouse
    'A': 'PAD_A', 'B': 'PAD_B', 'menu': 'PAD_Y', 'map': 'PAD_X', 'chat': ['PAD_L3', 'PAD_R3'], 'info': None, 'extra': 'PAD_BACK',          # (extra: DQ VI's vehicle command)
    'L': None, 'R': None, 'accel': 'PAD_RT', 'battle_speed': 'PAD_LT', 'modifier': None,
}
DEFAULTS = {
    'XB': dict(_BASE),                                                                       # Action A, Menu Y, Cancel B, Map X, Esc menu Menu (Start) (no more History key: View is free)
    'PS': dict(_BASE),                                                                       # Action ×, Menu △, Cancel ○, Map □, Esc menu Options (Start)
    'NS': dict(_BASE, A='PAD_B', B='PAD_A'),                                                 # Action A (right), Cancel B (bottom), Menu X (top), Map Y (left), Esc menu +
}
DEFAULT_PAD = DEFAULTS['XB']
OLD_DEFAULT_PAD = {                                                                          # the default: a binding still equal to it takes the new defaults (settings.py; cam_up / cam_down: actions removed)
    'up': 'PAD_UP', 'down': 'PAD_DOWN', 'left': 'PAD_LEFT', 'right': 'PAD_RIGHT',
    'cam_up': 'PAD_RS_UP', 'cam_down': 'PAD_RS_DOWN', 'cam_left': 'PAD_RS_LEFT', 'cam_right': 'PAD_RS_RIGHT',
    'A': 'PAD_A', 'B': 'PAD_B', 'menu': 'PAD_X', 'chat': 'PAD_Y', 'map': 'PAD_BACK', 'history': 'PAD_R3', 'info': 'PAD_L3',
    'L': 'PAD_LB', 'R': 'PAD_RB', 'accel': 'PAD_RT', 'battle_speed': 'PAD_LT', 'modifier': None,
}
MOUSE_STICK = 'right'          # the stick that moves the mouse pointer (the choice of the `pad_mouse` setting was removed: always the right one)


def inputs(value):
    """Inputs of a binding value: None -> (), a name -> (name,), a list -> its names."""
    if value is None: return ()
    return (value,) if isinstance(value, str) else tuple(value)


# What is printed on the controller, by family ('XB' Xbox, 'PS' PlayStation, 'NS' Nintendo; Xbox when the family is unknown): the inputs that are not face buttons are shown as text.
# The inputs are drawn with their picture (menus/prompts.py); this text is used where there is none. The inputs are positional (A = bottom button of any controller), so a Nintendo controller shows its "B" for PAD_A.
FACE = ('PAD_A', 'PAD_B', 'PAD_X', 'PAD_Y')
FAMILY_TEXT = {
    'XB': {'PAD_LB': 'LB', 'PAD_RB': 'RB', 'PAD_LT': 'LT', 'PAD_RT': 'RT', 'PAD_BACK': N_('settings.view'), 'PAD_START': 'Menu'},
    'PS': {'PAD_LB': 'L1', 'PAD_RB': 'R1', 'PAD_LT': 'L2', 'PAD_RT': 'R2', 'PAD_BACK': 'Create', 'PAD_START': 'Options', 'PAD_TOUCH': N_('settings.touch_pad')},
    'NS': {'PAD_LB': 'L', 'PAD_RB': 'R', 'PAD_LT': 'ZL', 'PAD_RT': 'ZR', 'PAD_BACK': '−', 'PAD_START': '+', 'PAD_L3': 'LS', 'PAD_R3': 'RS'},
}


def text_label(name, family='XB'):
    """Text shown for an input (or a list of inputs: "L3 / R3") in the Controls menu: the one printed on the controller of that family (the face buttons give their Xbox letter)."""
    if not isinstance(name, str): return ' / '.join(text_label(n, family) for n in inputs(name))
    return FAMILY_TEXT.get(family, FAMILY_TEXT['XB']).get(name) or LABELS.get(name) or name


def is_pad(symbol):
    return symbol in NAME


def valid_binding(value):
    """Is `value` something an action can be bound to (None, an input name that is not reserved, or a non-empty list of such names)?"""
    if value is None: return True
    if isinstance(value, str): return value in SYMBOL and value not in RESERVED
    return isinstance(value, (list, tuple)) and len(value) > 0 and all(isinstance(n, str) and n in SYMBOL and n not in RESERVED for n in value)


def _simple(names):
    """A list of inputs -> the value stored: None, a name, or a list."""
    names = list(dict.fromkeys(names))
    return None if not names else (names[0] if len(names) == 1 else names)


def with_stick(saved):
    """Binding saved before the left stick had its own inputs (PAD_UP... was the d-pad AND the stick): each d-pad direction is joined by the same stick direction, put first, so the
    stick goes on moving what it moved (unless the action already has two inputs: the player's choice is kept, the stick then has none). A binding that names a stick input is left as it is."""
    if not isinstance(saved, dict) or any(n in DPAD_OF_STICK for v in saved.values() if valid_binding(v) for n in inputs(v)): return saved
    out = dict(saved)
    for a, v in saved.items():
        if not valid_binding(v): continue
        names = list(inputs(v))
        for ls, dp in DPAD_OF_STICK.items():
            if dp in names and len(names) < 2: names.insert(names.index(dp), ls)
        out[a] = _simple(names)
    return out


def clean(saved, default=DEFAULT_PAD):
    """Binding read from a settings file -> valid binding: unknown actions and inputs dropped, an input given to two actions kept by the first one only, an action missing from the file
    takes its default inputs unless another action has taken them."""
    out = {}; taken = set()
    if isinstance(saved, dict):
        for a in default:
            if a in saved and valid_binding(saved[a]):
                keep = [n for n in inputs(saved[a]) if n not in taken]
                if keep or saved[a] is None: out[a] = _simple(keep); taken.update(keep)
    for a, n in default.items():
        if a not in out: keep = [x for x in inputs(n) if x not in taken]; out[a] = _simple(keep); taken.update(keep)
    return out
