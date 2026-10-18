# How the mod works

DmC: Devil May Cry runs on Unreal Engine 3 (game build 1.0.8916.1, 32-bit). The stock UE3
local-multiplayer code is still in the game: `GameViewportClient.CreatePlayer`, the splitscreen
layout table `SplitscreenInfo`, and per-player viewports. The mod switches that code back on and
works around the places where DmC and QLOC's PC port assume a single player.

## Files changed

`tools/setup.py` builds all of these from the user's own unmodified game files.

| File | Change |
|---|---|
| `DevilGame/CookedPCConsole/Engine.upk` | Stored uncompressed. Three unused cheats are repurposed: `SetOnlineDebugLevel` becomes `AddPlayer <ControllerId>`, `RememberSpot` becomes `SplitAxis` and `DebugPause` becomes `RemovePlayer`. Also changes `UpdateActiveSplitscreenType` and `PlayerController.GetPlayerViewPoint`. `Default2PSplitType` is set to `eSST_2P_VERTICAL`. |
| `DevilGame/CookedPCConsole/DevilGame.upk` | Stored uncompressed. Changes `DVGameInfo.PostLogin` (see "Spawning player 2"). Two unused cheats are repurposed: `LockStormSword` becomes `Despawn` and `LockSpiralTrap` becomes `RestartPlayer`. |
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
- `NTGameInfo_SP.RestartPlayer` starts with `NTAIServiceProvider.Get().ClearCoordinator()`, a reset
  meant for player 1's checkpoint restarts. Running it for player 2's join had two effects:
  - It wiped the enemy AI coordinator under a live fight, so enemies stopped attacking player 1.
  - Spawning or teleporting player 2 into an arena crashed in
    `ADVAICoordinator::execSetParticipantAction`.
- The fix inserts a guard: skip it unless the controller is player 1. It's added with
  `upkpatch.insert_code`, which relocates every absolute jump in the function.
- The pawn spawns at the checkpoint's start point, where player 1 usually still stands. That is why
  the spawn ignores collision.
- DmC players own their body through `NTPlayerController.m_NTPawn`. `NTPossess` never calls the
  engine's `Possess`, so `Controller.Pawn` stays empty. Pawn work therefore happens in DevilGame cheats
  that run on player 2's own controller, through `ConsoleCommand`.
- `AddPlayer` then runs `Teleport` (DevilGame, repurposed from `LockScythe`). It moves `m_NTPawn` next
  to `NT_GetLocalPlayerPawn()` (player 1), trying +X, -X, +Y, then above, and matches player 1's
  rotation. Pressing F6 again just regroups.

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
- `SplitAxis` (F7) cycles `DesiredSplitscreenType`: vertical → horizontal → `SHARED_SCREEN` (6, i.e.
  `eSST_MAX`). It then calls `LayoutPlayers`.
- `UpdateActiveSplitscreenType` is rewritten with the stock rules, plus one more: with two players,
  `SHARED_SCREEN` gives `eSST_NONE`. That layout has a single fullscreen entry in `SplitscreenInfo`, so
  player 2's view gets zero size and only player 1's camera is drawn.
- Shared camera: code appended to `PlayerController.GetPlayerViewPoint`, after DmC's camera has set
  `out_Location`. It runs for player 1 when two players share one view and the game is not in
  cinematic mode:
  - Player 1's pawn comes from `NT_GetLocalPlayerPawn()`. Player 2's is found with
    `DynamicActors(class'Pawn')` as the pawn whose `Owner` is player 2's controller
    (`NTPawn.PossessedBy` calls `SetOwner`).
  - It keeps the camera angle.
  - It moves the camera by half of the P1→P2 vector, so it centres on the midpoint.
  - It pulls the camera back along the camera→player-1 direction by `0.6 × distance`.

## Dropping and rejoining (F8 / F6)

- Destroying player 2's controller would run `NTPlayerController.Destroyed`, which calls
  `NTGFxMovieManager.Get().RemoveIngameUIReferences()` on the global UI manager.
- So F8 (`RemovePlayer`) keeps player 2 logged in. It:
  - runs `ConsoleCommand("Despawn")` on player 2's controller, which reaches DevilGame's cheat:
    `Outer.NTUnPossessAndDestroy()`
  - switches to `DROPPED` (7). This is the same single view as `SHARED_SCREEN`, but it tells F6 to
    restore the split.
- F6 (`AddPlayer`) finds player 2 without a pawn and runs `ConsoleCommand("RestartPlayer")`. That
  DevilGame cheat does the same `NTGameInfo_SP.RestartPlayer` + `PostRestartPlayer` as a mid-mission
  join. F6 then restores the split and regroups.

## Pause menu entry (`tools/build_ui.py`)

- The ESC menu is the Scaleform movie `DevilIngameUI.IngameMenu`, inside `Dante_Archetypes_SF.upk`.
  It is a GFx 3 / SWF 8 movie with AS2 and CLIK components.
- The class `Scripts.IngameMenu` wires seven fixed buttons in `Hook_InitAsMainGame` and calls back
  into UnrealScript with `ExternalInterface.call(...)`, which reaches
  `DVGFxMovieHandler_IngameUI_Callbacks` by function name.
- The mod appends AS2 to the class's `DoInitAction`, just before `End`, so no existing branch moves:
  - It wraps `Hook_InitAsMainGame`.
  - It attaches CLIK `Button` clips (an exported symbol of the movie): "SplitScreen Mod" below the
    last stock button, plus a three-row submenu.
- The submenu calls the game's existing `ExecConsoleCommand` callback with the mod's commands.
  `AddPlayer 100+n` sets the split view directly.
- Menu state is kept in `_global.coopP2` and `_global.coopView`.
- `tools/swf.py` (tag lister and AS2 disassembler) and `tools/as2.py` (assembler) do the SWF work.
  The movie's `RawData` array is rewritten and the export is appended at the end of the package.

## Pauses and cutscenes

- The game has one shared in-game UI movie. `NTPlayerController.InitGFxMovieHandler_IngameUI` runs on
  every possess and sets the UI callbacks' `m_pController = self`, so player 2 stole it.
  - Effect: popups and menus paused through player 1 but resumed through player 2, and player 1's
    pause entry was never released, so the game froze.
  - Fix (NTGameFramework): only the player whose pawn is `NT_GetLocalPlayerPawn()` may bind it.
- Cutscenes: player 1's `DVPlayerController.SetCinematicMode(true)` runs `AddPlayer 201`, which
  calls `SetCinematicMode(true, hide, HUD untouched, …)` on player 2. Leaving a cutscene runs
  `AddPlayer 200`.

- Joining while paused leaves the new pawn overlapping player 1 with nothing ticking, and the game
  locks up. So while `WorldInfo.Pauser != None`, `AddPlayer`/`RemovePlayer` only record "join" or
  "drop" in `CheatManager.ViewingFrom`, a localized string used only by the debug `ViewSelf` cheat.
- View changes while paused are queued as a command string in `CheatManager.OwnCamera`.
- `AddPlayer 200` carries out the recorded requests. If player 1 isn't in a cutscene, it then takes
  player 2 out of cinematic mode and regroups them via `Teleport`. `DVPlayerController.ResumeGame` and `DVPlayerController.SetCinematicMode(false)` run
  it, so player 2 catches up after every pause, popup and cutscene.

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
