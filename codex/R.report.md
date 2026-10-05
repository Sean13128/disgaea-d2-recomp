# R — second-boot installed game-data error

Fixed in the SDK; no commits/pushes. Only `port/build-r` was built. Dump, codecs, pad, RSX and overlay sources were untouched.

## Root causes / behavior

`cellGameDataCheck` considered any directory installed; `ContentPermit` manufactured an empty directory without PARAM.SFO. `CreateGameData` ignored guest initialization params, and setters/getters used boot-global strings without persistence.

**Firmware correction:** after NONE, ContentPermit returns empty paths unless the guest actually creates data. D2 imports no CreateGameData or SetParamString; writing a default SFO at this point would falsely advertise an installation whose files do not exist. D2 now repeatedly sees NONE for legacy empty directories and boots normally, without deleting their contents.

Explicit creation consumes `CellGameSetInitParams`, writes binary GD metadata using the existing SaveData PSF writer, applies supported localized-title updates, and publishes at Permit. Fresh installs stage/rename the directory; legacy orphans retain their files and receive an atomic SFO update. Existing valid metadata supplies stored strings/integers and preserves unknown entries. Free space is volume-derived; DataCheck sizeKB is 0/NONE or -1/not calculated, sysSizeKB=0 (RPCS3 convention); BootCheck system overhead is 4 KB; GetSizeKB sums each regular file rounded to KB. Shared metadata operations are serialized. Host paths no longer inherit the 128-byte guest-path limit.

References: [RPCS3 implementation](https://github.com/RPCS3/rpcs3/blob/master/rpcs3/Emu/Cell/Modules/cellGame.cpp), [ABI/constants](https://github.com/RPCS3/rpcs3/blob/master/rpcs3/Emu/Cell/Modules/cellGame.h). Reviewed via `gh`, along with the requested Twisted Metal tree and ps3recomp PR #160.

## D2 audit / error path

Only five cellGame imports: BootCheck (`0x390758`), DataCheck (`0x390738`), ContentPermit (`0x3906F8`), GetParamString (`0x3906D8`), PatchCheck (`0x390718`). No GetParamInt, GetSizeKB, DeleteGameData, CreateGameData or SetParamString imports/calls. GetParamString reads **disc APP_VER (id 106)** inside `0x171418`.

`0x15AAEC` records DataCheck OK as “installed”; `0x17B300` then validates installed files. Missing installation bypasses that file validation. `0x53254` counts failures; `0x52534` returns the count. At `0x1E034C` the startup code tests it; positive counts reach `0x1E0410` and call **`0x34C6C` at `0x1E0440`, message id 0x12C**. This is D2's own dialog, not cellMsgDialog. The reported English error string is at ELF guest `0x3A7EB0`, referenced by the string-table pointer at `0x4844E0`.

`R.trace-build.py` instruments that count and actual dialog branch in a **build-r source copy only**, then recompiles/relinks using its existing Ninja commands. No guest branch is bypassed. A normal CMake rebuild restores ordinary code.

## Files

SDK: `libs/system/cellGame.c/.h`, new `param_sfo.h`, refactored `savedata_sfo.h`; new `tests/test_gamedata_roundtrip.c`, adapted `test_game_paths.c`; page-aligned VM allocations in existing SaveData IO/fixed fixtures so their real vm_commit works under ASan. `patches/R-gamedata.diff` contains only R's SDK changes relative to the starting local tree; reverse-apply check passes.

Deliverables: `codex/R.gamedata-test.sh`, `R.trace-build.py`, `R.host-check.sh`, this report. No port source/CMake edits.

## Verification

- Release build succeeds: `port/runs/R-build-final.log`.
- `bash codex/R.gamedata-test.sh`: ASan/UBSan pass, `R-tests-final.log:13,117,132,236` create→separate-process reboot and legacy self-heal; `:31,150` failed atomic write preserves original SFO/retry succeeds; `:242` malformed SFO; `:270,304,305` SaveData regressions and complete suite.
- **Final binary, same persistent legacy HDD, two 40-second headless boots:** `R-boot1.log:746` and `R-boot2.log:729` both `installed_file_errors=0`; neither contains `ERROR_DIALOG`. DataCheck remains NONE; no fabricated SFO/files appear. Both exit 142 from the requested alarm. Software fallback keeps presenting (`:1718` frame 970, `:1700` frame 957).
- **Positive control:** a valid GD SFO without actual installed resources yields `R-positive-trace.log:6297` **47 errors** and `:6298` **ERROR_DIALOG at 0x1E0440**. The fix preserves detection of a genuinely broken installation.
- Shell/Python syntax and SDK whitespace checks pass. Disposable local HDD/test scratch was cleaned after verification; logs remain in `port/runs`.

## Remaining host check

Metal is unavailable in this sandbox. Run **`R_LEGACY=1 bash codex/R.host-check.sh`** on the real host. It builds only build-r, uses the same temporary HDD for both boots, skips movies for deterministic startup, sends no input that could dismiss an error, checks the guest dialog markers, and captures frames **3900/4200/4500**. Logs/frames go to `port/runs/R-host-*`; temporary HDD is retained under `/Volumes/Data/ai-tmp/codex/R-host.*`. Default 100 seconds per boot; increase `R_SECONDS` if frame 4200 is not reached. Uses grep, no rm.

Other-port regressions and full firmware session/BUSY/callback-create semantics remain outside this D2 fix; DeleteGameData and the old CheckCreate callback implementation were not expanded.
