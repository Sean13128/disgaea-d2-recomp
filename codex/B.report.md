# Task B — SPU lift and execution

## Root causes and changes

- The port shipped no SPU lifts/registry. Added `port/spu/images/{NisGraphics.spu,synth2}.elf`, each image's `spu_recomp.c/.h`, generated `port/spu/spu_workloads.c`, and `port/spu/README.md` with regeneration commands. Existing CMake `SPU_DIR` picks them up; no CMake/stub edits needed.
- SDK `runtime/spu/spu_dma.h` halted every SPU after 256 repeated DMA transfers. NisGraphics legitimately DMA-polls a PPU-owned command buffer, so all six workers died immediately after starting. Made `SPU_DMA_REPEAT_LIMIT` opt-in (unset/zero disables), with thread-local counters reset when the executing context changes. No title-specific override.
- Both images use the SDK extractor/lifter/workload builder. Full-ELF fingerprints: NisGraphics `0x9E876934B7F179D6`, synth2 `0x5009AA16A26A8923`; executable-segment fingerprints are also registered. 152 NisGraphics functions, 560 synth2 functions.

## Verification

- Configured/build only `port/build-b`, using the OPERATIONS.md flags from the `port` directory. `port/runs/B.configure.log` reports `Lifted SPU: 2 image(s)`; `port/runs/B.build.log` records successful native executable linking. Pipeline output is in `port/runs/B.lift.log`.
- First 40-second run, `port/runs/B.log`: line 123 reports `image_import src=0x003C1300 len=20116 entry=0x000D0 fp=0x9E876934B7F179D6 -> lifted entry registered`; line 139 reports `6 host threads running, 0 instant`. Lines 340–341 show the newly exposed `256 identical transfers ... halting the SPU` and `FAULT` (the other five workers fail the same way).
- After the SDK fix, 40-second run with `PS3RECOMP_METAL_HEADLESS=1 SPU_MFC_TRACE=2 SPU_MBOXTRACE=1`, `port/runs/B.headless.log`: line 127 confirms the same fingerprint matches, line 143 reports `6 host threads running, 0 instant`, and lines 146/148/151/155/156/1116 show tids `0x2000`–`0x2005` `RUNNING lifted image entry=0x000D0 (image 1)`.
- Lines 1310–1316 show all six pass 65,536 DMA transfers: `img=1 pc=0x03C58 cmd=0x40 lsa=0x05100 ea=0x020E1F10..0x020E1F60 size=16`. Final sampled counts per descriptor are 80–96 million GETs. No stopped/faulted SPU, unknown image, or unsupported-instruction execution diagnostics in this run. Timeout exit 142 is expected from the requested alarm wrapper.
- No mailbox writes or DMA PUTs observed. The lifted main loop at LS 0x16E8 fetches its descriptor, tests word +8, and repeats while it is zero. This is a memory/DMA command protocol at this stage, rather than a mailbox handshake. Threads remain alive waiting for PPU work.

## Remaining

- The sandbox reports `[RSX metal] no Metal device available` even with headless requested (`B.headless.log:64`); the PPU remains stalled elsewhere, so graphics task output and rendering are not yet verified.
- synth2 is lifted, linked, and registered, but the game did not import/start it during these runs. Eight synth2 `.word` lift warnings are float constants in a data table near LS 0x9400/0x94A0; actual audio execution remains unverified.
- These are six ordinary LV2 SPU group threads (non-SPURS), executed on native host threads through `spu_lifted_thread_run`. No hardware MMIO `sys_raw_spu_create` threads were created.
- Game dump, `port/build`, and other workers' build trees were untouched. No commits or pushes. Other workers' existing/concurrent SDK changes were not altered.
