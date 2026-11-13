# Architecture

## The idea

The Android version of Dragon Quest IV is made of two layers:

- **the engine**, `libdq4core.so`: a C++ library compiled for ARM64 that contains the whole game (scripts, battles, menus' logic, saves);
- **a Unity layer** (`libil2cpp.so`, C#) that displays what the engine asks for, plays the sounds and sends the touch input back.

The port keeps the engine exactly as it is and replaces the Unity layer:

```
 your APK files                      dq4_pc (Python)
 ┌──────────────────┐   read   ┌────────────────────────────────────────────────────────────────┐
 │ libdq4core.so    │ ───────► │ core/emu_core.py   Unicorn: loads the ELF, emulates libc,     │
 │                  │          │                    OpenGL texture uploads and file access      │
 │ Unity data       │ ───────► │ world/             maps, sprites, 3D models, sounds (UnityPy) │
 └──────────────────┘          │ core/engine.py     steps the engine, decodes its packets      │
                               │                    (what it asks of Unity), sends input back   │
                               │ window/, menus/    pyglet + OpenGL: draws scenery, sprites,   │
                               │                    windows, effects; keyboard, mouse, gamepad  │
                               └────────────────────────────────────────────────────────────────┘
```

Every frame, `window/game.py` runs one or more engine steps (`Engine.step`), then draws the state decoded from the packets the engine wrote for Unity (`core/pktlog.py` splits them, `core/engine.py` `State` keeps the result: camera, sprites, map, fades, windows, sounds). Input goes the other way: key masks for the engine's `GameUpdate`, and menu messages on the same queue the Unity `MenuPort` uses.

The engine is never modified on disk. The few in-memory patches and hooks the port needs are listed, with their guards, in [`engine-patches.md`](engine-patches.md).

## Folders

| Folder | Contents |
|---|---|
| `dq4_pc/core/` | `emu_core.py` (emulator, ELF loader, libc and OpenGL stubs), `engine.py` (engine driver, packet decoding, patches and hooks), `pktlog.py`, `history.py` (dialogue capture), `encounters.py`, `game_priority.py`, `lying_pose.py`, `legacy_state.py` (names used by older savestates) |
| `dq4_pc/world/` | `data.py` (reading the Unity data, caches), `fld.py` (map format), `fbx.py` (animated 3D models), `map_objects.py`, `hd.py` (EPX x8 and pixel perfect sprites), `flat_sceneries.py`, `scenery_outlines.py`, `map_tint.py` |
| `dq4_pc/window/` | the `Game` window, assembled from one mixin per theme: `game.py` (loop and drawing), `camera.py`, `field.py`, `battle_scene.py`, `title_screen.py`, `menu_display.py`, `keyboard_mouse.py`, `gamepad.py`, `full_screen.py`, `snapshots.py`, `options.py`, `battle_replay.py`, `staffroll.py`... and their pure logic (`inputs.py`, `screens.py`, `helpers.py`, `constants.py`, `shaders.py`) |
| `dq4_pc/menus/` | `ui_menu.py` (the game's windows, laid out from the game's own code), `pause.py` (the port's settings menu), `ui_history.py`, `hud_mobile.py` (on-screen buttons and D-pad), `pre_game.py`, `name_entry.py`, `saves_screen.py`, `language_screen.py`, `message_font.py`, `prompts.py`, `flags.py` |
| `dq4_pc/persistence/` | `settings.py` (`settings.json`), `saves.py` (import / export), `savestates.py`, `logfile_format.py`, `pad_inputs.py`, `write_dir.py` (atomic writes) |
| `dq4_pc/render/` | `postfx.py` (off-screen rendering: antialiasing, supersampling, filters), `screen_blur.py`, `title_sky.py`, screen effects of the game's `Capture` class (`tabi_effect.py`, `lamp_effect.py`, `riremito_effect.py`, `capture_effects.py`) |
| `dq4_pc/battle/` | `battle_effect.py` (battle start), `battle_speed.py` (battle clock), `battle_history.py`, `full_screen_effects.py` |
| `dq4_pc/texts/` | the port's own texts: `fr/` and `en/`, one file per domain (`settings`, `menus`, `window`, `misc`), each `TEXTS = {key: text}` |
| `dq4_pc/` | `main.py` (command line), `paths.py` (every folder and file of `data`), `sound.py` (music and sound effects), `language.py` (`tr`, `N_`) |
| `tools/` | `run_tests.sh` / `run_one.py` (test runner), `dump_il2cpp.*` (structure of the game's C# code, from your APK), `generate_ui.bat` and `ui_il2cpp/` (runs the game's window construction code under emulation to record the original layout), `make_key_pictures.py` |
| `tests/` | one `test_*.py` per subject; the ones that need the game read `DQ_APK`, `DQ_APK_EN`, `DQ_SAVES`, `DQ_MAP_CACHE` and are skipped without them |

## The `data` folder

Everything that belongs to the player stays in `data` (or the folder named by `DQ4_DATA`), never in the repository:

```
data\apk\fr\  data\apk\en\      the APK files, one folder per game language
data\saves\                     data1.dat ... data5.dat, data9.dat (the game's adventure logs) and savestates\
data\cache\  data\cache_en\     what the port computes from the APKs (maps, sprites, sounds, window layout): safe to delete
data\settings\                  settings.json and the history
data\logs\                      window_errors.log
```

Files left by older versions of the port (French folder names, older layouts) are moved into this layout at startup by `paths.migrate`, without deleting or overwriting anything.

## Texts and languages

The game's own texts come from the APK of the chosen language and are never touched. The port's texts are keys: the code calls `tr('menus.export_saves')`, and module constants mark their keys with `N_()` so that they are translated when drawn (the language can change while the game runs). `tests/test_language.py` checks that both languages have the same keys, the same placeholders, no French in the English texts, and that every key used by the code exists and every key is used.

## Tests

`tools/run_tests.sh` runs every test file in its own process and lists the skipped tests at the end. Most tests need nothing (fake engine, fake window); the ones marked "real engine" load the game from `DQ_APK`. GL drawing tests need an OpenGL context (pyglet "headless" mode on Linux, set by the runner).
