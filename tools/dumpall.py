"""Disassemble every function in a decompressed package into a text dump."""
import sys, os
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from upktables import Pkg
from disasm import parse_function, Disasm, flagstr
pk = Pkg(sys.argv[1]); out = open(sys.argv[2], 'w', encoding='utf-8'); bad = 0
for i, e in enumerate(pk.exps, 1):
    if pk.clsname(e) != 'Function': continue
    try:
        f = parse_function(pk, i)
        out.write('== %s [%d] %s\n' % (pk.path(i), i, flagstr(f['flags'])))
        lines = Disasm(pk, f['script']).run()
        bad += any('!!' in l for l in lines)
        out.write('\n'.join(lines) + '\n')
    except Exception as ex:
        bad += 1; out.write('== %s [%d] PARSE FAIL %s\n' % (pk.path(i), i, ex))
print(sys.argv[1], 'failures:', bad)
