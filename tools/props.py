"""Dump the tagged properties of an export (e.g. a Default__ object)."""
import struct, sys, os
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from upktables import Pkg
from disasm import find

def read_tags(pk, d, p, end, depth=0):
    out = []
    while p < end:
        n = pk.nm(*struct.unpack_from('<ii', d, p)); p += 8
        if n == 'None': break
        t = pk.nm(*struct.unpack_from('<ii', d, p)); p += 8
        size, aidx = struct.unpack_from('<ii', d, p); p += 8
        extra = ''
        if t == 'StructProperty': extra = pk.nm(*struct.unpack_from('<ii', d, p)); p += 8
        elif t == 'BoolProperty': extra = str(d[p]); p += 1
        elif t == 'ByteProperty': extra = pk.nm(*struct.unpack_from('<ii', d, p)); p += 8
        val = d[p:p + size]
        out.append((n, t, size, aidx, extra, p, val)); p += size
    return out, p

if __name__ == '__main__':
    pk = Pkg(sys.argv[1]); i = find(pk, sys.argv[2]); e = pk.exps[i - 1]
    d = pk.d; p = e['off'] + 4  # skip NetIndex
    tags, p = read_tags(pk, d, p, e['off'] + e['size'])
    for n, t, size, aidx, extra, off, val in tags:
        v = val.hex(' ') if size <= 48 else val[:48].hex(' ') + ' ...'
        if t == 'IntProperty': v = struct.unpack('<i', val)[0]
        if t == 'FloatProperty': v = struct.unpack('<f', val)[0]
        if t == 'ByteProperty' and size == 8: v = pk.nm(*struct.unpack('<ii', val))
        if t == 'ByteProperty' and size == 1: v = val[0]
        if t in ('ObjectProperty', 'ClassProperty', 'ComponentProperty'):
            o = struct.unpack('<i', val)[0]; v = pk.path(o) if o else 'None'
        print('%s[%d] %s %s size=%d @0x%x = %s' % (n, aidx, t, extra, size, off, v))
