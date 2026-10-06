
# Task AW — heat fix A: bounded adaptive poll-backoff timeout (yourname = AW, build dir port/build-aw)

Read codex/AV.report.md first (finding 1 and "Recommended order" step 1). Baseline data/binaries: /Volumes/Data/ai-tmp/claude/d2-heat (baseline-DisgaeaD2Recomp = current port/build).
Other context: the game generates ~71k timer wakeups/s in the hub, mostly 7 threads (6 NisGraphicsSpu_Group in mfc_poll and "RSX submit" gcm_put_watch) sitting in ps3_poll_backoff's fixed 100 us timed wait (ps3recomp/runtime/platform/guest_poll.c:~146-180). Goal: cut those wakeups without latency/liveness regressions.

## Do
1. In ps3_poll_backoff, replace the fixed 100 us timeout with a per-thread adaptive one for idle-graphics poll roles only:
   100 -> 200 -> 400 -> 800 -> 1000 us cap, growing only on an actual timeout with unchanged bytes; reset when the polled value changes or a new poll sequence starts (TLS keyed by ea/size/snapshot as AV describes; do not use caller `repeats`, it saturates). Do not reset on mere bucket broadcast / spurious wake.
   Keep 100 us for every other caller (PPU hot-read polls in ppu_loader.cpp, cellSync, GCM label waits in cellGcmSys.c ~2883, anything audio-related). Choose the role via an explicit parameter/variant at the call site (mfc_poll in runtime/spu/spu_dma.h and gcm_put_watch in libs/video/cellGcmSys.c ~1770) rather than name matching. Keep register-then-recheck, caller rereads, cancellation, and PS3_POLL_BACKOFF=0 behaviour.
   Env override for experiments: PS3_POLL_IDLE_CAP_US (default 1000; 100 = old behaviour).
2. Add cheap env-gated counters (PS3_POLL_STATS=1): per-thread name, timeouts vs notified returns, current cap; print a summary every ~10 s. No per-wake logging.
3. Tests: extend runtime/platform/tests/test_guest_poll*.c — notified publication returns well before the cap; un-notified publication completes within cap + tolerance; reset on change; hash-collision bucket; cross-line value; cancellation. Run the existing SPU DMA/coherency and full ctest in build-aw.
4. Headless measurement (PS3RECOMP_METAL_HEADLESS=1 if Metal unavailable), same save/hub route for baseline binary and yours, scratch hdd0 copies (never port/hdd0 directly for runs that write saves): copy port/hdd0 to a scratch dir under /Volumes/Data/ai-tmp/codex/, env:
   SDL_AUDIODRIVER=dummy D2_MOVIE_SKIP=1 PS3_SAVEDATA_UI=headless PS3_SAVEDATA_DIR=NPUB31321_NORMAL_00 PAD_SCRIPT='10:0x4000,14:0x4000,18:0x4000' GCM_FLIP_TRACE=1, ELF work/v140/EBOOT.elf, 90 s; after 45 s run `top -l 16 -s 2 -pid <pid> -stats pid,cpu,csw,idlew,th` and report csw/s and idlew/s from cumulative deltas, CPU%, and distinct flips/s + worst flip interval from the gcm-flip retire lines (see codex/AM.host-check.sh python for parsing). Also PS3_POLL_STATS output.
5. Write codex/AW.host-check.sh: same comparison on real Metal (baseline vs port/build-aw binary) for Claude to run outside the sandbox.
6. Export the SDK diff to patches/AW-runtime.diff. Do not commit.

Report: wakeup/csw before/after, fps + worst frame, test results, any caller you deliberately left at 100 us and why.
