/*
 * ps3recomp game project -- entry point template.
 *
 * This is the runner. It boots a lifted title through the toolkit's PPU
 * scaffold: allocate the flat guest VM, load the PPU ELF named on the command
 * line, register the lifted function table and the HLE NID handlers, start a
 * frame clock, and dispatch the entry OPD.
 *
 * The scaffold does the work; nothing below reimplements it. ppu_load_elf,
 * ppu_recomp_register, ppu_hle_init, ppu_sysprx_register, ppu_fs_register,
 * lv2_init_syscalls and ppu_run all come from the toolkit, compiled into this
 * project from PS3RECOMP_DIR (see CMakeLists.txt). What is left here is the
 * part a port owns: which backend to present through, how the frame clock is
 * paced, and whatever diagnostics the title turns out to need.
 *
 * runtime/ppu/tests/boot_main.cpp in the toolkit is the same boot in its
 * fully-instrumented form -- crash filter, hang watchdog, guest-PC sampling
 * profiler. Read it when a boot goes wrong; copy from it what the title
 * needs. It is deliberately not what a fresh project starts with.
 *
 * The one part that IS duplicated from it is the frame clock below, because a
 * port is expected to change its pacing and a shared one would be the wrong
 * shape for that. It was copied faithfully, comments and all. If a pacing bug
 * is fixed in one of the two, look at the other.
 *
 * This builds on Windows, macOS and Linux. CI builds and runs it against the
 * boot smoke title on the last two, and compile-checks it against clang-cl on
 * the first (tools/check_ppu_scaffold.py).
 */

/* The lifter's generated header, which declares ppu_context and the function
 * table. It comes first: everything below is written against that struct. */
#include "ppu_recomp.h"

/* The Win32 names -- Sleep, GetTickCount64, CreateThread, InterlockedIncrement,
 * VirtualAlloc, the scalar typedefs -- from one place. On Windows this is a
 * passthrough to <windows.h>; off Windows the toolkit's shim supplies the same
 * names over pthreads and mmap, so the call sites below are written once. */
#include "win32_compat.h"
#include "guest_poll.h"
#include "vm.h"

#include <stdint.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <atomic>
#ifdef __APPLE__
#include <CoreFoundation/CoreFoundation.h>
#include "sys_overlay.h"
#endif

#ifdef _WIN32
/* timeBeginPeriod: <windows.h> arrives with WIN32_LEAN_AND_MEAN set, which
 * excludes the multimedia timer API, so it is asked for by name -- and after
 * windows.h, since timeapi.h uses UINT. No shim exists off Windows because
 * there is nothing to shim: the 15.6 ms default timer granularity this works
 * around is a Windows problem. */
#include <timeapi.h>
#endif

/* ---------------------------------------------------------------------------
 * What the scaffold gives this file
 * -----------------------------------------------------------------------*/
extern "C" {
uint32_t ppu_load_elf(const char* path);      /* ELF -> guest RAM, returns entry OPD */
void     ppu_recomp_register(void);           /* generated: lifted table -> address map */
void     ppu_hle_init(void);                  /* firmware import NID -> HLE handler */
void     ppu_sysprx_register(void);           /* boot-critical CRT (sys_initialize_tls, ...) */
void     ppu_fs_register(void);               /* cellFs over the real game directory */
void     lv2_init_syscalls(void);             /* the lv2 syscall table */
int      ppu_run(uint32_t entry_opd, uint32_t stack_top);

/* This project's own: load whatever real system PRX modules the title needs
 * into guest RAM and register their exports. stubs.cpp has the empty version
 * a game with no lifted PRX wants. */
void     ps3_load_prx_modules(void);

extern const char* ppu_vfs_root;              /* host dir the PS3 mount points map into */

/* The status the guest handed to sys_process_exit. A title that exits that way
 * never returns through ppu_run, so this is only read on the path where the
 * entry function unwound instead. */
extern int     g_sys_process_exit_called;
extern int32_t g_sys_process_exit_code;
int32_t cellSaveDataHostRecover(void);

/* Host-provided symbols the runtime and the HLE libraries link against. */
uint8_t* vm_base = nullptr;
extern uint32_t ppu_vm_size;                  /* ppu_loader.cpp: the OOB guard */

/* Guest-callback dispatch. g_ps3_guest_caller is the hook the HLE runtime
 * calls back into recompiled code through -- cellSysutil events and the GCM
 * vblank/flip handlers. ppu_guest_call does the OPD -> dispatch. */
typedef void (*ps3_guest_caller_fn)(uint32_t, uint64_t, uint64_t, uint64_t, uint64_t,
                                    uint64_t, uint64_t, uint64_t, uint64_t);
extern ps3_guest_caller_fn g_ps3_guest_caller;
uint64_t ppu_guest_call(uint32_t, uint64_t, uint64_t, uint64_t, uint64_t,
                        uint64_t, uint64_t, uint64_t, uint64_t);

/* The GCM half of the frame clock. */
void     rsx_set_backend(struct rsx_backend*);
void     cellGcmTickVBlank(void);
void     cellGcmTickFlip(void);
unsigned cellGcm_vblank_wait_ms(void);
uint64_t cellGcmGetVBlankCount(void);
uint32_t cellGcm_flip_mode(void);
uint32_t cellGcmGetCurrentDisplayBufferId(void);
void     cellGcm_fifo_kick_wait(unsigned ms);
int      cellGcm_take_flip_pending(void);
void     cellGcm_fifo_enable_snapshot(void);
void     cellGcm_rsx_process_fifo(void);      /* drain get -> put */
unsigned cellGcm_flip_request_count(void);
}

/* ---------------------------------------------------------------------------
 * RSX present backend
 * -----------------------------------------------------------------------*/
/* D3D12 on Windows, Metal on Apple, and the null backend's headless software
 * path anywhere else -- the same selection runtime/host/host_posix.c and the
 * toolkit's boot harness make. All three expose the same three entry points,
 * so the frame clock below is backend-agnostic. */
#if defined(_WIN32)
extern "C" int  rsx_d3d12_backend_init(uint32_t w, uint32_t h, const char* title);
extern "C" void rsx_d3d12_backend_present(void);
extern "C" int  rsx_d3d12_backend_pump_messages(void);
#  define rsx_backend_init    rsx_d3d12_backend_init
#  define rsx_backend_present rsx_d3d12_backend_present
#  define rsx_backend_pump    rsx_d3d12_backend_pump_messages
#  define RSX_BACKEND_NAME    "D3D12"
#elif defined(__APPLE__)
extern "C" int  rsx_metal_backend_init(uint32_t w, uint32_t h, const char* title);
extern "C" void rsx_metal_backend_present(void);
extern "C" int rsx_metal_backend_submission_ok(void);
extern "C" void rsx_metal_backend_set_vsync(int enabled);
extern "C" void rsx_metal_backend_set_flip_buffer(uint32_t buffer);
extern "C" int  rsx_metal_backend_pump_messages(void);
#  define rsx_backend_init    rsx_metal_backend_init
#  define rsx_backend_present rsx_metal_backend_present
#  define rsx_backend_pump    rsx_metal_backend_pump_messages
#  define RSX_BACKEND_NAME    "Metal"
#else
extern "C" int  rsx_null_backend_init(uint32_t w, uint32_t h, const char* title);
extern "C" void rsx_null_backend_present(void);
extern "C" int  rsx_null_backend_pump_messages(void);
#  define rsx_backend_init    rsx_null_backend_init
#  define rsx_backend_present rsx_null_backend_present
#  define rsx_backend_pump    rsx_null_backend_pump_messages
#  define RSX_BACKEND_NAME    "null (headless software)"
#endif

/* If Metal is unavailable (including in a sandbox), keep draining the FIFO
 * through the existing software backend so guest fences can still complete. */
#ifdef __APPLE__
extern "C" int  rsx_null_backend_init(uint32_t w, uint32_t h, const char* title);
extern "C" void rsx_null_backend_present(void);
extern "C" int  rsx_null_backend_pump_messages(void);
#endif
static void (*s_backend_present)(void) = rsx_backend_present;
static int  (*s_backend_pump)(void) = rsx_backend_pump;

/* ---------------------------------------------------------------------------
 * Configuration
 * -----------------------------------------------------------------------*/
/* The flat VM must span every region the PS3 memory map uses, not just the
 * game image: sys_ppu_thread_create puts thread stacks at 0xD0000000, so a
 * smaller arena makes every spawned thread's stack access out of bounds. */
#define VM_SIZE       0x100010000ull   /* the full 32-bit guest space + a 64K guard */
#define STACK_TOP     0x0FF00000u      /* main-thread stack, below the 0x10000000 segment */
#define WINDOW_WIDTH  1280
#define WINDOW_HEIGHT 720

/* ---------------------------------------------------------------------------
 * Frame clock
 * -----------------------------------------------------------------------*/
/* On real hardware the RSX raises a vblank interrupt about 60 times a second
 * and that is what drives the game's frame loop. With no RSX it is synthesized
 * here: a host thread calls cellGcmTickVBlank/TickFlip, which invoke the
 * handlers the guest registered, and drains the GCM FIFO. Without this the
 * title initialises, registers its handlers and then waits forever.
 *
 * The ticks are driven off real elapsed time rather than off how long present()
 * took. A hidden or occluded window makes present block hard, and pacing the
 * ticks behind it paces the whole game behind it. */
static std::atomic<bool> s_stop_requested{false};
static std::atomic<bool> s_frame_stopping{false};
static std::atomic<int> s_stop_failure{0};
extern "C" void ps3_host_request_stop(void)
{
    if (!s_stop_requested.exchange(true)) fprintf(stderr, "[shutdown] stop requested\n");
}
#ifdef __APPLE__
extern "C" int cellSaveDataHostRequestStop(void);
extern "C" void ps3_guest_workers_request_stop(void);
extern "C" int ps3_guest_workers_stopped(void);
extern "C" void ps3_guest_workers_join(void);
extern "C" void d2_settings_flush(void);
extern "C" int32_t cellAudioQuit(void);
extern "C" void rsx_metal_backend_shutdown(void);
extern "C" void rsx_null_backend_shutdown(void);
#endif

static volatile LONG g_frames_presented = 0;

/* Frames handed to the backend at a guest FLIP boundary -- one per frame the
 * guest actually finished. The presents made before the guest's first flip, so
 * a fresh window is not left blank through a long boot, carry no guest frame
 * and are deliberately not counted. */
extern "C" unsigned ppu_boot_frames_presented(void)
{
    return (unsigned)g_frames_presented;
}

static int present_guest_frame(void)
{
#ifdef __APPLE__
    rsx_metal_backend_set_flip_buffer(cellGcmGetCurrentDisplayBufferId());
    rsx_metal_backend_set_vsync(cellGcm_flip_mode() == 2); /* DISPLAY_VSYNC */
#endif
    s_backend_present();
#ifdef __APPLE__
    if (!rsx_metal_backend_submission_ok()) return 0;
#endif
    /* This thread increments and guest threads read, so interlocked rather
     * than a volatile ++, which on arm64 is neither atomic nor a fence. */
    LONG frame = InterlockedIncrement(&g_frames_presented);
    if (frame <= 3 || frame % 60 == 0)
        fprintf(stderr, "[rsx] presented guest frame %ld\n", (long)frame);
    return 1;
}

extern "C" void d2_install_shader_trace(void);
extern "C" int d2_install_draw_trace(void);
extern "C" void rsx_draw_engine_present(void);
extern "C" void ppu_report_guest_lrs(void);

static DWORD WINAPI frame_clock(LPVOID)
{
    ps3_poll_thread_start("RSX render", 1);
    cellGcm_fifo_enable_snapshot();
    const char* title = getenv("PS3_TITLE");
    if (!title || !*title) title = "ps3recomp";

    int rsx_ok = (rsx_backend_init(WINDOW_WIDTH, WINDOW_HEIGHT, title) == 0);
    fprintf(stderr, "[rsx] %s backend init %s\n", RSX_BACKEND_NAME,
            rsx_ok ? "OK -- window open" : "FAILED");
#ifdef __APPLE__
    if (!rsx_ok) {
        rsx_ok = (rsx_null_backend_init(WINDOW_WIDTH, WINDOW_HEIGHT, title) == 0);
        if (rsx_ok) {
            s_backend_present = rsx_null_backend_present;
            s_backend_pump = rsx_null_backend_pump_messages;
        }
        fprintf(stderr, "[rsx] software fallback init %s (no Metal presentation)\n",
                rsx_ok ? "OK" : "FAILED");
        if (rsx_ok && getenv("PS3RECOMP_RSX_FIFO_ONLY")) {
            rsx_set_backend(nullptr);
            fprintf(stderr, "[rsx] FIFO timing only: software drawing disabled\n");
        }
    }
#endif

    if (!rsx_ok) { s_stop_failure = 1; ps3_host_request_stop(); }
    if (d2_install_draw_trace())
        s_backend_present = rsx_draw_engine_present;
    d2_install_shader_trace();

    uint64_t previous_vblank = cellGcmGetVBlankCount();
    ULONGLONG next_report = GetTickCount64() + 5000;
    const int boot_trace = getenv("D2_BOOT_TRACE") != nullptr;

    while (!s_frame_stopping.load()) {
        /* A kick drains immediately. VSYNC readiness is enforced by GCM,
         * using the same clock as its counters; HSYNC need not await vblank. */
        cellGcm_fifo_kick_wait(cellGcm_vblank_wait_ms());
        cellGcmTickVBlank();
        uint64_t vblank = cellGcmGetVBlankCount();
        ULONGLONG now = GetTickCount64();
        if (boot_trace && now >= next_report) {
            fprintf(stderr, "[d2-boot] frames=%u flip_requests=%u\n",
                    ppu_boot_frames_presented(), cellGcm_flip_request_count());
            ppu_report_guest_lrs();
            next_report = now + 5000;
        }
        /* Hold the batch until its scheduled refresh, submit it, then wake
         * the producer. Missed refreshes advance counters without bursts. */
        if (rsx_ok && cellGcm_take_flip_pending()) {
            if (present_guest_frame()) cellGcmTickFlip();
            else { fprintf(stderr, "[rsx] guest submission failed\n"); s_stop_failure = 1; ps3_host_request_stop(); break; }
        } else if (rsx_ok && vblank != previous_vblank && cellGcm_flip_request_count() == 0) {
            s_backend_present();
        }
        previous_vblank = vblank;
        if (rsx_ok) {
            cellGcm_rsx_process_fifo();
            if (s_backend_pump() != 0) ps3_host_request_stop();
        }
    }
    return 0;
}

/* ---------------------------------------------------------------------------
 * VFS root
 * -----------------------------------------------------------------------*/
/* Derive the directory holding PS3_GAME from the EBOOT path
 * <root>/PS3_GAME/USRDIR/EBOOT.elf -> <root>. $PS3_VFS_ROOT overrides. */
static char s_vfs_root[1024];

static void derive_vfs_root(const char* eboot)
{
    const char* env = getenv("PS3_VFS_ROOT");
    if (env && *env) { ppu_vfs_root = env; return; }

    strncpy(s_vfs_root, eboot, sizeof s_vfs_root - 1);
    for (char* p = s_vfs_root; *p; p++) if (*p == '\\') *p = '/';
    /* strip EBOOT.elf, USRDIR and PS3_GAME */
    for (int i = 0; i < 3; i++) { char* s = strrchr(s_vfs_root, '/'); if (s) *s = 0; }
    if (!s_vfs_root[0]) strcpy(s_vfs_root, ".");
    ppu_vfs_root = s_vfs_root;
}

/* ---------------------------------------------------------------------------
 * Guest VM
 * -----------------------------------------------------------------------*/
#ifdef _WIN32
/* Demand-paging for the flat VM: reserve the whole 4 GB guest space, which
 * costs no commit, and commit each 64 KB page on first access. Every 32-bit
 * guest offset is then valid, so a garbage guest pointer reads zero instead of
 * killing the process. Faults outside the arena fall through untouched. */
static LONG WINAPI vm_commit_veh(EXCEPTION_POINTERS* ep)
{
    if (ep->ExceptionRecord->ExceptionCode == EXCEPTION_ACCESS_VIOLATION) {
        ULONG_PTR fault = ep->ExceptionRecord->ExceptionInformation[1];
        uintptr_t base  = (uintptr_t)vm_base;
        if (vm_base && fault >= base && fault < base + VM_SIZE) {
            void* page = (void*)(fault & ~(uintptr_t)0xFFFF);
            if (VirtualAlloc(page, 0x10000, MEM_COMMIT, PAGE_READWRITE))
                return EXCEPTION_CONTINUE_EXECUTION;
        }
    }
    return EXCEPTION_CONTINUE_SEARCH;
}
#endif

static bool alloc_guest_vm(void)
{
#ifdef _WIN32
    AddVectoredExceptionHandler(1, vm_commit_veh);
    vm_base = (uint8_t*)VirtualAlloc(NULL, VM_SIZE, MEM_RESERVE, PAGE_READWRITE);
    ppu_vm_size = 0;              /* the whole space is backed; no OOB guard needed */
#else
    /* Use the SDK's aligned mapping: calloc (especially ASan's allocator)
     * need not return a page-aligned base, so later vm_commit/mprotect fails.
     * Preserve the runner's readable arena and bounds below 0xE0000000. */
    if (vm_init() != CELL_OK || vm_commit(0, 0xE0000000u) != CELL_OK)
        return false;
    ppu_vm_size = 0xE0000000u;
#endif
    return vm_base != nullptr;
}

/* ---------------------------------------------------------------------------
 * Main
 * -----------------------------------------------------------------------*/
static void harness_guest_caller(uint32_t opd, uint64_t a0, uint64_t a1,
                                 uint64_t a2, uint64_t a3, uint64_t a4,
                                 uint64_t a5, uint64_t a6, uint64_t a7)
{
    ppu_guest_call(opd, a0, a1, a2, a3, a4, a5, a6, a7);
}

#ifdef __APPLE__
extern "C" void d2_settings_init(void);
extern "C" int d2_settings_self_test(void);
#endif

int main(int argc, char** argv)
{
#ifdef __APPLE__
    if (argc == 2 && strcmp(argv[1], "--settings-test") == 0) return d2_settings_self_test();
    d2_settings_init();
#endif
    if (argc < 2) {
        printf("usage: %s <PPU ELF>\n", argv[0]);
        return 2;
    }

#ifdef _WIN32
#pragma comment(lib, "winmm.lib")
    /* 1 ms timer resolution. The default granularity is about 15.6 ms, which
     * inflates every shorter wait the title makes and throttles the whole
     * thing. POSIX timers are already fine-grained. */
    timeBeginPeriod(1);
    setvbuf(stdout, NULL, _IONBF, 0);   /* unbuffered: do not lose prints on a kill */
#endif

    printf("=== ps3recomp game runner ===\n");

    if (!alloc_guest_vm()) {
        fprintf(stderr, "ERROR: could not allocate the guest address space\n");
        return 1;
    }

    uint32_t entry = ppu_load_elf(argv[1]);
    if (!entry) {
        fprintf(stderr, "ERROR: could not load %s\n", argv[1]);
        return 1;
    }

    const uint32_t expected_entry = D2_GAME_VERSION == 140 ? 0x461000u : 0x3E0EE8u;
    const uint32_t expected_toc = D2_GAME_VERSION == 140 ? 0x47DF98u : 0x3FDE60u;
    if (entry != expected_entry || vm_read32(entry + 4) != expected_toc) {
        fprintf(stderr, "ERROR: this build requires D2 version %d (%s)\n",
                D2_GAME_VERSION, D2_GAME_VERSION == 140 ? "work/v140/EBOOT.elf" : "work/EBOOT.elf");
        return 1;
    }

    if (cellSaveDataHostRecover() != 0) {
        fprintf(stderr, "ERROR: savedata recovery failed; preserved transaction needs retry\n");
        return 1;
    }

    derive_vfs_root(argv[1]);
    printf("[boot] VFS root: %s\n", ppu_vfs_root);

    ppu_recomp_register();   /* lifted function table -> address map */
    ps3_load_prx_modules();  /* this game's lifted system PRX, if it has any */
    ppu_hle_init();          /* firmware import NID -> HLE handlers */
    ppu_sysprx_register();   /* boot-critical CRT */
    ppu_fs_register();       /* cellFs over the game directory */
    lv2_init_syscalls();     /* the lv2 syscall table */

    /* Install the guest-callback hook, then start the frame clock. It no-ops
     * until the title registers its vblank and flip handlers during init. */
    g_ps3_guest_caller = harness_guest_caller;
    HANDLE frame_thread = CreateThread(NULL, 4u * 1024 * 1024, frame_clock, NULL, 0, NULL);
    if (!frame_thread) { fprintf(stderr, "[boot] frame thread creation failed\n"); return 1; }

    printf("\n[boot] dispatching entry OPD 0x%08X (stack top 0x%08X)\n\n",
           entry, STACK_TOP);

#ifdef __APPLE__
    /* Own the guest entry worker here so a stop can join it without changing
     * ppu_run's loader/dispatch semantics. Main continues servicing AppKit. */
    struct GuestRun {
        uint32_t entry;
        int rc = 0;
        std::atomic<bool> done{false};
    } run{entry};
    pthread_t guest_thread;
    pthread_attr_t attr;
    pthread_attr_init(&attr); pthread_attr_setstacksize(&attr, 16u * 1024 * 1024);
    int error = pthread_create(&guest_thread, &attr, [](void* arg) -> void* {
        auto* r = static_cast<GuestRun*>(arg);
        pthread_cleanup_push([](void* arg) {
            auto* r = static_cast<GuestRun*>(arg);
            r->done.store(true); CFRunLoopWakeUp(CFRunLoopGetMain());
        }, arg);
        r->rc = ppu_run(r->entry, STACK_TOP);
        pthread_cleanup_pop(1);
        return nullptr;
    }, &run);
    pthread_attr_destroy(&attr);
    if (error) {
        s_frame_stopping = true;
        while (WaitForSingleObject(frame_thread, 0) != WAIT_OBJECT_0)
            CFRunLoopRunInMode(kCFRunLoopDefaultMode, 0.01, false);
        CloseHandle(frame_thread);
        fprintf(stderr, "[boot] guest thread creation failed: %s\n", strerror(error)); return 1;
    }
    bool stopping = false;
    ULONGLONG start = GetTickCount64();
    const char* stop_after = getenv("D2_STOP_AFTER_SECONDS");
    while (!run.done.load() || !stopping || !ps3_guest_workers_stopped()) {
        if (run.done.load()) ps3_host_request_stop();
        if (stop_after && GetTickCount64() - start >= (ULONGLONG)(atof(stop_after) * 1000))
            ps3_host_request_stop();
        if (s_stop_requested && !stopping) {
            /* Cancel only the dialog, never the save's commit. Admission closes
             * atomically; rendering/callbacks continue until the operation ends. */
            auto* overlay = new SysOverlaySnapshot;
            ps3_overlay_snapshot(overlay);
            if (overlay->active) ps3_overlay_finish(overlay->token, SYS_OVERLAY_BACK);
            delete overlay;
            if (cellSaveDataHostRequestStop()) {
                fprintf(stderr, "[shutdown] savedata quiescent; stopping guest workers\n");
                s_frame_stopping = true;
                while (WaitForSingleObject(frame_thread, 0) != WAIT_OBJECT_0)
                    CFRunLoopRunInMode(kCFRunLoopDefaultMode, 0.01, false);
                stopping = true; ps3_guest_workers_request_stop();
                pthread_cancel(guest_thread);
            }
        }
        if (CFRunLoopRunInMode(kCFRunLoopDefaultMode, 0.01, false) == kCFRunLoopRunFinished) Sleep(1);
    }
    pthread_join(guest_thread, nullptr);
    ps3_guest_workers_join();
    while (WaitForSingleObject(frame_thread, 0) != WAIT_OBJECT_0)
        CFRunLoopRunInMode(kCFRunLoopDefaultMode, 0.01, false);
    CloseHandle(frame_thread);
    d2_settings_flush(); cellAudioQuit();
    rsx_metal_backend_shutdown(); rsx_null_backend_shutdown();
    fprintf(stderr, "[shutdown] guest workers and frame thread stopped\n");
    int rc = run.rc ? run.rc : s_stop_failure.load();
#else
    int rc = ppu_run(entry, STACK_TOP);
    s_frame_stopping = true;
    WaitForSingleObject(frame_thread, INFINITE); CloseHandle(frame_thread);
#endif
    printf("\n[boot] ppu_run returned %d (entry function unwound)\n", rc);

    /* A title that called sys_process_exit never reaches this line: that path
     * ends in the host exit(). Getting here means the entry function returned
     * instead, so hand back the status the guest published if it published
     * one. Returning a hardcoded 0 would report success for a run that never
     * got anywhere. */
    return g_sys_process_exit_called ? (int)g_sys_process_exit_code : (rc != 0 ? 1 : 0);
}
