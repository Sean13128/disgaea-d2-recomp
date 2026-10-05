# AJ — data safety fixes

Implemented R01, R02, R03 and R06. No commits/pushes, game-dump writes, shared-build changes, packaging changes or test-registration changes.

## Root causes and changes

- **R01:** the loader checked `memsz` but copied unchecked `filesz`, skipped malformed segments, and trusted overflowing table offsets. `ppu_load_elf` now validates the entire ELF before guest writes/TLS state changes: ELF64/MSB/PPC64 headers, complete program/section tables, subtraction-based range checks, LOAD/TLS sizes, copied ranges, TLS source/destination, and mapped executable entry code/OPD. Empty PS3 LOADs remain supported. The port also verifies its expected entry OPD and TOC; `ppu_run` still checks code registration.
- **R02:** two renames could hide the old slot, without startup recovery or durability barriers. Commits now fsync staged files/directories and a binary intent record, use macOS `RENAME_SWAP` when supported, and retain the previous directory until the replacement and parent directories are durable. The portable fallback restores or completes interrupted transactions. Failed recovery preserves evidence and returns an error. Recovery runs at host startup and before save APIs. Internal journal names cannot collide with visible slot names. Integrated AL's atomic shutdown admission gate; active saves finish before its host stop proceeds.
- **R03:** direct writes to the final cache and ignored close errors exposed incomplete output. Decryption now uses exclusive sibling temps, checks writes/flush/fsync/close and decoded length, then publishes atomically. Length/digest completion markers reject truncated, missing-marker and same-length corrupt caches. Striped thread locks plus file locks serialize each key across threads/processes; existing reader descriptors survive replacement. Wrong-key/output errors preserve the previous output.
- **R06:** both runners now return 1 for failed `ppu_run` unless the guest supplied an explicit exit status.

Production files changed: `ps3recomp/runtime/ppu/ppu_loader.cpp`, `ps3recomp/libs/system/cellSaveData.{c,h}`, `ps3recomp/libs/filesystem/edat.c`, `port/main.cpp`, `ps3recomp/templates/project/main.cpp`. AL concurrently owns shutdown changes in main/save admission; those were preserved.

New fixtures: SDK `runtime/ppu/tests/test_loader_validation.cpp`, `runtime/ppu/tests/test_runner_failures.py`, `libs/system/tests/test_savedata_transaction.c`, `libs/filesystem/tests/test_edat_cache.py`.

## Verification

- `port/runs/AJ-build-final.log:7`: native 140 runner linked in **port/build-aj**. OPERATIONS flags used; concurrent R12 began honoring RECOMP_DIR, so the 140 source override became `src/recomp-140`.
- `AJ-loader-validation.log:24–45`: 22 ASan/UBSan loader cases, including no guest writes on rejection. `:40` covers the review's `0xDFFFFFE0 / memsz=16 / filesz=65536` segment. Actual runner: `AJ-runner-malformed.log:2,6` rejects it and exits **1**, no signal.
- `AJ-runner-unregistered.log:10,20,22`: code `0x07777770` is unregistered, `ppu_run returned -1`, host exits **1**.
- `AJ-save-transaction.log:1–24`: interruption after data writes, both fallback renames, atomic exchange; injected ENOSPC before commit and at all six post-rename file/directory barriers; failed install+restore retained then recovered; name collisions/spaces; active-save quit barrier. Production code with ASan/UBSan.
- `AJ-edat-cache.log:16,22–29,390`: corrupt/truncated/missing-marker caches, allocation/flush/close faults, actual zero RLIMIT_FSIZE buffered-output failure, 160 concurrent thread and 80 process resolve/open checks passed. `AJ-edat84.log` retains **84/84** crypto checks.
- `AJ-regressions.log:53`: **25/25 CPU suites passed**, including Q/T/Y/AA/AB, AG2 FIFO/engine, X hash, AA vertex/cache, EDAT, savedata and AC. Final savedata rerun: `AJ-savedata-final.log`, **2/2**. `AJ-save-import.log`: 12 tests, 11 passed, optional external pfdtool check skipped.
- Requested `work/EBOOT.elf` invocation: `AJ.log:4` correctly rejects version 100 with exit **1**. Matching 140 smoke: `AJ-v140.log:2830` reaches frame **2340** in 40 seconds, alarm exit **142**. `:74–90` records no Metal device/software fallback; existing headless movie decoder errors also appear.
- Both Git whitespace checks passed. Synthetic tests used disposable data; personal saves were not used in interruption/failure tests.

## Remaining

Real GPU/Finder behavior and physical power-loss durability were not tested. Process-interruption and syscall-failure recovery were tested on macOS, including real directory exchange and forced portable fallback; other hosts need native verification. AK owns test registration/bootstrap; the final combined SDK patch must include these shared runtime changes. AL owns complete quit behavior. No AJ decision is pending.
