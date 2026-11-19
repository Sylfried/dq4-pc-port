# Dragon Quest IV, V and VI — unofficial PC port

This project plays the **Android versions of Dragon Quest IV, V and VI** on a Windows PC. It runs the original game engine unmodified and replaces the Android display and input layer: the game is shown in a resizable **16:9** window and played with mouse, keyboard or gamepad, with savestates, a history of dialogues and battles, and optional settings.

> **This repository contains no game file.** It is code only. To play, you need **your own copy** of the Android game (its APK files), which the port reads on your computer. Nothing from the game is downloaded, copied or distributed by this project.

## Features

- **16:9 at any window size**, windowed or full screen, with the game's original windows and menus laid out as in the game. Display options: sprite filter (EPX x8 or pixel perfect), antialiasing, supersampling, sharpness, brightness, contrast, colour filter, vignette and edge blur.
- **Mouse, keyboard and gamepad** (Xbox, PlayStation and Switch layouts): the mouse replaces touch input, keys follow your keyboard layout (AZERTY or QWERTY) and can be rebound; optional on-screen buttons and D-pad as on mobile, placed with a built-in interface editor.
- **English or French**, for the game (each language reads its own APK files) and for the port's own menus.
- **Sound**: the game's music and sound effects, read from the APK and played by the port, with a general volume and one per category (music, jingles and fanfares, sound effects, interface sounds).
- **Saves**: the game's own adventure logs (import and export of the files from your phone) and **savestates** at any moment.
- **History** of dialogues and battles, with favourites; a past battle can be **replayed** by the engine.
- **Speeds**: walking accelerator (held key), text speed and battle speed; by default, the game's own speeds.
- **Game rules**, saved with each game and off by default (the original game): difficulty (experience, gold, casino tokens, damage, encounter rate), HP and MP restored on level up or after a battle, no random encounters, and a randomizer with a seed (items, monster drops, random encounters, bosses).

### Planned

Not available yet; game-changing additions will be options, off by default.

- **More languages**: APK folders for German, Spanish, Italian, Japanese, Korean and Chinese, a language added by choosing its flag, each language named in its own language, and the port's own texts translated through a spreadsheet it exports and reads back (one column per language).
- **Interface**: new default layouts for the larger screen, a taskbar icon per game, and an optional framed battle view over a blurred background.
- **Tactics**: the hero's own tactics, and in DQ IV the formation and tactics buttons in battle from the first chapters.
- **Extra modes**: monster rush (harder and harder battles, zone after zone) and boss rush (at the casino, each boss in its original scenery), with rewards such as casino tokens and equipment.
- **Challenges**: no shopping, no armour, party lost when its main character falls, permanent death, no church services, no bank; in DQ V no monster recruitment or permanent death of monsters; in DQ VI vocations limited per character.
- **Cheats**, per character and for the party: healing, HP / MP that do not go down, critical hits, immunity to status effects, experience and levels, gold, tokens, mini medals and items, no equipment restriction, no gold lost after a defeat, a chosen enemy at the next encounter, day / night cycle stopped; in DQ V recruitment at 100%, in DQ VI vocations mastered. Random encounters can already be turned off.
- **Achievements**: pop-up notifications and a grid view, completion goals (every item, monster, loot, travel destination, mini medal reward, level 99, casino feats, everything found), goals of each game (DQ IV's migrant town, DQ V's monsters and mini-games, DQ VI's vocations, contests and mini-games), and goals for difficulties, randomizers and challenges, disabled once a cheat is used.

## How it works

Each Android game is a C++ engine (`libdq4core.so`, `libdq5core.so`, `libdq6core.so`, ARM64) whose display and input go through a Unity layer. The port keeps the original engine and replaces the Unity layer with Python (pyglet / OpenGL):

- the engine runs unmodified in the [Unicorn](https://www.unicorn-engine.org/) CPU emulator; its file is read from your APK and never changed on disk;
- the port decodes what the engine sends to Unity (sprites, maps, windows, sounds) and draws it; maps, sprites and models are read from the APK's Unity data with [UnityPy](https://github.com/K0lb3/UnityPy);
- a few targeted in-memory patches and hooks adapt the engine to the PC (for example the 16:9 world map); every one of them is listed in [`docs/engine-patches.md`](docs/engine-patches.md).

More details: [`docs/architecture.md`](docs/architecture.md).

## Requirements

- Windows 10 or 11, and **Python 3.12, 3.13 or 3.14** from [python.org](https://www.python.org/downloads/) (tick "Add python.exe to PATH"). The launcher creates its own environment and installs the modules listed in `requirements.txt`.
- **The game's APK files**, taken from your own Android installation of *Dragon Quest IV*, *V* or *VI*: `base.apk`, `split_config.arm64_v8a.apk` and `split_UnityDataAssetPack.apk` (for example with `adb shell pm path <package>` then `adb pull`).
  - English: the game's own APKs.
  - French: the same three APKs patched with a French translation (a separate project, not included here).
- Optionally, your saves from the phone (`data1.dat` … `data5.dat`, `data9.dat`).

## Installation

1. Download this repository (Code > Download ZIP, or `git clone`).
2. Put your files in the `data` folder at the root of the project (its folders are already there, each with a short `README.txt`):

   ```
   data\apk\dq4\en\  base.apk, split_config.arm64_v8a.apk, split_UnityDataAssetPack.apk   (English)
   data\apk\dq4\fr\  the same three files, patched in French                               (optional)
   data\saves\dq4\   data1.dat ... data5.dat, data9.dat copied from your phone             (optional)
   ```
   Same layout for the other games, in `dq5\` and `dq6\` instead of `dq4\`. The game uses the folder of the language chosen in the settings (read at startup). To keep your data elsewhere, set the `DQ_DATA` environment variable to that folder.
3. Double-click **`launch_dq4.bat`**, **`launch_dq5.bat`** or **`launch_dq6.bat`**. The first launch creates the Python environment and installs the modules (a few minutes). The first launch of each game then reads the game's original window layout from your APK (a few minutes, once only: it downloads the free tool [Il2CppDumper](https://github.com/Perfare/Il2CppDumper) the first time, so an internet connection is needed once; without it, that launch shows plain menus and the next one tries again), and the game opens; the port prepares its caches (maps, sprites, sounds) in `data\cache\<game>` in the background. The three games share the Python environment and the settings; each one has its own saves and cache.

Everything the port writes (saves, savestates, settings, caches, logs) stays in `data`, whose content is ignored by git (only the `README.txt` of its folders is in the repository).

## Controls (defaults, all rebindable)

| Action | Keyboard / mouse | Gamepad (Xbox) |
|---|---|---|
| Move | W A S D (Z Q S D on AZERTY) | left stick or D-pad |
| Action (talk, examine, confirm) | Space, or click the bubble above a character | A |
| Command menu / confirm | Enter or Tab | Y |
| Cancel / back | Backspace | B |
| Map | M | X |
| Rotate the camera | ← → (both together: recenter), middle click held + mouse | LB / RB |
| Accelerator (held) | Shift | RT |
| Battle speed (in battle) | V | LT |
| Settings menu (history, savestates, settings) | Esc | Menu |
| On-screen information | F1 | — |
| Full screen | F11 or Alt + Enter | — |

Savestates: a special key (Ctrl by default) + a digit loads a savestate; the settings menu saves, loads and deletes them. Command line: `--slot N` loads adventure log N directly, `--no-logos` skips the intro logos; `python -m dq456_pc --help` lists every option.

## Bug reports

Bug reports are welcome in the issues (please never attach game files).

## Development

```
dq456_pc/            the port (Python package); games.py: one profile per game (DQ4, DQ5, DQ6), paths.py: every folder
  core/            the emulator (emu_core.py) and the engine driver (engine.py, pktlog.py), histories
  world/           reading maps, sprites and 3D models from the Unity data
  window/          the pyglet window: loop, camera, scenery, battles, menus, input
  menus/           the game's windows (ui_menu.py), the port's settings menu (pause.py), history, title screens
  persistence/     settings, saves import / export, savestates
  render/          post-processing (antialiasing, filters, blur), title sky
  battle/          battle effects, battle speed, battle history
  texts/           the port's own texts, one file per domain and language (fr/, en/)
  assets/          key and button pictures (Kenney "Input Prompts", CC0)
tests/             the tests (test_*.py)
tools/             the launcher shared by launch_dq4/5/6.bat, test runner, il2cpp structure dump, original window layout generator
docs/              architecture and engine patches
```

The tests run on Linux or Windows. Those that need the game are skipped without it:

```
DQ_APK=data/apk/dq4/fr DQ_APK_EN=data/apk/dq4/en DQ_SAVES=data/saves/dq4 DQ_MAP_CACHE=<cache folder> tools/run_tests.sh
```

`DQ_MAP_CACHE` is built with `python -m dq456_pc.world.data <apk folder> <cache folder>`; the interface tests also need the layout file (`ui_layout.json`) in it.

Texts: the code only holds keys (`settings.battle_speed`); `dq456_pc/language.py` returns the text of the current language from `dq456_pc/texts/<fr|en>/<domain>.py`. A new text needs an entry in both languages (checked by `tests/test_language.py`).

## Legal

- This project is **unofficial** and not affiliated with, endorsed or sponsored by Square Enix. *Dragon Quest* is a registered trademark of Square Enix Holdings Co., Ltd. All game content (code, graphics, music, text) belongs to its owners and is **not** part of this repository.
- The port's code is released under the **GNU General Public License, version 2 or (at your option) any later version**: see [`LICENSE`](LICENSE).
- Third-party components and their licenses: [`THIRD_PARTY_NOTICES.md`](THIRD_PARTY_NOTICES.md).
