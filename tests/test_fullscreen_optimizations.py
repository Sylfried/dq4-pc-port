"""Test of the removal of the Windows compatibility checkbox "Disable fullscreen optimizations" (`helpers.restore_fullscreen_optimizations`).

Windows only: here the registry (`winreg`) and the system are simulated. Verifies: nothing outside Windows; the checkbox set is removed for the venv interpreter AND the base interpreter;
the other settings are kept, the value is deleted when none remain; nothing to do = no write; a value of another type is left intact; a missing key or an error has no consequence.

    python3 -m pytest tests/test_fullscreen_optimizations.py -q -p no:cacheprovider
"""
import os, sys, types, unittest

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), '..'))
from dq4_pc.window import helpers as H

SZ, DWORD = 1, 4
VENV, BASE = r'C:\proj\.venv\Scripts\python.exe', r'C:\Python313\python.exe'
FLAG = 'DISABLEDXMAXIMIZEDWINDOWEDMODE'


class FakeKey:
    def __init__(self, values): self.values = values
    def __enter__(self): return self
    def __exit__(self, *a): return False


def fake_winreg(values, writes, missing_key=False):
    def query(k, name):
        if name not in k.values: raise FileNotFoundError(name)
        return k.values[name]
    def set_value(k, name, r, kind, data): k.values[name] = (data, kind); writes.append((name, data))
    def delete_value(k, name): del k.values[name]; writes.append((name, None))
    def open_key(root, path, r, access):
        if missing_key: raise FileNotFoundError(path)
        return FakeKey(values) if (root, path) == ('HKCU', H.FSO_KEY) else 1 / 0
    return types.SimpleNamespace(HKEY_CURRENT_USER='HKCU', KEY_QUERY_VALUE=1, KEY_SET_VALUE=2, REG_SZ=SZ,
                                 OpenKey=open_key, QueryValueEx=query, SetValueEx=set_value, DeleteValue=delete_value)


class Restore(unittest.TestCase):
    def run_on(self, values, platform='win32', winreg=None, missing_key=False):
        writes = []; old = (sys.platform, sys.executable, getattr(sys, '_base_executable', None), sys.modules.get('winreg'))
        sys.platform, sys.executable, sys._base_executable = platform, VENV, BASE
        sys.modules['winreg'] = winreg or fake_winreg(values, writes, missing_key)
        try: return H.restore_fullscreen_optimizations(), writes
        finally:
            sys.platform, sys.executable, sys._base_executable = old[:3]
            if old[3] is None: del sys.modules['winreg']
            else: sys.modules['winreg'] = old[3]

    def test_not_windows_nothing(self):
        values = {os.path.normpath(BASE): ('~ ' + FLAG, SZ)}
        self.assertEqual(self.run_on(values, 'linux'), ([], [])); self.assertEqual(values, {os.path.normpath(BASE): ('~ ' + FLAG, SZ)})

    def test_removes_the_value_of_both_interpreters(self):
        values = {os.path.normpath(VENV): ('~ ' + FLAG, SZ), os.path.normpath(BASE): ('~ ' + FLAG, SZ)}; done, writes = self.run_on(values)
        self.assertEqual(sorted(done), sorted([os.path.normpath(VENV), os.path.normpath(BASE)])); self.assertEqual(values, {})

    def test_keeps_the_other_flags(self):
        x = os.path.normpath(BASE); values = {x: ('~ RUNASADMIN ' + FLAG, SZ)}
        self.run_on(values); self.assertEqual(values[x], ('~ RUNASADMIN', SZ))

    def test_nothing_to_remove_nothing_written(self):
        x = os.path.normpath(BASE); values = {x: ('~ RUNASADMIN', SZ)}
        done, writes = self.run_on(values); self.assertEqual((done, writes), ([], [])); self.assertEqual(values, {x: ('~ RUNASADMIN', SZ)})
        self.assertEqual(self.run_on({}), ([], []))                    # (no value for these interpreters)

    def test_idempotent(self):
        values = {os.path.normpath(BASE): ('~ ' + FLAG, SZ)}; self.run_on(values)
        self.assertEqual(self.run_on(values), ([], []))

    def test_other_value_type_untouched(self):
        x = os.path.normpath(BASE); values = {x: (b'\x01', 3)}
        self.run_on(values); self.assertEqual(values[x], (b'\x01', 3))

    def test_missing_key_or_error_without_consequence(self):
        self.assertEqual(self.run_on({}, missing_key=True), ([], []))
        broken = fake_winreg({}, []); broken.OpenKey = lambda *a: (_ for _ in ()).throw(PermissionError('registre ferme'))
        self.assertEqual(self.run_on({}, winreg=broken), ([], []))


if __name__ == '__main__':
    unittest.main()
