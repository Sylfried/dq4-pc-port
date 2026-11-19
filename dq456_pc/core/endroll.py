"""Dragon Quest V / VI end credits: what Unity's EndrollPort and Endroll do with the credits' port (menu port of category 3, the one Dragon Quest IV uses for StaffrollPort).

The credits are pictures of text: the atlas `endroll/Retro<5|6>_endroll_en_<NN>` (alpha only, colored by the vertices) and its layout `<same name>.bin` (TextAssets), one pair per
section of the credits (the port's type: 0 to 5 in DQ V, 0 to 4 in DQ VI). The last section has a second pair (`_2`), placed under the first. Layout: three uint16 (count, side of
the atlas, height of the whole column), then per line seven uint16: flags, width, height, x, y (in the column), u, v (in the atlas, from its top). Flags: bit 1 = light blue text
(Color32 0x5e, 0xff, 0xff), otherwise white; bit 0 (DQ V only) = a line whose arrival at mid-screen sends an event to the engine.

Endroll.Setup builds one mesh of all the lines (x - side / 2, -y), scaled by 256 / side, on layer 11 (the orthographic camera's: SceneCamera.s_DSSAOrthoCamera), hidden until the engine
sends [0] on the port (EndrollPort.NoticeReceive: the column is put at y = START_Y, the top of the phone's screen, and shown). Then at each frame (Endroll.internalUpdate) the column goes
up by SCROLL units; when its remaining height (counter) reaches 0 the port sends [1] to the engine. DQ V also sends [0, n] when a flagged line reaches mid-screen: n from a table of
the game (EVENTS, starting at EVENT_FIRST[section] for the section's first flagged line; past its end a random 0 to 2), and [1] after the last section's last one.
While the port exists, EndrollPort.SetupCamera turns the scene camera off and clears the orthographic camera's view to black: only layer 11 is seen.
"""
import random
import struct

START_Y = 227.555             # Endroll.POSITIVE_H: half the height of the phone's screen, in units of the orthographic layer
SCROLL = {'dq5': 1.82, 'dq6': 1.55}          # Endroll.SCROLL_DELTA, units per frame
LAST_SECTION = {'dq5': 5, 'dq6': 4}          # the section with a second atlas (Endroll.LAST_INDEX)
END_EXTRA = {'dq5': 0.0, 'dq6': -198.0}      # DQ VI: its last section stops counting 198 units earlier
WHITE = (255, 255, 255, 255)
BLUE = (0x5e, 0xff, 0xff, 0xff)              # Color32 0xffffff5e (flag bit 1)
# DQ V: Endroll's two tables (<PrivateImplementationDetails> arrays of 62 and 6 integers, read from the game's metadata)
EVENTS = (2, 2, 2, 2, 1, 2, 2, 2, 2, 2, 2, 1, 0, 1, 0, 0, 1, 0, 1, 0, 0, 1, 0, 2, 0, 2, 1, 0, 1, 0, 1, 0, 0, 1, 1, 2, 0, 1, 0, 0, 1, 0, 2, 1, 2, 0, 1, 2, 0, 1, 0, 0, 1, 0, 1,
          0, 2, 1, 2, 2, 0, 0)
EVENT_FIRST = (0, 4, 9, 13, 18, 24)


def asset_name(game, section, second=False):
    """Name of a section's atlas (its layout: the same + '.bin')."""
    return 'endroll/Retro%s_endroll_en_%02d%s' % (game[-1], section + 1, '_2' if second else '')


def parse(raw):
    """Layout TextAsset -> (side of the atlas, height of the column, [(flags, w, h, x, y, u, v)])."""
    n, side, height = struct.unpack_from('<3H', raw, 0)
    return side, height, [struct.unpack_from('<7H', raw, 6 + 14 * i) for i in range(n)]


def setup(game, section, load):
    """State of the credits of a section (Endroll.Setup). load(name) -> bytes of a TextAsset (None if missing)."""
    st = {'game': game, 'section': section, 'shown': False, 'pos': START_Y, 'counter': 0.0, 'timers': [], 'sent_end': False, 'lines': [], 'scale': 0.5,
          'rng': random.Random(section)}
    pages = [asset_name(game, section)] + ([asset_name(game, section, True)] if section == LAST_SECTION.get(game) else [])
    top = 0
    for k, name in enumerate(pages):
        raw = load(name.split('/')[-1] + '.bin') if load else None
        if raw is None:
            if k == 0: return None
            break
        side, height, lines = parse(raw)
        if k == 0: st['scale'] = 256.0 / side; st['counter'] = st['scale'] * height - 2 * START_Y + END_EXTRA.get(game, 0.0) * (section == LAST_SECTION.get(game))
        else: st['counter'] += st['scale'] * height
        for fl, w, h, x, y, u, v in lines:
            st['lines'].append({'page': k, 'atlas': name.split('/')[-1], 'side': side, 'x': x - side // 2, 'y': top + y, 'w': w, 'h': h, 'u': u, 'v': v, 'color': BLUE if fl & 2 else WHITE})
            if fl & 1 and game == 'dq5': st['timers'].append(st['scale'] * (top + y) - START_Y)
        top += height
    return st


def notice(st, a):
    """EndrollPort.NoticeReceive: [0] puts the column at the top of the screen and shows it; other messages do nothing."""
    if a and (a[0] & 0xffff) == 0: st['pos'] = START_Y; st['shown'] = True


def update(st):
    """Endroll.internalUpdate (one frame): the column goes up; returns the messages for the engine ([1] at the end, DQ V: [0, n] at each flagged line)."""
    out = []
    if not st['shown'] or st.get('stopped'): return out
    d = SCROLL.get(st['game'], 1.82)
    st['pos'] += d; st['counter'] -= d
    if st['counter'] <= 0 and not st['sent_end']:
        st['sent_end'] = True; out.append((1,))
        if st['game'] == 'dq6' and st['section'] == LAST_SECTION['dq6']: st['stopped'] = True
    last = len(st['timers']) - 1
    for i, t in enumerate(st['timers']):
        if t is None: continue
        t -= d; st['timers'][i] = t
        if t > 0: continue
        k = EVENT_FIRST[st['section']] + i if st['section'] < len(EVENT_FIRST) else len(EVENTS)
        out.append((0, EVENTS[k] if k < len(EVENTS) else st['rng'].randrange(3)))
        st['timers'][i] = None
        if st['section'] == LAST_SECTION['dq5'] and i == last: out.append((1,))
    return out


def visible_lines(st, half_height):
    """Lines of the column inside the view (orthographic units: y from -half_height to +half_height): [(line, x, top y, scale)]."""
    s = st['scale']; out = []
    for ln in st['lines']:
        top = st['pos'] - s * ln['y']
        if top - s * ln['h'] > half_height or top < -half_height: continue
        out.append((ln, s * ln['x'], top, s))
    return out
