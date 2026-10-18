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

3. Enemy AI only attacks and positions itself where the camera can see: ADVAICoordinator::IsOnCamera
   (vtable slot 0x488) asks for the first local player's camera only, so enemies fighting player 2
   off player 1's screen never got to attack. With two or more players it now runs once per
   player camera and is true if any camera passes. The camera lookup it calls (0xFBDFC0, "first
   player with a DmC camera") starts its search at a player index we set; that index is 0 outside
   the wrapper, so single player is unchanged.

Every site is checked against the original bytes before writing.
Usage: python patch_exe.py <original exe> <output exe>
"""
import struct, sys

IMAGE_BASE = 0x400000
TEXT_VA, TEXT_RAW = 0x1000, 0x400  # .text section mapping (VirtualAddress, PointerToRawData)
RDATA_RAW = 0x1F1FC00              # .rdata PointerToRawData (VirtualAddress 0x1F21000)

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

IS_ON_CAMERA = 0x1968EB0                 # ADVAICoordinator::IsOnCamera (thiscall, ret 0x14)
IS_ON_CAMERA_GETCAM_CALL = 0x1968EB4     # call 0xFBDFC0
GET_PLAYER_CAMERA = 0xFBDFC0
GET_PLAYER_CAMERA_LOOP = 0xFBDFCA        # cmp [esi+0x4E0], edi (esi = GEngine, edi = index)
COORDINATOR_VTABLE_SLOT = 0x26E2A50 + 0x488
TEXT_TAIL_CAVE = 0x2320710               # .text raw padding past VirtualSize (we extend it)
CAMERA_INDEX = 0x2C37F00                 # unused tail of .data's last page (RW, zeroed)


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

    # 3. IsOnCamera for every player camera.
    pe_off, = struct.unpack_from('<I', d, 0x3C)
    optsz, = struct.unpack_from('<H', d, pe_off + 20)
    sec = pe_off + 24 + optsz
    assert d[sec:sec + 5] == b'.text'
    vsize, = struct.unpack_from('<I', d, sec + 8)
    rawsize, = struct.unpack_from('<I', d, sec + 16)
    assert vsize == 0x1F1F704 and rawsize == 0x1F1F800, (hex(vsize), hex(rawsize))
    struct.pack_into('<I', d, sec + 8, rawsize)          # map the padding as code too
    idx = struct.pack('<I', CAMERA_INDEX)
    getcam = TEXT_TAIL_CAVE                              # GET_PLAYER_CAMERA starting at [CAMERA_INDEX]
    code = (b'\x56\x57'                                  # push esi; push edi
            + b'\x8b\x35' + struct.pack('<I', GENGINE)   # mov esi, [GEngine]
            + b'\x8b\x3d' + idx)                         # mov edi, [index]
    code += b'\xe9' + rel32(getcam + len(code) + 5, GET_PLAYER_CAMERA_LOOP)
    wrapper = getcam + 0x20
    w = (b'\xa1' + struct.pack('<I', GENGINE)            # mov eax, [GEngine]
         + b'\x83\xb8\xe0\x04\x00\x00\x02')              # cmp dword [eax+0x4e0], 2
    w += b'\x0f\x8c' + rel32(wrapper + len(w) + 6, IS_ON_CAMERA)   # jl IsOnCamera (one player)
    w += b'\x53\x56\x57\x8b\xf1\x33\xdb'                 # push ebx/esi/edi; mov esi, ecx; xor ebx, ebx
    loop = len(w)
    w += b'\x89\x1d' + idx                               # loop: mov [index], ebx
    w += b'\xff\x74\x24\x20' * 5                         # copy the 5 argument dwords
    w += b'\x8b\xce'                                     # mov ecx, esi
    w += b'\xe8' + rel32(wrapper + len(w) + 5, IS_ON_CAMERA)
    w += b'\x85\xc0\x75\x12'                             # test eax, eax; jnz found
    w += b'\x43\xa1' + struct.pack('<I', GENGINE)        # inc ebx; mov eax, [GEngine]
    w += b'\x3b\x98\xe0\x04\x00\x00'                     # cmp ebx, [eax+0x4e0]
    w += b'\x7c' + struct.pack('<b', loop - (len(w) + 2))   # jl loop
    w += b'\x33\xc0\xeb\x05'                             # xor eax, eax; jmp done
    w += b'\xb8\x01\x00\x00\x00'                         # found: mov eax, 1
    w += b'\xc7\x05' + idx + b'\x00\x00\x00\x00'         # done: mov dword [index], 0
    w += b'\x5f\x5e\x5b\xc2\x14\x00'                     # pop edi/esi/ebx; ret 0x14
    assert len(code) <= 0x20
    blob = code + b'\x00' * (0x20 - len(code)) + w
    patch(d, TEXT_TAIL_CAVE, b'\x00' * len(blob), blob)
    patch(d, IS_ON_CAMERA_GETCAM_CALL, b'\xe8' + rel32(IS_ON_CAMERA_GETCAM_CALL + 5, GET_PLAYER_CAMERA),
          b'\xe8' + rel32(IS_ON_CAMERA_GETCAM_CALL + 5, getcam))
    vt = COORDINATOR_VTABLE_SLOT - IMAGE_BASE - 0x1F21000 + RDATA_RAW
    assert struct.unpack_from('<I', d, vt)[0] == IS_ON_CAMERA
    struct.pack_into('<I', d, vt, wrapper)

    # 4. The caves use absolute addresses, and the exe opts into ASLR (DYNAMIC_BASE) without us
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
