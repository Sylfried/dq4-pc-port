"""Priority of the game over the player's settings (no dependencies: imported by the engine, the window and the tests).

Principle: a player setting is a DEFAULT VALUE, applied as long as the game does not itself set the parameter. As soon as the game sets it explicitly (script command, event lock,
scene camera...), its value applies, until it gives control back. The player does not take back what the script has decided.
The functions below are the pure rules (tested by tests/test_game_priority.py); the detection of "the game set it" is done by the caller (engine.py, window.py)."""

STANDARD_LETTERS = 4        # letters written per engine frame by an ordinary dialogue (speed word 1 of the window type array, x 4): the game's "default" value for the text
SCRIPT_FADE_MARK = 0x10000       # bit added (by the viewer) to the packet 9 integer of a fade started by a game script command (fade_in / fade_out); the engine does not use this bit


def effective_value(player_setting, game_value=None):
    """The value that applies: the game's when it has set one (game_value is not None), otherwise the player's setting."""
    return player_setting if game_value is None else game_value


def effective_factor(player_setting, game_fixed, neutral=1.0):
    """Player setting that MULTIPLIES a game quantity (speed, zoom): when the game itself sets the quantity (game_fixed true), the neutral factor applies and the game's value stays as is."""
    return effective_value(player_setting, neutral if game_fixed else None)


def letters_per_frame(player_setting, engine_letters, standard=STANDARD_LETTERS):
    """Letters written on this engine frame. `engine_letters` = what the engine is about to write (window speed word x 4). At the standard (ordinary dialogue), it is the player's setting; any other value
    (battle windows that display their line all at once, speed set by the game) is the game's and the player's setting changes nothing there."""
    return effective_value(player_setting, None if engine_letters == standard else engine_letters)


def fade_duration(duration, factor, script=False):
    """Duration (in frames) of a fade to black once the "Transition speed" setting is applied: the original duration divided by the factor (x1 = as is, a fade of one frame or less is immediate).
    A fade started by a game script command keeps its duration: the script has set it, and itself waits for that number of frames."""
    return effective_value(max(1, int(round(duration / factor))) if duration > 1 and factor > 1.0 else duration, duration if script else None)
