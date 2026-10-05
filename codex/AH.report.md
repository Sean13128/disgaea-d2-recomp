# AH — polish pass (D2_GAME_VERSION=140)

## Root causes and changes

- **Overlay ghosting:** the faint text in AF's capture is the live DLC visitor announcement ("Battle Princess … visiting this Netherworld!") beneath the panel. The bitmap is cleared on every raster and page revisions replace the texture; the panel's `.96` alpha lets the guest text through. Made the panel fully opaque; the outside dimming stays translucent. Added full-panel alpha and GPU page/background-change checks.
- **Launcher:** AD already added an entry-OPD check. Added segment-mapped **TOC validation** matching the runner (140: entry `00461000`, TOC `0047DF98`; 100: `003E0EE8`, `003FDE60`). A mismatched configured ELF falls back to the matching project default and the corrected path is persisted. Replaced `execl` with an `NSTask` supervisor: launch errors, nonzero exits and signals show an NSAlert with status, log path and a bounded log tail. Configuration/directory failures also show alerts.
- **AG GPU harness:** line 71 tests a solid-red partial copy with nearest filtering, not the striped RESC captures. The encoder consumed source `7×5` and destination `9×7` clears as one MRT pass, then stopped binding at the size mismatch; the destination clear was lost. Split clear batches at differing target dimensions. Kept the pixel expectations; extended partial-copy coverage to 3× and added RGBA diagnostics. AG2's exact-subpixel RESC/presenter tests remain intact.
- **Portrait automation:** `AH.portrait-check.sh` copies slot-01 saves/cache/settings, warps to battle 101, then uses PAD_FILE and Vision OCR of captured frames to dismiss announcements, deploy Laharl, Move, choose Attack/target and request Execute. It requires three OCR-confirmed ATTACK ENTRY frames, checks four corner patches outside V's `(40,28)..(212,200)` circular mask, and requires the actual FF stencil pass. It rejects missing Metal, navigation failure and runtime faults; it never reports an absent portrait as a pixel pass. Navigation is **not yet verified on real Metal**.

## Files changed

SDK: `libs/video/rsx_metal_overlay.m`, `rsx_metal_backend.m`, `tests/test_metal_overlay.m`. AH-only patch: `patches/AH-polish-runtime.diff` (reverse-apply check passes).

Port: `port/CMakeLists.txt`, `port/src/d2_launcher.m`, `d2_launcher_paths.h.in`, new `d2_launcher_elf.h`.

Checks: modified `codex/AG.metal-test.m`; added `codex/AH.{elf-test.c,launcher-test.m,ocr.m,portrait-drive.py,portrait-check.sh,metal-check.sh}`; `.gitignore` exceptions and this report. Only `port/build-ah` was configured/built. No dump edits, gameplay changes, shared bundle rebuild, commits or pushes.

## Verification (retained logs)

- `AH.configure.log:12`: version 140; `AH.build.log:199`: runner linked; `AH.build-final.log:3`: launcher linked.
- `AH.overlay-before-test.log:1`: old `.96` alpha fails; `AH.overlay-after-test.log:1`: opaque-panel regression PASS.
- `AH.elf-test.log:1`: 100/140, spoofed entry with wrong TOC, truncated ELF PASS. Actual launcher tests (alerts intercepted): `AH.launcher-missing-test.log:8`, `AH.launcher-exit-test.log:23`: 100 config falls back to 140 and both NSAlert paths PASS.
- `AH.engine-test.log:135–145`: existing draw/stencil + AG2 transfer checks PASS; `AH.fifo-test.log:1–6,12`: sync/RESC PASS; `AH.hash-test.log:1`: 67,080 byte mutations PASS; `AH.edat-test.log:217`: 84 EDAT checks PASS.
- Cheat/editor and input regressions PASS: `AH.editor-test.log:16`, `AH.cheat-overlay-test.log:3`, `AH.system-test.log:43–47`, `AH.hotkey-test.log:1` (ASan/UBSan enabled for these checks).
- Requested 1.00 ELF is correctly rejected (`AH.mismatch.log:4`). Matching 40-second run exits at the expected alarm 142: slot 01 LOAD (`AH.battle.log:1916`) and warp 101 (`:2690`).
- `AH.portrait-validator-test.log:1`: the existing **real-Metal broken portrait** is rejected (corner 100% white). Script syntax passes; sandbox check explicitly fails with no Metal (`AH.portrait-sandbox.log:3`). `AH.metal-test.log:1`: GPU harness SKIP, exit 77.

All log paths above are under `port/runs/`.

## Remaining / real Mac commands

Run:

```sh
bash codex/AH.metal-check.sh
AH_SKIP_BUILD=1 bash codex/AH.portrait-check.sh
```

The first verifies the corrected clear/transfer encoder at 1/1.5/2/3× and opaque panel/page composition. The second retains frames, OCR, pad commands and assertion results under `port/runs/AH-portrait.*` (default timeout 180 s, `AH_SECONDS` configurable). No `rm` or `rg` in either shell script.

**GPU pixel correctness and successful automated attack navigation remain unverified here:** the sandbox exposes no Metal device, and Vision OCR also cannot run here. An additional fast blind-Cross probe reproduced AD's documented guest OOB/SIGBUS problem (`AH.battle-rapid.log:2948+`, signal 10); its gameplay cause was left unchanged. The OCR driver aborts on this fault. If the real-host check hits it or fails to reach Attack, use its retained frames/OCR to refine navigation or investigate the existing guest fault; do not count this as a verified portrait fix.

Read PR sp00nznet/ps3recomp#160 and reference-port layout/boot code through gh before implementation. Own disposable sandbox scratch was removed; evidence logs remain.
