"""Native fixes in DMC-DevilMayCry.exe for local co-op input.

QLOC's PC port lets any pad drive player 1, which breaks a second local player:

1. Its InputKey override (0x1933990) and InputAxis override (0xE9A750) both call
   GamePlayers[0]->SetControllerId(pad) whenever a gamepad button is pressed or a stick moves,
   so whichever pad was used last becomes player 1's. Both calls now go through caves that only
   run them while there is a single local player.

2. The joystick poll (0x18773B0) feeds button state to every local player's input handlers when
   the joystick is QLOC's global "current controller". With two or more players we compare
   against each player's own LocalPlayer.ControllerId (+0x60) instead; with one player the
   original "current controller" value is used, so single player is unchanged.

Every site is checked against the original bytes before writing.
Usage: python patch_exe.py <original exe> <output exe>
"""
import struct, sys

IMAGE_BASE = 0x400000
TEXT_VA, TEXT_RAW = 0x1000, 0x400  # .text section mapping (VirtualAddress, PointerToRawData)

GENGINE = 0x2B2C328                      # UEngine*; GamePlayers.Num() at +0x4E0
CURRENT_CONTROLLER = 0x2B551F0           # QLOC "current controller" global
LOCALPLAYER_SETCONTROLLERID = 0xDEECF0   # ULocalPlayer::eventSetControllerId (thiscall, 1 arg)
GET_CURRENT_CONTROLLER = 0x103F480

# (site, pushed register opcode, resume) for the two "pad becomes player 1" calls.
REASSIGN_SITES = [
    (0x1933A90, 0x55, 0x1933A96),        # InputKey override: push ebp; call SetControllerId
    (0xE9A86E, 0x56, 0xE9A874),          # InputAxis override: push esi; call SetControllerId
]
REASSIGN_CAVES = [0x19594A0, 0x1855B20]  # int3 padding between functions (52 and 49 bytes)
LOOP_CAVE = 0x17F9DD0                    # int3 padding (52 bytes)
LOOP_SITES = [0x1877A1D, 0x1877A8E, 0x1877E7D, 0x1877EEE]  # esi = ULocalPlayer* at each


def off(va):
    return va - IMAGE_BASE - TEXT_VA + TEXT_RAW


def rel32(src_next, dst):
    return struct.pack('<i', dst - src_next)


def patch(d, va, expect, new):
    o = off(va)
    got = bytes(d[o:o + len(expect)])
    if got != expect:
        raise SystemExit('unexpected bytes at %#x: %s (wanted %s)' % (va, got.hex(' '), expect.hex(' ')))
    assert len(new) == len(expect)
    d[o:o + len(new)] = new


MULTIPLAYER_TEST = (b'\xa1' + struct.pack('<I', GENGINE)   # mov eax, [GEngine]
                    + b'\x83\xb8\xe0\x04\x00\x00\x01')     # cmp dword [eax+0x4e0], 1


def main(src, dst):
    d = bytearray(open(src, 'rb').read())

    # 1. Single-player-only controller reassignment.
    for (site, push, resume), cave in zip(REASSIGN_SITES, REASSIGN_CAVES):
        code = (MULTIPLAYER_TEST
                + b'\x7f\x06'                                    # jg skip
                + bytes([push])                                  # push pad index
                + b'\xe8' + rel32(cave + 20, LOCALPLAYER_SETCONTROLLERID)
                + b'\xe9' + rel32(cave + 25, resume))            # skip: jmp back
        patch(d, cave, b'\xcc' * len(code), code)
        old = bytes([push]) + b'\xe8' + rel32(site + 6, LOCALPLAYER_SETCONTROLLERID)
        patch(d, site, old, b'\xe9' + rel32(site + 5, cave) + b'\x90')

    # 2. Which pad owns this player? (called with esi = ULocalPlayer*)
    code = (MULTIPLAYER_TEST
            + b'\x7f\x06'                                        # jg per_player
            + b'\xa1' + struct.pack('<I', CURRENT_CONTROLLER)    # mov eax, [CurrentController]
            + b'\xc3'                                            # ret
            + b'\x8b\x46\x60'                                    # per_player: mov eax, [esi+0x60]
            + b'\xc3')
    patch(d, LOOP_CAVE, b'\xcc' * len(code), code)
    for va in LOOP_SITES:
        patch(d, va, b'\xe8' + rel32(va + 5, GET_CURRENT_CONTROLLER), b'\xe8' + rel32(va + 5, LOOP_CAVE))

    # 3. The caves use absolute addresses, and the exe opts into ASLR (DYNAMIC_BASE) without us
    #    adding relocations for them. Load at the preferred base (0x400000) instead.
    pe_off, = struct.unpack_from('<I', d, 0x3C)
    dllchar_off = pe_off + 24 + 70
    dllchar, = struct.unpack_from('<H', d, dllchar_off)
    assert dllchar == 0x8140, hex(dllchar)
    struct.pack_into('<H', d, dllchar_off, dllchar & ~0x0040)

    open(dst, 'wb').write(d)
    try:
        import pefile  # optional: Windows does not check the PE checksum of a game exe
        pe = pefile.PE(dst)
        pe.OPTIONAL_HEADER.CheckSum = pe.generate_checksum()
        pe.write(dst)
        pe.close()
    except ImportError:
        pass
    print('wrote', dst)


if __name__ == '__main__':
    main(sys.argv[1], sys.argv[2])
