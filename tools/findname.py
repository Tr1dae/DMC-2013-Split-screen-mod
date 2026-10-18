"""Find packages whose name table mentions a string (decompresses only the first chunk block).
Usage: python findname.py <CookedPCConsole dir> <needle> [...]"""
import os, struct, sys
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from upkhdr import header
from lzo import lzo1x_decompress
d, needles = sys.argv[1], [n.encode() for n in sys.argv[2:]]
for f in sorted(os.listdir(d)):
    if not f.lower().endswith('.upk'): continue
    p = os.path.join(d, f)
    try:
        h = header(p)
        with open(p, 'rb') as fh: data = fh.read(h['chunks'][0][2] + min(h['chunks'][0][3], 1 << 22)) if h['chunks'] else fh.read(1 << 22)
        if h['chunks']:
            uoff, usize, coff, csize = h['chunks'][0]
            tag, bs, cs, us = struct.unpack_from('<4I', data, coff); q = coff + 16
            bc, bu = struct.unpack_from('<2I', data, q); q += 8
            nblocks = 0; acc = 0; sizes = []
            while acc < us: b1, b2 = struct.unpack_from('<2I', data, coff + 16 + 8 * len(sizes)); sizes.append((b1, b2)); acc += b2
            q = coff + 16 + 8 * len(sizes); blob = b''
            for b1, b2 in sizes[:4]:
                blob += lzo1x_decompress(data[q:q + b1], b2); q += b1
        else:
            blob = data
        hits = [n.decode() for n in needles if n in blob]
        if hits: print(f, hits)
    except Exception as e:
        print('ERR', f, e)
