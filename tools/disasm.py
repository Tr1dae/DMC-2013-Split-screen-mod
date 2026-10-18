"""UE3 (v845) UnrealScript bytecode disassembler for decompressed DmC packages.

Usage: python disasm.py <decompressed.upk> <Class.Function> [...]
"""
import struct, sys, os
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from upktables import Pkg

FUNC_FLAGS = {0x1: 'Final', 0x2: 'Defined', 0x4: 'Iterator', 0x8: 'Latent', 0x10: 'PreOperator',
              0x20: 'Singular', 0x40: 'Net', 0x80: 'NetReliable', 0x100: 'Simulated', 0x200: 'Exec',
              0x400: 'Native', 0x800: 'Event', 0x1000: 'Operator', 0x2000: 'Static',
              0x4000: 'HasOptionalParms', 0x8000: 'Const', 0x20000: 'Public', 0x40000: 'Private',
              0x80000: 'Protected', 0x100000: 'Delegate', 0x200000: 'NetServer',
              0x400000: 'HasOutParms', 0x800000: 'HasDefaults', 0x1000000: 'NetClient',
              0x2000000: 'DLLImport', 0x4000000: 'K2Call'}

SCRIPT_START = 48  # NetIndex + None + 9 dwords (Next, Super, ScriptText, Children, CppText, Line, TextPos, BSize, SSize)


def parse_function(pk, idx):
    e = pk.exps[idx - 1]
    b = pk.d[e['off']:e['off'] + e['size']]
    vals = struct.unpack_from('<9i', b, 12)
    bsize, ssize = vals[7], vals[8]
    p = SCRIPT_START + ssize
    inative, oper, flags = struct.unpack_from('<HBI', b, p)
    q = p + 7
    rep = None
    if flags & 0x40:
        rep, = struct.unpack_from('<H', b, q); q += 2
    fname = struct.unpack_from('<ii', b, q)
    return dict(export=e, raw=b, header=vals, next=vals[0], children=vals[3], bsize=bsize, ssize=ssize,
                script=b[SCRIPT_START:SCRIPT_START + ssize], inative=inative, oper=oper, flags=flags,
                flags_off=e['off'] + p + 3, rep=rep, friendly=pk.nm(*fname), tail_off=q + 8)


def flagstr(f):
    return '|'.join(n for b, n in FUNC_FLAGS.items() if f & b) + ' (0x%x)' % f


class Disasm:
    def __init__(s, pk, script):
        s.pk, s.b, s.p, s.mem = pk, script, 0, 0
        s.lines = []
        s.jumps = []        # disk offsets of absolute jump-target operands (u16, memory offsets)
        s.stmts = []        # (memory offset, disk offset) of each top-level statement

    def u8(s):
        v = s.b[s.p]; s.p += 1; s.mem += 1; return v

    def target(s):
        s.jumps.append(s.p)
        return s.u16()

    def u16(s):
        v, = struct.unpack_from('<H', s.b, s.p); s.p += 2; s.mem += 2; return v

    def i32(s):
        v, = struct.unpack_from('<i', s.b, s.p); s.p += 4; s.mem += 4; return v

    def f32(s):
        v, = struct.unpack_from('<f', s.b, s.p); s.p += 4; s.mem += 4; return v

    def obj(s):
        v, = struct.unpack_from('<i', s.b, s.p); s.p += 4; s.mem += 8
        if v == 0: return 'None'
        try: return s.pk.path(v) + ('' if v > 0 else '@imp')
        except Exception: return '?obj%d' % v

    def name(s):
        i, n = struct.unpack_from('<ii', s.b, s.p); s.p += 8; s.mem += 8
        try: return s.pk.nm(i, n)
        except Exception: return '?name%d' % i

    def zstr(s):
        e = s.b.index(0, s.p); v = s.b[s.p:e].decode('latin1'); s.mem += e + 1 - s.p; s.p = e + 1; return v

    def wzstr(s):
        e = s.p
        while s.b[e:e + 2] != b'\0\0': e += 2
        v = s.b[s.p:e].decode('utf-16le'); s.mem += e + 2 - s.p; s.p = e + 2; return v

    def params(s):
        out = []
        while s.b[s.p] != 0x16:
            out.append(s.expr())
        s.u8()
        return out

    def expr(s):
        t = s.u8()
        if t >= 0x70: return 'native%d(%s)' % (t, ', '.join(s.params()))
        if t >= 0x60:
            return 'native%d(%s)' % (((t - 0x60) << 8) + s.u8(), ', '.join(s.params()))
        if t == 0x00: return 'local:' + s.obj()
        if t == 0x01: return 'inst:' + s.obj()
        if t == 0x02: return 'default:' + s.obj()
        if t == 0x03: return 'state:' + s.obj()
        if t == 0x04: return 'return ' + s.expr()
        if t == 0x05:
            o = s.obj(); sz = s.u8(); return 'switch(%s) [%s,%d]' % (s.expr(), o, sz)
        if t == 0x06: return 'jump 0x%x' % s.target()
        if t == 0x07: off = s.target(); return 'if !(%s) jump 0x%x' % (s.expr(), off)
        if t == 0x08: return 'stop'
        if t == 0x09: ln = s.u16(); s.u8(); return 'assert(%s) line %d' % (s.expr(), ln)
        if t == 0x0A:
            pos = s.p; off = s.u16()
            if off != 0xFFFF: s.jumps.append(pos)
            return 'default: (next 0x%x)' % off if off == 0xFFFF else 'case %s: (next 0x%x)' % (s.expr(), off)
        if t == 0x0B: return 'nothing'
        if t == 0x0D: return 'goto ' + s.expr()
        if t == 0x0E: return 'eatret[%s] %s' % (s.obj(), s.expr())
        if t == 0x0F: a = s.expr(); return '%s = %s' % (a, s.expr())
        if t == 0x10: i = s.expr(); return '%s[%s]' % (s.expr(), i)
        if t == 0x11: return 'new(%s)' % ', '.join(s.expr() for _ in range(5))
        if t in (0x12, 0x19):
            a = s.expr(); skip = s.u16(); f = s.obj(); sz = s.u8()
            return '%s%s.%s' % (a, '.static' if t == 0x12 else '', s.expr())
        if t == 0x13: o = s.obj(); return 'class<%s>(%s)' % (o, s.expr())
        if t == 0x14: a = s.expr(); return '%s = %s' % (a, s.expr())
        if t == 0x15: return 'endparmvalue'
        if t == 0x16: return ')'
        if t == 0x17: return 'self'
        if t == 0x18: off = s.u16(); return 'skip(0x%x){%s}' % (off, s.expr())
        if t == 0x1A: i = s.expr(); return '%s[%s]' % (s.expr(), i)
        if t == 0x1B: n = s.name(); return '%s(%s)' % (n, ', '.join(s.params()))
        if t == 0x1C: o = s.obj(); return 'final:%s(%s)' % (o, ', '.join(s.params()))
        if t == 0x1D: return str(s.i32())
        if t == 0x1E: return '%gf' % s.f32()
        if t == 0x1F: return repr(s.zstr())
        if t == 0x20: return 'obj:' + s.obj()
        if t == 0x21: return "name'%s'" % s.name()
        if t == 0x22: return 'rot(%d,%d,%d)' % (s.i32(), s.i32(), s.i32())
        if t == 0x23: return 'vect(%g,%g,%g)' % (s.f32(), s.f32(), s.f32())
        if t == 0x24: return 'byte(%d)' % s.u8()
        if t == 0x25: return '0'
        if t == 0x26: return '1'
        if t == 0x27: return 'true'
        if t == 0x28: return 'false'
        if t == 0x29: return 'nativeparm:' + s.obj()
        if t == 0x2A: return 'none'
        if t == 0x2C: return str(s.u8())
        if t == 0x2D: return 'bool(%s)' % s.expr()
        if t == 0x2E: o = s.obj(); return '%s(%s)' % (o, s.expr())
        if t == 0x2F: a = s.expr(); off = s.target(); return 'foreach %s (end 0x%x)' % (a, off)
        if t == 0x30: return 'iteratorpop'
        if t == 0x31: return 'iteratornext'
        if t in (0x32, 0x33):
            o = s.obj(); a = s.expr(); return '%s %s %s' % (a, '==' if t == 0x32 else '!=', s.expr())
        if t == 0x34: return 'U' + repr(s.wzstr())
        if t == 0x35:
            prop = s.obj(); st = s.obj(); s.u8(); s.u8(); return '%s.%s' % (s.expr(), prop.split('.')[-1])
        if t == 0x36: return '%s.Length' % s.expr()
        if t == 0x37: n = s.name(); return 'global.%s(%s)' % (n, ', '.join(s.params()))
        if t == 0x38: c = s.u8(); return 'cast%d(%s)' % (c, s.expr())
        if t == 0x39: a = s.expr(); s.u16(); return '%s.Insert(%s)' % (a, ', '.join(s.params()))
        if t == 0x3A: return 'returnnothing[%s]' % s.obj()
        if t in (0x3B, 0x3C, 0x3D, 0x3E):
            return 'delcmp%x(%s)' % (t, ', '.join(s.params()))
        if t == 0x3F: return 'emptydelegate'
        if t == 0x40: a = s.expr(); s.u16(); return '%s.Remove(%s)' % (a, ', '.join(s.params()))
        if t == 0x41: return 'debuginfo(%d,%d,%d,%d)' % (s.i32(), s.i32(), s.i32(), s.u8())
        if t == 0x42:
            loc = s.u8(); o = s.obj(); n = s.name(); return 'delegate:%s(%s)' % (n, ', '.join(s.params()))
        if t == 0x43: n = s.name(); o = s.obj(); return 'delegateprop:%s' % n
        if t == 0x44: a = s.expr(); return '%s = %s' % (a, s.expr())
        if t == 0x45:
            c = s.expr(); s.u16(); a = s.expr(); s.u16(); return '(%s ? %s : %s)' % (c, a, s.expr())
        if t == 0x46: a = s.expr(); s.u16(); return '%s.Find(%s)' % (a, ', '.join(s.params()))
        if t == 0x47: a = s.expr(); s.u16(); return '%s.FindStruct(%s)' % (a, ', '.join(s.params()))
        if t == 0x48: return 'out:' + s.obj()
        if t == 0x49:
            sz = s.u16(); v = s.expr(); s.u8(); return 'defaultparm(%s)' % v
        if t == 0x4A: return 'emptyparm'
        if t == 0x4B: return 'instdelegate:' + s.name()
        if t == 0x51: return 'iface(%s)' % s.expr()
        if t == 0x52: o = s.obj(); return 'ifacecast<%s>(%s)' % (o, s.expr())
        if t == 0x53: return 'END'
        if t == 0x54: a = s.expr(); s.u16(); return '%s.Add(%s)' % (a, ', '.join(s.params()))
        if t == 0x55: a = s.expr(); s.u16(); return '%s.AddItem(%s)' % (a, ', '.join(s.params()))
        if t == 0x56: a = s.expr(); s.u16(); return '%s.RemoveItem(%s)' % (a, ', '.join(s.params()))
        if t == 0x57: a = s.expr(); s.u16(); return '%s.InsertItem(%s)' % (a, ', '.join(s.params()))
        if t == 0x58:
            a = s.expr(); it = s.expr(); hasidx = s.u8(); ix = s.expr(); off = s.target()
            return 'foreach %s(%s, %s) (end 0x%x)' % (a, it, ix, off)
        if t == 0x59: a = s.expr(); s.u16(); return '%s.Sort(%s)' % (a, ', '.join(s.params()))
        if t == 0x5A: return 'filtereditoronly 0x%x' % s.target()
        raise ValueError('unknown token 0x%02x at disk 0x%x' % (t, s.p - 1))

    def run(s):
        while s.p < len(s.b):
            m = s.mem; p0 = s.p
            s.stmts.append((m, p0))
            try:
                txt = s.expr()
                if getattr(s, 'hexdump', False):
                    txt += '\n        ' + s.b[p0:s.p].hex(' ')
                s.lines.append('  %04x: %s' % (m, txt))
            except Exception as ex:
                s.lines.append('  %04x: !! %s ; rest=%s' % (m, ex, s.b[s.p:s.p + 32].hex(' ')))
                break
        return s.lines


def find(pk, path):
    for i in range(1, len(pk.exps) + 1):
        if pk.path(i) == path: return i
    raise KeyError(path)


def show(pk, path):
    i = find(pk, path)
    f = parse_function(pk, i)
    print('%s  [export %d] flags=%s native=%d bsize=%d ssize=%d' % (path, i, flagstr(f['flags']), f['inative'], f['bsize'], f['ssize']))
    c = f['children']; locs = []
    while c > 0:
        e = pk.exps[c - 1]; locs.append('%s %s' % (pk.clsname(e), e['name']))
        c = struct.unpack_from('<i', pk.d, e['off'] + 12)[0]
    if locs: print('  params/locals:', ', '.join(locs))
    d = Disasm(pk, f['script']); d.hexdump = os.environ.get('HEX') == '1'
    for l in d.run(): print(l)


if __name__ == '__main__':
    pk = Pkg(sys.argv[1])
    for p in sys.argv[2:]:
        show(pk, p); print()
