import struct, sys, os
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from upkhdr import header
class Pkg:
    def __init__(s, path):
        s.h = h = header(path); s.d = d = open(path,'rb').read()
        p = h['nameoff']; s.names=[]
        for _ in range(h['namecount']):
            n,=struct.unpack_from('<i',d,p); p+=4
            if n<0: nm=d[p:p-2*n].decode('utf-16le'); p+=-2*n
            else: nm=d[p:p+n].decode('latin1'); p+=n
            s.names.append(nm.rstrip('\0')); p+=8
        p=h['impoff']; s.imps=[]
        for _ in range(h['impcount']):
            cp,cpn,cn,cnn,outer,on,onn=struct.unpack_from('<iiiiiii',d,p); p+=28
            s.imps.append(dict(cls=s.nm(cn,cnn),outer=outer,name=s.nm(on,onn)))
        p=h['expoff']; s.exps=[]
        for _ in range(h['expcount']):
            ci,si,oi,on,onn,ai,of,ss,so,ef,nc=struct.unpack_from('<iiiiiiQiiii',d,p); p+=48
            p+=4*nc+16+4
            s.exps.append(dict(cls=ci,sup=si,outer=oi,name=s.nm(on,onn),size=ss,off=so,flags=of))
    def nm(s,i,n): return s.names[i]+('_%d'%(n-1) if n else '')
    def ref(s,i):
        if i>0: return s.exps[i-1]
        if i<0: return s.imps[-i-1]
    def path(s,i):
        parts=[]
        while i:
            o=s.ref(i); parts.append(o['name']); i=o['outer']
        return '.'.join(reversed(parts))
    def clsname(s,e):
        c=e['cls']; return 'Class' if c==0 else s.ref(c)['name']
if __name__=='__main__':
    pk=Pkg(sys.argv[1]); mode=sys.argv[2]
    if mode=='names': print('\n'.join(pk.names))
    elif mode=='exports':
        for i,e in enumerate(pk.exps,1): print(i, pk.clsname(e), pk.path(i), e['size'])
