# Task L — save/load

SDK save/load now round-trips through D2's actual lifted callbacks. Native gameplay saves and RPCS3 import/export still need a host check. No dump, pad, graphics, or codec files were edited; no commits or pushes.

## Root causes and fixes

- SaveData ignored `PS3_HDD0_ROOT`, wrote text `PARAM.SFO`, and used a plaintext `PARAM.PFD` as its secure-file manifest. It now writes binary little-endian PSF metadata and RPCS3-style `*filename` secure flags under `$PS3_HDD0_ROOT/home/00000001/savedata/<dir>`. Normal/secure files remain plaintext, like RPCS3. Imported SFO entries and ownership metadata are preserved on ordinary updates; no fake PFD is generated.
- List callbacks used an undersized ListSet allocation, discarded updated userdata, omitted list parameters, confused filtering with selection, and mishandled terminal results. D2's title probe returns **OK_LAST_NOCONFIRM (2)** just to count saves; it must return CELL_OK without stat/file callbacks. Empty interactive load returns CELL_CANCEL. Callback errors return CBRESULT rather than silently succeeding.
- Corrected host structure models (CBResult pointer/userdata, ListGet/ListSet/NewData, FileStat filename padding, StatGet reserved fields, DoneGet sizeKB). Guest marshalling remains explicit: BE scalars, 32-bit pointers; CBResult 20, ListGet 76, ListSet 24, StatGet 1704, FileStat 56, FileSet 48 bytes.
- Writes now stage metadata/files beside the target save and commit after all callbacks succeed. Failed callbacks/I/O retain the old save. Fixed WRITE offset truncation, short-buffer rejection, DELETE errors, recreated saves, file-type persistence, real free space, and concurrent/reentrant BUSY. Callback scratch moved out of the guest heap to committed `0x2FFE0000` (still configurable).
- Added native macOS slot selection, save confirmation, empty-load notice, and deletion confirmation on the AppKit main thread. Autosaves do not prompt. Scripted/headless runs use callback focus or explicit environment selections.
- cellGame reported the default BLES00000 because this runner never initialized its metadata. SDK getters/BootCheck now lazily read the mounted disc's PARAM.SFO. ContentPermit now creates the directory DataCheck actually selected, including before BootCheck, and no longer mirrors HDD game data into the mounted disc.

## Static audit

All **13 relevant imports / 27 direct call sites**, including the unnamed overlay NID, are listed in [L.imports.txt](L.imports.txt).

| API | D2 caller(s) |
|---|---|
| ListLoad2 | `0x16500C`, title/count probe `0x17E368` |
| ListSave2 | `0x165108` |
| AutoSave2 | `0x164A5C` |
| Delete2 | `0x1649B4` — system deletion UI, no callbacks |
| EnableOverlay | `0x163914`; NID `0xE7FA820B` |
| BootCheck / GetParamString / PatchCheck | `0x171418` |
| DataCheck / ContentPermit | DataCheck `0x15AAEC`; ContentPermit `0x15AAEC`, `0x171418` |
| MsgDialogOpen2 | `0x16064C`, `0x1606F0`, `0x16072C`, `0x17D828`, `0x17E450`, `0x1B5094` |
| MsgDialogOpenErrorCode / Abort | `0x16072C` / `0x16492C` |

D2 has no Fixed/Done-callback API imports. Existing SDK Fixed tests still pass; DoneGet's model was corrected. Its actual callbacks are: title list `0x17D410`, list load `0x16382C`, list save `0x16440C`, load stat `0x163C20`, save/auto stat `0x164404/0x164408 → 0x163EBC`, load file `0x164C3C`, save file `0x164D74`. Save writes ICON0 and secure `SAVEDATA.DAT`, skipping absent optional ICON1/PIC1/SND0 buffers, then returns LAST. Slot formats are `%s_NORMAL_%02d` and `%s_AUTO`.

cellGamePatchCheck and MsgDialogOpenErrorCode were implemented concurrently by M. Those additions compile in L’s build; existing deferred-dialog regressions pass. L did not edit those APIs. Open2 completions remain deferred to cellSysutilCheckCallback; Abort cancels. Native message-dialog rendering is still outside this change.

## Files changed

- SDK: `libs/system/cellSaveData.c/.h`, new `savedata_sfo.h`, new `savedata_macos.h/.m`, `cellGame.c`, three existing system test fixtures; one source-list entry in SDK `CMakeLists.txt`.
- Port deliverables: `codex/L.savedata-test.c`, `L.savedata-test.sh`, `L.host-check.sh`, `L.imports.txt`, this report, and [patches/L-savedata.diff](../patches/L-savedata.diff). The patch captures L's changes separately from concurrent workers.
- Only `port/build-l` was configured/built, with the OPERATIONS.md configure flags.

## Verification

`L_SANITIZE=1 bash codex/L.savedata-test.sh` passes ASan/UBSan. The script extracts local lifted callbacks without adding game code to the SDK. Only libc helpers and NIS option queries are shimmed; callback bodies execute unchanged. Fixture payload is synthetic; ICON0 is the real 61,923-byte disc PNG, read without modifying it.

Evidence in `port/runs/L-harness-asan.log`:

- 15: actual title probe result=2, count=0, CELL_OK.
- 20: empty list CELL_CANCEL, no stat/file callbacks.
- 30–31: ICON0 WRITE **61923 → 61923**, secure SAVEDATA.DAT WRITE **4099 → 4099**.
- 43–45: secure payload READ **4099 → 4099**, byte-exact comparison passes.
- 58: overwrite decline and callback failure after writing staged payload both preserve the original; reentrant BUSY passes.
- 67–75: actual AutoSave2, truncation/NOTRUNC/delete/bounds errors, explicit Delete2, empty subsequent load, and scratch save cleanup pass.

Existing regressions: `L-fixed.log:34`, `L-io.log:17`, `L-game-paths.log:5`, `L-dialog.log:23` all pass. Build succeeds (`L-build.log`). Script syntax and whitespace checks pass.

40-second sandbox run: `port/runs/L-final.log:200–202` shows real D2 ListLoad2 / OPD **0x003EBA70** / terminal result **2**, dirNum=0; `:203–205` shows **BLUS31313** read from PARAM.SFO and BootCheck; `:1607` reaches guest frame **1140**. Exit 142 is the requested alarm. No save callback errors/guest faults observed. The concurrent movie path reports decoder errors separately; this run did not reach a gameplay save point.

ABI/protocol and disk layout were checked against [RPCS3's SaveData header](https://github.com/RPCS3/rpcs3/blob/master/rpcs3/Emu/Cell/Modules/cellSaveData.h) and [implementation](https://github.com/RPCS3/rpcs3/blob/master/rpcs3/Emu/Cell/Modules/cellSaveData.cpp), plus [ps3recomp PR #158](https://github.com/sp00nznet/ps3recomp/pull/158) and the requested reference-port/PR #160 repository searches.

## Host follow-up / remaining

Run `bash codex/L.host-check.sh tests`, then `bash codex/L.host-check.sh interactive` to save/load from gameplay and exercise native dialogs. `continue` sends timed input; `inspect` validates SFO fields and prints file SHA-256 values. Script uses grep, no rm, and at most 512 PAD_SCRIPT events.

For deterministic replay: `PS3_SAVEDATA_UI=headless`, `PS3_SAVEDATA_DIR=<exact slot>`, `PS3_SAVEDATA_CONFIRM=yes|no`; deletion requires `PS3_SAVEDATA_DELETE_DIR=<exact slot>`. `L_PAD_SCRIPT` overrides input timing, and `L_SECONDS` defaults to 40. `save` mode requires a verified route in L_PAD_SCRIPT; no hub-save timing is fabricated.

Remaining: real-host save → restart → Continue into the resumed scene; native dialog interaction; importing/exporting an actual gameplay save in RPCS3. This implements RPCS3's directory/SFO/plain-file layout, not physical-console encryption/PFD signing. Sudden process/power failure during directory replacement is not a crash-durability guarantee; a retained `previous` directory is logged if rollback cannot restore it. Scratch heap/table configuration and callback error semantics are generic SDK corrections and should get other-port regressions before upstreaming.
