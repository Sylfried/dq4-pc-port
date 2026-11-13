"""launch_dq4.bat: the console closes with the game window; messages in French or English depending on Windows' language. The file is read as text (without Windows): after the line that launches the game, `pause` is only allowed
in the block "if the exit code is not 0" (the game stopped on an error: the message is left readable), and the launcher returns the game's exit code. CRLF line endings are kept. The messages are labels
(`:m_xxx_fr` / `:m_xxx_en`) at the bottom of the file, called by `call :m_xxx_%DQLANG%`: each call must have both versions, the English one with no French word, and the file must stay ASCII.

    python3 tests/test_launcher.py"""
import os, re, unittest

HERE = os.path.dirname(os.path.abspath(__file__))
BAT = os.path.join(HERE, '..', 'launch_dq4.bat')


def lines():
    with open(BAT, 'rb') as f: raw_value = f.read()
    return raw_value, raw_value.decode('latin-1').split('\r\n')


def body():
    """The launcher's own lines: up to "exit /b %CODE%" (after that, there are only the message labels)."""
    _, l = lines()
    return l[:l.index('exit /b %CODE%') + 1]


def messages():
    """{label name: lines} for the `:m_...` labels."""
    _, l = lines(); res = {}; lookup_key = None
    for x in l[l.index('exit /b %CODE%') + 1:]:
        if x.startswith(':m_'): lookup_key = x[1:].strip(); res[lookup_key] = []
        elif lookup_key is not None and x.strip() and not x.lower().startswith('rem'): res[lookup_key].append(x)
    return res


class Launcher(unittest.TestCase):
    def test_windows_line_endings(self):
        raw_value, _ = lines()
        self.assertNotIn(b'\n', raw_value.replace(b'\r\n', b''), 'a lone line feed (LF) breaks the labels and blocks of cmd.exe')

    def test_console_closes_with_game(self):
        l = body()
        i = max(k for k, x in enumerate(l) if '-m dq4_pc' in x and 'import' not in x and '.chemins' not in x)                    # the line that launches the game
        after = l[i + 1:]
        self.assertTrue(any(x.strip().startswith('set "CODE=%errorlevel%"') for x in after[:2]), "the game's exit code must be read at once")
        level = 0; in_error = False
        for x in after:
            t = x.strip()
            if t.startswith('if not "%CODE%"=="0" ('): in_error = True; level = 1; continue
            if in_error:
                level += t.count('(') - t.count(')') if not t.startswith('echo') else 0
                if t == ')': in_error = False
                continue
            self.assertNotEqual(t.lower(), 'pause', 'a pause outside the error block would keep the console open after the game closes')
        self.assertTrue(any(x.strip() == 'pause' for x in after), 'on an error, the console must stay so that the message can be read')
        self.assertEqual(after[-1].strip(), 'exit /b %CODE%')

    def test_pauses_before_launch_are_preparation_errors(self):
        l = body()
        i = max(k for k, x in enumerate(l) if '-m dq4_pc' in x and 'import' not in x and '.chemins' not in x)
        for k, x in enumerate(l[:i]):
            if x.strip().lower() == 'pause':                                                              # each earlier pause follows a failure message (Python not found, installation...) or an "exit /b 1"
                context_text = ' '.join(l[max(0, k - 6):k + 2]).lower()
                self.assertTrue('exit /b 1' in context_text or 'call :m_' in context_text, 'pause without a message: line %d' % (k + 1))

    def test_each_message_is_called_and_returns(self):
        calls = set(re.findall(r'call :(m_\w+)', ' '.join(x for x in body() if not x.lower().startswith('rem'))))
        m = messages()
        self.assertGreaterEqual(len(calls), 10)
        for a in calls: self.assertIn(a, m, 'message without a label: ' + a)
        for lookup_key in m:
            self.assertIn(lookup_key, calls, 'etiquette jamais appelee : ' + lookup_key)
            self.assertEqual(m[lookup_key][-1].strip(), 'exit /b', 'the label %s must return (exit /b)' % lookup_key)

    def test_no_language_detection(self):
        l = ' '.join(x for x in lines()[1] if not x.lower().startswith('rem'))
        for word in ('PreferredUILanguages', 'LocaleName', 'DQLANG', '_fr', '_en'): self.assertNotIn(word, l, 'the launcher messages are in English only: ' + word)

    def test_messages_are_in_english(self):
        french = re.compile(r"\b(le|la|les|une?|des|du|est|sont|vient|refait|erreur|jeu|dossier|ici|relance|installe|echec|echoue|seule|fois|lit|tes|ton|menus simples|pour|depuis|puis|cette|coche|supprime|lance|lecture|creation|reprise|environnement|fenetres|dans|avec|sans|sur|ou)\b|'", re.I)
        for lookup_key, lg in messages().items():
            for x in lg:
                if x.strip().lower().startswith('title'): x = x[5:]
                remainder = re.sub(r'"[^"]*"|\^\(|\^\)|\b[\w\\.]+\.(bat|log|py)\b|data\\\S*|donnees\\\S*|dq4_pc\\\S*|DQ4_DATA|tools\\\S*', '', x)             # paths and proper names excluded
                self.assertIsNone(french.search(remainder), 'French word in %s: %s' % (lookup_key, x.strip()))

    def test_ascii_only(self):
        raw_value, _ = lines()
        raw_value.decode('ascii')                                                                                # the Windows console does not display accents without a setting: no non-ASCII byte


if __name__ == '__main__':
    unittest.main(verbosity=1)
