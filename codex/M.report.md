# Task M

Implemented all assigned import handlers in the SDK; built only `port/build-m`. No commits/pushes or edits to the game dump, `port/build`, cellPad, cellGcmSys, cellResc, codecs, or save-data sources.

## Root causes and fixes

- The generic NID generator excluded the L10n export names. Added registrations and guest-aware **SJISstoUTF8s (33435818), jstrchk (750C363D), UTF8stoSJISs (DD5EBDEB)**. Conversions use established CP932 codecs (iconv on macOS/POSIX, Win32 codecs on Windows), BE byte lengths, size queries, partial output, and firmware results `0/1/2/3`. Input length remains unchanged. jstrchk detects ASCII/JIS and plausible UTF-8/SJIS/EUC-JP masks; RPCS3's jstrchk is still a placeholder.
- Added the four PRX load variants with resident/pre-lifted module IDs, missing-path/bad-fd/unsupported-format errors; register_library publishes resident guest exports safely to the existing PRX registry. **sys_spu_image_close was already registered** in spu_raw.c: replaced its unconditional success with descriptor/type validation. Its storage remains VM-owned.
- Added offline listen/accept/send/shutdown with socket lifecycle checks, guest errno and no host networking. Fixed errno lookup overwriting the preceding error; preserved PS3_NET_ONLINE.
- Added AioWrite with real writes and worker-thread completion; fixed absolute AIO transfers disturbing the source file position. SdataOpenByFd decrypts an independent view at the supplied source offset and returns real errors. Added deferred error-dialog completion, BE signed tick addition, permanent trophy-handle abortion, Home NOAPP and disc NOTPATCH results.
- Redirected stderr previously enabled verbose logging automatically. Default is now quiet; `PS3RECOMP_TRACE_WAIT=1`, `PS3RECOMP_TRACE_EVENT=1`, `PS3RECOMP_TRACE_HOTREAD=1` enable individual streams; `PS3_VERBOSE=1` enables all. Existing SEMTID, PS3_EVT_RECV, PPU_SPINBT, PPU_HOTMAP and other diagnostic switches remain operative. Errors and bounded milestones remain.
- Fixed the shared C/C++ atomic header incompatibility exposed by the concurrent codec work. C17 and C++20 now use their own atomic APIs with identical memory ordering.

## Files and verification

Check artifacts: `codex/M.check.sh`, `M.imports-test.c`, `M.context-test.cpp`, `M.logging-test.c`, `M.memory-test.c`, `M.coverage.py`; results are in `M.coverage.json` and `M.timings.json`.

Exact SDK file list: [M.files.txt](M.files.txt). Worker-only patch, excluding concurrent workers' hunks: [M-runtime.diff](../patches/M-runtime.diff). No game-specific overrides were needed.

`bash codex/M.check.sh` passes ASan/UBSan tests for Japanese/CP932 conversion and errors, guest endianness, asynchronous write completion, real AIO read/write, encrypted embedded SDATA, PRX registration/load errors, socket errors, RTC aliasing, dialogs, trophy abortion and C/C++ reservation atomics. Evidence: `port/runs/M-check.log:1,13,15–25`; no sanitizer errors. Incremental build passes (`port/runs/M-build.log`, final executable link).

Coverage follows the dashboard's import-table comparison plus runtime context and D2 override registrations: **303/305 imports (99.34%), 24/26 complete libraries (92.31%)**. These totals include concurrent codec/Resc additions. M adds 19 previously unregistered imports and fixes the existing SPU close handler. Remaining: **cellKbRead FF0A21B7** and **_cellGcmFunc15 3A33C1FD**, both excluded from M. Reproduce with `python3 codex/M.coverage.py`; full results: [M.coverage.json](M.coverage.json).

## Logging / CPU

Matched 40-second headless runs of the same final benchmark build:

| Mode | Log bytes / lines | WAIT / evt / HOTREAD | User + system CPU |
|---|---:|---:|---:|
| PS3_VERBOSE=1 | 1,492,992 / 21,288 | 13,785 / 6,932 / 0 | 16.81 + 9.56 = 26.37 s |
| Default | 33,799 / 584 | 0 / 6 / 0 | 16.39 + 8.00 = 24.39 s |

**97.7% less log output; 1.98 CPU seconds saved per 40 seconds (7.5%).** Evidence: `M-final.log:583`, `M-final-trace.log:21287` and [M.timings.json](M.timings.json). Earlier snapshots are retained in that JSON; the concurrent scheduler changes account for much of the larger overall CPU reduction and are not attributed to M. HOTREAD tracing was observed enabled in the earlier matched trace run (54 lines); environment gate tests also cover explicit zero overrides.

## Remaining limits

- cellPad's unconditional SetPortSetting output remains noisy (1,216 cellPad lines in the latest 40-second smoke); PAD_SCRIPT prints require PAD_SCRIPT already and emit configured press milestones. These sources were explicitly excluded.
- Native runtime cannot execute arbitrary, unlifted PRXs; loaders return UNSUPPORTED_PRX_TYPE for those. SDATA uses the existing decoder's supported formats; licensed/compressed EDAT remains unsupported. Write data transfer currently happens during submission, with completion on a worker; AioRead retains the SDK's existing inline completion ordering.
- Headless sandbox has no Metal device. The shared movie path reports VideoToolbox **-12911 / guest vdec 80610105** (`M-final.log:311–313`), then continues presenting frames (`:506,567`); codec/real-host verification belongs to K. No unresolved NIDs appeared in the headless runs. Latest post-test smoke: `port/runs/M.log:1658` reaches frame **1200**, with **zero unresolved NIDs / WAIT / HOTREAD**; `:321` retains the VideoToolbox error. Alarm termination after 40 seconds is expected.

References fetched via gh: [RPCS3 L10n](https://github.com/RPCS3/rpcs3/blob/master/rpcs3/Emu/Cell/Modules/cellL10n.cpp), [RPCS3 filesystem](https://github.com/RPCS3/rpcs3/blob/master/rpcs3/Emu/Cell/Modules/cellFs.cpp), [Twisted Metal](https://github.com/sp00nznet/twistedmetal/blob/main/src/hle_extra.cpp), [macOS PR #160](https://github.com/sp00nznet/ps3recomp/pull/160).
