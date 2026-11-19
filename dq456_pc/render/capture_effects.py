"""Screen effects of the `Capture` class of the Unity layer (packet 34, value & 0xf = 3: travel / Chimaera Wings, 5: lamp / Ranaruta, 6: Riremito; 4, battle start, is in battle/battle_effect.py).

Pure module (numpy only, nothing graphical): shared constants and skeleton of the `Capture` loop. Each effect is a C# coroutine (`Capture.<Tabi>d__49`, `<DarkLamp>d__47`, `<Riremito>d__48`)
that `Capture.Caputer` advances by ONE step at each LateUpdate (30 Hz), in this order:
  1. if a capture is requested (`Snap`): the game camera (without the interface) is rendered into a texture, the "capture";
  2. if the blur is active (`SetBlur(actual)`): the interface camera renders the state of the PREVIOUS frame (blurred background + effect mesh) into a HALF-resolution texture (two textures alternating):
     this is the blurred background of the current frame, an afterimage;
  3. one call of `MoveNext` (one step: mesh vertices and colors); when the coroutine returns false, the game lowers bit 1 of `Global.Flag` that the engine was waiting for (`IsScreenEffectEnd`).
The vertices are in normalized screen coordinates (-1..1: the `Custom/Capture` and `Custom/CaptureBlur` shaders copy the position into `gl_Position`, without a matrix); the drawing is described by `drawings()`:
first the background (`Blend SrcAlpha Zero`: blur texture x color, replaces the screen), then the capture (`Blend SrcAlpha OneMinusSrcAlpha`), on a solid black background, the game camera being turned off.
The durations depend neither on chance (no `Random`) nor on a clock: everything is a function of the number of frames. The rules of each effect were read from the libil2cpp disassembly (addresses in comments),
then compared with the real machine code run under Unicorn (Tabi and lamp: vertices, colors, fields identical to the bit)."""
import math
import struct
import numpy as np

F32 = np.float32

KINDS = {3: 'tabi', 5: 'lamp', 6: 'riremito', 9: 'pegasus', 10: 'ido'}           # packet 34: value & 0xf -> effect (Capture.ScreenEffect, 0xCC6474); 9 and 10: DQ VI only (value & 0xff, pegasus_effect.py, ido_effect.py)
V2_ONLY = ('pegasus', 'ido')
NOT_AWAITED = ('pegasus',)                         # effects that do not raise bit 1 of Global.Flag (the engine goes on): their duration is not shortened
FRAMES = {'tabi': 64, 'tabi_return': 45, 'lamp': 64, 'riremito': 63, 'ido': 64, 'ido_return': 65, 'pegasus': 82, 'pegasus_return': 43}      # MoveNext calls up to the one that returns false (bit 1 drops at that call)
IDO_FADES = {False: ((43, 'out', 20),), True: ((1, 'black', 0), (4, 'in', 20))}      # DQ VI well: (call, Fade command, frames): departure SetFadeOutBlack(20) at ca = 40; arrival SetFadeOutBlack(0), then SetFadeIn(20)
BLACK_CALL = {'lamp': 63, 'riremito': 62}                # call (numbered from 1) where `Fade.SetFadeOutBlack(0)` turns the screen completely black at once (it stays black until the fade-in started by the engine)
FADE_IN_CALL = 3                                   # travel, arrival: `Fade.SetFadeIn(30)` is started at call 3 (effect setup)
FADE_IN = 30                                        # frames of this fade-in


def f32(bits):
    """32-bit float from its bit pattern (the libil2cpp literals, read as they are)."""
    return F32(struct.unpack('<f', struct.pack('<I', bits))[0])


def frames_of(kind, inverse=False):
    """Number of MoveNext calls of an effect (`inverse`: arrival of the travel, bit 7 of the packet value)."""
    return FRAMES[kind + '_return' if kind in ('tabi', 'ido', 'pegasus') and inverse else kind]


def calls_made(n, duration, frames):
    """MoveNext calls made when the effect has lived `n` engine frames (0 = the one where the packet arrived: the first call takes place in the same frame). `duration` = engine frames of the effect
    (`frames` when "Transition speed" is at x1, fewer afterward: the effect is then replayed faster, like the battle cascade), `frames` = its original calls."""
    return min(frames, int(math.ceil((n + 1) * frames / float(duration))))


class CaptureEffect:
    """Skeleton of `Capture`: the capture and the blur pass are done by the host (window), which registers in `on_blur`; the subclasses provide `_move_next` and `drawings`."""

    def __init__(self):
        self.frames = 0               # MoveNext calls already made
        self.finished = False             # MoveNext returned false: the game lowered bit 1 of Global.Flag
        self.render_active = False      # MeshRenderer of the Capture object: while it is turned off, the game stays displayed normally
        self.on_blur = None          # callback on_blur(effect, idx): "render drawings() (state of the previous frame) into blur texture no. idx, at half resolution"
        self.blur_read = None           # index of the blur texture read by the background of the current frame; None until a pass has taken place (black texture)
        self.blur_written = 0           # Capture.l_blurTexNum
        self._blur = False            # Capture.l_bBlur
        self._capture = False         # Capture.l_bCapture (Snap)

    def stage(self):
        """One `Capture` LateUpdate: capture (done by the host before the first call), blur pass, one MoveNext call. Returns true as long as the effect continues."""
        self._capture = False                 # Caputer: the capture is taken before MoveNext of the next call (the window has already copied it)
        if self._blur:
            i = self.blur_written
            if self.on_blur: self.on_blur(self, i)
            self.blur_read = i; self.blur_written = i ^ 1       # the background reads the texture that was just written; the first frame makes a second pass into the other texture, overwritten before being read: nothing to do
        suite = self._move_next()
        self.frames += 1
        if not suite: self.finished = True
        return suite

    def _move_next(self):
        return False

    def drawings(self):
        """List of drawings (name, positions (n, 2), uv (n, 2), rgba (n, 4)), in the game's order: 'blur' (background, replaces the screen: blur texture) then 'capture' (alpha blend: capture texture);
        'trail' (DQ VI: alpha blend over the rest: blur texture, or the capture before the first pass).
        Non-indexed triangles. Empty when the MeshRenderer is turned off."""
        return []


def triangle_grid(columns, rows):
    """Triangle indices of a grid of `columns` x `rows` cells whose vertices are laid out row by row (columns + 1 per row): (a, a+1, b) and (a+1, b+1, b), a = r * (columns + 1) + c, b = a + columns + 1
    (Tabi loop 0xCCB71C, lamp loop 0xCC895C: both have the same orientation)."""
    nx = columns + 1
    a = (np.arange(rows)[:, None] * nx + np.arange(columns)[None, :]).reshape(-1, 1)
    return (a + np.array([0, 1, nx, 1, nx + 1, nx])[None, :]).reshape(-1).astype(np.int32)


# the two triangles of the full-screen background (vertices: 0 top left, 1 bottom left, 2 top right, 3 bottom right) and its uv
BACKGROUND_TRIANGLES = np.array([0, 2, 1, 2, 3, 1])
BACKGROUND_CORNERS = np.array([[-1, 1], [-1, -1], [1, 1], [1, -1]], F32)
BACKGROUND_UV = np.array([[0, 1], [0, 0], [1, 1], [1, 0]], F32)
