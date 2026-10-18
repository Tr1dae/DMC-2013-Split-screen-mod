"""Package the currently installed (tested) CoopMod build plus sources into a zip.

Usage (from the game folder): python CoopMod/tools/make_release.py <name>
"""
import glob, hashlib, os, sys, zipfile

INSTALLED = {
    'DevilGame/CookedPCConsole/Engine.upk': 'build/Engine.upk',
    'DevilGame/CookedPCConsole/DevilGame.upk': 'build/DevilGame.upk',
    'DevilGame/CookedPCConsole/NTGameFramework.upk': 'build/NTGameFramework.upk',
    'DevilGame/Config/DefaultInput.ini': 'build/DefaultInput.ini',
    'Binaries/Win32/DMC-DevilMayCry.exe': 'build/DMC-DevilMayCry.exe',
    'Binaries/Win32/xinput1_3.dll': 'build/xinput1_3.dll',
}
SOURCES = ['tools/*.py', 'native/*.c', 'native/*.def', 'native/*.bat', 'install.bat', 'uninstall.bat', 'README.md']


def sha(data):
    return hashlib.sha1(data).hexdigest()[:12]


def main(name):
    os.makedirs('CoopMod/releases', exist_ok=True)
    zp = 'CoopMod/releases/%s.zip' % name
    files = {src: 'CoopMod/' + arc for src, arc in INSTALLED.items()}
    for pat in SOURCES:
        for f in glob.glob('CoopMod/' + pat):
            files[f] = f.replace(os.sep, '/')
    with zipfile.ZipFile(zp, 'w', zipfile.ZIP_DEFLATED, compresslevel=9) as z:
        for src, arc in files.items():
            z.write(src, arc)
    with zipfile.ZipFile(zp) as z:
        assert z.testzip() is None
        for src, arc in INSTALLED.items():
            assert sha(z.read('CoopMod/' + arc)) == sha(open(src, 'rb').read()), arc
            print('  %s  %s' % (sha(z.read('CoopMod/' + arc)), arc))
        print('%s: %d files, %.1f MB, verified' % (zp, len(z.namelist()), os.path.getsize(zp) / 2 ** 20))


if __name__ == '__main__':
    main(sys.argv[1])
