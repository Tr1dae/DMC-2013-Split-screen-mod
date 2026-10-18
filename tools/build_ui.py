"""Add a "SplitScreen Mod" entry to the ESC pause menu (DevilIngameUI.IngameMenu).

The pause menu is a Scaleform (GFx 3, AS2) movie inside Dante_Archetypes_SF.upk. Its class
Scripts.IngameMenu wires seven fixed CLIK buttons in Hook_InitAsMainGame. We append AS2 code to
the class's DoInitAction that wraps Hook_InitAsMainGame and attaches extra CLIK "Button" clips
(the movie exports that symbol), so no timeline or graphics change:

  * "SplitScreen Mod" under "Main Menu" opens a submenu in place of the normal buttons:
      Split Screen: On/Off           -> ExecConsoleCommand "AddPlayer 1" / "RemovePlayer"
      Camera: Side by Side / Top & Bottom / Shared Screen -> "AddPlayer 10<view>"
      Health: 1x / 0.75x / 0.5x / 0.25x  -> "DamageScale <1 / 1.333 / 2 / 4>" (shared health pool)
      Player 2: Dante / Kat / Vergil     -> "AddPlayer 300 / 301 / 302" (applied when the menu closes)
      Back
  * The buttons call the game's own ExecConsoleCommand UI callback
    (DVGFxMovieHandler_IngameUI_Callbacks), which runs a console command on player 1. Joining or
    dropping while paused is only recorded by the Engine side and carried out on resume.
  * B / Esc / Start on the SplitScreen Mod page returns to the pause page.
  * Menu state lives in _global.coopP2 / coopView / coopHealth, which persist while the game runs
    (as does the DamageScale value on the game side).

Usage: python build_ui.py <original Dante_Archetypes_SF.upk> <output upk>
"""
import os, struct, sys
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from as2 import *
import swf
from upkpatch import PatchedPackage

MOVIE = 'DevilIngameUI.IngameMenu'
CLASS_SPRITE = 66                 # DoInitAction that defines Scripts.IngameMenu
VIEW_SIDE, VIEW_TOP, VIEW_SHARED = 2, 1, 6   # DesiredSplitscreenType values (6 = mod's shared screen)
# Health setting: (label, damage scale players take). Fewer hit points = more damage per hit.
HEALTH_LEVELS = [('1x', '1'), ('0.75x', '1.333'), ('0.5x', '2'), ('0.25x', '4')]
CHARACTERS = ['Dante', 'Kat', 'Vergil']        # "AddPlayer 300 + index" on the game side

R_ARG, R_PM, R_TMP = Reg(2), Reg(3), Reg(4)


def proto():
    return member(var('_global'), 'Scripts', 'IngameMenu', 'prototype')


def glob(name):
    return member(var('_global'), name)


def pm():
    return member(val(THIS), 'PauseMenu')


def method(name, params, body):
    return set_member(proto(), name, function(params, body + ret()))


def console(cmd):
    return external_call('ExecConsoleCommand', cmd)


def menu_code():
    stock = ['button0%d' % i for i in range(1, 8)]
    coop = [('coopB0', 61, 'onCoopMenu'), ('coopB1', 62, 'onCoopSplit'),
            ('coopB2', 63, 'onCoopCamera'), ('coopB4', 64, 'onCoopHealth'), ('coopB5', 65, 'onCoopCharacter'),
            ('coopB3', 66, 'onCoopBack')]

    setup = set_reg(R_PM, pm())
    setup += if_not(eq(member(val(R_PM), 'coopB0'), val(UNDEFINED)), 'have')
    for name, depth, handler in coop:
        setup += set_reg(R_TMP, call_method(val(R_PM), 'attachMovie', 'Button', name, depth))
        setup += set_member(val(R_TMP), '_xscale', member(val(R_PM), 'button07', '_xscale'))
        setup += set_member(val(R_TMP), '_yscale', member(val(R_PM), 'button07', '_yscale'))
        setup += stmt(call_method(val(R_TMP), 'addEventListener', 'press', THIS, handler))
    setup += label('have')
    # SplitScreen Mod sits one row below the last stock button; the submenu reuses rows 1-3.
    setup += set_member(member(val(R_PM), 'coopB0'), '_x', member(val(R_PM), 'button07', '_x'))
    setup += set_member(member(val(R_PM), 'coopB0'), '_y',
                        add(member(val(R_PM), 'button07', '_y'),
                            sub(member(val(R_PM), 'button07', '_y'), member(val(R_PM), 'button06', '_y'))))
    for i, (name, _, _) in enumerate(coop[1:], 1):
        setup += set_member(member(val(R_PM), name), '_x', member(val(R_PM), 'button0%d' % i, '_x'))
        setup += set_member(member(val(R_PM), name), '_y', member(val(R_PM), 'button0%d' % i, '_y'))
    setup += set_member(member(val(R_PM), 'coopB0'), 'label', 'SplitScreen Mod')
    setup += set_member(member(val(R_PM), 'coopB3'), 'label', 'Back')
    setup += if_not(eq(glob('coopView'), val(UNDEFINED)), 'viewset')
    setup += set_member(var('_global'), 'coopView', VIEW_SIDE)
    setup += label('viewset')
    setup += if_not(eq(glob('coopHealth'), val(UNDEFINED)), 'healthset')
    setup += set_member(var('_global'), 'coopHealth', 0)
    setup += label('healthset')
    setup += if_not(eq(glob('coopChar'), val(UNDEFINED)), 'charset')
    setup += set_member(var('_global'), 'coopChar', 0)
    setup += label('charset')
    setup += stmt(call_method(val(THIS), 'coopShow', False, False))

    labels = set_reg(R_PM, pm())
    labels += if_not(eq(glob('coopP2'), val(True)), 'off')
    labels += set_member(member(val(R_PM), 'coopB1'), 'label', 'Split Screen: On') + jump('cam')
    labels += label('off') + set_member(member(val(R_PM), 'coopB1'), 'label', 'Split Screen: Off')
    labels += label('cam') + set_reg(R_TMP, glob('coopView'))
    labels += if_not(eq(val(R_TMP), val(VIEW_TOP)), 'nt')
    labels += set_member(member(val(R_PM), 'coopB2'), 'label', 'Camera: Top & Bottom') + jump('end')
    labels += label('nt') + if_not(eq(val(R_TMP), val(VIEW_SHARED)), 'ns')
    labels += set_member(member(val(R_PM), 'coopB2'), 'label', 'Camera: Shared Screen') + jump('end')
    labels += label('ns') + set_member(member(val(R_PM), 'coopB2'), 'label', 'Camera: Side by Side')
    labels += label('end') + set_reg(R_TMP, glob('coopHealth'))
    for i, (name, _) in enumerate(HEALTH_LEVELS):
        labels += if_not(eq(val(R_TMP), val(i)), 'h%d' % i)
        labels += set_member(member(val(R_PM), 'coopB4'), 'label', 'Health: ' + name) + jump('hdone')
        labels += label('h%d' % i)
    labels += label('hdone')
    labels += set_reg(R_TMP, glob('coopChar'))
    for i, name in enumerate(CHARACTERS):
        labels += if_not(eq(val(R_TMP), val(i)), 'p%d' % i)
        labels += set_member(member(val(R_PM), 'coopB5'), 'label', 'Player 2: ' + name) + jump('cpdone')
        labels += label('p%d' % i)
    labels += label('cpdone')

    sound = stmt(call_method(val(THIS), 'PlayForwardSound'))
    view_cmd = add(val('AddPlayer 10'), glob('coopView'))          # "AddPlayer 102" etc.

    split = sound + if_not(eq(glob('coopP2'), val(True)), 'join')
    split += console('RemovePlayer') + set_member(var('_global'), 'coopP2', False) + jump('lbl')
    split += label('join') + console('AddPlayer 1')
    split += external_call('ExecConsoleCommand', view_cmd)
    split += set_member(var('_global'), 'coopP2', True)
    split += label('lbl') + stmt(call_method(val(THIS), 'coopLabels'))

    camera = sound + set_reg(R_TMP, glob('coopView'))
    camera += if_not(eq(val(R_TMP), val(VIEW_SIDE)), 'c1') + set_member(var('_global'), 'coopView', VIEW_TOP) + jump('c3')
    camera += label('c1') + if_not(eq(val(R_TMP), val(VIEW_TOP)), 'c2')
    camera += set_member(var('_global'), 'coopView', VIEW_SHARED) + jump('c3')
    camera += label('c2') + set_member(var('_global'), 'coopView', VIEW_SIDE)
    camera += label('c3') + if_not(eq(glob('coopP2'), val(True)), 'c4')
    camera += external_call('ExecConsoleCommand', view_cmd)
    camera += label('c4') + stmt(call_method(val(THIS), 'coopLabels'))

    # Health cycles 1x -> 0.75x -> 0.5x -> 0.25x -> 1x and applies at once (paused or not).
    health = sound + set_reg(R_TMP, glob('coopHealth'))
    for i in range(len(HEALTH_LEVELS)):
        nxt = (i + 1) % len(HEALTH_LEVELS)
        health += if_not(eq(val(R_TMP), val(i)), 'c%d' % i)
        health += set_member(var('_global'), 'coopHealth', nxt)
        health += console('DamageScale ' + HEALTH_LEVELS[nxt][1]) + jump('cdone')
        health += label('c%d' % i)
    health += set_member(var('_global'), 'coopHealth', 0) + console('DamageScale 1')
    health += label('cdone') + stmt(call_method(val(THIS), 'coopLabels'))

    # Player 2 character cycles Dante -> Kat -> Vergil; the game side applies it when the menu closes.
    character = sound + set_reg(R_TMP, glob('coopChar'))
    for i in range(len(CHARACTERS)):
        nxt = (i + 1) % len(CHARACTERS)
        character += if_not(eq(val(R_TMP), val(i)), 'ch%d' % i)
        character += set_member(var('_global'), 'coopChar', nxt) + console('AddPlayer %d' % (300 + nxt))
        character += jump('chdone') + label('ch%d' % i)
    character += set_member(var('_global'), 'coopChar', 0) + console('AddPlayer 300')
    character += label('chdone') + stmt(call_method(val(THIS), 'coopLabels'))

    def show_body():
        # coopShow(on = r2, focus = r3); r4 = PauseMenu
        pmr = Reg(4)
        b = set_reg(pmr, pm()) + set_member(val(THIS), 'coopMode', val(R_ARG))
        for n in stock + ['coopB0']:
            b += set_member(member(val(pmr), n), '_visible', not_(val(R_ARG)))
        for n, _, _ in coop[1:]:
            b += set_member(member(val(pmr), n), '_visible', val(R_ARG))
        b += stmt(call_method(val(THIS), 'coopLabels'))
        b += if_not(val(Reg(3)), 'nofocus')
        b += if_not(val(R_ARG), 'back')
        b += stmt(call_method(var('Selection'), 'setFocus', member(val(pmr), 'coopB1'))) + jump('nofocus')
        b += label('back') + stmt(call_method(var('Selection'), 'setFocus', member(val(pmr), 'coopB0')))
        b += label('nofocus')
        return b

    code = if_not(eq(member(proto(), 'coopOrigMain'), val(UNDEFINED)), 'installed')
    code += set_member(proto(), 'coopOrigMain', member(proto(), 'Hook_InitAsMainGame'))
    code += method('Hook_InitAsMainGame', ['SelectedButtonIndex'],
                   stmt(call_method(val(THIS), 'coopOrigMain', val(R_ARG))) +
                   stmt(call_method(val(THIS), 'coopSetup')))
    code += method('coopSetup', [], setup)
    code += method('coopShow', ['on', 'focus'], show_body())
    code += method('coopLabels', [], labels)
    code += method('onCoopMenu', ['event'], sound + stmt(call_method(val(THIS), 'coopShow', True, True)))
    code += method('onCoopBack', ['event'], sound + stmt(call_method(val(THIS), 'coopShow', False, True)))
    code += method('onCoopSplit', ['event'], split)
    code += method('onCoopCamera', ['event'], camera)
    code += method('onCoopHealth', ['event'], health)
    code += method('onCoopCharacter', ['event'], character)
    # B / Esc / Start on the SplitScreen Mod page goes back to the pause page instead of resuming.
    code += set_member(proto(), 'coopOrigBack', member(proto(), 'BackButtonPressed'))
    code += method('BackButtonPressed', [],
                   if_not(eq(member(val(THIS), 'coopMode'), val(True)), 'stock') +
                   stmt(call_method(val(THIS), 'coopShow', False, True)) + ret() +
                   label('stock') + stmt(call_method(val(THIS), 'coopOrigBack')))
    code += label('installed')
    return assemble(code)


def patch_swf(data):
    """Insert the menu code just before the End action of the class DoInitAction."""
    d = bytearray(data)
    for code, start, body, ln in swf.iter_tags(d, swf.body_start(d), len(d)):
        if code == 59 and struct.unpack_from('<H', d, body)[0] == CLASS_SPRITE:
            end = body + ln
            assert d[end - 1] == 0, 'DoInitAction does not end with End'
            extra = menu_code()
            d[end - 1:end - 1] = extra
            assert struct.unpack_from('<H', d, start)[0] & 0x3F == 0x3F, 'expected a long tag header'
            struct.pack_into('<I', d, start + 2, ln + len(extra))
            struct.pack_into('<I', d, 4, len(d))          # SWF file length
            return bytes(d), len(extra)
    raise KeyError('class DoInitAction')


def build(src, dst):
    pp = PatchedPackage(src, os.path.join(os.path.dirname(os.path.abspath(dst)), '_scratch'))
    pk = pp.pkg
    fn = pp.export_index(MOVIE)
    old = pp.export_data(fn)
    from props import read_tags
    e = pk.exps[fn - 1]
    tags, _ = read_tags(pk, pk.d, e['off'] + 4, e['off'] + e['size'])
    raw = next(t for t in tags if t[0] == 'RawData')
    name, typ, size, aidx, extra_, off, val_ = raw
    count, = struct.unpack_from('<i', val_, 0)
    swf_bytes = val_[4:4 + count]
    new_swf, added = patch_swf(swf_bytes)
    rel = off - e['off']                          # value offset inside the export
    new_val = struct.pack('<i', len(new_swf)) + new_swf
    new = bytearray(old[:rel] + new_val + old[rel + size:])
    struct.pack_into('<i', new, rel - 8, len(new_val))  # tag Size (before ArrayIndex, which is 0)
    assert struct.unpack_from('<i', old, rel - 8)[0] == size and struct.unpack_from('<i', old, rel - 4)[0] == 0
    pp.replace_export_data(fn, bytes(new))
    pp.save(dst)
    print('wrote', dst, '(+%d bytes of AS2)' % added)
    return new_swf


if __name__ == '__main__':
    out = build(sys.argv[1], sys.argv[2])
    if len(sys.argv) > 3:
        open(sys.argv[3], 'wb').write(out)
