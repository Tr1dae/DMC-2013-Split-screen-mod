"""Build the co-op script patches.

Engine.upk
  * Cheat `SetOnlineDebugLevel <int>` becomes `AddPlayer <ControllerId>`:
        VC = LocalPlayer(Outer.Player).ViewportClient;
        if (VC.FindPlayerByControllerId(ControllerId) == None)
            VC.CreatePlayer(ControllerId, VC.ConnectingMessage, true);
  * Cheat `RememberSpot` becomes `SplitAxis` (toggle side-by-side / top-bottom):
        if (VC.ActiveSplitscreenType == eSST_2P_VERTICAL) VC.DesiredSplitscreenType = eSST_2P_HORIZONTAL;
        else                                               VC.DesiredSplitscreenType = eSST_2P_VERTICAL;
        VC.LayoutPlayers();
  * Default2PSplitType defaults to eSST_2P_VERTICAL (side by side).

DevilGame.upk
  * DVGameInfo.PostLogin disables a new player's input until the match starts. A player who
    joins mid-mission never sees the match start, so only do that before it is in progress:
        super.PostLogin(NewPlayer);
        if (!bMatchInProgress) NTInput(NewPlayer.PlayerInput).DisableInput(3, true);

Usage: python build_packages.py <backup CookedPCConsole dir> <output dir>
"""
import struct, sys, os
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from upkpatch import *

ESST_2P_HORIZONTAL, ESST_2P_VERTICAL = 1, 2


def find_import(pk, path):
    for i in range(1, len(pk.imps) + 1):
        if pk.path(-i) == path:
            return -i
    raise KeyError(path)


def repurpose_cheat(pp, old_name, new_name, script):
    """Give CheatManager.<old_name> new bytecode and rename it (export + class FuncMap)."""
    pk = pp.pkg
    fn = pp.export_index('CheatManager.' + old_name)
    new = build_function(pp.export_data(fn), script, friendly=(pk.names.index(new_name), 0))
    pp.replace_export_data(fn, new)
    pp.rename_export(fn, new_name)
    pp.replace_in_export(pp.export_index('CheatManager'),
                         struct.pack('<iii', pk.names.index(old_name), 0, fn),
                         struct.pack('<iii', pk.names.index(new_name), 0, fn))
    return fn


def build_engine(src, dst):
    pp = PatchedPackage(src, os.path.join(os.path.dirname(dst), '_scratch'))
    pk, E = pp.pkg, pp.export_index

    Outer = find_import(pk, 'Core.Object.Outer')
    Player = E('PlayerController.Player')
    LocalPlayerCls = E('LocalPlayer')
    ViewportClient = E('LocalPlayer.ViewportClient')

    def VC():
        lp = dyncast(LocalPlayerCls, context(inst(Outer), Player, inst(Player)))
        return context(lp, ViewportClient, inst(ViewportClient))

    def vc_prop(path):
        p = E(path)
        return context(VC(), p, inst(p))

    # AddPlayer <ControllerId>
    cid = E('CheatManager.SetOnlineDebugLevel.DebugLevel')
    PawnP, LocationP, RotationP, ActorP = E('Controller.Pawn'), E('Actor.Location'), E('Actor.Rotation'), E('Player.Actor')
    SetLocation, SetRotation = E('Actor.SetLocation'), E('Actor.SetRotation')

    def new_lp():
        return context(VC(), E('GameViewportClient.FindPlayerByControllerId.ReturnValue'),
                       final_call(E('GameViewportClient.FindPlayerByControllerId'), local(cid)))

    def new_pc():
        return context(new_lp(), ActorP, inst(ActorP))

    def new_pawn():
        return context(new_pc(), PawnP, inst(PawnP))

    def my_pawn():
        return context(inst(Outer), PawnP, inst(PawnP))

    def try_place(dx, dy, dz):
        dest = native(0xD7, context(my_pawn(), LocationP, inst(LocationP)), vect(dx, dy, dz))  # vector +
        return context(new_pawn(), E('Actor.SetLocation.ReturnValue'), final_call(SetLocation, dest, EMPTY))

    create = context(VC(), E('GameViewportClient.CreatePlayer.ReturnValue'),
                     virtual_call(pk, 'CreatePlayer', local(cid),
                                  vc_prop('GameViewportClient.ConnectingMessage'), TRUE))
    face_pawn = context(new_pawn(), E('Actor.SetRotation.ReturnValue'),
                        final_call(SetRotation, context(my_pawn(), RotationP, inst(RotationP)), EMPTY))
    face_pc = context(new_pc(), E('Actor.SetRotation.ReturnValue'),
                      final_call(SetRotation, context(inst(Outer), RotationP, inst(RotationP)), EMPTY))
    script = assemble([
        # Join if this pad has no player yet; pressing it again just regroups.
        ('jump_if_not', 'joined', native(0x72, new_lp(), NONE)),       # ==
        create,
        'joined',
        # Spawn starts are often far away or in unloaded level chunks: put them next to us.
        ('jump_if_not', 'placed', native(0x81, try_place(120, 0, 0))),  # !
        ('jump_if_not', 'placed', native(0x81, try_place(-120, 0, 0))),
        ('jump_if_not', 'placed', native(0x81, try_place(0, 120, 0))),
        try_place(0, 0, 150),
        'placed',
        face_pawn,
        face_pc,
        RETURN_NOTHING, END])
    repurpose_cheat(pp, 'SetOnlineDebugLevel', 'AddPlayer', script)

    # SplitAxis
    byte_to_int = lambda e: cat(raw([0x38, 0x3A]), e)
    is_vertical = native(0x9A, byte_to_int(vc_prop('GameViewportClient.ActiveSplitscreenType')),
                         byte_to_int(raw([0x24, ESST_2P_VERTICAL])))                      # int ==
    set_h = cat(tok(0x0F), vc_prop('GameViewportClient.DesiredSplitscreenType'), raw([0x24, ESST_2P_HORIZONTAL]))
    set_v = cat(tok(0x0F), vc_prop('GameViewportClient.DesiredSplitscreenType'), raw([0x24, ESST_2P_VERTICAL]))
    layout = context(VC(), 0, virtual_call(pk, 'LayoutPlayers'))
    if_len = 3 + is_vertical.mem
    else_at = if_len + set_h.mem + 3
    end_at = else_at + set_v.mem
    script = cat(jump_if_not(else_at, is_vertical), set_h, tok(0x06), u16(end_at), set_v,
                 layout, RETURN_NOTHING, END)
    repurpose_cheat(pp, 'RememberSpot', 'SplitAxis', script)

    # Side-by-side by default.
    n = pk.names.index
    pp.replace_in_export(E('Default__GameViewportClient'),
                         struct.pack('<iiii', n('ESplitScreenType'), 0, n('eSST_2P_HORIZONTAL'), 0),
                         struct.pack('<iiii', n('ESplitScreenType'), 0, n('eSST_2P_VERTICAL'), 0))
    pp.save(dst)
    print('wrote', dst)


def build_devilgame(src, dst):
    pp = PatchedPackage(src, os.path.join(os.path.dirname(dst), '_scratch'))
    pk, E = pp.pkg, pp.export_index
    fn = E('DVGameInfo.PostLogin')
    old = pp.export_data(fn)
    from disasm import parse_function
    f = parse_function(pk, fn)
    s = f['script']
    # Existing statements: super.PostLogin(NewPlayer) [disk 0:11, mem 0x13] and
    # NTInput(NewPlayer.PlayerInput).DisableInput(3, true) [disk 11:51, mem 0x40].
    assert s[0] == 0x1C and s[11] == 0x19 and s[51:] == b'\x04\x0b\x53', s.hex(' ')
    super_call = Code(s[0:11], 0x13)
    disable = Code(s[11:51], 0x40)
    # Same statement shape with EnableInput(3): NTInput(NewPlayer.PlayerInput).EnableInput(3)
    enable_fn = find_import(pk, 'NTGameFramework.NTInput.EnableInput')
    new_player = struct.unpack_from('<i', s, 6)[0]   # s = 1c <super fn> 00 <NewPlayer> 16
    player_input = find_import(pk, 'Engine.PlayerController.PlayerInput')
    ntinput_cls = find_import(pk, 'NTGameFramework.NTInput')
    enable = context(dyncast(ntinput_cls, context(local(new_player), player_input, inst(player_input))),
                     0, final_call(enable_fn, raw([0x2C, 3])))
    in_progress = find_import(pk, 'NTGameFramework.NTGameInfo_Native.bMatchInProgress')
    # DVGameInfo has bDelayedStart set, so GameInfo.PostLogin never calls RestartPlayer: players
    # are only spawned when the match starts. A mid-mission joiner needs it done here. We call the
    # NTGameInfo_SP version directly: DVGameInfo.RestartPlayer would also re-point the game's
    # single "player pawn" (m_PlayerPawn), pickup system and upgrades at the new player.
    restart_sp = find_import(pk, 'NTGameFramework.NTGameInfo_SP.RestartPlayer')
    restart = final_call(restart_sp, local(new_player))
    post_restart = context(local(new_player), 0, virtual_call(pk, 'PostRestartPlayer'))
    # Keep the original disable (it may do more than block input), then undo it for mid-mission joins.
    script = assemble([super_call, disable,
                       ('jump_if_not', 'end', cat(tok(0x2D), inst(in_progress))),
                       enable, restart, post_restart,
                       'end', RETURN_NOTHING, END])
    pp.replace_export_data(fn, build_function(old, script))
    pp.save(dst)
    print('wrote', dst)


def build_ntgameframework(src, dst):
    """NTGameInfo_SP.SpawnPlayerPawn: Spawn(PawnClass,,, StartLocation, StartRotation,, bNoCollisionFail=true).

    Players spawn at the checkpoint's start. When player 2 joins, player 1 is often still standing
    there, so the collision-checked spawn fails and player 2 gets a controller with no pawn.
    AddPlayer moves the new pawn next to player 1 right after it spawns."""
    pp = PatchedPackage(src, os.path.join(os.path.dirname(dst), '_scratch'))
    fn = pp.export_index('NTGameInfo_SP.SpawnPlayerPawn')
    rot = struct.pack('<i', pp.export_index('NTGameInfo_SP.SpawnPlayerPawn.StartRotation'))
    pp.replace_in_export(fn, b'\x00' + rot + b'\x4a\x4a\x16', b'\x00' + rot + b'\x4a\x27\x16')
    pp.save(dst)
    print('wrote', dst)


if __name__ == '__main__':
    src_dir, out_dir = sys.argv[1], sys.argv[2]
    os.makedirs(out_dir, exist_ok=True)
    build_engine(os.path.join(src_dir, 'Engine.upk'), os.path.join(out_dir, 'Engine.upk'))
    build_devilgame(os.path.join(src_dir, 'DevilGame.upk'), os.path.join(out_dir, 'DevilGame.upk'))
    build_ntgameframework(os.path.join(src_dir, 'NTGameFramework.upk'), os.path.join(out_dir, 'NTGameFramework.upk'))
