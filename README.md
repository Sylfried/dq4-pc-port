# Dragon Quest IV, V and VI — unofficial PC port

*[Version française plus bas](#version-française).*

An unofficial, fan-made way to play the **Android versions of Dragon Quest IV, V and VI** on a Windows PC: the original game in a resizable **16:9** window, with mouse, keyboard or gamepad, its own music and sound effects, savestates and a few optional comfort features.

> **This repository contains no game file.** It is code only. To play, you need **your own copy** of the Android game (its APK files), which the port reads on your computer. Nothing from the game is downloaded, copied or distributed by this project.

## Features

- **16:9 at any window size**, windowed or full screen; the game's original windows and menus, laid out as in the game; sprite upscaling (EPX x8 or pixel perfect), antialiasing, sharpness, contrast, colour filter, vignette and edge blur.
- **Mouse, keyboard and gamepad** (Xbox, PlayStation and Switch layouts): the mouse replaces touch input, keys follow your keyboard layout (AZERTY or QWERTY) and can be rebound; optional on-screen buttons and D-pad as on mobile, placed with a built-in interface editor.
- **English or French**, for the game (each language reads its own APK files) and for the port's own menus.
- **The original music and sound effects**, with a volume per category.
- **Saves**: the game's own adventure logs (import and export of the files from your phone) and **savestates** at any moment.
- **History** of dialogues and battles, with favourites; a past battle can be **replayed** by the engine.
- **Optional comfort**: walking accelerator, text and battle speeds, camera rotation; game-changing options (such as HP / MP restored on level up or after a battle) are off by default.

## How it works

Each Android game is a C++ engine (`libdq4core.so`, `libdq5core.so`, `libdq6core.so`, ARM64) whose display and input go through a Unity layer. This port keeps the original engine and replaces the Unity layer with Python (pyglet / OpenGL):

- the engine runs unmodified in the [Unicorn](https://www.unicorn-engine.org/) CPU emulator; its file is read from your APK and never changed on disk;
- the port decodes what the engine sends to Unity (sprites, maps, windows, sounds) and draws it; maps, sprites and models are read from the APK's Unity data with [UnityPy](https://github.com/K0lb3/UnityPy);
- a few targeted in-memory patches and hooks adapt the engine to the PC (for example the 16:9 world map); every one of them is listed in [`docs/engine-patches.md`](docs/engine-patches.md).

More details: [`docs/architecture.md`](docs/architecture.md).

## Requirements

- Windows 10 or 11, and **Python 3.12, 3.13 or 3.14** from [python.org](https://www.python.org/downloads/) (tick "Add python.exe to PATH"). The launcher creates its own environment and installs the modules listed in `requirements.txt`.
- **The game's APK files**, taken from your own Android installation of *Dragon Quest IV*, *V* or *VI*: `base.apk`, `split_config.arm64_v8a.apk` and `split_UnityDataAssetPack.apk` (for example with `adb shell pm path <package>` then `adb pull`).
  - English: the game's own APKs.
  - French: the same three APKs patched with a French fan translation (a separate project, not included here).
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

- **Unofficial fan project**, not affiliated with, endorsed or sponsored by Square Enix. *Dragon Quest* is a registered trademark of Square Enix Holdings Co., Ltd. All game content (code, graphics, music, text) belongs to its owners and is **not** part of this repository.
- The port's code is released under the **GNU General Public License, version 2 or (at your option) any later version**: see [`LICENSE`](LICENSE).
- Third-party components and their licenses: [`THIRD_PARTY_NOTICES.md`](THIRD_PARTY_NOTICES.md).

---

## Version française

Un portage **non officiel**, fait par des fans, pour jouer aux **versions Android de Dragon Quest IV, V et VI** sur PC Windows : le jeu d'origine dans une fenêtre **16:9** redimensionnable, à la souris, au clavier ou à la manette, avec sa musique et ses bruitages, des états instantanés et quelques options de confort.

> **Ce dépôt ne contient aucun fichier du jeu.** Il ne contient que du code. Pour jouer, il faut **votre propre copie** du jeu Android (ses fichiers APK), que le portage lit sur votre ordinateur. Ce projet ne télécharge, ne copie et ne distribue rien du jeu.

### Installation

1. Installez **Python 3.12, 3.13 ou 3.14** depuis [python.org](https://www.python.org/downloads/) (cochez « Add python.exe to PATH »).
2. Récupérez ce dépôt (Code > Download ZIP, ou `git clone`).
3. Placez vos fichiers dans le dossier `data` à la racine du projet (ses dossiers existent déjà, chacun avec un court `README.txt`) :
   - `data\apk\dq4\fr\` : `base.apk`, `split_config.arm64_v8a.apk`, `split_UnityDataAssetPack.apk`, patchés avec une traduction française (projet séparé, non inclus) ;
   - `data\apk\dq4\en\` : les trois mêmes fichiers de la version anglaise d'origine (facultatif) ;
   - `data\saves\dq4\` : vos sauvegardes copiées depuis le téléphone (`data1.dat` … `data5.dat`, `data9.dat`, facultatif) ;
   - même rangement pour les autres jeux, dans `dq5\` et `dq6\` au lieu de `dq4\`.
4. Double-cliquez sur **`launch_dq4.bat`**, **`launch_dq5.bat`** ou **`launch_dq6.bat`**. Le premier lancement prépare l'environnement Python (quelques minutes). Le premier lancement de chaque jeu lit ensuite la disposition d'origine des fenêtres du jeu dans votre APK (quelques minutes, une seule fois : l'outil libre [Il2CppDumper](https://github.com/Perfare/Il2CppDumper) est téléchargé la première fois, il faut donc une connexion internet une fois ; sans elle, ce lancement affiche des menus simples et le suivant réessaie), puis le jeu s'ouvre.

Tout ce que le portage écrit (sauvegardes, états, réglages, caches, journaux) reste dans `data`, dont le contenu est ignoré par git (seul le `README.txt` de ses dossiers est dans le dépôt). Les commandes sont dans le tableau ci-dessus (toutes modifiables dans le menu Échap > Commandes).

### Mentions légales

Projet de fans **non officiel**, sans lien avec Square Enix. *Dragon Quest* est une marque déposée de Square Enix Holdings Co., Ltd. Le contenu du jeu appartient à ses ayants droit et ne fait **pas** partie de ce dépôt. Le code du portage est distribué sous **licence GNU GPL, version 2 ou (à votre choix) toute version ultérieure** ([`LICENSE`](LICENSE)) ; composants tiers : [`THIRD_PARTY_NOTICES.md`](THIRD_PARTY_NOTICES.md).
