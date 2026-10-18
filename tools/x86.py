"""Capstone helpers for the 32-bit DmC exe."""
import sys, os, re, struct
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import capstone, pefile
from peutil import PE, EXE

pe = PE()
md = capstone.Cs(capstone.CS_ARCH_X86, capstone.CS_MODE_32)
md.detail = False
_pf = None

def imports():
    global _pf
    if _pf is None:
        _pf = pefile.PE(EXE, fast_load=True)
        _pf.parse_data_directories(directories=[pefile.DIRECTORY_ENTRY['IMAGE_DIRECTORY_ENTRY_IMPORT']])
    out = {}
    for ent in _pf.DIRECTORY_ENTRY_IMPORT:
        for imp in ent.imports:
            out[(ent.dll.decode(), (imp.name or b'#%d' % imp.ordinal).decode())] = imp.address
    return out

def dis(va, n=200, stop_ret=True, maxlen=4000):
    o = pe.va2off(va); code = pe.d[o:o + maxlen]; out = []
    for ins in md.disasm(code, va):
        out.append('%08x: %-24s %s %s' % (ins.address, ins.bytes.hex(' '), ins.mnemonic, ins.op_str))
        if len(out) >= n or (stop_ret and ins.mnemonic in ('ret', 'retn') and len(out) > 2): break
    return '\n'.join(out)

def text_refs(target, kinds=('call_ind', 'any')):
    """File offsets in .text that contain `target` as a 32-bit immediate/displacement."""
    n, va, vs, ra, rs = pe.secs[0]
    pat = re.escape(struct.pack('<I', target))
    return [pe.off2va(m.start()) for m in re.finditer(pat, pe.d[ra:ra + rs])] and \
           [pe.off2va(ra + m.start()) for m in re.finditer(pat, pe.d[ra:ra + rs])]

def call_refs(target):
    """VAs of `call rel32` instructions targeting `target`."""
    n, va, vs, ra, rs = pe.secs[0]; d = pe.d; base = pe.base + va; res = []
    for m in re.finditer(b'\xe8', d[ra:ra + rs]):
        i = m.start()
        rel, = struct.unpack_from('<i', d, ra + i + 1)
        if base + i + 5 + rel == target: res.append(base + i)
    return res

def func_start(va, back=0x2000):
    """Guess function start: scan back for int3/ret padding followed by code."""
    o = pe.va2off(va)
    for k in range(o, o - back, -1):
        if pe.d[k - 1] in (0xcc, 0xc3) and pe.d[k] != 0xcc and (pe.d[k-2] in (0xcc, 0xc3, 0x00) or pe.d[k-1]==0xcc):
            if pe.d[k - 1] == 0xcc: return pe.off2va(k)
    return None

def native_thunk(cls_exec_name):
    """Address of the exec thunk registered under e.g. 'UUIInteractionexecGetPlayerIndex'."""
    import re
    m = re.search(re.escape(cls_exec_name.encode()) + b'\x00', pe.d)
    st = m.start()
    for r in pe.refs(pe.off2va(st)):
        return struct.unpack_from('<I', pe.d, r + 4)[0]

def thunk_target(thunk):
    """Follow the `call rel32` inside a standard exec thunk to the C++ implementation."""
    o = pe.va2off(thunk)
    for ins in md.disasm(pe.d[o:o + 120], thunk):
        if ins.mnemonic == 'call' and ins.op_str.startswith('0x'):
            t = int(ins.op_str, 16)
            if t != 0x1eb0d26: last = t
        if ins.mnemonic == 'ret': break
    return last

def rtti_vtables(classname):
    """Return [(col_offset_in_class, vtable_va)] for an MSVC RTTI class name like 'UGameViewportClient'."""
    import re
    key = ('.?AV%s@@' % classname).encode() + b'\x00'
    m = re.search(re.escape(key), pe.d)
    if not m: return []
    td = pe.off2va(m.start()) - 8
    out = []
    for r in pe.refs(td):
        col = pe.off2va(r) - 12
        sig, off, cdoff = struct.unpack_from('<III', pe.d, r - 12)
        if sig != 0: continue
        for vr in pe.refs(col):
            out.append((off, pe.off2va(vr) + 4))
    return out

def vfunc(vt, idx):
    return struct.unpack_from('<I', pe.d, pe.va2off(vt) + 4 * idx)[0]
