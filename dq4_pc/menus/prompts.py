"""Pictures of the keys and gamepad buttons in the "Controls" menu: Kenney "Input Prompts" (CC0, www.kenney.nl), 128 x 128 PNG files in
dq4_pc/assets/input_prompts (only the ones used here; licence: LICENSE.txt in that folder, docs/licenses.md).

The gamepad inputs are positional (`PAD_A` = the bottom face button of any controller, see persistence/pad_inputs.py): the family of the connected controller decides the picture
('XB' Xbox, 'PS' PlayStation, 'NS' Nintendo Switch: its bottom button is printed "B"). A key or an input with no picture keeps its text (left / right modifiers, numeric keypad digits...)."""
import os

FOLDER = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), 'assets', 'input_prompts')

_COMMON = ('PAD_UP', 'PAD_DOWN', 'PAD_LEFT', 'PAD_RIGHT', 'PAD_RS_UP', 'PAD_RS_DOWN', 'PAD_RS_LEFT', 'PAD_RS_RIGHT')


def _family(prefix, dpad, stick, faces, rest):
    d = dict(zip(_COMMON, ['%s_%s' % (dpad, s) for s in ('up', 'down', 'left', 'right')] + ['%s_%s' % (stick, s) for s in ('up', 'down', 'left', 'right')]))
    d.update(zip(('PAD_A', 'PAD_B', 'PAD_X', 'PAD_Y'), faces)); d.update(rest)
    return d


PAD_FILES = {
    'XB': _family('xbox', 'xbox_dpad', 'xbox_stick_r', ('xbox_button_color_a', 'xbox_button_color_b', 'xbox_button_color_x', 'xbox_button_color_y'),
                  {'PAD_LB': 'xbox_lb', 'PAD_RB': 'xbox_rb', 'PAD_LT': 'xbox_lt', 'PAD_RT': 'xbox_rt', 'PAD_BACK': 'xbox_button_view', 'PAD_START': 'xbox_button_menu',
                   'PAD_L3': 'xbox_stick_l_press', 'PAD_R3': 'xbox_stick_r_press'}),
    'PS': _family('playstation', 'playstation_dpad', 'playstation_stick_r', ('playstation_button_color_cross', 'playstation_button_color_circle', 'playstation_button_color_square', 'playstation_button_color_triangle'),
                  {'PAD_LB': 'playstation_trigger_l1', 'PAD_RB': 'playstation_trigger_r1', 'PAD_LT': 'playstation_trigger_l2', 'PAD_RT': 'playstation_trigger_r2', 'PAD_BACK': 'playstation5_button_create',
                   'PAD_START': 'playstation5_button_options', 'PAD_L3': 'playstation_button_l3', 'PAD_R3': 'playstation_button_r3', 'PAD_TOUCH': 'playstation5_touchpad'}),
    'NS': _family('switch', 'switch_dpad', 'switch_stick_r', ('switch_button_b', 'switch_button_a', 'switch_button_y', 'switch_button_x'),          # (positional: bottom "B", right "A", left "Y", top "X")
                  {'PAD_LB': 'switch_button_l', 'PAD_RB': 'switch_button_r', 'PAD_LT': 'switch_button_zl', 'PAD_RT': 'switch_button_zr', 'PAD_BACK': 'switch_button_minus', 'PAD_START': 'switch_button_plus',
                   'PAD_L3': 'switch_stick_l_press', 'PAD_R3': 'switch_stick_r_press'}),
}

KEY_FILES = {**{c: 'keyboard_' + c.lower() for c in 'ABCDEFGHIJKLMNOPQRSTUVWXYZ'}, **{'_%d' % i: 'keyboard_%d' % i for i in range(10)}, **{'F%d' % i: 'keyboard_f%d' % i for i in range(1, 13)},
             'UP': 'keyboard_arrow_up', 'DOWN': 'keyboard_arrow_down', 'LEFT': 'keyboard_arrow_left', 'RIGHT': 'keyboard_arrow_right', 'SPACE': 'keyboard_space', 'RETURN': 'keyboard_enter',
             'ENTER': 'keyboard_enter', 'NUM_ENTER': 'keyboard_numpad_enter', 'TAB': 'keyboard_tab', 'BACKSPACE': 'keyboard_backspace', 'ESCAPE': 'keyboard_escape', 'DELETE': 'keyboard_delete', 'INSERT': 'keyboard_insert',
             'HOME': 'keyboard_home', 'END': 'keyboard_end', 'PAGEUP': 'keyboard_page_up', 'PAGEDOWN': 'keyboard_page_down', 'CAPSLOCK': 'keyboard_capslock', 'COMMA': 'keyboard_comma',
             'PERIOD': 'keyboard_period', 'SEMICOLON': 'keyboard_semicolon', 'COLON': 'keyboard_colon', 'EXCLAMATION': 'keyboard_exclamation', 'MINUS': 'keyboard_minus', 'PLUS': 'keyboard_plus',
             'EQUAL': 'keyboard_equals', 'SLASH': 'keyboard_slash_forward', 'BACKSLASH': 'keyboard_slash_back', 'NUM_ADD': 'keyboard_numpad_plus', 'APOSTROPHE': 'keyboard_apostrophe',
             'BRACKETLEFT': 'keyboard_bracket_open', 'BRACKETRIGHT': 'keyboard_bracket_close', 'ASTERISK': 'keyboard_asterisk', 'NUM_MULTIPLY': 'keyboard_asterisk',
             'LSHIFT': 'keyboard_shift', 'RSHIFT': 'keyboard_shift', 'LALT': 'keyboard_alt', 'RALT': 'keyboard_altgr',
             'LCTRL': 'keyboard_ctrl', 'RCTRL': 'keyboard_ctrl'}
# (pyglet names the main Enter key 'ENTER' as well as 'RETURN' (same code): both are the main key; the keypad's is 'NUM_ENTER'. both Shift keys show the hollow arrow printed on keyboards, the left Alt
# "ALT", the right one "ALT GR" (French keyboards): pictures drawn by tools/make_key_pictures.py from Kenney's keys; both Ctrl keys "CTRL", same tool)


def path(file):
    """Full path of a picture of the folder, or None if it is not there."""
    p = os.path.join(FOLDER, file + '.png')
    return p if os.path.isfile(p) else None


def pad_file(family, name):
    """Picture of gamepad input `name` on a controller of `family` (Xbox if the family is unknown), or None."""
    f = PAD_FILES.get(family, PAD_FILES['XB']).get(name)
    return path(f) if f else None


def key_file(name):
    """Picture of keyboard key `name` (pyglet key name, as stored in the settings), or None."""
    f = KEY_FILES.get(name) if name else None
    return path(f) if f else None


_images = {}


def image(p):
    """PIL RGBA image of a picture (read once)."""
    if p not in _images:
        from PIL import Image
        _images[p] = Image.open(p).convert('RGBA')
    return _images[p]
