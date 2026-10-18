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


def repurpose_cheat(pp, old_name, new_name, script, cls='CheatManager'):
    """Give <cls>.<old_name> new bytecode and rename it (export + class FuncMap)."""
    pk = pp.pkg
    fn = pp.export_index(cls + '.' + old_name)
    new = build_function(pp.export_data(fn), script, friendly=(pk.names.index(new_name), 0))
    pp.replace_export_data(fn, new)
    pp.rename_export(fn, new_name)
    pp.replace_in_export(pp.export_index(cls),
                         struct.pack('<iii', pk.names.index(old_name), 0, fn),
                         struct.pack('<iii', pk.names.index(new_name), 0, fn))
    return fn


# DesiredSplitscreenType value meaning "two players, one fullscreen view of player 1" (shared
# screen). eSST_MAX is never a real layout, so UpdateActiveSplitscreenType can tell it apart from
# eSST_NONE, which still means "use the default 2-player split".
SHARED_SCREEN = 6
# Same single view, but player 2 was dropped with F8; F6 returns to the split from this one only.
DROPPED = 7

# UnrealScript native operator indices (Object.uc).
OP_LESS_INT, OP_GREATER_INT, OP_EQ_INT, OP_NE_INT = 0x96, 0x97, 0x9A, 0x9B
OP_EQ_OBJ, OP_NOT_BOOL, OP_MUL_FLOAT = 0x72, 0x81, 0xAB
OP_MUL_VEC_FLOAT, OP_ADD_VEC, OP_SUB_VEC, OP_VSIZE, OP_NORMAL = 0xD4, 0xD7, 0xD8, 0xE1, 0xE2


def int_eq_byte(e, v):
    return native(OP_EQ_INT, byte_to_int(e), byte_to_int(byteconst(v)))


def int_ne_byte(e, v):
    return native(OP_NE_INT, byte_to_int(e), byte_to_int(byteconst(v)))


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
    CCRet = E('PlayerController.ConsoleCommand.ReturnValue')

    def console(pc, command):
        """pc.ConsoleCommand(command): runs an exec on that player's own exec chain (its CheatManager)."""
        return eat_return(CCRet, context(pc, CCRet, virtual_call(pk, 'ConsoleCommand', strconst(command), EMPTY)))

    desired = lambda: vc_prop('GameViewportClient.DesiredSplitscreenType')
    active = lambda: vc_prop('GameViewportClient.ActiveSplitscreenType')
    layout = lambda: context(VC(), 0, virtual_call(pk, 'LayoutPlayers'))
    # DmC players own their pawn through NTPlayerController.m_NTPawn and never set Controller.Pawn,
    # so pawn work is done by DevilGame cheats run on player 2's own controller (see build_devilgame).
    script = assemble([
        # Join if this pad has no player yet; pressing it again just regroups.
        ('jump_if_not', 'joined', native(OP_EQ_OBJ, new_lp(), NONE)),
        create,
        'joined',
        # Dropped with F8 (controller kept, Dante despawned)? RestartPlayer respawns them; it does
        # nothing if they already have a pawn. Then leave the dropped single view.
        console(new_pc(), 'RestartPlayer'),
        ('jump_if_not', 'not_dropped', int_eq_byte(desired(), DROPPED)),
        let(desired(), byteconst(0)),
        'not_dropped',
        # Spawn starts are often far away or in unloaded level chunks: put them next to player 1.
        console(new_pc(), 'Teleport'),
        face_pc,
        layout(),
        RETURN_NOTHING, END])
    repurpose_cheat(pp, 'SetOnlineDebugLevel', 'AddPlayer', script)

    # RemovePlayer (F8): despawn player 2's Dante via DevilGame's Despawn cheat on their own
    # controller, and show player 1 fullscreen. The controller stays logged in: destroying it would
    # run NTPlayerController.Destroyed, which clears the *global* in-game UI references.
    OuterImp, GamePlayers = Outer, E('Engine.GamePlayers')

    def gp(vc):
        return context(context(vc, OuterImp, inst(OuterImp)), GamePlayers, inst(GamePlayers))

    def gp_pc(vc, i):
        return context(array_elem(tok(0x25 + i), gp(vc)), ActorP, inst(ActorP))            # IntZero / IntOne
    script = assemble([
        ('jump_if_not', 'end', native(OP_GREATER_INT, cat(tok(0x36), gp(VC())), tok(0x26))),  # Length > 1
        console(gp_pc(VC(), 1), 'Despawn'),
        let(desired(), byteconst(DROPPED)),
        layout(),
        'end', RETURN_NOTHING, END])
    repurpose_cheat(pp, 'DebugPause', 'RemovePlayer', script)

    # SplitAxis (F7): side by side -> top/bottom -> shared screen -> side by side.
    script = assemble([
        ('jump_if_not', 'not_v', int_eq_byte(active(), ESST_2P_VERTICAL)),
        let(desired(), byteconst(ESST_2P_HORIZONTAL)), ('jump', 'layout'),
        'not_v',
        ('jump_if_not', 'not_h', int_eq_byte(active(), ESST_2P_HORIZONTAL)),
        let(desired(), byteconst(SHARED_SCREEN)), ('jump', 'layout'),
        'not_h',
        let(desired(), byteconst(ESST_2P_VERTICAL)),
        'layout', layout(), RETURN_NOTHING, END])
    repurpose_cheat(pp, 'RememberSpot', 'SplitAxis', script)

    # UpdateActiveSplitscreenType: stock rules, plus SHARED_SCREEN -> eSST_NONE for two players.
    # With eSST_NONE, SplitscreenInfo has a single fullscreen entry, so LayoutPlayers gives player 2
    # a zero-size view and only player 1's camera is drawn.
    fn = E('GameViewportClient.UpdateActiveSplitscreenType')
    st = E('GameViewportClient.UpdateActiveSplitscreenType.SplitType')
    n = lambda: cat(tok(0x36), context(inst(OuterImp), GamePlayers, inst(GamePlayers)))
    two = raw([0x2C, 2])
    three = raw([0x2C, 3])
    set_st = lambda e: let(local(st), e)
    script = assemble([
        set_st(inst(E('GameViewportClient.DesiredSplitscreenType'))),
        ('jump_if_not', 'many', native(OP_LESS_INT, n(), two)),
        set_st(byteconst(0)), ('jump', 'done'),
        'many',
        ('jump_if_not', 'not2', native(OP_EQ_INT, n(), two)),
        ('jump_if_not', 'not_shared', native(OP_GREATER_INT, byte_to_int(local(st)), byte_to_int(byteconst(5)))),
        set_st(byteconst(0)), ('jump', 'done'),                                  # SHARED_SCREEN or DROPPED
        'not_shared',
        ('jump_if_not', 'done', andand(int_ne_byte(local(st), 1), int_ne_byte(local(st), 2))),
        set_st(inst(E('GameViewportClient.Default2PSplitType'))), ('jump', 'done'),
        'not2',
        ('jump_if_not', 'not3', native(OP_EQ_INT, n(), three)),
        ('jump_if_not', 'done', andand(int_ne_byte(local(st), 3), int_ne_byte(local(st), 4))),
        set_st(inst(E('GameViewportClient.Default3PSplitType'))), ('jump', 'done'),
        'not3',
        set_st(byteconst(5)),
        'done',
        let(inst(E('GameViewportClient.ActiveSplitscreenType')), local(st)),
        RETURN_NOTHING, END])
    pp.replace_export_data(fn, build_function(pp.export_data(fn), script))

    build_shared_camera(pp, E, OuterImp, GamePlayers, LocalPlayerCls, ViewportClient, Player,
                        PawnP, LocationP, ActorP)

    # Side-by-side by default.
    n = pk.names.index
    pp.replace_in_export(E('Default__GameViewportClient'),
                         struct.pack('<iiii', n('ESplitScreenType'), 0, n('eSST_2P_HORIZONTAL'), 0),
                         struct.pack('<iiii', n('ESplitScreenType'), 0, n('eSST_2P_VERTICAL'), 0))
    pp.save(dst)
    print('wrote', dst)


SHARED_CAMERA_PULLBACK = 0.6   # extra camera distance per unit of distance between the players


def build_shared_camera(pp, E, OuterImp, GamePlayers, LocalPlayerCls, ViewportClient, Player,
                        PawnP, LocationP, ActorP):
    """Shared screen camera, appended to PlayerController.GetPlayerViewPoint (after DmC's camera
    has produced out_Location). ULocalPlayer::CalcSceneView renders from this event.

        if (VC.Outer.GamePlayers.Length >= 2 && VC.ActiveSplitscreenType == eSST_NONE
            && !bCinematicMode && self == GamePlayers[0].Actor)
        {
            // DmC pawns are owned by their controller (NTPawn.PossessedBy -> SetOwner) but
            // Controller.Pawn is never set, so look player 2's pawn up by owner.
            foreach DynamicActors(class'Pawn', TheViewTarget)
                if (TheViewTarget.Owner == GamePlayers[1].Actor) break;   // (found)
            P1 = NT_GetLocalPlayerPawn();
            D = P2.Location - P1.Location;
            out_Location += D * 0.5 + Normal(out_Location - P1.Location) * (VSize(D) * PULLBACK);
        }

    i.e. keep player 1's camera angle, move it to the midpoint of both players and pull it back as
    they spread apart. Cutscenes (cinematic mode) are left alone."""
    pk = pp.pkg
    fn = E('PlayerController.GetPlayerViewPoint')
    out_loc = E('PlayerController.GetPlayerViewPoint.out_Location')
    found = E('PlayerController.GetPlayerViewPoint.TheViewTarget')    # Actor local, unused by now
    from disasm import parse_function
    f = parse_function(pk, fn)
    s = f['script']
    assert s[-3:] == b'\x04\x0b\x53', s[-3:].hex()
    body = s[:-3]
    body_mem = f['bsize'] - 3
    dyn = E('Actor.DynamicActors')
    assert parse_function(pk, dyn)['inative'] == 313
    get_p1 = E('Actor.NT_GetLocalPlayerPawn')
    OwnerP = E('Actor.Owner')

    vc = context(dyncast(LocalPlayerCls, inst(Player)), ViewportClient, inst(ViewportClient))
    gp = lambda: context(context(vc, OuterImp, inst(OuterImp)), GamePlayers, inst(GamePlayers))
    gp_pc = lambda i: context(array_elem(tok(0x25 + i), gp()), ActorP, inst(ActorP))
    p1_loc = lambda: context(final_call(get_p1), LocationP, inst(LocationP))
    delta = lambda: native(OP_SUB_VEC, context(local(found), LocationP, inst(LocationP)), p1_loc())

    cond = native(0x99, cat(tok(0x36), gp()), raw([0x2C, 2]))                                   # Length >= 2
    cond = andand(cond, int_eq_byte(context(vc, E('GameViewportClient.ActiveSplitscreenType'),
                                            inst(E('GameViewportClient.ActiveSplitscreenType'))), 0))
    cond = andand(cond, native(OP_NOT_BOOL, boolvar(inst(E('PlayerController.bCinematicMode')))))
    cond = andand(cond, native(OP_EQ_OBJ, tok(0x17), gp_pc(0)))                                 # self
    owns = native(OP_EQ_OBJ, context(local(found), OwnerP, inst(OwnerP)), gp_pc(1))
    shift = native(OP_MUL_VEC_FLOAT, delta(), floatconst(0.5))
    pull = native(OP_MUL_VEC_FLOAT, native(OP_NORMAL, native(OP_SUB_VEC, outvar(out_loc), p1_loc())),
                  native(OP_MUL_FLOAT, native(OP_VSIZE, delta()), floatconst(SHARED_CAMERA_PULLBACK)))
    extra = assemble([
        ('jump_if_not', 'end', cond),
        ('foreach', 'loop_end', native_ext(313, objconst(E('Pawn')), local(found), EMPTY)),
        ('jump_if_not', 'next', owns),
        ITER_POP, ('jump', 'found'),
        'next', ITER_NEXT,
        'loop_end', ITER_POP,
        ('jump', 'end'),                                                       # player 2 has no pawn
        'found',
        ('jump_if_not', 'end', native(0x77, final_call(get_p1), NONE)),        # player 1 pawn != None
        let(outvar(out_loc), native(OP_ADD_VEC, native(OP_ADD_VEC, outvar(out_loc), shift), pull)),
        'end', RETURN_NOTHING, END], base=body_mem)
    script = Code(body, body_mem) + extra
    pp.replace_export_data(fn, build_function(pp.export_data(fn), script))


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

    # Cheats run on a player's own controller (Outer) by Engine's AddPlayer/RemovePlayer via
    # PlayerController.ConsoleCommand. Repurposes two unused upgrade-lock cheats.
    outer = find_import(pk, 'Core.Object.Outer')
    ntpc = find_import(pk, 'NTGameFramework.NTPlayerController')
    nt_pawn = find_import(pk, 'NTGameFramework.NTPlayerController.m_NTPawn')
    world, game = find_import(pk, 'Engine.Actor.WorldInfo'), find_import(pk, 'Engine.WorldInfo.Game')
    # Despawn: NTPlayerController(Outer).NTUnPossessAndDestroy()
    script = assemble([context(inst(outer), 0, virtual_call(pk, 'NTUnPossessAndDestroy')), RETURN_NOTHING, END])
    repurpose_cheat(pp, 'LockStormSword', 'Despawn', script, cls='DVExecFunctions')
    # RestartPlayer: if (NTPlayerController(Outer).m_NTPawn == None) { the PostLogin join spawn }
    no_pawn = native(0x72, context(dyncast(ntpc, inst(outer)), nt_pawn, inst(nt_pawn)), NONE)
    game_obj = context(context(inst(outer), world, inst(world)), game, inst(game))
    script = assemble([
        ('jump_if_not', 'end', no_pawn),
        context(game_obj, 0, final_call(restart_sp, inst(outer))),
        context(inst(outer), 0, virtual_call(pk, 'PostRestartPlayer')),
        'end', RETURN_NOTHING, END])
    repurpose_cheat(pp, 'LockSpiralTrap', 'RestartPlayer', script, cls='DVExecFunctions')

    # Teleport: move this player's pawn next to player 1's (spawn starts are often far away or in
    # unloaded level chunks), trying +X, -X, +Y and then above, and match player 1's facing.
    #   P1 = class'Actor'.static.NT_GetLocalPlayerPawn();  P = NTPlayerController(Outer).m_NTPawn;
    #   if (!P.SetLocation(P1.Location + vect(120,0,0))) if (...) ...;  P.SetRotation(P1.Rotation);
    actor_cls = find_import(pk, 'Engine.Actor')
    get_p1 = find_import(pk, 'Engine.Actor.NT_GetLocalPlayerPawn')
    loc, rot = find_import(pk, 'Engine.Actor.Location'), find_import(pk, 'Engine.Actor.Rotation')
    set_loc, set_rot = find_import(pk, 'Engine.Actor.SetLocation'), find_import(pk, 'Engine.Actor.SetRotation')
    p1 = lambda: static_call(actor_cls, 0, final_call(get_p1))
    me = lambda: context(dyncast(ntpc, inst(outer)), nt_pawn, inst(nt_pawn))

    def try_place(dx, dy, dz):
        dest = native(0xD7, context(p1(), loc, inst(loc)), vect(dx, dy, dz))                 # vector +
        return context(me(), 0, final_call(set_loc, dest, EMPTY))
    script = assemble([
        ('jump_if_not', 'placed', native(0x81, try_place(120, 0, 0))),                       # !
        ('jump_if_not', 'placed', native(0x81, try_place(-120, 0, 0))),
        ('jump_if_not', 'placed', native(0x81, try_place(0, 120, 0))),
        try_place(0, 0, 150),
        'placed',
        context(me(), 0, final_call(set_rot, context(p1(), rot, inst(rot)), EMPTY)),
        RETURN_NOTHING, END])
    repurpose_cheat(pp, 'LockScythe', 'Teleport', script, cls='DVExecFunctions')
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
