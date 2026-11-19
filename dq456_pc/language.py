"""Language of the port's own texts: everything specific to the port (settings, history, saves, license, F1 information, console messages...).
The game's texts (dialogues, game menus, names) come from the game files: they follow the APK files of the game version (data\\apk\\<game>\\<code>), not this module.

Languages: one file per language in `dq456_pc/languages/`, named by its code, the language and the country in lower case (`fr-fr.json`, `en-us.json`, `pt-br.json`...): the same code names
the language's APK folder (`paths.Folders.choose_apk`). Any `<code>.json` there is a language of the port. A file holds the language's own name (as the language list shows it), the
ISO 3166 code of its flag (`dq456_pc/assets/flags/<flag>.png`), a line of help for the translators and every text, one entry per line, in the order of the English file:

    {"key": "display.contrast", "en": "Contrast", "text": "Contraste"},

`key`: the name of the text (it starts with its section, SECTIONS: the menu or theme it belongs to); `en`: the English text, the reference every translation starts from; `text`: the
text displayed in this language. An empty `text`, or one that does not fit the English one (other placeholders %s, %d..., other spaces at its edges, other line breaks: `check_text`),
is not used: English is displayed. The keys of the screens that add a language (ENGLISH_ONLY) are only in the English file: those screens are always in English. The language screen
adds a language (`create_language`: its file with the English texts and empty `text`s) and loads a file again after it is edited (`check_language`: what is translated, what is not).

"Language" setting (Display page): `system` (default: the computer's language when the port has it, otherwise English) or a language code. The code holds KEYS, never texts:
`tr('display.contrast')` returns the text of that key in the current language; a key with no text in it, or a language whose file is missing or broken, shows the English text; anything that is not a known key is returned
unchanged (game texts, numbers). Template texts are formatted AFTER translation: `tr('save_states.state_loaded') % n`. A help text can chain several keys separated by three spaces.
Module constants are marked with `N_` (the key is returned as is and translated when it is displayed).

Inside a sentence, `language_name(code)` gives a language's name in the language displayed (`language.name_<code>`; a language added later: its own name). `font_families` gives the
fonts of a label: the game font has the Latin and Japanese letters, not the Korean or the Chinese ones (those come from the system fonts)."""
import json
import os
import re
import sys

FOLDER = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'languages')    # one file per language: <code>.json
BUILT_IN = ('en-us', 'fr-fr', 'de-de', 'es-es', 'it-it', 'ja-jp', 'ko-kr', 'zh-cn', 'zh-tw')     # (the order of the language list; the languages added later come after, by code)
REFERENCE = 'en-us'                                      # the text every translation starts from, and the one shown when a language has none (a missing, empty or refused text)
FALLBACK = ('en-us', 'fr-fr')                            # (the game's APK folders a language without its own falls back on: paths.Folders.choose_apk)
SECTIONS = ('language', 'new_language', 'menu', 'common', 'display', 'sound', 'controls', 'keys', 'save_states', 'saves', 'history', 'new_game', 'difficulty', 'randomizer', 'interface', 'window', 'debug')      # (the first part of a key: its menu or theme)
ENGLISH_ONLY = 'new_language.'                           # (keys of the screens that add a language: only in the English file, always displayed in English)
HELP = ('Translate each "en" text into "text" (keep the codes such as %s, %d, %(name)s or {0}, the line breaks \\n and the spaces at the start or end). '
        'An empty "text" stays in English. Save as UTF-8, then press "Load the texts" in the language screen.')
OLD_CODES = {'en': 'en-us', 'fr': 'fr-fr', 'de': 'de-de', 'es': 'es-es', 'it': 'it-it', 'ja': 'ja-jp', 'ko': 'ko-kr', 'zh': 'zh-cn'}      # (codes of earlier versions: settings.json, folders)
SENTENCE_NAMES = {'en-us': 'language.name_en_us', 'fr-fr': 'language.name_fr_fr', 'de-de': 'language.name_de_de', 'es-es': 'language.name_es_es', 'it-it': 'language.name_it_it',
                  'ja-jp': 'language.name_ja_jp', 'ko-kr': 'language.name_ko_kr', 'zh-cn': 'language.name_zh_cn', 'zh-tw': 'language.name_zh_tw'}     # (each name in the language displayed)
CODE = re.compile(r'^[a-z]{2}-[a-z]{2}$')
KEY = re.compile(r'^[a-z0-9_]+\.[a-z0-9_]+$')
GAPS = re.compile(r'%[-+ #0]*\d*(?:\.\d+)?[sdifgxXrc%]|\{[^{}]*\}')
WINDOWS_PRIMARY = {0x09: 'en', 0x0C: 'fr', 0x07: 'de', 0x0A: 'es', 0x10: 'it', 0x11: 'ja', 0x12: 'ko', 0x04: 'zh'}      # primary language of a Windows identifier
TRADITIONAL = {0x0404, 0x0C04, 0x1404}                   # Windows identifiers of Chinese in traditional characters (Taiwan, Hong Kong, Macao)
ENGLISH_NAMES = {'english': 'en', 'french': 'fr', 'german': 'de', 'spanish': 'es', 'italian': 'it', 'japanese': 'ja', 'korean': 'ko', 'chinese': 'zh'}     # Windows locale names ("German_Germany")
SYSTEM_FONTS = {                                         # system fonts of the languages whose letters the game font may lack (Windows first, then Linux), by the language part of the code
    'ja': ('Yu Gothic UI', 'Meiryo UI', 'Meiryo', 'MS Gothic', 'Noto Sans CJK JP', 'Noto Sans JP'),
    'ko': ('Malgun Gothic', 'Gulim', 'Noto Sans CJK KR', 'Noto Sans KR', 'NanumGothic', 'UnDotum'),
    'zh-cn': ('Microsoft YaHei UI', 'Microsoft YaHei', 'SimHei', 'Noto Sans CJK SC', 'Noto Sans SC', 'WenQuanYi Micro Hei'),
    'zh': ('Microsoft JhengHei UI', 'Microsoft JhengHei', 'PMingLiU', 'Noto Sans CJK TC', 'Noto Sans TC', 'WenQuanYi Micro Hei'),
}
GAME_FONT_LAST = ('ko', 'zh')                            # languages whose letters the game font lacks: their system fonts come first (Japanese: GMaruGo / M+ are Japanese fonts)
LANGUAGES = []                                           # codes of the languages of the port (the files of FOLDER), in the order of the language list; `refresh` reads them again
NAMES = {}                                               # code -> its own name ("Français")
FLAGS = {}                                               # code -> flag code ("fr")
CHOICES = ['system']                                     # values of the "Language" setting
DEFAULT = 'system'
_request = DEFAULT
_current = None
_catalogs = {}
_files = {}                                              # code -> {key: text} as its file writes them (empty texts included)
PROBLEMS = {}                                            # code -> what keeps its file from being read whole


# ---- the language files ----------------------------------------------------------------------------------------------------
def path_of(code):
    """The file of language `code`: dq456_pc/languages/<code>.json."""
    return os.path.join(FOLDER, code + '.json')


def read_file(path):
    """(own name, flag, {key: text}, [problems]) of a language file (see the module); an entry that is not {"key": ..., "text": ...} is a problem, the others are still read.
    {key: text} is None when the file cannot be read at all (missing, not JSON: its problem says where)."""
    try:
        with open(path, encoding='utf-8-sig') as f: d = json.load(f)
    except (OSError, ValueError) as ex: return '', '', None, ['%s: %s' % (os.path.basename(path), ex)]
    if not isinstance(d, dict): return '', '', None, ['%s: not a JSON object' % os.path.basename(path)]
    texts = {}; problems = []
    entries = d.get('entries') if isinstance(d.get('entries'), list) else []
    for n, e in enumerate(entries, 1):
        key = e.get('key') if isinstance(e, dict) else None; text = e.get('text', '') if isinstance(e, dict) else None
        if not isinstance(key, str) or not KEY.match(key) or not isinstance(text, str): problems.append('entry %d: not {"key": ..., "text": ...}' % n); continue
        if key in texts: problems.append('%s: written twice' % key)
        texts[key] = text
    name, flag = (d.get(f) if isinstance(d.get(f), str) else '' for f in ('name', 'flag'))
    return name.strip(), flag.strip().lower(), texts, problems


def write_file(path, name, flag, items):
    """Writes a language file: its own name, its flag, the help line and [(key, English, text)], one entry per line (UTF-8, the system's line endings, as git writes the
    files out on it). -> True if the file changed (line endings apart)."""
    js = lambda v: json.dumps(v, ensure_ascii=False)
    body = ['  {"key": %s, "en": %s, "text": %s}' % (js(k), js(en), js(t)) for k, en, t in items]
    lines = ['{', ' "name": %s,' % js(name), ' "flag": %s,' % js(flag), ' "help": %s,' % js(HELP), ' "entries": ['] + [x + ',' for x in body[:-1]] + body[-1:] + [' ]', '}']
    data = (os.linesep.join(lines) + os.linesep).encode('utf-8')
    try:
        with open(path, 'rb') as f:
            if f.read().replace(b'\r\n', b'\n') == data.replace(b'\r\n', b'\n'): return False
    except OSError: pass
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, 'wb') as f: f.write(data)
    return True


def edges(t):
    return t[:len(t) - len(t.lstrip())], t[len(t.rstrip()):]


def check_text(reference, text):
    """None if `text` can stand for the English `reference` (same placeholders %s, %d... in the same order, same spaces at the edges, same line breaks), else what is wrong."""
    if not text.strip(): return 'empty'
    if GAPS.findall(reference) != GAPS.findall(text): return 'placeholders %s instead of %s' % (' '.join(GAPS.findall(text)) or 'none', ' '.join(GAPS.findall(reference)) or 'none')
    if edges(reference) != edges(text): return 'spaces at the start or end'
    if reference.count('\n') != text.count('\n'): return '%d line breaks instead of %d' % (text.count('\n'), reference.count('\n'))
    return None


def section_texts(code, section):
    """{key: text} of one section of a language (the keys that start with `section.`), as its file writes them."""
    return {k: t for k, t in _files.get(OLD_CODES.get(code, code), {}).items() if k.split('.', 1)[0] == section}


def save_language(code, name=None, flag=None):
    """Writes the file of language `code` again in the order of the English file, the English texts of today in "en", its own texts in "text" (a key it lacks: an empty text; a key
    English no longer has: left out); `name` / `flag`: those of a new language. A file that cannot be read is left as it is (a translation being written). -> True if it changed."""
    path = path_of(code); ref = read_file(path_of(REFERENCE))[2] or {}
    if os.path.exists(path):
        n, f, own, _ = read_file(path)
        if own is None: return False
    else: n, f, own = '', '', {}
    items = [(k, en, en if code == REFERENCE else own.get(k, '')) for k, en in ref.items() if code == REFERENCE or not k.startswith(ENGLISH_ONLY)]
    return write_file(path, name or n or code, (flag or f or code[3:]).lower(), items)


# ---- the languages ---------------------------------------------------------------------------------------------------------
def refresh():
    """Reads again which languages exist (dq456_pc/languages/<code>.json), their own names, flags and texts; forgets the catalogs built (a file edited changes them)."""
    try: entries = sorted(os.listdir(FOLDER))
    except OSError: entries = []
    found = [c for c, ext in map(os.path.splitext, entries) if ext == '.json' and CODE.match(c)]
    order = [c for c in BUILT_IN if c in found] + [c for c in found if c not in BUILT_IN]
    LANGUAGES[:] = order; CHOICES[:] = ['system'] + order
    for d in (NAMES, FLAGS, _catalogs, _files, PROBLEMS): d.clear()
    for code in order:
        name, flag, texts, problems = read_file(path_of(code))
        _files[code] = texts or {}; PROBLEMS[code] = problems
        NAMES[code] = name or code; FLAGS[code] = flag or code[3:]


def normalized(choice):
    """A setting's value with the codes of earlier versions brought up to date ('fr' -> 'fr-fr'); 'system' for anything unknown."""
    choice = OLD_CODES.get(choice, choice) if isinstance(choice, str) else choice
    if choice == 'systeme': choice = 'system'
    return choice if choice in CHOICES else DEFAULT


def system_language(reader=None):
    """The computer's language if the port has it (its own variant if the port has it, otherwise the first variant of that language: fr-be -> fr-fr; Chinese of Taiwan, Hong Kong or
    Macao -> traditional characters), otherwise English. `reader`: function with no argument that returns the interface language (tests)."""
    code = None
    try:
        code = reader() if reader else _interface_language()
    except Exception:
        code = None
    return _code_of(code) or REFERENCE


def _code_of(code):
    """A language of the port for `code`: Windows language identifier (integer, e.g. 0x040C), or text "fr_FR.UTF-8" / "de-AT" / "German_Germany"; None if none matches."""
    if code is None: return None
    if isinstance(code, int):
        lang = WINDOWS_PRIMARY.get(code & 0x3FF)
        if lang == 'zh': return _pick('zh', 'tw' if code in TRADITIONAL else 'cn')
        return _pick(lang, None) if lang else None
    t = str(code).strip().lower().replace('_', '-')
    m = re.match(r'^([a-z]{2})(?:-([a-z]{4}))?(?:-([a-z]{2}))?(?:[.@]|$)', t)
    if m:
        lang, script, region = m.groups()
        if lang == 'zh' and (script == 'hant' or region in ('tw', 'hk', 'mo')): region = 'tw'
        elif lang == 'zh': region = region if region in ('cn', 'sg') else 'cn'
        if any(c[:2] == lang for c in LANGUAGES): return _pick(lang, region)
    for name, lang in ENGLISH_NAMES.items():
        if t.startswith(name):
            if lang == 'zh': return _pick('zh', 'tw' if 'traditional' in t or 'taiwan' in t or 'hong' in t else 'cn')
            return _pick(lang, None)
    return None


def _pick(lang, region):
    """The language `lang`-`region` if the port has it, otherwise the first one of `lang`; None if the port has none."""
    if region and '%s-%s' % (lang, region) in LANGUAGES: return '%s-%s' % (lang, region)
    return next((c for c in LANGUAGES if c[:2] == lang), None)


def _interface_language():
    """The computer's display language: Windows (its locale name, "fr-CA"), otherwise the environment variables, otherwise the locale."""
    if sys.platform == 'win32':
        import ctypes
        lcid = ctypes.windll.kernel32.GetUserDefaultUILanguage()
        buf = ctypes.create_unicode_buffer(85)
        try:
            if ctypes.windll.kernel32.LCIDToLocaleName(lcid, buf, 85, 0): return buf.value
        except Exception: pass
        return lcid
    for k in ('LC_ALL', 'LC_MESSAGES', 'LANG', 'LANGUAGE'):
        v = os.environ.get(k)
        if v: return v.split(':')[0]
    import locale
    return (locale.getlocale()[0] or '')


def select_language(choice, reader=None):
    """Sets the language: `choice` among CHOICES (an earlier version's code is brought up to date; any other value: `system`). -> a language code."""
    global _request, _current
    _request = normalized(choice)
    _current = system_language(reader) if _request == 'system' else _request
    return _current


def current_language():
    """The code of the language displayed."""
    if _current is None: select_language(DEFAULT)
    return _current


def requested():
    """The chosen setting: 'system' or a language code."""
    return _request


def catalog(language=None):
    """{key: text} of a language (`language` None: the current one): the texts of its file that can stand for the English ones (an empty text, or one `check_text` refuses, is
    left out: English is displayed)."""
    language = OLD_CODES.get(language, language) if language else current_language()
    if language not in _catalogs:
        own = _files.get(language, {})
        if language == REFERENCE: _catalogs[language] = {k: t for k, t in own.items() if t}
        else:
            ref = catalog(REFERENCE)
            _catalogs[language] = {k: t for k, t in own.items() if k in ref and check_text(ref[k], t) is None}
    return _catalogs[language]


def tr(text):
    """The text of key `text` in the current language (English if the key has no text in that language); anything that is not a known key is returned unchanged."""
    if not isinstance(text, str): return text
    t = catalog().get(text)
    if t is None: t = catalog(REFERENCE).get(text)
    return text if t is None else t


def N_(text):
    """Marks a key held by a module constant, translated when it is displayed (returned as is)."""
    return text


def language_name(code):
    """Name of the language `code` in the language displayed, as written inside a sentence ("Switch the game to %s", "Game: %s"); a language added later: its own name."""
    if code in SENTENCE_NAMES: return tr(SENTENCE_NAMES[code])
    return NAMES.get(code, str(code))


def language_of_name(text):
    """The code of a language's own name ("Deutsch" -> 'de-de'), None for any other text (its label is written with that language's fonts)."""
    return next((c for c, n in NAMES.items() if n == text), None)


def font_families(game_fonts=(), language=None):
    """Font families of a label written in `language` (None: the current one): the game font first when it has the letters of the language, that language's system fonts otherwise."""
    lg = language or current_language()
    own = SYSTEM_FONTS.get(lg) or SYSTEM_FONTS.get(lg[:2], ())
    return own + tuple(game_fonts) if lg[:2] in GAME_FONT_LAST else tuple(game_fonts) + own


WIDE = '\u3000-\u30ff\u3400-\u9fff\uf900-\ufaff\uff00-\uffef'          # Japanese and Chinese characters and their punctuation (written without spaces; Korean has spaces)
_UNITS = re.compile(r'(\s*)([%s]|[^\s%s]+)' % (WIDE, WIDE))
NO_LINE_START = set('、。，．・：；！？）」』】〉》〕｝…ー')                  # (Japanese and Chinese punctuation never starts a line)


def wrap(text, width, measure):
    """Lines of `text` of at most `width` (measure(string) -> width): split at spaces (runs of spaces count as one), and between two Japanese or Chinese characters, whose texts have no
    spaces; a punctuation mark that cannot start a line stays at the end of the previous one; a word wider than the line stays whole on its own line."""
    lines = []; cur = ''
    for space, unit in _UNITS.findall(text):
        attempt = cur + (' ' if space and cur else '') + unit
        if cur and unit not in NO_LINE_START and measure(attempt) > width: lines.append(cur); cur = unit
        else: cur = attempt
    if cur: lines.append(cur)
    return lines


def plural_one(n):
    """True if `n` takes the singular: 0 and 1 in French, 1 elsewhere (the languages without plural write both forms the same)."""
    return n < 2 if current_language()[:2] == 'fr' else n == 1


def read_setting(path):
    """The "language" setting of a settings.json file (for console messages, before the settings are loaded); 'system' if absent or unreadable. An older file has it as "langue"
    (and 'systeme'), or with an earlier code ('fr')."""
    try:
        import json
        with open(path, encoding='utf-8') as f: d = json.load(f)
        return normalized(d.get('language', d.get('langue', DEFAULT)))
    except Exception:
        return DEFAULT


# ---- adding a language -----------------------------------------------------------------------------------------------------
def create_language(code, name, flag):
    """Creates the file of a new language: its own name, its flag, every text in English in "en" and an empty "text" to translate (until then, English is displayed)."""
    if not CODE.match(code): raise ValueError('language code: ' + code)
    if os.path.exists(path_of(code)): raise FileExistsError(path_of(code))
    save_language(code, name, flag); refresh()


def check_language(code):
    """Reads the files again (the one of `code` was edited) and checks it against English. -> (texts translated, texts still in English, [problems]); a problem: what keeps the file
    from being read, a text left out (its placeholders, its spaces at the edges or its line breaks differ from the English text), a key English does not have."""
    refresh()
    own = _files.get(code, {}); ref = catalog(REFERENCE); problems = list(PROBLEMS.get(code, ()))
    keys = [k for k in ref if code == REFERENCE or not k.startswith(ENGLISH_ONLY)]; done = 0
    for k in keys:
        t = own.get(k, '')
        if not t: continue
        why = None if code == REFERENCE else check_text(ref[k], t)
        if why: problems.append('%s: %s' % (k, why))
        else: done += 1
    problems += ['%s: no such key in English' % k for k in own if k not in ref]
    return done, len(keys) - done, problems


refresh()
