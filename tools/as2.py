"""Tiny ActionScript 2 bytecode assembler for patching Scaleform (GFx 3 / SWF 8) movies.

Code is a list of items: bytes (raw actions), label strings ('L:name'), ('if', label),
('jump', label) or ('function', params, body_items). Build expressions with the helpers below;
every helper returns a list of items, so they concatenate with +.

Conventions match the game's own compiled functions: inside a function r1 = this and
parameters are r2.., free registers above that can be used for locals.
"""
import struct

A_POP, A_NOT, A_ADD2, A_EQUALS2, A_STRICTEQ, A_GETVAR, A_SETVAR = 0x17, 0x12, 0x47, 0x49, 0x66, 0x1C, 0x1D
A_GETMEMBER, A_SETMEMBER, A_CALLMETHOD, A_CALLFUNC, A_RETURN, A_INITARRAY = 0x4E, 0x4F, 0x52, 0x3D, 0x3E, 0x42
A_NEWOBJECT, A_GREATER, A_LESS2, A_PUSHDUP, A_SUBTRACT = 0x40, 0x67, 0x48, 0x4C, 0x0B


class Reg:
    def __init__(self, n): self.n = n


THIS = Reg(1)
UNDEFINED = object()
NULL = object()


def act(code, payload=b''):
    if code < 0x80:
        assert not payload
        return [bytes([code])]
    return [bytes([code]) + struct.pack('<H', len(payload)) + payload]


def push(*vals):
    p = b''
    for v in vals:
        if v is UNDEFINED: p += b'\x03'
        elif v is NULL: p += b'\x02'
        elif isinstance(v, Reg): p += b'\x04' + bytes([v.n])
        elif v is True or v is False: p += b'\x05' + bytes([1 if v else 0])
        elif isinstance(v, int): p += b'\x07' + struct.pack('<i', v)
        elif isinstance(v, float): p += b'\x06' + struct.pack('<II', *reversed(struct.unpack('<II', struct.pack('<d', v))))
        elif isinstance(v, str): p += b'\x00' + v.encode('latin1') + b'\0'
        else: raise TypeError(v)
    return act(0x96, p)


def store(reg): return act(0x87, bytes([reg.n]))


# ---- expressions (each leaves one value on the stack)
def val(v): return push(v)
def var(name): return push(name) + act(A_GETVAR)
def member(obj, *names):
    code = obj if isinstance(obj, list) else val(obj)
    for n in names:
        code = code + push(n) + act(A_GETMEMBER)
    return code
def call_method(obj, name, *args):
    """obj.name(args...) -> value on stack."""
    code = []
    for a in reversed(args):
        code += a if isinstance(a, list) else val(a)
    code += push(len(args))
    code += obj if isinstance(obj, list) else val(obj)
    return code + push(name) + act(A_CALLMETHOD)
def not_(e): return e + act(A_NOT)
def eq(a, b): return a + b + act(A_EQUALS2)
def add(a, b): return a + b + act(A_ADD2)
def sub(a, b): return a + b + act(A_SUBTRACT)


# ---- statements
def stmt(e): return e + act(A_POP)
def set_member(obj, name, value):
    code = obj if isinstance(obj, list) else val(obj)
    return code + push(name) + (value if isinstance(value, list) else val(value)) + act(A_SETMEMBER)
def set_reg(reg, e): return e + store(reg) + act(A_POP)
def if_not(cond, label): return cond + act(A_NOT) + [('if', label)]
def if_(cond, label): return cond + [('if', label)]
def jump(label): return [('jump', label)]
def label(name): return ['L:' + name]
def ret(): return push(UNDEFINED) + act(A_RETURN)
def function(params, body, registers=8):
    return [('function', params, body, registers)]


def external_call(*args):
    """flash.external.ExternalInterface.call(args...)"""
    return stmt(call_method(member(var('flash'), 'external', 'ExternalInterface'), 'call', *args))


# ---- assembly
def assemble(items):
    """Resolve labels and functions to bytes."""
    # First pass: sizes. Branches are 5 bytes; functions are header + body.
    def size(it):
        if isinstance(it, bytes): return len(it)
        if isinstance(it, str): return 0
        if it[0] in ('if', 'jump'): return 5
        if it[0] == 'function': return len(function_bytes(it))
        raise ValueError(it)
    pos, labels = 0, {}
    for it in items:
        if isinstance(it, str):
            labels[it[2:]] = pos
        pos += size(it)
    out, pos = b'', 0
    for it in items:
        if isinstance(it, bytes): out += it
        elif isinstance(it, str): pass
        elif it[0] in ('if', 'jump'):
            target = labels[it[1]]
            off = target - (pos + 5)
            out += bytes([0x9D if it[0] == 'if' else 0x99]) + struct.pack('<Hh', 2, off)
        elif it[0] == 'function':
            out += function_bytes(it)
        pos += size(it)
    return out


def function_bytes(it):
    _, params, body, registers = it
    code = assemble(body)
    hdr = b'\0'                                       # anonymous
    hdr += struct.pack('<HB', len(params), registers)
    flags = 0x29                                      # PreloadThis | SuppressArguments | SuppressSuper (as the game's)
    hdr += struct.pack('<H', flags)
    for i, p in enumerate(params):
        hdr += bytes([i + 2]) + p.encode('latin1') + b'\0'
    hdr += struct.pack('<H', len(code))
    return bytes([0x8E]) + struct.pack('<H', len(hdr)) + hdr + code
