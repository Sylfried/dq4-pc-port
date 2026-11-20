"""Loading bar of the startup's black screen: the engine, the save, the game's resources and the first map load before anything is shown (several seconds; much longer on a
first launch of a game or a language, when the title images, the portraits, the menu resources and the data pack are read from the APK files). A thin bar across the bottom of
the screen and its percentage say that the game is loading, not stuck. Not drawn over the entry logos (they cover the loading, as on mobile).

The steps are long single calls: the bar moves at each step (`show_loading`), at each line the once-only reads print (`loading_log`) and, while the engine loads in its
thread, toward 50 % with the time spent (`creep`)."""
import math
import pyglet
from pyglet import gl
from dq456_pc import language as LG
from dq456_pc.language import N_, tr

LOADING_TEXT = N_('window.loading_percent')
ENGINE_SHARE = (0.05, 0.5)          # the engine loading in its thread: from 5 to 50 %
ENGINE_TIME = 6.0                   # seconds: the bar goes toward 50 % as 1 - e^(-t / ENGINE_TIME) while the engine loads
TRACK, FILL, TEXT = (55, 55, 55), (235, 235, 235), (200, 200, 200, 255)


def creep(seconds):
    """Share of the bar while the engine loads, after `seconds`."""
    a, b = ENGINE_SHARE
    return a + (b - a) * (1.0 - math.exp(-max(0.0, seconds) / ENGINE_TIME))


def bar_geometry(w, h):
    """(x, y, width, height) of the bar in a `w` x `h` window: across the bottom, 10 % margins."""
    x = round(w * 0.1); bh = max(4, round(h * 0.008))
    return x, round(h * 0.035), w - 2 * x, bh


class LoadingBarMixin:
    load_fraction = 0.0                 # share shown (it never goes back)
    loading = True                      # the startup's loading: the once-only reads move the bar (False once the game runs: their lines are only printed)

    def load_progress(self, fraction):
        self.load_fraction = max(self.load_fraction, min(1.0, float(fraction)))

    def draw_load_bar(self):
        """The bar and its percentage over the current frame (black)."""
        x, y, bw, bh = bar_geometry(self.width, self.height)
        gl.glEnable(gl.GL_BLEND); gl.glBlendFunc(gl.GL_SRC_ALPHA, gl.GL_ONE_MINUS_SRC_ALPHA)
        pyglet.shapes.Rectangle(x, y, bw, bh, color=TRACK).draw()
        if self.load_fraction > 0: pyglet.shapes.Rectangle(x, y, max(1, round(bw * self.load_fraction)), bh, color=FILL).draw()
        pyglet.text.Label(tr(LOADING_TEXT) % round(100 * self.load_fraction), font_name=LG.font_families(), font_size=max(9.0, self.height / 64.0), color=TEXT,
                          x=self.width / 2, y=y + bh + self.height * 0.012, anchor_x='center', anchor_y='bottom').draw()

    def show_loading(self, fraction=None):
        """A black frame with the bar, shown at once (`fraction`: the share reached); the window stays alive between two loads of the startup."""
        if fraction is not None: self.load_progress(fraction)
        try:
            self.switch_to(); gl.glClearColor(0, 0, 0, 1); self.clear(); gl.glViewport(0, 0, *self.get_framebuffer_size())
            self.draw_load_bar(); self.flip(); self.dispatch_events()
        except Exception: pass

    def loading_log(self, upto):
        """`log` function of a once-only read of the startup: each line is printed and, during the startup, moves the bar a quarter of the way toward `upto`."""
        def log(*a):
            print(*a, flush=True)
            if self.loading: self.show_loading(self.load_fraction + (upto - self.load_fraction) * 0.25)
        return log
