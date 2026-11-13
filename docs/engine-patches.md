# Engine memory patches and hooks

The game engine (`libdq4core.so`, read from the APK you supply) is **never modified on disk**: it is loaded into memory inside the Unicorn emulator and never written back. The port changes the engine's behaviour only through the in-memory patches, hooks and writes listed on this page. Any new patch or hook must be added here; `tests/test_engine_hooks.py` counts the hooks installed at runtime and fails when the number no longer matches this page.

**Count (measured at runtime by counting the calls of `Uc.hook_add` while the engine is created; see `tests/test_engine_hooks.py`)**: **39 hooks** (`UC_HOOK_CODE` / `UC_HOOK_MEM_WRITE`) with the French texts, 38 with the English ones, of which **37 outside `emu_core.py`** and 2 inside it (imports and invalid memory accesses). By file, outside `emu_core.py`: `core/engine.py` **22** (`__init__` 3, `_text_hooks` 3, `_level_hooks` 1, `_forced_monster_hooks` 1, `_copy_name_hooks` 1 (French texts only), `_game_time_hooks` 1, `_magic_hooks` 6, `_fade_hooks` 5, `_divert_params` 1), `battle/battle_history.py` **8** (`BattleSensor.__init__`), `core/pktlog.py` **3**, `core/history.py` **4** (`Sensor.__init__`). To list every site that writes into the engine: `grep -rn "mem_w(\|mem_write\|hook_add\|reg_write" dq4_pc/`.

None of these sites writes a scenario flag, an event variable, gold, the inventory, the hero's position or the state of chests and NPCs. Two of them change a value of the playthrough: S5 (battle message speed, imposed by the port's settings) and S7 (HP and MP restored on level up, an option that is off by default).

## Code or data patches and hooks that write

| Ref | Site in the engine | Role | Guard / when | Where |
|---|---|---|---|---|
| S1 | `g_isAmazon` (`libdq4core + 0x24f684`), 1 byte ← 1 | removes the "cloud save" entry from the start menu (the game does the same for its Amazon build; the online services do not exist on PC) | at creation, then after each savestate load | `core/engine.py` (`__init__`, `reapply_fixes`) |
| S2 | `FieldData::drawSymbol` +0x44, +0x48, +0x4c: three `add` immediates (192, 448, 788) set to 1600 | the places of the world map stay visible over the whole 16:9 width | instruction pattern checked before writing, otherwise nothing; at creation and after a savestate | `core/engine.py` (`_widen_symbols`) |
| S3 | `TownMenu_OPERATION_ROOT::menuUpdate` `0x16ef28`: `cmp w8, #7` → `cmp w8, #4095` | the "Settings" button of the game's Misc menu opens the port's settings menu instead of the original one (see R5) | original instruction checked; at creation and after a savestate | `core/engine.py` (`CMP_PARAMS`, `patch_params`) |
| S4 | walking speeds: `TownPlayerAction::walkSpeed` (819), `walkSpeed2` (655), `FieldPlayer::Speed` (12288), constants `0x27520c` and `0x275210` (8192) | reset to their original values when a savestate is loaded; the accelerator speeds up the engine's clock, never these values | on savestate load | `core/engine.py` (`ORIGIN_SPEEDS`, `reset_speeds`) |
| S5 | `status::g_Option + 5` (`OptionStatus.battleSpeed`, battle message speed) | imposed by the port's "Battle speed" setting: 4 (by hand) for "Manual", 0 (shortest wait) for the others; 4 while a jingle or the victory fanfare plays (`Engine.hold_messages`), the previous value afterwards. The game's own value is kept and given back if the option is released | written before each frame; the value is part of `OptionStatus`, so it can end up in a game save | `core/engine.py` (`impose_scroll_mode`, `write_scroll_mode`), `window/options.py` (`apply_scroll`) |
| S6 | hook `ui_MsgLoop + 0x128` (`sxth w20, w8`): register `x8` | dialogue text speed (letters per frame); does nothing at the game's own speed nor for a speed fixed by the game (battle windows) | original instruction checked, otherwise nothing | `core/engine.py` (`_text_hooks`) |
| S7 | hook `HaveStatus::levelup(bool) + 0x3f8` (`tbz w20, #0`): register `x20` | option "HP and MP restored on level up": forces the bit that `debugLevelup` already sets, the engine itself refills HP and MP | only if the option (Modifiers page, off by default) is on; instruction checked | `core/engine.py` (`_level_hooks`) |
| S8 | hook `UnitySetFade` (`0x17e120`): register `x0`, plus four entry / exit hooks on `__cmd_fade_in::initialize` and `__cmd_fade_out::initialize` that only set a Python flag | marks (bit `0x10000`, unused by the engine) the fade packet of a fade started by a script, so that "Transition speed" does not shorten it | `UnitySetFade` checked, otherwise the setting applies to every fade | `core/engine.py` (`_fade_hooks`) |
| S9 | hooks of the Magic menu outside battle, at the two calls of `UseAction::execUse` and at `useMagicNoTarget + 0x2e0`; writes `UseActionParam + 0x210` (result messages ← `0xc3d6d`, the game's "nothing happens" message) and `gTownMenuItemUseManager + 0xaa` | a spell that costs MP but had no effect (healing at full HP) shows the game's "nothing happens" message instead of its success message, once for a group spell | only if the spell costs MP, the MP did not drop and the message is its success message or none; the sites are checked at launch, otherwise no hook | `core/engine.py` (`_magic_hooks`) |
| S10 | `EXIT_COUNTDOWN` (`libdq4core + 0x258254`, 1 byte) | rescaled in proportion to a fade to black shortened by "Transition speed", so that the exit sound effect is still requested mid-fade | only when an exit fade was shortened; written once per exit | `core/engine.py` (`_exit_countdown`) |
| S11 | hook `GameStatus::addPlayTime(2)` (the `bl` of `Global::NativeExec`): register PC ← next instruction | the play time saved in the game does not grow faster when the game runs accelerated | only when the game speed exceeds x1 | `core/engine.py` (`_game_time_hooks`) |
| S12 | `TownMenu_MESSAGE + 0x10` (`MESSAGE_RESULT`, 4 bytes ← 0) | resets the answer of a previous Yes / No box before the "Return to title screen" box opens, so that a leftover "Yes" does not confirm it | when the return-to-title box opens | `core/engine.py` (`_return_to_title_before`) |
| S13 | 16-byte work buffer of the history sensors, allocated in the engine heap (`GameCore.scratch`), zeroed before each call | output buffer for the engine functions the history sensors call; kept from one call to the next, forgotten when a savestate is loaded | at each history reading | `core/history.py` (`Sensor.model`), `battle/battle_history.py` (`BattleSensor`) |
| S14 | hook `SDrawCTRL::PutChar` (entry): reads the canvas, the code and the write position; writes `obj + 0x46` (2 bytes) | kerning of letter pairs that are too far apart in dialogues and battle messages (0 to 4 pixels, `MessageFont.kern`) | nothing after a space, tab, line break, "$" or ";"; font read from the data pack, otherwise no hook | `core/engine.py` (`_text_hooks`) |
| S15 | hook `Encount::brew + 0x1c0`: writes `Encount + 0x34` (4 monster numbers) and `+ 0x44` (4 counts) | testing only (`--force-monster N`): every random encounter is a single monster N | only with `--force-monster`; instructions checked; scripted battles are not affected | `core/engine.py` (`_forced_monster_hooks`) |
| S16 | frame of each battle monster's animation (`BattleMonsterDraw2::m_singleton` + slot × 0xa90 + 0x30 + animation × 0xb8 + 0xa8) | battle replay from the history only, between two turns: each monster's animation is kept at the frame the real clock has reached while the engine runs the command phase ahead | only during a replay; a replay gives the same messages and outcome (`tests/test_battle_replay.py`) | `window/battle_replay.py` (`monster_frames`, `hold_monsters`) |
| S17 | string `libdq4core + 0xc9170` (12 bytes): `copy of ;` ← `double de ;`; hook `MsgVar::extract_var + 0xb8`: before a vowel the name moves back 2 bytes behind `double d'` | French texts only: name of a monster's copy of a character, built by the engine from the English prefix | the English string and the instruction are checked, otherwise nothing; French texts recognized from the first monster name; string at creation and after a savestate, hook at creation | `core/engine.py` (`patch_copy_prefix`, `_copy_name_hooks`) |

## Writes that play the role of Unity

The engine expects these from the Unity layer of the original game, which the port replaces.

| Ref | Site | Role | Where |
|---|---|---|---|
| U1 | bit 0 of the first word of the output buffer (`Global.Flag`) | "a fade is in progress" (`Fade.FadePlane.CheckFade`) | `core/engine.py` (`step`) |
| U2 | bit 1 of the same word | "screen effect in progress" (`Capture.ScreenEffect`) during the battle-start cascade | `core/engine.py` (`_effect_flag`) |
| U3 | bit 0 of `table[idx × 32 + 0x14]` of a map object | "animation finished" callback (door, chest, jar) | `core/engine.py` (`_finish_anims`) |
| U4 | interface → engine message queue; reset of the engine → interface queue | what `MenuPort.Send` does: menu keys and clicks, name entry | `core/engine.py` (`send_menu`, `_consume_messages`) |
| U5 | parameter buffer of the message canvas, then a call of `SDrawCTRL::CanvasSetup` | Unity creates this 512 x 512 canvas through a port message | `core/engine.py` (`_create_canvas`) |
| U6 | input list: message `(1, 0x1000 \| slot)` then −1 | "end of a 3D model's animation" (`FbxObject.IsEndAnimation`), without which a spell's 3D effect never leaves the screen | `core/engine.py` (`_finish_fbx_anims`) |
| U7 | messages `[512, id0, id1]` on the staff roll port, then `UnityRenderEvent(1)` at every frame; the emulator copies the engine's `glTexSubImage2D` rows into the registered textures | what Unity's `StaffrollPort` does; without it the credits never advance | `core/engine.py` (`_staffroll_after`), `core/emu_core.py` (`h_glBindTexture`, `h_glTexSubImage2D`) |

## Other writes

| Ref | Site | Role | Where |
|---|---|---|---|
| E1 | `savestates.apply`: library image, heap, data, TLS | loading of a savestate requested by the player (file version checked), followed by `reapply_fixes` | `persistence/savestates.py` (`apply`), `core/engine.py` (`reapply_fixes`) |
| F1 | `GameCore.h_fopen` / `h_fclose` | the `dataN.dat` files the engine opens for writing are redirected to the port's save folder (atomic write: `.tmp` then `os.replace`); the originals are only read; during a battle replay nothing is written | `core/engine.py` (`GameCore`) |

## Engine function calls (no direct write)

- **A1** Return to the title screen (settings menu > "Return to title screen", after confirmation): `profile::SaveLoad::killbank(4, 0)` (erases the autosave bank, as the game's own button does), `PlayerManager::setLock(1)`, `Global::startTitle()`.
- **A2** Loading of an adventure log (`SaveLoad::loadbank`) and re-reading of the catalog after an import (`getCatalogView`, `getCatalogRecent`, `getCatalogStatus`).
- **A3** Initialization (`DevInit`, `MenuPortInit`, `GameInit`) and `GameUpdate` at each frame with the key mask.
- **A4** Test shortcut to the ending (Modifiers page, off by default; `Engine.start_ending`): `StoryStatus::setChapter`, `PartyStatus::clear` / `add`, `HaveStatusInfo::setup`, `cmd_set_flag`, `cmd_save_last_party`, `Global::startTown('ckout')`, then `TownPlayerManager::setPosition`. It changes the playthrough in memory only when the shortcut is used; nothing is saved unless the game's own save box is accepted.

## Read-only hooks

| Ref | Site | What it reads | Where |
|---|---|---|---|
| R1 | `MenuPort::SetVisible` | whether the message window is shown | `core/engine.py` |
| R2 | `FieldData::drawBlock` | the object that carries the world map | `core/engine.py` |
| R3 | `FLDObject::SetCommonAnimation` | the current animated object | `core/engine.py` |
| R4 | `OptionStatus::setBattleSpeed` | a change of the message speed made by the game itself | `core/engine.py` (`_text_hooks`) |
| R5 | `TownMenu_OPERATION_ROOT::menuUpdate` `0x16ef28` | the chosen button (7 = "Settings"): opens the port's settings menu | `core/engine.py` (`_divert_params`) |
| R6 | `TextBuffer::cat` | each message page, for the dialogue history | `core/history.py` |
| R7 | `profile::SaveLoad::loadbank` and `Global::startTitle` (entries) | which adventure log is being played, for one history per adventure | `core/history.py` |
| R8 | `PartyStatus::startBattle`, `BattleActorManager2::execMonsterDeath`, `BattleExecDefeatMonster::initialize`, `BattleExecEscape::setup`, `Global::endBattle` | defeated enemies, gold and experience, for the battle history | `battle/battle_history.py` |
| R9 | `UC_HOOK_MEM_WRITE` on the write cursors `0x258278` and `0x258280`, and `UnityGetPacket` | splits the engine → Unity packets | `core/pktlog.py` |

The history hooks (R6 to R8) are wrapped in `try`: an error there never stops the engine. The `DQ_*` debugging environment variables do not modify the engine.
