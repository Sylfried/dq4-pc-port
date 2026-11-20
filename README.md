# Dragon Quest IV, V and VI — unofficial PC port

This project plays the **Android versions of Dragon Quest IV, V and VI** on a Windows PC. It runs the original game engine unmodified and replaces the Android display and input layer: the game is shown in a resizable **16:9** window and played with mouse, keyboard or gamepad, with savestates, a history of dialogues and battles, and optional settings.

> **This repository contains no game file.** It is code only. To play, you need **your own copy** of the Android game (its APK files), which the port reads on your computer. Nothing from the game is downloaded, copied or distributed by this project.

## Features

- **16:9 at any window size**, windowed or full screen, with the game's original windows and menus laid out as in the game. Display options: sprite filter (EPX x8 or pixel perfect), antialiasing, supersampling, sharpness, brightness, contrast, colour filter, vignette and edge blur.
- **Mouse, keyboard and gamepad** (Xbox, PlayStation and Switch layouts): the mouse replaces touch input, keys follow your keyboard layout (AZERTY or QWERTY) and can be rebound; optional on-screen buttons and D-pad as on mobile, placed with a built-in interface editor.
- **Nine languages for the port's own menus**: English, French, German, Spanish, Italian, Japanese, Korean, simplified and traditional Chinese, each chosen by its flag on the start menu or in the settings (by default, the computer's language), and **more added by the players** from the language screen (see [Languages](#languages)). The game itself speaks the language of the APK files it reads: each language has its own APK folder; without APK files there, the English ones are used.
- **Sound**: the game's music and sound effects, read from the APK and played by the port, with a general volume and one per category (music, jingles and fanfares, sound effects, interface sounds).
- **Saves**: the game's own adventure logs (import and export of the files from your phone) and **savestates** at any moment.
- **History** of dialogues and battles, with favourites; a past battle can be **replayed** by the engine.
- **Speeds**: walking accelerator (held key), text speed and battle speed; by default, the game's own speeds.
- **Game rules**, saved with each game and off by default (the original game): difficulty (experience, gold, casino tokens, damage, encounter rate), HP and MP restored on level up or after a battle, no random encounters, and a randomizer with a seed (items, monster drops, random encounters, bosses).

### Planned

Not available yet; game-changing additions will be options, off by default.

- **The game's own texts in Japanese, Korean and Chinese**: the published APK files already hold them; the port does not show them yet (the game runs in English).
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
  - Another language: the same three APKs patched in that language by the translation project (a separate project, not included here: see [Languages](#languages)).
- Optionally, your saves from the phone (`data1.dat` … `data5.dat`, `data9.dat`).

## Installation

1. Download this repository (Code > Download ZIP, or `git clone`).
2. Put your files in the `data` folder at the root of the project (its folders are already there, each with a short `README.txt`):

   ```
   data\apk\dq4\en-us\  base.apk, split_config.arm64_v8a.apk, split_UnityDataAssetPack.apk   (English)
   data\apk\dq4\fr-fr\  the same three files, patched in French                               (optional)
   data\apk\dq4\<code>\ the same three files for another language (de-de, es-es, ja-jp...)    (optional)
   data\saves\dq4\      data1.dat ... data5.dat, data9.dat copied from your phone             (optional)
   ```
   Same layout for the other games, in `dq5\` and `dq6\` instead of `dq4\`. The game uses the folder of the language chosen in the settings (read at startup); a folder without APK files falls back on `en-us`, then `fr-fr`. Folders of earlier versions (`fr`, `en`) are renamed at the first launch. To keep your data elsewhere, set the `DQ_DATA` environment variable to that folder.
3. Double-click **`launch_dq4.bat`**, **`launch_dq5.bat`** or **`launch_dq6.bat`**. The first launch creates the Python environment and installs the modules (a few minutes). The first launch of each game then reads the game's original window layout from your APK (a few minutes, once only: it downloads the free tool [Il2CppDumper](https://github.com/Perfare/Il2CppDumper) the first time, so an internet connection is needed once; without it, that launch shows plain menus and the next one tries again), and the game opens (a bar at the bottom of the black loading screen shows the progress; the intro logos follow once everything is loaded); the port prepares its caches (maps, sprites, sounds) in `data\cache\<game>` in the background. The three games share the Python environment and the settings; each one has its own saves and cache.

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

Every button of the game's windows can be reached with the keyboard: the movement keys go from button to button ("Rien", "Quitter" and the other back buttons included; at the top or bottom of a list that scrolls, they scroll it), Space or Enter presses the button, Backspace or Esc goes back, ← → turn the pages.

Savestates: a special key (Ctrl by default) + a digit loads a savestate; the settings menu saves, loads and deletes them. Command line: `--slot N` loads adventure log N directly, `--no-logos` skips the intro logos; `python -m dq456_pc --help` lists every option.

## Bug reports

Bug reports are welcome in the issues (please never attach game files).

## Languages

Every language has a **code**, its language and its country in lower case (`en-us`, `fr-fr`, `pt-br`...), used for two folders that go together:

- `dq456_pc\languages\<code>.json`: the port's own texts (menus, settings, messages);
- `data\apk\<game>\<code>\`: the game's APK files in that language.

Choosing a language shows the port's texts in it at once, and runs the game with the APK files of its folder; when that folder has none, the game runs in English (`en-us`, otherwise `fr-fr`) while the port's texts stay in the chosen language.

### The port's texts

All the languages are in one folder, `dq456_pc\languages\`, one file per language named by its code (`en-us.json`, `fr-fr.json`, `pt-br.json`...). Each file holds the language's name and flag, then every text of the port, one per line, in the order of the English file:

```
{
 "name": "Français",
 "flag": "fr",
 "help": "Translate each \"en\" text into \"text\" ...",
 "entries": [
  {"key": "display.contrast", "en": "Contrast", "text": "Contraste"},
  {"key": "window.fullscreen", "en": " (fullscreen)", "text": " (plein écran)"},
  ...
 ]
}
```

- `key`: the name of the text, never changed (its first part is the menu or theme: `display`, `sound`, `history`...);
- `en`: the English text, the reference to translate from;
- `text`: the text displayed in this language; an empty `text` shows the English one;
- codes that start with `%` (`%s`, `%d`, `%.1f`...) stay, in the same order: the port puts numbers and names there; `\n` starts a new line; spaces at the start or end of the English text stay too. A text that does not keep them is not used (English is shown);
- `name`: the language's name in the language itself, as the language list shows it; `flag`: the code of its flag (`dq456_pc\assets\flags`).

To add a language, on the start menu: **Language** (globe) > **Add a language** (these screens are in English, whatever the language chosen), choose its flag, type its folder code and its name, then **Create**. Its file is created with every English text and an empty `text`, and its APK folders are created. Translate the file (Notepad++, VS Code...: UTF-8), a little at a time if you like, then press **Load the texts**: the port reads it again and says how many texts are translated; a text that does not fit the English one stays in English and is listed in `data\logs\texts_<code>.txt`. **Edit its texts** opens the same panel for an existing language (and adds to its file the texts that a new version of the port added, empty).

### The game's texts

The game's texts come from the APK files. The translation project (a separate repository, `dq456-translate`) extracts the texts of your own APK files and builds patched APK files from a translation; put them in `data\apk\<game>\<code>\` to play the game in that language. The published APK files already hold the game's texts in English, Japanese, Korean and Chinese, but the port only shows the English ones for now.

### Proposing a language

1. Fork this repository (or create a branch if you can), add your language from the language screen and translate its file, `dq456_pc\languages\<code>.json`.
2. Run `python tests/test_language.py`: it checks that every language has the keys of the English file in the same order, the same `%` codes as English, and a flag.
3. Commit `dq456_pc\languages\<code>.json` and the `README.txt` of the new `data\apk\<game>\<code>\` folders, then open a pull request. Once reviewed, it is merged into `main` and published with the next release, for everyone.

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
  languages/       the port's own texts: one file per language (en-us.json, fr-fr.json...)
  assets/          key and button pictures (Kenney "Input Prompts", CC0), flags (public domain)
tests/             the tests (test_*.py)
tools/             the launcher shared by launch_dq4/5/6.bat, test runner, il2cpp structure dump, original window layout generator
docs/              architecture and engine patches
```

The tests run on Linux or Windows. Those that need the game are skipped without it:

```
DQ_APK=data/apk/dq4/fr-fr DQ_APK_EN=data/apk/dq4/en-us DQ_SAVES=data/saves/dq4 DQ_MAP_CACHE=<cache folder> tools/run_tests.sh
```

`DQ_MAP_CACHE` is built with `python -m dq456_pc.world.data <apk folder> <cache folder>`; the interface tests also need the layout file (`ui_layout.json`) in it.

Texts: the code only holds keys (`display.contrast`, `language.title`); `dq456_pc/language.py` returns the text of the current language from `dq456_pc/languages/<code>.json`, falling back to English (the only fallback: a text missing, empty or refused in a language, or a language file that cannot be read, shows the English one). A new text goes into `en-us.json` (its `en` and its `text`); `language.save_language(code)` then adds it, empty, to another language's file (checked by `tests/test_language.py`).

## Legal

- This project is **unofficial** and not affiliated with, endorsed or sponsored by Square Enix. *Dragon Quest* is a registered trademark of Square Enix Holdings Co., Ltd. All game content (code, graphics, music, text) belongs to its owners and is **not** part of this repository.
- The port's code is released under the **GNU General Public License, version 2 or (at your option) any later version**: see [`LICENSE`](LICENSE).
- Third-party components and their licenses: [`THIRD_PARTY_NOTICES.md`](THIRD_PARTY_NOTICES.md).
