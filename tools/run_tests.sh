#!/bin/bash
# The whole test suite, one line per file, then the skipped tests and the number of failed files; the exit code is 0 only if every file passed.
#
# Set what you need before running; the rest has a default value:
#   DQ_APK         folder of the patched APKs (without it, the real-engine tests are skipped)
#   DQ_SAVES       folder of the saves, READ ONLY (the tests write to /tmp)
#   DQ_MAP_CACHE   map cache (python3 -m dq4_pc.world.data <apk> <folder>, about 1 minute)
#   DQ_APK_EN      folder of the English APKs (language tests)
#   DQ_UI_CACHE    interface cache (ui_layout.json): without it, the layout tests are skipped (default: DQ_MAP_CACHE)
#   DQ_REQUIRE_ALL 1 = a skipped test is a failure (for a machine that has every cache)
# Each file goes through run_one.py: its skipped tests are listed at the end ("SKIPPED", one line per reason), so that a green suite cannot hide a hole.
cd "$(dirname "$0")/.." || exit 1
export PYGLET_HEADLESS=1 PYGLET_AUDIO=silent
export DQ_MAP_CACHE="${DQ_MAP_CACHE:-/tmp/dq4_map_cache}"
export DQ_UI_CACHE="${DQ_UI_CACHE:-$DQ_MAP_CACHE}"
[ -z "$DQ_APK" ] && echo "DQ_APK is not set: the real-engine tests will be skipped."
skips=$(mktemp); failed=0
for f in tests/test_*.py; do
  n=$(basename "$f" .py)
  out=$(timeout 900 python3 -W ignore tools/run_one.py "$f" --apk "$DQ_APK" --saves "$DQ_SAVES" 2>&1)
  case "$out" in *unrecognized*|*"no such option"*) out=$(timeout 900 python3 -W ignore tools/run_one.py "$f" 2>&1);; esac
  echo "$out" | grep '^SKIPPED ' | sed "s/^SKIPPED /$n: /" >> "$skips"
  summary=$(echo "$out" | grep -v '^SKIPPED ' | tail -3 | tr '\n' ' ')
  case "$summary" in *FAILED*) failed=$((failed + 1));; *OK*) ;; *) failed=$((failed + 1));; esac
  echo "$n: $summary"
done
if [ -s "$skips" ]; then
  echo "SKIPPED TESTS ($(wc -l < "$skips")), by reason:"
  sed 's/^[^:]*: [^:]*: //' "$skips" | sort | uniq -c | sort -rn
  echo "(detail: one line per test)"; cat "$skips"
else echo "SKIPPED TESTS: none"
fi
rm -f "$skips"
echo "FAILED FILES: $failed"
echo END
[ "$failed" -eq 0 ]
