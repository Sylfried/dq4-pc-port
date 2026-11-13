"""Runs one test file as a script (like `python3 tests/test_x.py ...`) and makes its skipped tests visible.

    python3 tools/run_one.py tests/test_x.py [arguments of the test]

A skipped test (`skipTest`, `skipUnless`...) counts as passed in unittest's summary: the suite could be green with a hole (a cache or an
argument missing). Here every skip is also written on one line, `SKIPPED <test>: <reason>`, at the end of the output; with DQ_REQUIRE_ALL=1
it becomes a failure (for a machine that has every cache).
"""
import os, runpy, sys, unittest

REQUIRE_ALL = os.environ.get('DQ_REQUIRE_ALL') == '1'
skipped = []
_original = unittest.TextTestResult.addSkip


def _add_skip(self, test, reason):
    skipped.append((str(test), reason))
    if not REQUIRE_ALL: return _original(self, test, reason)
    try: raise AssertionError('skipped while DQ_REQUIRE_ALL=1: %s' % reason)
    except AssertionError: self.addFailure(test, sys.exc_info())


def _report():
    for name, reason in skipped: print('SKIPPED %s: %s' % (name, reason), flush=True)


def main(argv):
    if not argv: print(__doc__); return 2
    path = os.path.abspath(argv[0])
    unittest.TextTestResult.addSkip = _add_skip
    sys.argv = [path] + argv[1:]
    sys.path.insert(0, os.path.dirname(path))                      # (as when the file is run as a script: the tests import their neighbors)
    try: runpy.run_path(path, run_name='__main__')
    except SystemExit as e:
        _report(); return e.code
    _report(); return 0


if __name__ == '__main__':
    sys.exit(main(sys.argv[1:]))
