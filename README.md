# DmC: Devil May Cry (2013): Local Split-Screen Co-op

A fan mod that adds **2-player couch co-op** to DmC: Devil May Cry (PC, Steam). Each player has their
own Dante and their own camera, in side-by-side or top/bottom split screen.

> Work in progress. Two-player split screen works in missions. Several systems are still built
> for one player, so expect rough edges (see [Known issues](#known-issues)).

## Features

- Player 2 joins mid-mission on the second controller and spawns beside player 1
- Each controller drives its own Dante
- Split screen, side by side by default, with a key to switch to top/bottom
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
| **F7** | Cycle the view: side by side → top/bottom → shared screen (one camera framing both players, *experimental*) |
| **F8** | Drop player 2 (their Dante leaves) and show player 1 fullscreen, for example for platforming or QTE sections |

- Player 1 uses the first controller, plus keyboard and mouse.
- Player 2 uses the second controller.
- Press F6 in a mission, not on the main menu.

## Known issues

- Single-player systems still assume one Dante. Player 2 can lock on to and target player 1, and the
  HUD, checkpoints and death handling are player 1's.
- The shared-screen camera is a first version: it can clip through walls when the players spread out, and player 2's stick directions follow player 2's own (hidden) camera.
- Rumble and on-screen button prompts follow whichever controller was used last.
- If player 1 uses the keyboard, controller buttons may pause for both players until a controller
  button is pressed.

## Roadmap

- [x] Second local player with their own camera and controller
- [x] Drop player 2 / single-screen mode for platforming and QTE sections
- [~] Shared camera mode, with both players on one screen (first version)
- [ ] Player 2 not targeting player 1
- [ ] Shared HUD, health and death rules
- [ ] Distinct character models for player 2

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
