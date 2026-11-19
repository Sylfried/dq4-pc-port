# Third-party components

## Game content

This repository contains **no content from the game**. The game engines (`libdq4core.so`, `libdq5core.so`, `libdq6core.so`), the Unity data, the music, the graphics and the texts are read at runtime from APK files that each player supplies from their own copy of the game; caches computed from them stay in the player's `data` folder, which is excluded from the repository. *Dragon Quest* and all related content are the property of their respective owners (Square Enix Holdings Co., Ltd. and its licensors). This project is unofficial and not affiliated with or endorsed by Square Enix.

## Assets included in this repository

| Component | Where | License |
|---|---|---|
| Kenney "Input Prompts" 1.1 (key and gamepad button pictures, www.kenney.nl); four key pictures (Shift, Alt, Alt Gr, Ctrl) assembled from Kenney's own blank key and letters by `tools/make_key_pictures.py`; the left stick's four directions made from the right stick's pictures with the "L" of Kenney's left stick press picture by `tools/make_stick_pictures.py` | `dq456_pc/assets/input_prompts/` | CC0 1.0 (public domain dedication), see `dq456_pc/assets/input_prompts/LICENSE.txt` |

## Python modules installed by the launcher (not included)

`launch_dq4.bat` installs these from PyPI on the player's computer (`requirements.txt`); none of them is copied into this repository.

| Module | Use | License |
|---|---|---|
| [Unicorn](https://www.unicorn-engine.org/) 2.1.4 | runs the game's ARM64 engine | GPL v2 (the upstream repository's `COPYING`; built on QEMU) |
| [pyglet](https://pyglet.org/) 2.1.19 | window, OpenGL, input, sound output | BSD 3-Clause |
| [NumPy](https://numpy.org/) 2.5.4 | arrays (geometry, pictures, sound) | BSD 3-Clause (with bundled components under compatible licenses) |
| [Pillow](https://python-pillow.org/) 13.0.0 | pictures | MIT-CMU (HPND) |
| [UnityPy](https://github.com/K0lb3/UnityPy) 1.25.4 | reading the Unity data of the APK | MIT |
| [Capstone](https://www.capstone-engine.org/) 5.0.9 | disassembly, used by the window layout generator (`tools/ui_il2cpp`) | BSD 3-Clause |
| [soundfile](https://github.com/bastibe/python-soundfile) 0.14.0 | decoding the game's music (Ogg Vorbis), with libsndfile | BSD 3-Clause (libsndfile: LGPL 2.1) |

## Tool downloaded on demand (not included)

| Tool | Use | License |
|---|---|---|
| [Il2CppDumper](https://github.com/Perfare/Il2CppDumper) | `tools/dump_il2cpp.py` downloads it to read the structure of the game's C# code from the player's own APK (output kept in the player's `data\cache`) | MIT |

The port's own code is licensed under the GNU General Public License, version 2 or any later version (`LICENSE`), which keeps it compatible with Unicorn's GPL v2.
