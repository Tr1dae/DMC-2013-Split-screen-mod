import struct, sys
def rd(f, fmt): return struct.unpack('<'+fmt, f.read(struct.calcsize('<'+fmt)))
def fstr(f):
    n,=rd(f,'i')
    if n==0: return ''
    if n<0: return f.read(-n*2).decode('utf-16le').rstrip('\0')
    return f.read(n).decode('latin1').rstrip('\0')
def header(path):
    f=open(path,'rb'); h={}
    h['tag'],h['ver'],h['lic'],h['hdrsize']=rd(f,'IHHi')
    h['folder']=fstr(f)
    h['flags'],h['namecount'],h['nameoff'],h['expcount'],h['expoff'],h['impcount'],h['impoff'],h['depoff']=rd(f,'8I')
    h['ieguid'],h['impguids'],h['expguids'],h['thumb']=rd(f,'4I')
    h['guid']=f.read(16).hex()
    gc,=rd(f,'i'); h['gens']=[rd(f,'3i') for _ in range(gc)]
    h['engver'],h['cookver'],h['compflags'],nch=rd(f,'4I')
    h['chunks']=[rd(f,'4I') for _ in range(nch)]
    h['pos']=f.tell()
    return h
if __name__=='__main__':
    for p in sys.argv[1:]:
        h=header(p); print(p); [print(' ',k,v if k!='chunks' else (len(v), v[:3])) for k,v in h.items()]
