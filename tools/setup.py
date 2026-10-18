"""Back up the original game files and build the co-op mod from them.

Run from anywhere: python -I CoopMod/tools/setup.py
The CoopMod folder must sit inside the game folder (next to Binaries/ and DevilGame/).
Nothing in the game folder is changed; run install.bat afterwards to copy build/ into the game.
"""
import hashlib, os, shutil, subprocess, sys

HERE = os.path.dirname(os.path.abspath(__file__))
MOD = os.path.dirname(HERE)
GAME = os.path.dirname(MOD)

# Unmodified Steam files these patches were written against (game version 1.0.8916.1, 2025 update).
ORIGINALS = {
    'DevilGame/CookedPCConsole/Engine.upk':          ('backup/CookedPCConsole/Engine.upk', 'd17ec467c04f545ea5ab52b3a01bd11eeed5dad8'),
    'DevilGame/CookedPCConsole/DevilGame.upk':       ('backup/CookedPCConsole/DevilGame.upk', 'c66af7c6dca5a267722797ff340c954883aeadb7'),
    'DevilGame/CookedPCConsole/NTGameFramework.upk': ('backup/CookedPCConsole/NTGameFramework.upk', 'ea6aed0d4f12ff9d300514b07b1b2d9046778125'),
    'DevilGame/Config/DefaultInput.ini':             ('backup/Config/DefaultInput.ini', 'f363f561b9bb5e861175f89c86db5f22008dff27'),
    'Binaries/Win32/DMC-DevilMayCry.exe':            ('backup/Binaries/DMC-DevilMayCry.exe', 'b0e636b04d1dbda991e946af14f36fa79ad57912'),
}

BINDINGS = [
    '; CoopMod: F6 player 2 joins on the second gamepad (ControllerId 1) / respawns / regroups',
    'Bindings=(Name="F6",\t\t\tCommand="AddPlayer 1")',
    '; CoopMod: F7 cycles side-by-side / top-bottom / shared screen',
    'Bindings=(Name="F7",\t\t\tCommand="SplitAxis")',
    '; CoopMod: F8 drops player 2 (single player view until F6)',
    'Bindings=(Name="F8",\t\t\tCommand="RemovePlayer")',
    '; CoopMod: F10 force-clears a stuck pause',
    'Bindings=(Name="F10",\t\t\tCommand="ClearPause")',
]


def sha1(path):
    with open(path, 'rb') as f:
        return hashlib.sha1(f.read()).hexdigest()


def backup_originals():
    for game_rel, (backup_rel, want) in ORIGINALS.items():
        src, dst = os.path.join(GAME, game_rel), os.path.join(MOD, backup_rel)
        if os.path.exists(dst):
            if sha1(dst) != want:
                sys.exit('backup %s is not the original file; delete it and verify game files in Steam' % backup_rel)
            continue
        if sha1(src) != want:
            sys.exit('%s is not the expected original.\n'
                     'Use Steam > DmC > Properties > Installed Files > Verify integrity, then run setup again.' % game_rel)
        os.makedirs(os.path.dirname(dst), exist_ok=True)
        shutil.copy2(src, dst)
        print('backed up', game_rel)


def build_input_ini():
    src = os.path.join(MOD, 'backup/Config/DefaultInput.ini')
    lines = open(src, 'r', encoding='latin1', newline='').read().split('\n')
    anchor = next(i for i, l in enumerate(lines) if l.startswith('Bindings=(Name="XboxTypeS_RightY"'))
    eol = '\r' if lines[anchor].endswith('\r') else ''
    lines[anchor + 1:anchor + 1] = [b + eol for b in BINDINGS]
    with open(os.path.join(MOD, 'build/DefaultInput.ini'), 'w', encoding='latin1', newline='') as f:
        f.write('\n'.join(lines))
    print('wrote build/DefaultInput.ini')


def main():
    backup_originals()
    os.makedirs(os.path.join(MOD, 'build'), exist_ok=True)
    py = [sys.executable, '-I']
    subprocess.check_call(py + [os.path.join(HERE, 'build_packages.py'),
                                os.path.join(MOD, 'backup/CookedPCConsole'), os.path.join(MOD, 'build')])
    shutil.rmtree(os.path.join(MOD, 'build/_scratch'), ignore_errors=True)
    subprocess.check_call(py + [os.path.join(HERE, 'patch_exe.py'),
                                os.path.join(MOD, 'backup/Binaries/DMC-DevilMayCry.exe'),
                                os.path.join(MOD, 'build/DMC-DevilMayCry.exe')])
    build_input_ini()
    if not os.path.exists(os.path.join(MOD, 'build/xinput1_3.dll')):
        print('note: build/xinput1_3.dll (optional diagnostics helper) not built; see native/build.bat')
    print('\nDone. Run install.bat to copy the mod into the game.')


if __name__ == '__main__':
    main()
