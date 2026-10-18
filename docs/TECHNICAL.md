# How the mod works

DmC: Devil May Cry runs on Unreal Engine 3 (game build 1.0.8916.1, 32-bit). The stock UE3
local-multiplayer code is still in the game: `GameViewportClient.CreatePlayer`, the splitscreen
layout table `SplitscreenInfo`, and per-player viewports. The mod switches that code back on and
works around the places where DmC and QLOC's PC port assume a single player.

## Files changed

`tools/setup.py` builds all of these from the user's own unmodified game files.

| File | Change |
|---|---|
| `DevilGame/CookedPCConsole/Engine.upk` | Stored uncompressed. Two unused cheats are repurposed: `SetOnlineDebugLevel` becomes `AddPlayer <ControllerId>` and `RememberSpot` becomes `SplitAxis`. `Default2PSplitType` is set to `eSST_2P_VERTICAL`. |
| `DevilGame/CookedPCConsole/DevilGame.upk` | Stored uncompressed. Changes `DVGameInfo.PostLogin` (see "Spawning player 2"). |
| `DevilGame/CookedPCConsole/NTGameFramework.upk` | Stored uncompressed. A one-byte change: `NTGameInfo_SP.SpawnPlayerPawn` passes `bNoCollisionFail=true` to `Spawn`. |
| `Binaries/Win32/DMC-DevilMayCry.exe` | QLOC input fixes, plus ASLR switched off (see below). |
| `DevilGame/Config/DefaultInput.ini` | F6 / F7 key bindings. |
| `Binaries/Win32/xinput1_3.dll` | Optional diagnostics helper (`native/`). |

### Package format notes

- The script packages are LZO-compressed (file version 845, licensee 4).
- The patcher writes them uncompressed. Every object keeps its original offset: the summary loses its
  chunk table, but the uncompressed summary ends exactly at `NameOffset`.
- Changed exports are appended at the end of the file, and the export table is repointed at them.
- Renaming a function also updates the key in its class's serialized `FuncMap`.
- In memory, bytecode object references count as 8 bytes, while on disk they take 4. Jump and skip
  offsets use the in-memory sizes.

## Spawning player 2

- `AddPlayer` calls `CreatePlayer(id, err, true)`. That logs a new `PlayerController` in through
  `DVGameInfo.Login` and `PostLogin`.
- `DVGameInfo` has `bDelayedStart` set, so `GameInfo.PostLogin` never calls `RestartPlayer`. In
  single player, pawns are only spawned when the match starts.
- The patched `DVGameInfo.PostLogin` keeps the original `DisableInput(3, true)`. For a mid-mission
  join it then:
  - re-enables input
  - calls `NTGameInfo_SP.RestartPlayer` directly. The `DVGameInfo` override would repoint
    `m_PlayerPawn`, the pickup system and upgrades at the new player.
  - calls `PostRestartPlayer`
- The pawn spawns at the checkpoint's start point, where player 1 usually still stands. That is why
  the spawn ignores collision.
- `AddPlayer` then moves the new pawn next to player 1, trying +X, -X, +Y, then above, and matches
  player 1's rotation. Pressing F6 again just regroups.

## Controller routing (exe)

QLOC's PC port lets any pad drive player 1:

1. **"Any pad becomes player 1."** The InputKey override (`0x1933990`) and InputAxis override
   (`0xE9A750`) call `GamePlayers[0]->SetControllerId(pad)` on every pad button or stick use.
   - Both calls now go through caves (`0x19594A0`, `0x1855B20`) that only run them while there is a
     single local player.
2. **Buttons go to every player.** The joystick poll (`0x18773B0`) feeds a pad's buttons to every
   local player while that pad is the global "current controller" (`0x2B551F0`).
   - The four checks (`0x1877A1D`, `0x1877A8E`, `0x1877E7D`, `0x1877EEE`) now call a cave
     (`0x17F9DD0`).
   - With 2+ players the cave returns each player's own `LocalPlayer.ControllerId` (`+0x60`). With one
     player it returns the original value, so single player is unchanged.
3. **ASLR is off.** The caves use absolute addresses, so the exe's `DYNAMIC_BASE` flag is cleared and it
   always loads at `0x400000`. With ASLR on, the game crashed at the first logo.

`patch_exe.py` checks the original bytes at every site before writing.

## Splitscreen

- `ShouldForceFullscreenViewport` (`0x95D4C0`) is stock UE3. It forces one fullscreen view only when:
  - there are no players
  - the current map is a menu level
  - player 1 is in cinematic mode (cutscenes and QTEs)
  - the `FORCEFULLSCREEN` console command is toggled on (it defaults to off)
- `SplitAxis` toggles `DesiredSplitscreenType` between vertical and horizontal, then calls
  `LayoutPlayers`.

## Diagnostics DLL (`native/`)

- The game imports `XInputGetState`/`XInputSetState` (ordinals 2 and 3) from `xinput1_3.dll`, so a DLL
  of that name next to the exe is loaded first. The helper forwards every call to the system DLL.
- Every 250 ms it writes changes to `CoopMod/coop_log.txt`:
  - pad activity
  - QLOC's controller state
  - the joystick table
  - each player's ControllerId and pawn
- It hooks `UObject::CallFunction` (`0x47B370`) and `UObject::ProcessEvent` (`0x47B7B0`). When
  `AddPlayer` runs, it writes a nested script-call trace, with return values of the spawn functions,
  to `CoopMod/coop_trace.txt`.
- Build it with `native/build.bat` (needs Visual Studio's x86 C compiler).

## Useful addresses (exe at 0x400000)

| What | Address |
|---|---|
| `GEngine` (`GamePlayers` Data `+0x4DC`, Num `+0x4E0`) | `0x2B2C328` |
| GNames `TArray<FNameEntry*>` | `0x2B0AC38` |
| `UObject`: Outer / Name / Class | `+0x24` / `+0x28` / `+0x30` |
| `ULocalPlayer`: Actor / ControllerId | `+0x3C` / `+0x60` |
| `ANTPlayerController::m_NTPawn` | `+0x614` |
| QLOC current controller / input mode | `0x2B551F0` / `0x2B551E8` |
| Joystick table (stride `0x474`) / count | `0x2B6C4E4` / `0x2B6C4E8` |
| `UObject::CallFunction` / `ProcessEvent` | `0x47B370` / `0x47B7B0` |

## Tools (`tools/`)

- `setup.py`: verifies and backs up the originals, then builds everything into `build/`
- `upkdecomp.py` / `lzo.py`: LZO package decompression
- `upktables.py`: name, import and export tables
- `disasm.py` / `dumpall.py`: UnrealScript bytecode disassembler (`HEX=1` shows raw bytes)
- `props.py`: dumps default-object properties
- `upkpatch.py`: uncompressed package writer and bytecode assembler
- `build_packages.py`: the script patches
- `patch_exe.py`: the native exe patches
- `peutil.py` / `x86.py`: PE and capstone helpers for exe analysis
- `make_release.py`: zips the installed build and the sources for a local checkpoint
