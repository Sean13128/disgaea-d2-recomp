# Task E — loading race, SPU fault and FIOS cache

**Four final 60-second headless runs completed loading and kept presenting until the alarm. Zero NisGraphics SPU faults; reused HDD1 cache works.** Only `port/build-e` was configured/built. Game dump and other workers’ build directories were untouched. No commits or pushes.

## Root causes and fixes

- **SPU descriptor tearing:** dynamic-size `memcpy` split a 16-byte MFC transfer. NisGraphics saw job type `FFFFFFFF` with ready flag `1`, indexed before its dispatch table and branched to LS zero. `E-diag.log:8923–8929` captures the fault and LS `05100` tuple `00000000 FFFFFFFF 00000001 00000000`. Aligned quadword DMA GET/PUT now uses acquire/release 128-bit host atomics on arm64; bulk transfers retain memcpy.
- **Mutex holder established:** NowLoadingThread (guest tid 23) held cellSync mutex `01FF0CB8` while awaiting graphics work from the dead SPU. `E-lwm.log:8542` records its acquisition, `:8549` the fault, `:8605` main’s unanswered lock; `E-fresh1.log:718` maps that native holder to guest tid 23. RPCS3’s cellSync ticket/endian logic and the lifted barriers were checked. This observed hang did not require changing lwarx/stwcx reservation semantics.
- **POSIX lwmutex exclusion was disabled:** `_WIN32` guards omitted semaphore locking and lwcond release/reacquire on macOS. Enabled the existing portable semaphore implementation, atomically published semaphore slots, and corrected trylock’s EBUSY code.
- **Second, independent FIFO race:** the drain thread’s automatic overflow recovery rewound guest `context->current` while commands were still being produced, losing a closing SET_REFERENCE. After the SPU fix, fresh1/2/3 stalled at 1553/1047/2039 frames; fresh3 requested `18B2` while the final drained reference was `18B1` (`:37626`, `:40091`). Recovery is now opt-in (`GCM_FORCE_RECYCLE=1`); normal recycling stays on the producer’s existing buffer-full callback. The regression fixture deterministically fails with legacy recovery enabled and passes by default.
- **FIOS cache:** stdio buffered the small cache.dat header past completed guest writes; timeout could leave cache.idx valid and cache.dat empty. Host-opened descriptors are now unbuffered. cellFsUnlink was a success-only stub, so corrupt-cache recovery reopened the same files forever; it now performs host unlink, reports errors and rejects the disc mount. Corrected CELL_FS_EIO’s value. `E-cache-corrupt.log:102–107` shows the failed header read, successful removal of both files and recreation, followed by 542 frames in the 20-second recovery probe.

## Changed files

SDK: `runtime/spu/spu_dma.h`, `runtime/ppu/ppu_sysprx.cpp`, `runtime/ppu/ppu_fs.cpp`, `libs/video/cellGcmSys.c`. E-only changes are isolated in `patches/E-runtime.diff` (preserving concurrent F graphics edits). Fixtures: `codex/E.validate.cpp`, `E.dma-validate.c`, `E.validate.py`. All temporary tracing was removed.

## Verification

`E.final-build.log`: successful link. `E-test-final.log:7–11`: mutual exclusion/recursion/busy/timeout/condition release-reacquire, 1M coherent DMA snapshots, producer-pointer/fence preservation, immediate header visibility and unlink/ENOENT all PASS. `E-test-legacy-recycle.log:5` reproduces the old pointer-reset assertion failure. SDK `git diff --check` passes.

All final runs used the requested VFS/HDD0/alarm command, `PS3RECOMP_METAL_HEADLESS=1`, `D2_BOOT_TRACE=1`, and private HDD1 directories. Frame counts are the last periodic **55-second presented-frame sample**; late flip counts are separately logged requests, rounded down to the last multiple of ten. All processes exited 142 from the 60-second alarm.

| Log and frame-count line | HDD1 | Presented @55s | Last late flip request | End |
|---|---|---:|---:|---|
| E-fresh4.log:36055 | fresh | 2470 | not enabled | alarm; still presenting |
| E-fresh5.log:36046 | fresh | 2489 | 2700 | alarm; still presenting |
| E-fresh6.log:36023 | fresh | 2485 | 2720 | alarm; still presenting |
| E-reuse4.log:36141 | reused fresh4 | 2557 | 2790 | alarm; still presenting |

All four finish loading through `ITEMSYMBOL.dat`; NowLoadingThread exits normally. `E-reuse4.log:102` explicitly says **Reusing existing disk-based cache files**. None logs an SPU FAULT or stalled frame counter. Earlier diagnostic runs: baseline 1181, diag 407, lwmutex-only 337 (SPU fault); DMA-only 858 (later FIFO fence stall); fresh1/2/3 1553/1047/2039 (same FIFO stall). Corrupt-cache probe was 20s; all others 60s.

## Remaining

This sandbox has no Metal device (`E-fresh5.log:74–95`); results use the software presentation fallback. Real Metal pixels/title screen/gameplay still need host verification with E+F combined. Intro PAMF imports `CA8181C1`/`44F5C9E3` and cellRescSetWaitFlip `0D3C22CE` remain unresolved (`E-fresh5.log:282–312,390`). Final snapshots may catch a normal short GCM fence wait, but presentation counters continue advancing.

Prior art read via gh: RPCS3 `SPUThread.cpp` quadword DMA and `cellSync.h/.cpp` ticket semantics; sp00nznet/ps3recomp PR #160 and Twisted Metal layout. Own disposable caches/reference downloads were removed after verification.
