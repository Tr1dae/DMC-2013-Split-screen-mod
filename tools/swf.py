"""Minimal SWF / Scaleform GFx (AS2) reader: tag list and ActionScript 2 disassembly.

Usage:
  python swf.py extract <decompressed.upk> <SwfMovie path> <out.gfx>   # RawData -> file
  python swf.py tags <file.gfx>
  python swf.py as <file.gfx>                                         # disassemble all AS2
"""
import struct, sys, os, zlib

TAG_NAMES = {0: 'End', 1: 'ShowFrame', 2: 'DefineShape', 4: 'PlaceObject', 5: 'RemoveObject', 6: 'DefineBits',
             7: 'DefineButton', 9: 'SetBackgroundColor', 10: 'DefineFont', 11: 'DefineText', 12: 'DoAction',
             13: 'DefineFontInfo', 14: 'DefineSound', 22: 'DefineShape2', 26: 'PlaceObject2', 28: 'RemoveObject2',
             32: 'DefineShape3', 33: 'DefineText2', 34: 'DefineButton2', 36: 'DefineBitsLossless2',
             37: 'DefineEditText', 39: 'DefineSprite', 43: 'FrameLabel', 48: 'DefineFont2', 56: 'ExportAssets',
             57: 'ImportAssets', 59: 'DoInitAction', 62: 'DefineFontInfo2', 69: 'FileAttributes',
             70: 'PlaceObject3', 71: 'ImportAssets2', 73: 'DefineFontAlignZones', 74: 'CSMTextSettings',
             75: 'DefineFont3', 77: 'Metadata', 78: 'DefineScalingGrid', 83: 'DefineShape4', 88: 'DefineFontName',
             1000: 'GFx_ExporterInfo', 1001: 'GFx_DefineExternalImage', 1002: 'GFx_FontTextureInfo',
             1003: 'GFx_DefineExternalGradient', 1004: 'GFx_DefineGradientMap', 1005: 'GFx_DefineCompactedFont',
             1006: 'GFx_DefineExternalSound', 1007: 'GFx_DefineExternalStreamSound', 1008: 'GFx_DefineSubImage',
             1009: 'GFx_DefineExternalImage2'}


def extract(upk, path, out):
    sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
    from upktables import Pkg
    from props import read_tags
    pk = Pkg(upk)
    i = next(i for i in range(1, len(pk.exps) + 1) if pk.path(i) == path)
    e = pk.exps[i - 1]
    tags, _ = read_tags(pk, pk.d, e['off'] + 4, e['off'] + e['size'])
    for n, t, size, aidx, extra, off, val in tags:
        if n == 'RawData':
            cnt, = struct.unpack_from('<i', val, 0)
            open(out, 'wb').write(val[4:4 + cnt])
            print('wrote', out, cnt, 'bytes; RawData at file offset', hex(off))
            return off, cnt
    raise KeyError('RawData')


def load(path):
    d = open(path, 'rb').read()
    sig = d[:3]
    if sig in (b'CWS', b'CFX'):
        d = d[:8] + zlib.decompress(d[8:])
    return d


def body_start(d):
    nbits = d[8] >> 3
    rect_bytes = (5 + 4 * nbits + 7) // 8
    return 8 + rect_bytes + 4          # + frame rate (2) + frame count (2)


def iter_tags(d, p, end):
    while p < end:
        code_len, = struct.unpack_from('<H', d, p); start = p; p += 2
        code, ln = code_len >> 6, code_len & 0x3F
        if ln == 0x3F:
            ln, = struct.unpack_from('<I', d, p); p += 4
        yield code, start, p, ln
        p += ln
        if code == 0: break


def list_tags(d, p=None, end=None, depth=0):
    p = body_start(d) if p is None else p
    end = len(d) if end is None else end
    for code, start, body, ln in iter_tags(d, p, end):
        extra = ''
        if code == 39:
            sid, frames = struct.unpack_from('<HH', d, body); extra = 'id=%d frames=%d' % (sid, frames)
        elif code == 56:
            n, = struct.unpack_from('<H', d, body); q = body + 2; items = []
            for _ in range(n):
                cid, = struct.unpack_from('<H', d, q); q += 2
                e = d.index(0, q); items.append('%d=%s' % (cid, d[q:e].decode('latin1'))); q = e + 1
            extra = ', '.join(items)
        elif code == 59:
            extra = 'sprite=%d' % struct.unpack_from('<H', d, body)[0]
        elif code == 43:
            extra = d[body:d.index(0, body)].decode('latin1')
        elif code == 26 or code == 70:
            extra = place_info(d, body, code)
        print('%s%-26s @%06x len=%-6d %s' % ('  ' * depth, TAG_NAMES.get(code, str(code)), start, ln, extra))
        if code == 39:
            list_tags(d, body + 4, body + ln, depth + 1)


def place_info(d, p, code):
    flags = d[p]; q = p + 1
    if code == 70: flags2 = d[q]; q += 1
    depth, = struct.unpack_from('<H', d, q); q += 2
    s = 'depth=%d' % depth
    if code == 70 and (flags2 & 0x08 or (flags2 & 0x10 and flags & 0x02)):
        e = d.index(0, q); s += ' class=' + d[q:e].decode('latin1'); q = e + 1
    if flags & 0x02:
        s += ' char=%d' % struct.unpack_from('<H', d, q)[0]; q += 2
    if flags & 0x04:   # matrix: skip
        q = skip_matrix(d, q)
    if flags & 0x08:
        q = skip_cxform(d, q)
    if flags & 0x10: q += 2
    if flags & 0x20:
        e = d.index(0, q); s += ' name=' + d[q:e].decode('latin1')
    return s


class Bits:
    def __init__(s, d, p): s.d, s.p, s.b = d, p, 0
    def read(s, n):
        v = 0
        for _ in range(n):
            v = (v << 1) | ((s.d[s.p] >> (7 - s.b)) & 1); s.b += 1
            if s.b == 8: s.b = 0; s.p += 1
        return v
    def end(s): return s.p + (1 if s.b else 0)


def skip_matrix(d, p):
    b = Bits(d, p)
    if b.read(1): n = b.read(5); b.read(n); b.read(n)
    if b.read(1): n = b.read(5); b.read(n); b.read(n)
    n = b.read(5); b.read(n); b.read(n)
    return b.end()


def skip_cxform(d, p):
    b = Bits(d, p)
    add, mult = b.read(1), b.read(1); n = b.read(4)
    if mult: [b.read(n) for _ in range(4)]
    if add: [b.read(n) for _ in range(4)]
    return b.end()


# ---------------------------------------------------------------- AS2 disassembler
ACTIONS = {0x04: 'NextFrame', 0x05: 'PrevFrame', 0x06: 'Play', 0x07: 'Stop', 0x08: 'ToggleQuality', 0x09: 'StopSounds',
           0x0A: 'Add', 0x0B: 'Subtract', 0x0C: 'Multiply', 0x0D: 'Divide', 0x0E: 'Equals', 0x0F: 'Less', 0x10: 'And',
           0x11: 'Or', 0x12: 'Not', 0x13: 'StringEquals', 0x14: 'StringLength', 0x15: 'StringExtract', 0x17: 'Pop',
           0x18: 'ToInteger', 0x1C: 'GetVariable', 0x1D: 'SetVariable', 0x20: 'SetTarget2', 0x21: 'StringAdd',
           0x22: 'GetProperty', 0x23: 'SetProperty', 0x24: 'CloneSprite', 0x25: 'RemoveSprite', 0x26: 'Trace',
           0x27: 'StartDrag', 0x28: 'EndDrag', 0x29: 'StringLess', 0x2A: 'Throw', 0x2B: 'CastOp', 0x2C: 'ImplementsOp',
           0x30: 'RandomNumber', 0x31: 'MBStringLength', 0x32: 'CharToAscii', 0x33: 'AsciiToChar', 0x34: 'GetTime',
           0x35: 'MBStringExtract', 0x36: 'MBCharToAscii', 0x37: 'MBAsciiToChar', 0x3A: 'Delete', 0x3B: 'Delete2',
           0x3C: 'DefineLocal', 0x3D: 'CallFunction', 0x3E: 'Return', 0x3F: 'Modulo', 0x40: 'NewObject',
           0x41: 'DefineLocal2', 0x42: 'InitArray', 0x43: 'InitObject', 0x44: 'TypeOf', 0x45: 'TargetPath',
           0x46: 'Enumerate', 0x47: 'Add2', 0x48: 'Less2', 0x49: 'Equals2', 0x4A: 'ToNumber', 0x4B: 'ToString',
           0x4C: 'PushDuplicate', 0x4D: 'StackSwap', 0x4E: 'GetMember', 0x4F: 'SetMember', 0x50: 'Increment',
           0x51: 'Decrement', 0x52: 'CallMethod', 0x53: 'NewMethod', 0x54: 'InstanceOf', 0x55: 'Enumerate2',
           0x60: 'BitAnd', 0x61: 'BitOr', 0x62: 'BitXor', 0x63: 'BitLShift', 0x64: 'BitRShift', 0x65: 'BitURShift',
           0x66: 'StrictEquals', 0x67: 'Greater', 0x68: 'StringGreater', 0x69: 'Extends',
           0x81: 'GotoFrame', 0x83: 'GetURL', 0x87: 'StoreRegister', 0x88: 'ConstantPool', 0x8A: 'WaitForFrame',
           0x8B: 'SetTarget', 0x8C: 'GoToLabel', 0x8D: 'WaitForFrame2', 0x8E: 'DefineFunction2', 0x8F: 'Try',
           0x94: 'With', 0x96: 'Push', 0x99: 'Jump', 0x9A: 'GetURL2', 0x9B: 'DefineFunction', 0x9D: 'If',
           0x9E: 'Call', 0x9F: 'GotoFrame2'}


def disasm_actions(d, p, end, pool=None, indent=0, out=None):
    """Disassemble an AS2 action block. Returns (lines, constant pool)."""
    out = [] if out is None else out
    pool = [] if pool is None else pool
    pad = '  ' * indent
    while p < end:
        a = d[p]; start = p; p += 1
        if a == 0:
            out.append('%s%06x End' % (pad, start)); break
        ln = 0
        if a >= 0x80:
            ln, = struct.unpack_from('<H', d, p); p += 2
        name = ACTIONS.get(a, 'Unknown_%02x' % a)
        body = p; p += ln
        arg = ''
        if a == 0x88:
            n, = struct.unpack_from('<H', d, body); q = body + 2; pool = []
            for _ in range(n):
                e = d.index(0, q); pool.append(d[q:e].decode('latin1')); q = e + 1
            arg = '%d strings' % n
        elif a == 0x96:
            arg = ', '.join(push_values(d, body, body + ln, pool))
        elif a in (0x99, 0x9D):
            off, = struct.unpack_from('<h', d, body); arg = '-> %06x' % (body + 2 + off)
        elif a == 0x87:
            arg = 'r%d' % d[body]
        elif a in (0x8C,):
            arg = repr(d[body:d.index(0, body)].decode('latin1'))
        elif a in (0x8E, 0x9B):
            q = body; e = d.index(0, q); fname = d[q:e].decode('latin1'); q = e + 1
            nparams, = struct.unpack_from('<H', d, q); q += 2
            params = []
            if a == 0x8E:
                regs = d[q]; q += 1; q += 2
                for _ in range(nparams):
                    r = d[q]; q += 1; e = d.index(0, q); params.append('r%d:%s' % (r, d[q:e].decode('latin1'))); q = e + 1
            else:
                for _ in range(nparams):
                    e = d.index(0, q); params.append(d[q:e].decode('latin1')); q = e + 1
            code_size, = struct.unpack_from('<H', d, q); q += 2
            out.append('%s%06x %s %s(%s) [%d bytes]' % (pad, start, name, fname or '<anon>', ', '.join(params), code_size))
            disasm_actions(d, p, p + code_size, pool, indent + 1, out)
            p += code_size
            continue
        out.append('%s%06x %s %s' % (pad, start, name, arg))
    return out, pool


def push_values(d, p, end, pool):
    vals = []
    while p < end:
        t = d[p]; p += 1
        if t == 0: e = d.index(0, p); vals.append(repr(d[p:e].decode('latin1'))); p = e + 1
        elif t == 1: vals.append('%gf' % struct.unpack_from('<f', d, p)[0]); p += 4
        elif t == 2: vals.append('null')
        elif t == 3: vals.append('undefined')
        elif t == 4: vals.append('r%d' % d[p]); p += 1
        elif t == 5: vals.append('true' if d[p] else 'false'); p += 1
        elif t == 6:
            lo, hi = struct.unpack_from('<II', d, p); vals.append('%g' % struct.unpack('<d', struct.pack('<II', hi, lo))[0]); p += 8
        elif t == 7: vals.append(str(struct.unpack_from('<i', d, p)[0])); p += 4
        elif t == 8: i = d[p]; p += 1; vals.append('c%d:%r' % (i, pool[i] if i < len(pool) else '?'))
        elif t == 9: i, = struct.unpack_from('<H', d, p); p += 2; vals.append('c%d:%r' % (i, pool[i] if i < len(pool) else '?'))
        else: vals.append('?type%d' % t); break
    return vals


def all_actions(d, p=None, end=None, sprite=None, out=None):
    out = [] if out is None else out
    p = body_start(d) if p is None else p
    end = len(d) if end is None else end
    for code, start, body, ln in iter_tags(d, p, end):
        if code == 12:
            out.append('==== DoAction in %s @%06x' % (sprite or 'root', start))
            disasm_actions(d, body, body + ln, out=out)
        elif code == 59:
            sid, = struct.unpack_from('<H', d, body)
            out.append('==== DoInitAction sprite=%d @%06x' % (sid, start))
            disasm_actions(d, body + 2, body + ln, out=out)
        elif code == 39:
            sid, = struct.unpack_from('<H', d, body)
            all_actions(d, body + 4, body + ln, 'sprite %d' % sid, out)
        elif code in (26, 70):
            pass  # clip event actions not decoded
    return out


if __name__ == '__main__':
    cmd = sys.argv[1]
    if cmd == 'extract':
        extract(sys.argv[2], sys.argv[3], sys.argv[4])
    elif cmd == 'tags':
        list_tags(load(sys.argv[2]))
    elif cmd == 'as':
        print('\n'.join(all_actions(load(sys.argv[2]))))
