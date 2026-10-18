"""Write patched, uncompressed copies of DmC script packages.

The engine reads an uncompressed package just as well as an LZO one, as long as
the summary says it is uncompressed. Object offsets inside the file do not move:
the decompressed image keeps every byte at its original uncompressed offset, and
the summary shrinks by the removed chunk table but is padded out to NameOffset.
Modified exports are appended at the end of the file and the export table is
pointed at them, so no other data shifts.
"""
import struct, sys, os
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from upkhdr import header
from upkdecomp import decompress
from upktables import Pkg

PKG_StoreCompressed = 0x02000000


def summary_end(d, p):
    """Offset just past the summary fields that follow the chunk table (v845)."""
    p += 4                                        # PackageSource
    n, = struct.unpack_from('<i', d, p); p += 4   # AdditionalPackagesToCook
    for _ in range(n):
        l, = struct.unpack_from('<i', d, p); p += 4 + (l if l >= 0 else -2 * l)
    n, = struct.unpack_from('<i', d, p); p += 4   # TextureAllocations
    for _ in range(n):
        p += 20                                   # SizeX, SizeY, NumMips, Format, TexCreateFlags
        k, = struct.unpack_from('<i', d, p); p += 4 + 4 * k
    return p


class PatchedPackage:
    def __init__(self, original_path, scratch_dir):
        os.makedirs(scratch_dir, exist_ok=True)
        tmp = os.path.join(scratch_dir, os.path.basename(original_path))
        self.h = decompress(original_path, tmp)
        self.original = open(original_path, 'rb').read()
        self.d = bytearray(open(tmp, 'rb').read())
        self.pkg = Pkg(tmp)
        self._make_uncompressed_header()
        self.entry_offs = []
        p = self.h['expoff']
        for _ in range(self.h['expcount']):
            self.entry_offs.append(p)
            nc, = struct.unpack_from('<i', self.d, p + 44)
            p += 68 + 4 * nc

    def _make_uncompressed_header(self):
        h, d = self.h, self.d
        # The summary must come from the original file: in the decompressed image the
        # first chunk can start before the compressed summary ends.
        src = self.original
        nch = len(h['chunks'])
        chunk_list = h['pos'] - 16 * nch
        assert struct.unpack_from('<I', src, chunk_list - 4)[0] == nch
        summary = bytearray(src[:chunk_list])
        # Flags live at a fixed spot after the folder name.
        flags_off = 4 + 2 + 2 + 4 + 4 + len(h['folder']) + 1 if h['folder'] else 12 + 4
        assert struct.unpack_from('<I', summary, flags_off)[0] == h['flags'], 'flags offset'
        struct.pack_into('<I', summary, flags_off, h['flags'] & ~PKG_StoreCompressed)
        assert struct.unpack_from('<I', summary, chunk_list - 8)[0] == h['compflags']
        struct.pack_into('<II', summary, chunk_list - 8, 0, 0)
        summary += src[h['pos']:summary_end(src, h['pos'])]
        assert len(summary) <= h['nameoff'], 'uncompressed summary does not fit before NameOffset'
        d[:h['nameoff']] = bytes(summary) + b'\0' * (h['nameoff'] - len(summary))

    def name_index(self, name):
        return self.pkg.names.index(name)

    def export_index(self, path):
        for i in range(1, len(self.pkg.exps) + 1):
            if self.pkg.path(i) == path:
                return i
        raise KeyError(path)

    def export_data(self, idx):
        size, off = struct.unpack_from('<ii', self.d, self.entry_offs[idx - 1] + 32)
        return bytes(self.d[off:off + size])

    def replace_export_data(self, idx, data):
        while len(self.d) % 4: self.d.append(0)
        off = len(self.d)
        self.d += data
        struct.pack_into('<ii', self.d, self.entry_offs[idx - 1] + 32, len(data), off)

    def rename_export(self, idx, name):
        struct.pack_into('<ii', self.d, self.entry_offs[idx - 1] + 12, self.name_index(name), 0)

    def replace_in_export(self, idx, old, new):
        data = self.export_data(idx)
        assert data.count(old) == 1, 'expected exactly one match, found %d' % data.count(old)
        size, off = struct.unpack_from('<ii', self.d, self.entry_offs[idx - 1] + 32)
        p = off + data.index(old)
        self.d[p:p + len(new)] = new

    def save(self, path):
        open(path, 'wb').write(self.d)


# ---------------------------------------------------------------- bytecode assembly
# Each piece is (disk_bytes, memory_size). On disk an object reference is 4 bytes
# but the VM counts 8, and jump/skip offsets are measured in memory bytes.

class Code:
    def __init__(self, disk=b'', mem=0):
        self.disk, self.mem = disk, mem

    def __add__(self, o):
        return Code(self.disk + o.disk, self.mem + o.mem)


def raw(b): return Code(bytes(b), len(b))
def tok(t): return raw([t])
def obj(i): return Code(struct.pack('<i', i), 8)
def name(pk, n): return Code(struct.pack('<ii', pk.names.index(n), 0), 8)
def u16(v): return raw(struct.pack('<H', v))
def cat(*parts):
    c = Code()
    for p in parts: c = c + p
    return c

def local(i): return tok(0x00) + obj(i)
def inst(i): return tok(0x01) + obj(i)
def context(objexpr, field, inner):
    return cat(tok(0x19), objexpr, u16(inner.mem), obj(field), raw([0]), inner)
def dyncast(cls, e): return cat(tok(0x2E), obj(cls), e)
def final_call(fn, *args): return cat(tok(0x1C), obj(fn), *args, tok(0x16))
def virtual_call(pk, fname, *args): return cat(tok(0x1B), name(pk, fname), *args, tok(0x16))
def native(n, *args):
    assert n < 0x100
    return cat(tok(n), *args, tok(0x16))
NONE = tok(0x2A)
TRUE = tok(0x27)
EMPTY = tok(0x4A)  # omitted optional parameter
def vect(x, y, z): return tok(0x23) + raw(struct.pack('<fff', x, y, z))


def outvar(i): return tok(0x48) + obj(i)
def let(lhs, rhs): return cat(tok(0x0F), lhs, rhs)
def strconst(s): return cat(tok(0x1F), raw(s.encode('latin1') + b'\0'))
def byteconst(v): return raw([0x24, v])
def byte_to_int(e): return cat(raw([0x38, 0x3A]), e)
def boolvar(e): return cat(tok(0x2D), e)
def array_elem(index, array): return cat(tok(0x10), index, array)
def eat_return(ret_prop, e): return cat(tok(0x0E), obj(ret_prop), e)
def andand(a, b):
    """a && b with short-circuit (the skip covers b and the closing EndFunctionParms)."""
    return cat(tok(0x82), a, tok(0x18), u16(b.mem + 1), b, tok(0x16))
def floatconst(f): return tok(0x1E) + raw(struct.pack('<f', f))
def objconst(i): return tok(0x20) + obj(i)
def static_call(cls, ret_field, call):
    """class'X'.static.F(...) from a class that is not an X (EX_ClassContext)."""
    return cat(tok(0x12), objconst(cls), u16(call.mem), obj(ret_field), raw([0]), call)
def native_ext(n, *args):
    """Native function with index >= 0x100 (two-byte token)."""
    return cat(raw([0x60 + (n >> 8), n & 0xFF]), *args, tok(0x16))
ITER_NEXT, ITER_POP = tok(0x31), tok(0x30)


def assemble(items, base=0):
    """Lay out statements with labels. Items are Code, a label string, or
    ('jump_if_not', label, cond) / ('jump', label). Offsets are in memory bytes; `base` is where
    the first item lands inside the function (for code appended after existing bytecode)."""
    def size(it):
        if isinstance(it, str): return 0
        if isinstance(it, tuple): return 3 + (it[2].mem if it[0] in ('jump_if_not', 'foreach') else 0)
        return it.mem
    labels, pos = {}, base
    for it in items:
        if isinstance(it, str): labels[it] = pos
        pos += size(it)
    out = Code()
    for it in items:
        if isinstance(it, str): continue
        if isinstance(it, tuple):
            kind, label = it[0], labels[it[1]]
            if kind == 'jump_if_not': out = out + jump_if_not(label, it[2])
            elif kind == 'foreach': out = out + cat(tok(0x2F), it[2], u16(label))   # label = its IteratorPop
            else: out = out + cat(tok(0x06), u16(label))
        else:
            out = out + it
    return out
RETURN_NOTHING = raw([0x04, 0x0B])
END = tok(0x53)
def jump_if_not(target_mem, cond): return cat(tok(0x07), u16(target_mem), cond)


def build_function(original, script, flags=None, friendly=None):
    """Rebuild a UFunction export around new bytecode. `original` is the old export bytes."""
    from disasm import SCRIPT_START
    hdr = bytearray(original[:SCRIPT_START])
    old_ssize, = struct.unpack_from('<i', hdr, SCRIPT_START - 4)
    struct.pack_into('<ii', hdr, SCRIPT_START - 8, script.mem, len(script.disk))
    tail = bytearray(original[SCRIPT_START + old_ssize:])
    if flags is not None:
        struct.pack_into('<I', tail, 3, flags)
    if friendly is not None:
        fl, = struct.unpack_from('<I', tail, 3)
        fpos = 7 + (2 if fl & 0x40 else 0)
        struct.pack_into('<ii', tail, fpos, *friendly)
    return bytes(hdr) + script.disk + bytes(tail)
