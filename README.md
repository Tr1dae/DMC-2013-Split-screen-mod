# DmC: Devil May Cry (2013): Local Split-Screen Co-op

A fan mod that adds **2-player couch co-op** to DmC: Devil May Cry (PC, Steam). Each player has their
own Dante and their own camera, in side-by-side or top/bottom split screen.

> Work in progress. Two-player split screen works in missions. Several systems are still built
> for one player, so expect rough edges (see [Known issues](#known-issues)).

## Features

- Player 2 joins mid-mission on the second controller and spawns beside player 1
- Each controller drives its own character: player 2 plays as Vergil by default (or Dante)
- Split screen, side by side by default, with a key to switch to top/bottom, or a shared camera
- Enemies pick the nearest player and attack both; one shared health pool with a difficulty setting
- "SplitScreen Mod" page in the pause menu for all settings
- Cutscenes and QTEs automatically switch to one fullscreen view (built into the engine)
- Single-player behaviour is unchanged until player 2 joins

## Requirements

- DmC: Devil May Cry on Steam, the current version (1.0.8916.1, July 2025 update). `setup.bat` checks
  your files and refuses to build if they differ.
- [Python 3](https://www.python.org/downloads/) (any recent version, standard library only)
- Two controllers. Xbox-style (XInput) pads are tested.

## Install

1. Download or clone this repository into the game folder, so that it sits next to `Binaries` and `DevilGame`:
   ```
   ...\steamapps\common\DmC Devil May Cry\CoopMod\
   ```
2. Run **`setup.bat`**. It checks that your game files are the unmodified originals, copies them to
   `CoopMod\backup\`, and builds the mod into `CoopMod\build\`. Your game files are not changed yet.
3. Close the game and run **`install.bat`**.

To remove the mod, run **`uninstall.bat`**, or use Steam's *Verify integrity of game files*.

The mod is distributed as source and scripts only. The patched game files are built on your PC from
your own copy of the game.

## Controls

| Key | Action |
|---|---|
| **F6** | Player 2 joins on the second controller and spawns next to player 1. Press again to teleport player 2 back to player 1. After F8, F6 brings player 2 back. |
| **F7** | Cycle the view: side by side → top/bottom → shared screen (one camera that frames both players) |
| **F8** | Drop player 2 (their Dante leaves) and show player 1 fullscreen, for example for platforming or QTE sections |
| **F10** | Force-clear a stuck pause (if the game freezes after a popup) |

In the ESC pause menu, **SplitScreen Mod** (below Main Menu) opens a settings page:
**Split Screen: On/Off** adds or drops player 2, and **Camera** switches between side by side,
top & bottom and shared screen. Changes apply when you resume. B/Back returns to the pause page.

During cutscenes player 2 is hidden and frozen. Afterwards, and after every pause or popup, player 2
is brought back next to player 1.

- Player 1 uses the first controller, plus keyboard and mouse.
- Player 2 uses the second controller.
- Press F6 in a mission, not on the main menu.

## Known issues

- Single-player systems still assume one Dante. Player 2 can lock on to and target player 1, and the
  HUD, checkpoints and death handling are player 1's.
- The shared-screen camera can clip through walls when the players spread far apart, and player 2's stick directions follow player 2's own (hidden) camera.
- If the game ever stays frozen after a popup or menu, press F10 to unfreeze it.
- Rumble and on-screen button prompts follow whichever controller was used last.
- If player 1 uses the keyboard, controller buttons may pause for both players until a controller
  button is pressed.

## Roadmap

- [x] Second local player with their own camera and controller
- [x] Drop player 2 / single-screen mode for platforming and QTE sections
- [x] Shared camera mode, with both players on one screen
- [x] In-game "SplitScreen Mod" settings menu in the pause screen (split, camera, health, player 2 character)
- [x] Enemies fight both players: nearest-player targeting with a switch cooldown, attacks off camera
- [x] Shared health pool (either player's damage and pickups), health multiplier setting
- [ ] Player 2 not targeting player 1
- [x] Player 2 plays as Vergil by default (pause menu: Vergil / Dante): his mesh is retargeted onto Dante's
      skeleton, which it shares bone for bone
- [ ] Kat as player 2: works through the same retarget but shares only 80 of Dante's bones, so her
      fingertips and neck need skinning cleanup in a DCC app first
- [ ] Repackage Vergil's / Kat's meshes into small standalone packages (today they load from level packages)

## How it works

See [docs/TECHNICAL.md](docs/TECHNICAL.md). In short:
- The engine's leftover local-multiplayer code is re-enabled through small UnrealScript bytecode patches.
- A few native fixes in the exe undo the PC port's "any controller drives player 1" logic.

The `tools/` folder has the Python tools written for this: an LZO package decompressor, a bytecode
disassembler and assembler, and a package patcher. They may be useful for other UE3 games.

## Credits and disclaimer

- Inspired by the *DmC Debug Menu* mod on Nexus Mods, which showed that DmC's packages can be patched.
- DmC: Devil May Cry is © Capcom; developed by Ninja Theory, PC port by QLOC.
- This is an unofficial fan project. It is not affiliated with or endorsed by any of them, and no game
  files are included.
- Use at your own risk, and back up your saves.
