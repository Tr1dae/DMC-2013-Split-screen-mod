"""Minimal PE helpers for the 32-bit DmC exe."""
import os, struct
EXE = os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))),
                   'Binaries', 'Win32', 'DMC-DevilMayCry.exe')  # CoopMod/ sits in the game folder
class PE:
    def __init__(s, path=EXE):
        s.d = d = open(path, 'rb').read()
        pe = struct.unpack_from('<I', d, 0x3c)[0]; optsz = struct.unpack_from('<H', d, pe + 20)[0]
        nsec = struct.unpack_from('<H', d, pe + 6)[0]; s.base = struct.unpack_from('<I', d, pe + 24 + 28)[0]
        s.secs = []; o = pe + 24 + optsz
        for _ in range(nsec):
            n = d[o:o + 8].rstrip(b'\0').decode(); vs, va, rs, ra = struct.unpack_from('<4I', d, o + 8)
            s.secs.append((n, va, vs, ra, rs)); o += 40
    def off2va(s, off):
        for n, va, vs, ra, rs in s.secs:
            if ra <= off < ra + rs: return s.base + va + off - ra
    def va2off(s, v):
        for n, va, vs, ra, rs in s.secs:
            if s.base + va <= v < s.base + va + rs: return v - s.base - va + ra
    def cstr_start(s, off):
        while s.d[off - 1] != 0: off -= 1
        return off
    def refs(s, va):
        import re
        return [m.start() for m in re.finditer(re.escape(struct.pack('<I', va)), s.d)]
