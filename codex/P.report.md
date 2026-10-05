# P — in-game system overlay

The shared overlay implementation was already present when this task resumed. Reviewed and verified it, then fixed a reproducible concurrent-input race. Only `port/build-p` was configured/built. No game dump, codec source, runtime poll/backoff, other build directory, commit or push changes.

## Root causes and behavior

- SaveData's AppKit modals stole focus and blocked the host UI; message-dialog stubs had no visible UI. SaveData and MsgDialog now share the locked SDK overlay model and CoreText/Metal panels: slot selection/subtitles, save/overwrite/delete confirmation, empty-load notice, OK/Yes-No/error dialogs and one/two progress bars. Native SaveData alert sources are removed.
- Metal composes after the guest frame and before presentation. A separate compositor timer preserves/repaints the last guest image while SaveData blocks its calling guest thread; AppKit continues handling events. Message-dialog Open remains asynchronous, allowing progress updates and deferred completion through `cellSysutilCheckCallback`. Close supports delay; Abort suppresses callbacks.
- Host keyboard/SDL reports drive navigation. D-pad/Cross/Circle and Enter's Start alias are suppressed from guest digital/pressure/directional reports. Dismissal buttons remain suppressed until release. Headless/no-Metal resolution and explicit savedata environment selections remain available.
- This review reproduced an ordering race between SaveData and compositor polling: an older held-Cross snapshot could arrive after release and dismiss the dialog. Polls now use a nonblocking serialization guard; a snapshot is applied only to the dialog token it sampled. The guard never blocks AppKit behind a worker awaiting main-queue input polling.

## Files changed

This pass: `ps3recomp/libs/system/sys_overlay.c`, `ps3recomp/libs/system/tests/test_sys_overlay.c`, `codex/P.host-check.sh`, and this report.

Existing P implementation retained: SDK `libs/system/sys_overlay.{c,h}`, `cellSaveData.c`, `cellMsgDialog.{c,h}`, `libs/input/cellPad.{c,h}`, `libs/video/rsx_metal_overlay.{m,h}`, `rsx_metal_backend.m`, SDK `CMakeLists.txt`, system/input/Metal tests, and P check/save regression scripts. `savedata_macos.{m,h}` are absent. Earlier pre-libpad controller ownership correction remains covered by tests.

## Verification

- `port/runs/P-poll-repro.log:21`: new regression fails before the fix, reproducing accidental completion.
- `port/runs/P-final-tests.log:43–47,59,63–68,83,97`: ASan/UBSan overlay state machine, concurrent polling/replacement, blocking guest/concurrent snapshots, headless resolution, deferred callbacks/results, keyboard/SDL suppression/release, CoreText raster and SaveData adapters pass. `:69` explicitly skips GPU composition because no Metal device is available. Notice raster visually inspected: upright, readable title/message/button hints.
- `port/runs/P-current-savedata.log:15,20,36,45,58,67–75`: unchanged lifted D2 callbacks pass title probe/cancellation, byte-exact save/load, overwrite rollback, autosave and deletion.
- `port/runs/P-final-build.log:8`: native executable links. Operations-guide configuration uses the specified flags and build-p. Shell syntax and SDK whitespace checks pass; no native modal alert calls remain in SaveData/MsgDialog.
- Required 40-second run: `port/runs/P-final-smoke.log:202` records the real title count probe (one existing slot); `:2580` presents frame **1740**. Expected alarm exit **142**, zero guest faults/unresolved NIDs. `:35–38` confirms no Metal device and software fallback. This smoke does not prove visible overlays or Continue navigation.

## Remaining / host check

Run `bash codex/P.host-check.sh` on the real Mac, disconnecting physical pads for deterministic input. It builds only P, requires native event/GPU tests, uses isolated empty saves/cache, requires the title's zero-slot probe, chooses Continue, captures the in-window no-save overlay via `PS3RECOMP_METAL_FRAME_DUMP`, dismisses with Cross, then sends Up/Cross for New Game. Review captures for the story transition; `interactive` supports physical-pad/focus checks. Script uses grep and no rm.

Visible GPU composition and Continue → notice → New Game remain real-host checks. Optional slot icons are omitted. Rebuild/repackage the app after integration.

Prior art: requested reference repositories and [ps3recomp PR #160](https://github.com/sp00nznet/ps3recomp/pull/160), SDK pad/sysutil queues, and [RPCS3 message-dialog ABI/implementation](https://github.com/RPCS3/rpcs3/blob/master/rpcs3/Emu/Cell/Modules/cellMsgDialog.cpp), read via gh.
