"""Font of the game's messages: the one the engine uses to draw dialogues and battle messages in its text canvas (SDrawCTRL / TextCanvas), not the SE-GARRIR menu font.

The file (`assets/English.font` of the data pack, copied into the cache by `extract_message_font`) is read as is, with ALL its glyphs: a character that the patch or another game of the series (DQ5, DQ6) adds to the font
therefore displays without changing anything here. Format (taken from `SFont::Load`, `FontHeader::GetGlyph`):
  - 28 header bytes: "TNOF", then (at byte 24) the height of a glyph cell (24);
  - table of 65,536 entries of 4 bytes (UTF-16 code -> entry): high byte = glyph width (bits 0 to 6) and flag (bit 7), the other 24 bits = position of the glyph in the data;
  - data: for each glyph, `width_px x height_px` opacity bytes (0 to 255), in rows, compressed: a byte "1xxxxxxx" repeats the next byte `xxxxxxx` times, a byte "0xxxxxxx" is followed by `xxxxxxx` bytes
    as is, a 0 byte ends it.
Placement (`SDrawCTRL::PutChar` 0x1575a0 and `TextCanvas::PutChar` 0x152820 of libdq4core.so; verified pixel for pixel against the real engine's canvas, tests/test_message_font.py): the write position advances by the
glyph width; a flagged glyph (V, W, t, v, w, y of the patch) is placed one pixel further left and advances two pixels less (kerning); the space advances by the engine's space width (6, `obj + 0x38`) and not by the
glyph width (5); the tab by `obj + 0x3c`; the wide space U+3000 by `obj + 0x3a`; line breaks (U+000A, U+000D) do nothing; "$" is not drawn for language 1 (English) and ";" is drawn
(like a space) only for language 2; a code absent from the font is drawn with the glyph of "@" (entry 0x40 of the table: `[FontHeader + 0x128]`). Each glyph REPLACES the pixels of its cell (there is no
blending); a gap between letters (`g_letterSpace`, 0 in game) is added to each advance.
**Tightening (deviation from the mobile game)**: a pair of glyphs drawn one after the other whose optical gap exceeds 3 empty columns ("f-", "t-", "To", "L'"...) is tightened (`kern`); the real engine is brought to it by a hook
on `SDrawCTRL::PutChar` (engine.py, `_text_hooks`), `plan` applies the same rule.
Module without pyglet: only `line` (a line's texture) needs it."""
import struct
import numpy as np

TABLE_SIZE = 65536
TABLE_START = 28
DATA_START = TABLE_START + 4 * TABLE_SIZE       # the game's file: the data follow the table (SFont::Load copies 0x40000 bytes of table)
BASELINE = 20                                    # row of the cell where the baseline passes: the bottom of capitals is at row 19 (measured on the engine's canvas: top cell 15 units below the frame, 1st baseline at 35 units, 20 + 15)
KERN_GAP = 3                                     # maximum optical gap (empty columns between the ink of two neighboring glyphs); beyond it, the tightening brings the gap back to this value
KERN_MAX = 4                                     # maximum kerning of a pair (pixels)
KERN_SKIP = '*'                                  # "*:" (speaker mark): keeps the game's spacing
CODE_DEFAULT = 0x40                                    # glyph for codes absent from the font: the "@"


class MessageFont:
    """Message font of the game (see the module). `width_px(text)`: advance of the write position (canvas pixels = interface units, 1 to 1); `line(text)`: the texture of a line, like BitmapFont."""
    PAD = 1                                           # margin columns on the left of the texture (a flagged glyph overflows by one pixel to the left of the write position)
    SCALE = 1.0                                         # one interface unit per canvas pixel (measured: 434 units wide for 0.8477 x 512 canvas pixels)

    LIMIT = 410                                      # width of a dialogue line in canvas pixels (`CTextAutoReturn`: [0x2523c4], value read from the engine during a dialogue)

    def __init__(self, path=None, data=None, language=1, space=6, wide_space=6, tab_width=15, spacing=0):
        if data is None:
            with open(path, 'rb') as f: data = f.read()
        if data[:4] != b'TNOF': raise ValueError('message font unreadable (signature)')
        self.d = data
        self.table = np.frombuffer(data, '<u4', TABLE_SIZE, TABLE_START)
        self.height_px = struct.unpack_from('<H', data, 24)[0] or 24
        self.base = DATA_START
        self.language, self.space, self.wide_space, self.tab_width, self.spacing = language, space, wide_space, tab_width, spacing
        self.tex = {}; self.wid = {}; self._g = {}
        self.G = self                                 # (for tools that test `code in font.G`)

    def __contains__(self, code):
        return 0 <= code < TABLE_SIZE and bool(self.table[code] >> 24)

    # ---- glyphs
    def glyph(self, code):
        """-> (flag, width, height x width uint8 bitmap) of the glyph for `code` (that of "@" if the font does not have it: GetGlyph)."""
        g = self._g.get(code)
        if g is None:
            e = int(self.table[code]) if 0 <= code < TABLE_SIZE else 0
            if not (e >> 24): e = int(self.table[CODE_DEFAULT])
            width_px = (e >> 24) & 0x7f; flag = (e >> 31) & 1; n = width_px * self.height_px
            output = bytearray(); i = self.base + (e & 0xffffff); d = self.d
            while len(output) < n and i < len(d):
                t = d[i]; i += 1; k = t & 0x7f
                if k == 0: break
                if t & 0x80: output += d[i:i + 1] * k; i += 1
                else: output += d[i:i + k]; i += k
            output = bytes(output[:n]).ljust(n, b'\0')
            g = self._g[code] = (flag, width_px, np.frombuffer(output, np.uint8).reshape(self.height_px, width_px) if width_px else np.zeros((self.height_px, 0), np.uint8))
        return g

    # ---- placement
    def plan(self, text):
        """-> (cells, end): cells = [(x, glyph)] with x the column of the cell (write position, minus 1 for a flagged glyph); end = write position at the end of the text."""
        pen = 0; cel = []; prev = None                  # prev: glyph drawn just before (None after a space, a tab or an undrawn character)
        for ch in text:
            c = ord(ch)
            if c > 0xffff: c = 0xfffd
            if c in (0x0a, 0x0d): prev = None; continue
            if c == 0x09: pen += self.tab_width; prev = None; continue
            if c == 0x20: pen += self.space; prev = None; continue
            if c == 0x3000: pen += self.wide_space; prev = None; continue
            if c == 0x24 and self.language == 1: prev = None; continue
            if c == 0x3b:
                if self.language == 2: pen += self.space
                prev = None; continue
            if prev is not None: pen -= self.kern(prev, c)
            g = self.glyph(c); flag, w = g[0], g[1]
            cel.append((pen - flag, g)); pen += (w - 2 if flag else w) + self.spacing; prev = c
        return cel, pen

    def advance(self, c):
        """Advance of the write position after glyph `c`; None if `c` is not a glyph (space, tab, line break, "$" or ";": the tightening state restarts from zero after them)."""
        if c in (0x09, 0x0a, 0x0d, 0x20, 0x3000, 0x3b) or (c == 0x24 and self.language == 1): return None
        g = self.glyph(c); return (g[1] - 2 if g[0] else g[1]) + self.spacing

    def _rows(self, c):
        """(column of the first, of the last ink of each row) of glyph `c`; -1 / large = empty row."""
        r = self._g.get(('rows', c))
        if r is None:
            bm = self.glyph(c)[2]; n = bm.shape[0]; left = np.full(n, 1 << 20); right = np.full(n, -1)
            for y in range(n):
                cols = np.flatnonzero(bm[y])
                if len(cols): left[y], right[y] = cols[0], cols[-1]
            r = self._g[('rows', c)] = (left, right)
        return r

    def kern(self, a, b):
        """Tightening (pixels) of the pair of glyphs a, b drawn one after the other (codes): the optical gap between their ink, row by row (a row of b is compared with those of a around it,
        to within one row: no diagonal contact), is reduced to at most KERN_GAP empty columns; 0 for pairs already tight, glyphs with no ink and pairs that begin with "*".
        The engine (hook on SDrawCTRL::PutChar) and `plan` apply the same rule; line wrapping (`cut_width`, `CTextAutoReturn`) does not know it: it does not change."""
        k = self._g.get(('kern', a, b))
        if k is None:
            k = 0
            if a != ord(KERN_SKIP):
                (fa, wa, _), (fb, _, _) = self.glyph(a)[:3], self.glyph(b)[:3]
                (_, ra), (lb, _) = self._rows(a), self._rows(b)
                shift = (wa - 2 if fa else wa) - fb + fa                  # column of b's cell, a's cell being at 0
                gaps = [shift + lb[y] - max(ra[max(y - 1, 0):y + 2]) - 1 for y in range(len(lb)) if lb[y] < 1 << 20 and max(ra[max(y - 1, 0):y + 2]) >= 0]
                if gaps: k = max(0, min(KERN_MAX, min(gaps) - KERN_GAP))
            self._g[('kern', a, b)] = k
        return k

    def width_px(self, text):
        """Advance of the write position on a line (canvas pixels): what is needed to break lines like the engine."""
        w = self.wid.get(text)
        if w is None:
            if len(self.wid) > 20000: self.wid.clear()
            w = self.wid[text] = self.plan(text)[1]
        return w

    def cut_width(self, c):
        """Width that a character adds to a line for the break computation (`CTextAutoReturn::AutoReturn`): like the drawing advance, but "$" counts its width (it is not drawn) and ";" counts 0."""
        k = ord(c)
        if k > 0xffff: k = 0xfffd
        if k == 0x09: return self.tab_width
        if k == 0x20: return self.space
        if k == 0x3b: return self.space if self.language == 2 else 0
        if k == 0x3000: return self.wide_space
        g = self.glyph(k)
        return (g[1] - 2 if g[0] else g[1]) + self.spacing

    def wrap_text(self, text, limit=None):
        """Lines of a text broken like the engine (`CTextAutoReturn::AutoReturn`, 0x157ed0): the line width is accumulated character by character; when it reaches the limit, it goes back to the last break point
        (after a space, a "㈠" or a hyphen) and moves to the next line; without a break point the overflowing character stays on the line. A line break in the text resets the width to zero, and one that follows
        immediately after an automatic break is swallowed. -> list of lines (the space before a break stays at the end of the line)."""
        limit = self.LIMIT if limit is None else limit
        t = text; n = len(t); i = 0; output = []; w = 0; cand = None      # cand = (i, output length) after the last break point
        while i < n:
            c = t[i]; i += 1
            if c == '\r': continue
            if c == '\n': output.append('\n'); w = 0; cand = None; continue
            w += self.cut_width(c); output.append(c)
            cut = c == ' ' or c == '\u3220'
            if c == '-':
                cut = True
                if self.language == 1: cut = not (i - 2 >= 0 and t[i - 2] == '-') and not (i < n and t[i] == '-')
            if cut: cand = (i, len(output))
            if w >= limit:
                if cand is not None:
                    i = cand[0]; del output[cand[1]:]
                output.append('\n'); w = 0; cand = None
                if i < n and t[i] == '\n': i += 1
        return ''.join(output).split('\n')

    def pixels(self, text):
        """Image (height x width, uint8) of the line, with the write position at column PAD: exactly what the engine writes into its canvas (each glyph replaces its cell)."""
        cel, end = self.plan(text)
        right = max([end] + [x + g[1] for x, g in cel]) + 2 * self.PAD
        a = np.zeros((self.height_px, max(right, 1)), np.uint8)
        for x, (_, w, bm) in cel:
            if w: a[:, self.PAD + x:self.PAD + x + w] = bm
        return a

    def line(self, text):
        """-> (texture, width, height, base) in canvas pixels; base = distance from the top of the image to the baseline (like BitmapFont.line)."""
        r = self.tex.get(text)
        if r is None:
            import pyglet
            from pyglet import gl
            if len(self.tex) > 800:
                for t, *_ in self.tex.values(): t.delete() if hasattr(t, 'delete') else None
                self.tex.clear()
            a = self.pixels(text); H, W = a.shape
            rgba = np.zeros((H, W, 4), np.uint8); rgba[..., :3] = 255; rgba[..., 3] = a
            img = pyglet.image.ImageData(W, H, 'RGBA', np.ascontiguousarray(rgba[::-1]).tobytes(), pitch=W * 4)
            t = img.get_texture(); gl.glBindTexture(t.target, t.id)
            gl.glTexParameteri(t.target, gl.GL_TEXTURE_MIN_FILTER, gl.GL_LINEAR); gl.glTexParameteri(t.target, gl.GL_TEXTURE_MAG_FILTER, gl.GL_LINEAR)      # bilinear filter, like the game's canvas texture
            gl.glTexParameteri(t.target, gl.GL_TEXTURE_WRAP_S, gl.GL_CLAMP_TO_EDGE); gl.glTexParameteri(t.target, gl.GL_TEXTURE_WRAP_T, gl.GL_CLAMP_TO_EDGE)
            r = self.tex[text] = (t, W, H, BASELINE)
        return r


def extract_message_font(apk_folder, cache, log=print, name_str='English.font', dest='ui_messages.font'):
    """Copies the game's message font from the game's data pack (split_UnityDataAssetPack.apk, assets/English.font) into the cache, only once. -> True if it is there."""
    import os, zipfile
    path = os.path.join(cache, dest)
    if os.path.exists(path): return True
    try:
        os.makedirs(cache, exist_ok=True)
        with zipfile.ZipFile(os.path.join(apk_folder, 'split_UnityDataAssetPack.apk')) as z: raw = z.read('assets/' + name_str)
        if raw[:4] != b'TNOF': raise ValueError('unexpected signature')
        with open(path + '.tmp', 'wb') as f: f.write(raw)
        os.replace(path + '.tmp', path); return True
    except Exception as ex:
        log('Message font not extracted (%r): using the SE-GARRIR menu font instead.' % (ex,)); return False
