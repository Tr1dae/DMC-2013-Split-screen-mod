/*
 * CoopMod native helper, loaded as Binaries/Win32/xinput1_3.dll.
 *
 * The game imports XInputGetState/XInputSetState (ordinals 2 and 3) from xinput1_3.dll, so a
 * DLL of that name next to the exe is loaded instead of the system one. We forward every call
 * to the real DLL from the system directory.
 *
 * Diagnostics: a background thread writes CoopMod/coop_log.txt whenever the pad/player picture
 * changes: XInput pad activity, QLOC's "current controller" state, the joystick table, and each
 * local player's ControllerId and pawn.
 */
#include <windows.h>
#include <stdio.h>
#include <math.h>

/* ---- forwarding ------------------------------------------------------------------------- */

typedef struct { WORD wButtons; BYTE bLeftTrigger, bRightTrigger; SHORT sThumbLX, sThumbLY, sThumbRX, sThumbRY; } PAD;
typedef struct { DWORD dwPacketNumber; PAD Gamepad; } PADSTATE;

static HMODULE g_real;
static FARPROC g_fn[9];
static const char *g_names[9] = { 0, 0, "XInputGetState", "XInputSetState", "XInputGetCapabilities",
                                  "XInputEnable", "XInputGetDSoundAudioDeviceGuids",
                                  "XInputGetBatteryInformation", "XInputGetKeystroke" };

static void load_real(void)
{
    static const char *candidates[] = { "\\xinput1_3.dll", "\\xinput1_4.dll", "\\xinput9_1_0.dll" };
    char path[MAX_PATH];
    int i;
    if (g_real) return;
    for (i = 0; i < 3 && !g_real; i++) {
        GetSystemDirectoryA(path, MAX_PATH);
        strcat_s(path, MAX_PATH, candidates[i]);
        g_real = LoadLibraryA(path);
    }
    for (i = 2; i < 9 && g_real; i++) g_fn[i] = GetProcAddress(g_real, g_names[i]);
}

static volatile LONG g_padActive[4], g_padConnected[4];

DWORD WINAPI XInputGetState(DWORD idx, PADSTATE *s)
{
    DWORD r;
    load_real();
    if (!g_fn[2]) return ERROR_DEVICE_NOT_CONNECTED;
    r = ((DWORD (WINAPI *)(DWORD, PADSTATE *))g_fn[2])(idx, s);
    if (idx < 4) {
        g_padConnected[idx] = (r == ERROR_SUCCESS);
        if (r == ERROR_SUCCESS) {
            PAD *p = &s->Gamepad;
            int stick = abs(p->sThumbLX) > 8000 || abs(p->sThumbLY) > 8000 ||
                        abs(p->sThumbRX) > 8000 || abs(p->sThumbRY) > 8000;
            g_padActive[idx] = (p->wButtons != 0) || stick || p->bLeftTrigger > 30 || p->bRightTrigger > 30;
        }
    }
    return r;
}

DWORD WINAPI XInputSetState(DWORD idx, void *v)
{
    load_real();
    return g_fn[3] ? ((DWORD (WINAPI *)(DWORD, void *))g_fn[3])(idx, v) : ERROR_DEVICE_NOT_CONNECTED;
}

DWORD WINAPI XInputGetCapabilities(DWORD idx, DWORD flags, void *caps)
{
    load_real();
    return g_fn[4] ? ((DWORD (WINAPI *)(DWORD, DWORD, void *))g_fn[4])(idx, flags, caps) : ERROR_DEVICE_NOT_CONNECTED;
}

void WINAPI XInputEnable(BOOL enable)
{
    load_real();
    if (g_fn[5]) ((void (WINAPI *)(BOOL))g_fn[5])(enable);
}

DWORD WINAPI XInputGetDSoundAudioDeviceGuids(DWORD idx, GUID *render, GUID *capture)
{
    load_real();
    return g_fn[6] ? ((DWORD (WINAPI *)(DWORD, GUID *, GUID *))g_fn[6])(idx, render, capture) : ERROR_DEVICE_NOT_CONNECTED;
}

DWORD WINAPI XInputGetBatteryInformation(DWORD idx, BYTE type, void *info)
{
    load_real();
    return g_fn[7] ? ((DWORD (WINAPI *)(DWORD, BYTE, void *))g_fn[7])(idx, type, info) : ERROR_DEVICE_NOT_CONNECTED;
}

DWORD WINAPI XInputGetKeystroke(DWORD idx, DWORD reserved, void *ks)
{
    load_real();
    return g_fn[8] ? ((DWORD (WINAPI *)(DWORD, DWORD, void *))g_fn[8])(idx, reserved, ks) : ERROR_EMPTY;
}

/* ---- diagnostics ------------------------------------------------------------------------ */

/* Addresses in DMC-DevilMayCry.exe at its preferred base 0x400000. */
#define EXE_BASE            0x400000
#define G_ENGINE            0x2B2C328   /* UEngine*: GamePlayers.Data +0x4DC, .Num +0x4E0 */
#define G_CURRENT_PAD       0x2B551F0   /* QLOC current controller */
#define G_INPUT_MODE        0x2B551E8   /* QLOC input mode (1 = keyboard) */
#define G_LAST_PAD          0x2A254CC   /* QLOC last pad that claimed player 1 */
#define G_LAST_KBD          0x2A254D0
#define G_JOY_DATA          0x2B6C4E4   /* joystick table, stride 0x474 */
#define G_JOY_NUM           0x2B6C4E8

static DWORD g_base;
static char g_logPath[MAX_PATH];

static DWORD rd(DWORD addr)
{
    DWORD v = 0xDEADBEEF;
    __try { v = *(DWORD *)addr; } __except (EXCEPTION_EXECUTE_HANDLER) {}
    return v;
}
#define G(a) rd(g_base + (a) - EXE_BASE)

static void logline(const char *s)
{
    FILE *f;
    SYSTEMTIME t;
    if (fopen_s(&f, g_logPath, "a") || !f) return;
    GetLocalTime(&t);
    fprintf(f, "%02d:%02d:%02d.%03d %s\n", t.wHour, t.wMinute, t.wSecond, t.wMilliseconds, s);
    fclose(f);
}

static DWORD WINAPI monitor(void *unused)
{
    char cur[2048], last[2048] = "";
    (void)unused;
    for (;;) {
        DWORD eng = G(G_ENGINE), n, data, i, jn, jd;
        int len = 0;
        len += sprintf_s(cur + len, sizeof(cur) - len, "pads[");
        for (i = 0; i < 4; i++)
            len += sprintf_s(cur + len, sizeof(cur) - len, "%s%c", i ? " " : "",
                             !g_padConnected[i] ? '-' : g_padActive[i] ? '#' : 'o');
        len += sprintf_s(cur + len, sizeof(cur) - len, "] qloc cur=%d mode=%d lastPad=%d lastKbd=%d",
                         (int)G(G_CURRENT_PAD), (int)G(G_INPUT_MODE), (int)G(G_LAST_PAD), (int)G(G_LAST_KBD));
        jn = G(G_JOY_NUM); jd = G(G_JOY_DATA);
        len += sprintf_s(cur + len, sizeof(cur) - len, " joy[");
        for (i = 0; i < jn && i < 8 && jd; i++) {
            DWORD j = jd + i * 0x474;
            len += sprintf_s(cur + len, sizeof(cur) - len, "%s{t%d id%d on%d}", i ? " " : "",
                             (int)rd(j + 0x10), (int)rd(j + 0x14), (int)rd(j + 0x454));
        }
        len += sprintf_s(cur + len, sizeof(cur) - len, "]");
        if (eng && eng != 0xDEADBEEF) {
            n = rd(eng + 0x4E0); data = rd(eng + 0x4DC);
            len += sprintf_s(cur + len, sizeof(cur) - len, " players=%d", (int)n);
            for (i = 0; i < n && i < 4 && data; i++) {
                DWORD lp = rd(data + 4 * i), pc = lp ? rd(lp + 0x3C) : 0;
                DWORD pawn = (pc && pc != 0xDEADBEEF) ? rd(pc + 0x614) : 0;
                len += sprintf_s(cur + len, sizeof(cur) - len, " P%d{cid=%d pc=%s pawn=%s}", (int)i + 1,
                                 (int)rd(lp + 0x60), pc ? "yes" : "no", pawn ? "yes" : "no");
            }
        }
        if (strcmp(cur, last)) { logline(cur); strcpy_s(last, sizeof(last), cur); }
        Sleep(250);
    }
}

/* ---- script call tracer ----------------------------------------------------------------
 * Hooks UObject::CallFunction (script VM calls, 0x47B370) and UObject::ProcessEvent (native ->
 * script events, 0x47B7B0). When a function named TRACE_TRIGGER starts, the next TRACE_MAX calls
 * are written to CoopMod/coop_trace.txt with nesting depth, and object return values of
 * interesting functions are printed after they return.
 */
#define FN_CALLFUNCTION     0x47B370    /* thiscall (FFrame&, RESULT_DECL, UFunction*), ret 0xC */
#define FN_PROCESSEVENT     0x47B7B0    /* thiscall (UFunction*, void* Parms, void* Result), ret 0xC */
#define G_NAMES_DATA        0x2B0AC38   /* TArray<FNameEntry*> */
#define G_NAMES_NUM         0x2B0AC3C
#define OBJ_OUTER           0x24
#define OBJ_NAME            0x28
#define OBJ_CLASS           0x30
#define TRACE_TRIGGER       "AddPlayer"
#define TRACE_MAX           6000

typedef void (__fastcall *PFN_CF)(void *self, void *edx, void *stack, void *result, void *fn);
typedef void (__fastcall *PFN_PE)(void *self, void *edx, void *fn, void *parms, void *result);
static PFN_CF g_origCF;
static PFN_PE g_origPE;
static int g_nameStrOff = -1, g_nameWide;
static FILE *g_trace;
static int g_traceLeft, g_depth;
static char g_tracePath[MAX_PATH];

static const char *name_of_index(int idx, char *buf, int cap)
{
    DWORD data = G(G_NAMES_DATA), num = G(G_NAMES_NUM), e;
    buf[0] = 0;
    if (!data || idx < 0 || (DWORD)idx >= num) { sprintf_s(buf, cap, "?%d", idx); return buf; }
    e = rd(data + 4 * idx);
    if (!e || g_nameStrOff < 0) { sprintf_s(buf, cap, "?%d", idx); return buf; }
    __try {
        if (g_nameWide) { int i; const WCHAR *w = (const WCHAR *)(e + g_nameStrOff);
                          for (i = 0; i < cap - 1 && w[i]; i++) buf[i] = (char)w[i]; buf[i] = 0; }
        else strncpy_s(buf, cap, (const char *)(e + g_nameStrOff), _TRUNCATE);
    } __except (EXCEPTION_EXECUTE_HANDLER) { sprintf_s(buf, cap, "?%d", idx); }
    return buf;
}

static const char *obj_name(DWORD obj, char *buf, int cap)
{
    /* FName = index + instance number; number N > 0 displays as Name_(N-1), e.g. two
       DVPlayerController_Dante actors are DVPlayerController_Dante_0 and _1. */
    int num;
    if (!obj) { strcpy_s(buf, cap, "None"); return buf; }
    name_of_index((int)rd(obj + OBJ_NAME), buf, cap);
    num = (int)rd(obj + OBJ_NAME + 4);
    if (num > 0 && num < 100000) { size_t l = strlen(buf); sprintf_s(buf + l, cap - l, "_%d", num - 1); }
    return buf;
}

static void find_name_layout(void)
{
    /* Entry 0 is "None": find where its characters start. */
    DWORD data = G(G_NAMES_DATA), e;
    int off;
    if (!data || !(e = rd(data))) return;
    for (off = 0; off <= 0x20; off += 4) {
        __try {
            if (!memcmp((void *)(e + off), "None", 5)) { g_nameStrOff = off; g_nameWide = 0; return; }
            if (!memcmp((void *)(e + off), L"None", 10)) { g_nameStrOff = off; g_nameWide = 1; return; }
        } __except (EXCEPTION_EXECUTE_HANDLER) { return; }
    }
}

static int is_watched(const char *fn)
{
    static const char *w[] = { "Spawn", "SpawnPlayerPawn", "NTFindPlayerStart", "FindPlayerStart",
        "FindCheckpoint", "GetPlayerStart", "DetermineCharacterTemplate", "Login", "CreatePlayer",
        "SpawnPlayActor", "FindPlayerByControllerId", "NT_GetLocalPlayerPawn", 0 };
    int i;
    for (i = 0; w[i]; i++) if (!strcmp(fn, w[i])) return 1;
    return 0;
}

static void trace_call(const char *kind, DWORD self, DWORD fn)
{
    char a[96], b[96], c[96], d[96];
    if (!g_trace || g_traceLeft <= 0) return;
    obj_name(fn, a, sizeof a);
    fprintf(g_trace, "%*s%s %s.%s on %s(%s)\n", g_depth * 2, "", kind,
            obj_name(rd(fn + OBJ_OUTER), b, sizeof b), a,
            obj_name(rd(self + OBJ_CLASS), c, sizeof c), obj_name(self, d, sizeof d));
    if (--g_traceLeft == 0) { fprintf(g_trace, "---- trace limit ----\n"); fclose(g_trace); g_trace = 0; }
}

static void trace_result(DWORD fn, void *result)
{
    char a[96], b[96], c[96];
    DWORD r;
    if (!g_trace || !result) return;
    obj_name(fn, a, sizeof a);
    if (!is_watched(a)) return;
    r = rd((DWORD)result);
    fprintf(g_trace, "%*s  -> %s returned %s(%s)\n", g_depth * 2, "", a,
            r ? obj_name(rd(r + OBJ_CLASS), b, sizeof b) : "", obj_name(r, c, sizeof c));
}

/* Functions that start a trace, and how many calls to record after each. */
static struct { const char *name; int max; int idx; } g_triggers[] = {
    { TRACE_TRIGGER, TRACE_MAX, -1 },   /* F6: the join/spawn chain */
    { "SplitAxis", 30000, -1 },         /* F7: a few frames of camera calls after the view changes */
    { "RemovePlayer", 6000, -1 },       /* F8 */
};
#define NTRIGGERS (sizeof g_triggers / sizeof g_triggers[0])
static int g_triggerScanned, g_viewPointIdx = -1;
static void find_watch_indices(void);

static void find_trigger_index(void)
{
    /* Called once the name table is populated; triggers are script function names. */
    DWORD num = G(G_NAMES_NUM), i, t;
    char buf[160];
    g_triggerScanned = 1;
    for (i = 0; i < num; i++) {
        name_of_index((int)i, buf, sizeof buf);
        for (t = 0; t < NTRIGGERS; t++) if (g_triggers[t].idx < 0 && !strcmp(buf, g_triggers[t].name)) g_triggers[t].idx = (int)i;
        if (g_viewPointIdx < 0 && !strcmp(buf, "GetPlayerViewPoint")) g_viewPointIdx = (int)i;
    }
    find_watch_indices();
    for (t = 0; t < NTRIGGERS; t++) {
        sprintf_s(buf, sizeof buf, "tracer: trigger '%s' is name %d", g_triggers[t].name, g_triggers[t].idx);
        logline(buf);
    }
}

static void maybe_start_trace(void *fn)
{
    /* Exec commands (key bindings, console) arrive through ProcessEvent, script calls through
       CallFunction, so both hooks check the triggers. */
    int idx, t;
    if (g_nameStrOff < 0) find_name_layout();
    if (g_nameStrOff >= 0 && !g_triggerScanned && G(G_NAMES_NUM) > 20000) find_trigger_index();
    if (g_trace || !g_triggerScanned) return;
    idx = (int)rd((DWORD)fn + OBJ_NAME);
    for (t = 0; t < (int)NTRIGGERS; t++) {
        if (g_triggers[t].idx >= 0 && idx == g_triggers[t].idx) {
            if (!fopen_s(&g_trace, g_tracePath, "a") && g_trace) {
                fprintf(g_trace, "==== trace start (%s) ====\n", g_triggers[t].name);
                g_traceLeft = g_triggers[t].max; g_depth = 0;
            }
            return;
        }
    }
}

/* ---- always-on watch log ----------------------------------------------------------------
 * Every call to one of these functions is written to CoopMod/coop_watch.txt with the object it
 * runs on and the script function that called it (FFrame: Node +0x10, Object +0x14).
 */
static const char *g_watchNames[] = { "SetPause", "ClearPause", "ConditionalPause", "PauseGame",
    "ResumeGame", "Tut_ShowBox", "Tut_HideBox", "OnControllerChanged", "OnLostFocusPause",
    "Handle_PausePressed", "DisplayGameMenu", "DisplayIngameDialog", "SetCinematicMode", "AddPlayer",
    /* markers: harmless calls the mod's AddPlayer makes at each early exit (logged only from there) */
    "IsPrimaryPlayer", "GetSplitscreenPlayerCount", 0 };
#define WATCH_FIRST_MARKER 14
static int g_watchIdx[32];
static char g_watchPath[MAX_PATH];

static void find_watch_indices(void)
{
    DWORD num = G(G_NAMES_NUM), i;
    int w;
    char buf[96];
    for (w = 0; g_watchNames[w]; w++) g_watchIdx[w] = -1;
    for (i = 0; i < num; i++) {
        name_of_index((int)i, buf, sizeof buf);
        for (w = 0; g_watchNames[w]; w++) if (g_watchIdx[w] < 0 && !strcmp(buf, g_watchNames[w])) g_watchIdx[w] = (int)i;
    }
}

static void watch_call(const char *kind, DWORD self, DWORD fn, DWORD stack)
{
    char a[96], b[96], c[96], d[96], e[96], f[96];
    int idx = (int)rd(fn + OBJ_NAME), w;
    FILE *out;
    SYSTEMTIME t;
    for (w = 0; g_watchNames[w]; w++) if (g_watchIdx[w] == idx) break;
    if (!g_watchNames[w]) return;
    if (w >= WATCH_FIRST_MARKER) {
        if (!stack) return;
        obj_name(rd(stack + 0x10), f, sizeof f);
        if (strcmp(f, "AddPlayer")) return;
    }
    if (fopen_s(&out, g_watchPath, "a") || !out) return;
    GetLocalTime(&t);
    obj_name(fn, a, sizeof a);
    obj_name(rd(fn + OBJ_OUTER), b, sizeof b);
    obj_name(self, c, sizeof c);
    if (stack) { obj_name(rd(stack + 0x14), d, sizeof d); obj_name(rd(rd(stack + 0x10) + OBJ_OUTER), e, sizeof e);
                 obj_name(rd(stack + 0x10), f, sizeof f); }
    fprintf(out, "%02d:%02d:%02d.%03d %s %s.%s on %s", t.wHour, t.wMinute, t.wSecond, t.wMilliseconds, kind, b, a, c);
    if (stack) fprintf(out, "  <- %s.%s in %s", e, f, d);
    fprintf(out, "\n");
    fclose(out);
}

static void trace_viewpoint(DWORD self, DWORD fn, void *parms)
{
    /* GetPlayerViewPoint(out vector out_Location, out rotator out_Rotation): show the result. */
    char a[96];
    float *v = (float *)parms;
    int *r = (int *)parms;
    if (!g_trace || !parms || (int)rd(fn + OBJ_NAME) != g_viewPointIdx) return;
    __try {
        fprintf(g_trace, "%*s  -> view of %s: loc=(%.0f %.0f %.0f) rot=(%d %d %d)\n", g_depth * 2, "",
                obj_name(self, a, sizeof a), v[0], v[1], v[2], r[3], r[4], r[5]);
    } __except (EXCEPTION_EXECUTE_HANDLER) {}
}

static void __fastcall hk_CallFunction(void *self, void *edx, void *stack, void *result, void *fn)
{
    maybe_start_trace(fn);
    if (g_triggerScanned) watch_call("CF", (DWORD)self, (DWORD)fn, (DWORD)stack);
    trace_call("CF", (DWORD)self, (DWORD)fn);
    g_depth++;
    g_origCF(self, edx, stack, result, fn);
    g_depth--;
    trace_result((DWORD)fn, result);
    if (g_trace && g_depth == 0) fflush(g_trace);
}

static void __fastcall hk_ProcessEvent(void *self, void *edx, void *fn, void *parms, void *result)
{
    maybe_start_trace(fn);
    if (g_triggerScanned) watch_call("PE", (DWORD)self, (DWORD)fn, 0);
    trace_call("PE", (DWORD)self, (DWORD)fn);
    g_depth++;
    g_origPE(self, edx, fn, parms, result);
    g_depth--;
    trace_viewpoint((DWORD)self, (DWORD)fn, parms);
    if (g_trace && g_depth == 0) fflush(g_trace);
}

static void *hook(DWORD target, int stolen, void *detour)
{
    BYTE *tramp = VirtualAlloc(NULL, 32, MEM_COMMIT | MEM_RESERVE, PAGE_EXECUTE_READWRITE);
    DWORD old;
    memcpy(tramp, (void *)target, stolen);                         /* stolen bytes are position-independent */
    tramp[stolen] = 0xE9;
    *(DWORD *)(tramp + stolen + 1) = target + stolen - ((DWORD)tramp + stolen + 5);
    VirtualProtect((void *)target, stolen, PAGE_EXECUTE_READWRITE, &old);
    *(BYTE *)target = 0xE9;
    *(DWORD *)(target + 1) = (DWORD)detour - (target + 5);
    memset((void *)(target + 5), 0x90, stolen - 5);
    VirtualProtect((void *)target, stolen, old, &old);
    FlushInstructionCache(GetCurrentProcess(), (void *)target, stolen);
    return tramp;
}

static void install_hooks(void)
{
    static const BYTE cf[] = { 0x55, 0x8D, 0xAC, 0x24, 0xFC, 0xFB, 0xFF, 0xFF };          /* push ebp; lea ebp,[esp-404h] */
    static const BYTE pe[] = { 0x55, 0x8B, 0xEC, 0x6A, 0xFF, 0x68 };                        /* push ebp; mov ebp,esp; push -1; push imm32 */
    DWORD cfa = g_base + FN_CALLFUNCTION - EXE_BASE, pea = g_base + FN_PROCESSEVENT - EXE_BASE;
    if (memcmp((void *)cfa, cf, sizeof cf) || memcmp((void *)pea, pe, sizeof pe)) {
        logline("tracer: unexpected prologue bytes, hooks NOT installed");
        return;
    }
    g_origCF = (PFN_CF)hook(cfa, 8, hk_CallFunction);
    g_origPE = (PFN_PE)hook(pea, 10, hk_ProcessEvent);
    logline("tracer: hooks installed");
}

BOOL WINAPI DllMain(HINSTANCE inst, DWORD reason, LPVOID reserved)
{
    (void)reserved;
    if (reason == DLL_PROCESS_ATTACH) {
        char *slash;
        DisableThreadLibraryCalls(inst);
        g_base = (DWORD)GetModuleHandleA(NULL);
        GetModuleFileNameA(inst, g_logPath, MAX_PATH);        /* ...\Binaries\Win32\xinput1_3.dll */
        if ((slash = strrchr(g_logPath, '\\'))) *slash = 0;
        strcpy_s(g_tracePath, MAX_PATH, g_logPath);
        strcpy_s(g_watchPath, MAX_PATH, g_logPath);
        strcat_s(g_logPath, MAX_PATH, "\\..\\..\\CoopMod\\coop_log.txt");
        strcat_s(g_tracePath, MAX_PATH, "\\..\\..\\CoopMod\\coop_trace.txt");
        strcat_s(g_watchPath, MAX_PATH, "\\..\\..\\CoopMod\\coop_watch.txt");
        logline("---- CoopMod xinput proxy loaded ----");
        install_hooks();
        CreateThread(NULL, 0, monitor, NULL, 0, NULL);
    }
    return TRUE;
}
