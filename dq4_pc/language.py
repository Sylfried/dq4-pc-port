"""Language of the port's own texts: French or English for everything specific to the port (settings, history, saves, license, F1 information, console messages...).
The game's texts (dialogues, game menus, names) come from the game files and do not change.

"Language" setting (Display page): `system` (default: French if Windows is in French, whatever the variant, otherwise English), `en`, `fr`.

The code holds KEYS, never texts: `tr('settings.battle_speed')` returns the text of that key in the current language, read from `dq4_pc/texts/<language>/<domain>.py`
(`TEXTS = {key: text}`, one file per domain: settings, menus, window, misc). A key with no text in the current language falls back to French; anything that is not a known key is
returned unchanged (game texts, numbers). Template texts are formatted AFTER translation: `tr('window.state_loaded') % n`. A help text can chain several keys separated by three spaces.
Module constants are marked with `N_` (the key is returned as is and translated when it is displayed): `ACTIONS = (('up', N_('settings.up')), ...)` then `tr(label)` when drawing."""
import importlib
import os
import sys

CHOICES = ('system', 'en', 'fr')                         # values of the "Language" setting
DEFAULT = 'system'
LANGUAGES = ('fr', 'en')
DOMAINS = ('settings', 'menus', 'window', 'misc')        # the files of dq4_pc/texts/<language>/ (each one defines TEXTS = {key: text})
_request = DEFAULT
_current = None
_catalogs = {}


def system_language(reader=None):
    """'fr' if the computer is in French (any variant: France, Belgium, Canada, Switzerland...), otherwise 'en'. `reader`: function with no argument that returns the interface language (tests)."""
    code = None
    try:
        code = reader() if reader else _interface_language()
    except Exception:
        code = None
    return 'fr' if _is_french(code) else 'en'


def _is_french(code):
    """`code`: Windows language identifier (integer, e.g. 0x040C), or text "fr_FR.UTF-8" / "fr-BE" / "French_France"."""
    if code is None: return False
    if isinstance(code, int): return (code & 0x3FF) == 0x0C              # primary identifier 0x0C = French (all variants)
    t = str(code).strip().lower().replace('-', '_')
    return t.startswith('fr') and (len(t) == 2 or t[2] in '_.@' or t.startswith('french'))


def _interface_language():
    """The computer's display language: Windows (GetUserDefaultUILanguage), otherwise the environment variables, otherwise the locale."""
    if sys.platform == 'win32':
        import ctypes
        return ctypes.windll.kernel32.GetUserDefaultUILanguage()
    for k in ('LC_ALL', 'LC_MESSAGES', 'LANG', 'LANGUAGE'):
        v = os.environ.get(k)
        if v: return v.split(':')[0]
    import locale
    return (locale.getlocale()[0] or '')


def select_language(choice, reader=None):
    """Sets the language: `choice` among CHOICES (any other value: `system`). -> 'fr' or 'en'."""
    global _request, _current
    _request = choice if choice in CHOICES else DEFAULT
    _current = system_language(reader) if _request == 'system' else _request
    return _current


def current_language():
    """'fr' or 'en'."""
    if _current is None: select_language(DEFAULT)
    return _current


def requested():
    """The chosen setting: 'system', 'en' or 'fr'."""
    return _request


def catalog(language=None):
    """{key: text} of a language (`language` None: the current one), read once from dq4_pc/texts/<language>/."""
    language = language or current_language()
    if language not in _catalogs:
        c = {}
        for domain in DOMAINS:
            c.update(importlib.import_module('dq4_pc.texts.%s.%s' % (language, domain)).TEXTS)
        _catalogs[language] = c
    return _catalogs[language]


def tr(text):
    """The text of key `text` in the current language (French if the key has no text in that language); anything that is not a known key is returned unchanged."""
    if not isinstance(text, str): return text
    t = catalog().get(text)
    if t is None and current_language() != 'fr': t = catalog('fr').get(text)
    return text if t is None else t


def N_(text):
    """Marks a key held by a module constant, translated when it is displayed (returned as is)."""
    return text


def read_setting(path):
    """The "language" setting of a settings.json file (for console messages, before the settings are loaded); 'system' if absent or unreadable. An older file has it as "langue" (and 'systeme')."""
    try:
        import json
        with open(path, encoding='utf-8') as f: d = json.load(f)
        v = d.get('language', d.get('langue', DEFAULT))
        v = 'system' if v == 'systeme' else v
        return v if v in CHOICES else DEFAULT
    except Exception:
        return DEFAULT
