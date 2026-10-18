import struct, sys, os
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from upkhdr import header
from lzo import lzo1x_decompress
def decompress(path, outpath):
    h = header(path); data = open(path,'rb').read()
    total = max(u+s for u,s,_,_ in h['chunks'])
    out = bytearray(total)
    out[:h['nameoff']] = data[:h['nameoff']]  # header (compression flags left as-is)
    for uoff, usize, coff, csize in h['chunks']:
        tag, bs, cs, us = struct.unpack_from('<4I', data, coff); p = coff+16
        blocks=[]; acc=0
        while acc < us:
            bc, bu = struct.unpack_from('<2I', data, p); p += 8; blocks.append((bc,bu)); acc += bu
        o = uoff
        for bc, bu in blocks:
            d = lzo1x_decompress(data[p:p+bc], bu); p += bc
            assert len(d)==bu, (len(d),bu)
            out[o:o+bu] = d; o += bu
    open(outpath,'wb').write(out); return h
if __name__=='__main__':
    for p in sys.argv[2:]:
        h=decompress(p, os.path.join(sys.argv[1], os.path.basename(p)))
        print('ok', p, len(h['chunks']))
