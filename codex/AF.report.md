# AF — D2 cheat and editor menu

Implemented for BLUS31313 **1.00 and 1.40**. Both load the real post-game slot 01, display its 118 units / 939 items, apply edits, complete D2 save callbacks, and reload the persisted values. The AF build is left configured for 1.40. No commits, dump edits, original-save edits, or changes to another worker's build.

## Root causes / approach

- Artemis instruction pokes do not change statically compiled PPU code. The port substitutes EXP, SP, item-shop and damage hooks in **build copies**, preserving lifted source. CMake requires all four substitutions to match.
- Guest heap addresses move between versions. The resolver validates the party-count helper signature, decodes its `lwz r9,disp(r2)` to find the live root pointer, then validates RAM bounds, counts, names, levels, classes and HL. It does not use the observed heap address as a locator. Unsupported or mismatched builds disable writes.
- P's system dialogs were one-shot and automatically resolved headless. A persistent editor mode now captures pad input, queues actions together with their selected row, repeats navigation, preserves selection during refresh and discards queued actions when pages change.
- Host callbacks only enqueue requests. Guest reads/writes, native item helpers and continuous HP/SP restoration run on PPU thread 1 after the vblank pump, once per observed vblank. Saves/loads block mutations and invalidate pending edits. The main PPU thread remains active; opening the menu pauses guest **input**, not the entire simulation.
- Native inventory deletion takes `(0, pool_index)`, not `(pool_index, ...)`. Add/remove use signature-checked game helpers and validate that the native pool pointer aliases the mapped save pool; direct byte clearing would leave counters/caches inconsistent.
- One-hit kills only replace enemy HP decreases, including signed underflow; healing and neutral units are unaffected. SP hooks also recognize validated battle-entity records at versioned call sites, rather than assuming every record belongs to the persistent party array. Free-shop changes only negative item-shop purchase transactions; sale proceeds remain normal.

## Delivered behavior

F1 or **Cmd+Shift+C** toggles the in-window editor. `d2_cheats_toggle_menu()` is exported with C linkage for AG's weak menu-bar reference. The focused window accepts these hotkeys even with `PAD_NO_KEYBOARD=1`; repeats are ignored.

- **General:** HL, primary unit Mana, bonus gauge/progress, Cheat Shop CP and five rates; infinite HP/SP, one-hit kills, EXP multiplier 1–1024x, free item-shop purchases.
- **Characters:** roster with names/levels; level, EXP, Mana, current/max/effective/base stats, aptitudes, class, movement/jump/counters/throw/critical; existing skills' IDs/levels/EXP/boost and four equipment records' item fields. Level changes synchronize EXP through the native class EXP table. Class changes validate the loaded class table and refresh cached class/model data.
- **Items:** combined bag/warehouse pool, native add by validated item ID, confirmed native remove, rarity value/category, level, stats, movement/jump/range/counters/critical and Item World level limit.
- **Presets:** default plus three slots under `~/Library/Application Support/DisgaeaD2Recomp/cheats/`. Atomic JSON save; size/type/title validation before guest writes; range clamps on load. Presets contain General values, primary-unit Mana and toggles. Character/item edits persist through the game's save.

Keyboard controls: arrows navigate/adjust; **Q/W** change pages; **Z** chooses/edits; **A** cycles numerical step; **X** backs out. Numeric editing has minimum, maximum, Apply and Cancel. Gamepad equivalents are D-pad, L1/R1, Cross, Square and Circle.

## Mapping and version table

All payload fields are big-endian. Save payload size is **1,498,152 bytes**; the same common layout was verified in both versions. Offsets below are relative to the resolved root, character record, or item record as indicated.

| Structure / field | Offset / layout |
|---|---|
| HL | root `+568`, u64, cap 9,999,999,999,999 |
| Party | root `+598`, stride `1A60`; count `+1507EC`, u16, capacity 128 |
| Name / EXP / Mana / level / class | char `+650` (48 bytes), `+8` u64, `+1150` u32, `+1154` u16, `+1158` u16 |
| Current HP / SP | char `+1070 / +1078`, u64; clamp to recorded maxima |
| Effective/max HP, SP, ATK, DEF, INT, RES, HIT, SPD | char `+1080..10B8`, eight u64 |
| Base stats, same order | char `+10C0..10F8`, eight u64 |
| Aptitudes | char `+1524`, eight u16; effective mirror `+1504`, bonus vector `+1514` |
| Critical, move, counter, throw, jump | char base `+116E / 1170 / 1172 / 1174 / 1176`; effective mirror is next byte |
| Skills | count char `+117B`; IDs `+B6C` u16, EXP `+76C` u32, levels `+E6C` u8, boosts `+D6C` u8 |
| Equipment | char `+10`, four embedded item records, stride `190` |
| Inventory | root `+DD518`, stride `190`, capacity 999; total `+13EE08`, u16 |
| Item identity / level / level limit / name | item `+B8 / BA / BC` u16; `+F1`, 48 bytes |
| Item HP, SP, ATK, DEF, INT, RES, HIT, SPD | item `+78..B0`, eight u64 |
| Item rarity value / category | item `+D2 / DF`, u8 |
| Item counters / move / jump / range / critical | item `+CC / D6 / D7 / D9 / DC`, u8 |
| Bonus progress / gauge | root `+150800 / +150802`, u16, caps 99 / 9 |
| Cheat Shop CP / rates | root `+1508A0`; five u16 at `+1508A4..1508AC`: EXP, Mana, HL, weapon mastery, skill EXP |

| Version | TOC | Count helper | Derived pointer slot | EXP / SP / shop / damage hook |
|---|---|---|---|---|
| 1.00 | `003FDE60` | `0001957C` | `003F6024` | `0001A1DC / 000F2A14 / 000CDABC / 000E8954` |
| 1.40 | `0047DF98` | `00019678` | `00476164` | `0001A274 / 000F9020 / 000D3748 / 000EEA0C` |

The JSON includes per-version signatures, native helper addresses, TOC-relative manager/table slots, and battle SP callers. Runtime roots observed were `007B9290` / `00839990`; these are diagnostic values only. Future builds need newly matched signatures/helpers and a validated profile, rather than a heap-address adjustment.

## Research sources

[Apollo BLUS31313](https://github.com/bucanero/apollo-patches/blob/main/PS3/BLUS31313.savepatch) and [NPUB31321](https://github.com/bucanero/apollo-patches/blob/main/PS3/NPUB31321.savepatch) provide save-offset corroboration. [Artemis BLES01939 1.00](https://github.com/bucanero/ArtemisPS3/blob/master/docs/codes/Disgaea%20D2%20A%20Brighter%20Darkness%20BLES01939%2001.00.ncl) and [1.40](https://github.com/bucanero/ArtemisPS3/blob/master/docs/codes/Disgaea%20D2%20A%20Brighter%20Darkness%20BLES01939%2001.40.ncl) contain bungholio/mull/community instruction and pattern cheats for damage, SP, EXP and other systems. BLES addresses were treated as leads and matched against the actual BLUS lifted code, not assumed interchangeable. Mapping also used D2 constructors/accessors, inventory helpers, class/EXP lookup functions, native save callbacks and the decrypted real save.

[RPCS3 issue 4022](https://github.com/RPCS3/rpcs3/issues/4022) documents D2 SPU speed-patch work; it did not provide editor structure mappings. [This CE-table discussion](https://gamefaqs.gamespot.com/boards/687861-disgaea-d2-a-brighter-darkness/76920211) mentions character/class editing; a usable downloadable table was not recovered. No separate verified NetCheat/CCAPI or RPCS3 gameplay-editor table is claimed. Reference repositories and [ps3recomp PR 160](https://github.com/sp00nznet/ps3recomp/pull/160) were inspected with `gh`; P's existing overlay was the reusable implementation here.

## Files changed

- Port: `port/src/d2_cheats.{cpp,h}`, `d2_cheats_data.h.in`, `d2_cheats_lift.cmake`, `port/d2_cheats.v1.json`; cheat-specific additions to `port/CMakeLists.txt`, `port/stubs.cpp`, `.gitignore`.
- SDK: `libs/system/sys_overlay.{c,h}`, `libs/video/rsx_metal_overlay.m` (editor raster/footer only), `libs/input/pad_macos.m` (weak host hotkey hook), `runtime/ppu/ppu_hle.cpp` (weak guest frame hook). AF-only SDK diff: `patches/AF-cheats-runtime.diff`; its reverse application was checked against the current SDK. It excludes AG's concurrent Metal capture/resolution changes.
- Checks: `codex/AF.check.sh`, `AF.host-check.sh`, `AF.save-check.py`, `AF.editor-test.cpp`, `AF.overlay-test.c`, `AF.hotkey-test.m`, `AF.raster-test.cpp`, this report. No AG settings/NSMenu, audio, codec or GCM FIFO edits.

## Verification

`bash codex/AF.check.sh` passes with ASan/UBSan: bounded BE RAM/clamps, stale/version rejection, EXP/level synchronization, aptitude mirrors, damage/EXP/free-shop/SP wrappers, atomic preset validation, real AppKit dispatch/focus/repeat handling, persistent editor queue/repeat/selection, and P's existing system-dialog/sysutil regressions. `port/runs/AF.check.log` contains the PASS summaries.

- **1.00:** `port/runs/AF-host.MBmrDH/verify/run.log:2001–2003` reads HL **993701506631**, party **118**, Laharl **Lv9999 / Mana106348**, item count **939**. Lines **2143–2149** record all edits and native add/remove `939 -> 940 -> 939 (PASS)`. Lines **2157–2158** show `SAVE complete for 'NPUB31321_NORMAL_01'` and actual D2 stat/file callbacks result **00000000**.
- **1.40:** `port/runs/AF-host.xTRHXy/verify/run.log:1753–1755` reads the same real values. Lines **1896–1902** record writes/add/remove; **1910–1911** show `SAVE complete` / callback result **00000000**. `port/runs/AF.host-final-{100,140}.log` and each run's `save-diff.log` confirm HL +1, Laharl Mana +1, base ATK **3002705 -> 3002706**, first-item HP **0 -> 1**, level **2 -> 3**, count still **939**, and all **118 names/levels preserved**.
- The original encrypted retail slot was decrypted again with `tools/d2_save_import.py`; PFD v4/HMAC checks passed for `PARAM.SFO[0]`, `PARAM.SFO[3]`, `SAVEDATA.DAT`. Its decrypted SHA256 still matches the original native slot: `9f5a847eb6f1804536986a93682a8304cd613f3d3ad4c702c6d087ba4e27fc30`. `port/runs/AF.save-diff.log` and `AF.save-diff-140.log` record those comparisons. Native saves are already plaintext and have no retail PFD, so the comparator handles them directly.
- Fresh launches from edited HDD copies reloaded all five edits: `port/runs/AF.reload.log:1256–1262` (1.00), and `port/runs/AF.reload-140-final.log:1745–1751` (1.40).
- Save automation calls **real D2 stat/file callbacks**, using a protected test HDD copy and borrowed/restored guest stack. It does not claim an interactive traversal of the game's Save menu or all of its serialization preparation.
- `port/runs/AF-raster/*.png` are visually inspected **CoreText raster previews** from the actual editor with the real save payload: General/roster/numeric editing are readable, with no clipping. They are not live Metal screenshots. The sandbox has no Metal device.

For Claude's real-window captures: `bash codex/AF.host-check.sh all` (default 1.40), or `AF_VERSION=100 bash codex/AF.host-check.sh all`. It uses only `build-af`, private HDD/cache copies, 40-second runs, `PS3RECOMP_METAL_FRAME_DUMP`, and converts final captures to PNG using macOS `sips`. `verify` runs the save/diff check; `AF_HEADLESS=1` performs state checks only. A cold-cache 1.40 attempt did not reach load within 40 seconds; copying the established FIOS cache into the private test directory made the final run pass. Logs/captures stay in `port/runs`; scratch copies are removed on exit unless `AF_KEEP_HDD=1`. AF's disposable research/test HDD copies were removed after verification.

## Remaining

Real Metal composition/hotkeys and actual battle/shop interactions still need the host check. Battle toggle behavior is covered by model/wrapper tests, not a human attack/purchase session. Base/effective stats may be recalculated by level-up/equipment changes; refresh totals by re-entering the map before saving. Character name editing, equip/unequip/swapping identities, skill insertion/deletion, separate bag/warehouse filtering, advanced Item World innocents/routes/depth, and Netherworld/story flags remain unmapped or deliberately unavailable. Existing equipment fields/skills are editable; item identity replacement is view-only and new identities use the validated native Add helper. Do not treat this as complete coverage of every requested editor mutation.
