# AT — Native Item Editor with visuals

A native AppKit **Item Editor** window, opened from **Cheats → Item Editor…** (AS's menu calls `d2_item_editor_show()`; AT defines it). For tests, `D2_ITEM_EDITOR=1` opens it. Verified on a live **1.40** game with the post-game slot 01 (939 items). An edit made through the UI survived a real D2 save (game stat/file callbacks, result 0) and a fresh relaunch. Full `ctest` in `port/build-at` passes **51/51**, including the new `d2.AT-items`. Nothing committed or pushed.

## Feature list vs the CE table (fearlessrevolution t=4887)

I read the thread itself. I did not download its `.CT` attachments: they are files, and the brief allowed reading only. The thread covers RPCS3 BLUS31313 v1.30 and shows:

- money/EXP/mana/reincarnation;
- character IDs and evilities;
- item IDs/types, item stats, innocents ("specialists") and mastery;
- Cheat Shop rates;
- "highlighted" character/item Lua scripts;
- hex ID lists for evilities, skills and innocents.

| CE table feature | Item Editor |
|---|---|
| Item ID / type | Base-item picker: searchable, every item in the game's table with its icon, category and ID. Used for **Add Item…** and **Change Base Item…** (keeps level and the innocents that fit). |
| Item stats (HP SP ATK DEF INT RES HIT SPD) | Editable base stats. The total with innocents is read-only and recomputed by the game's own recalc after each Apply. |
| Innocents / specialists, type + level | 6 slots. Type picker filled from the game's innocent table (names/IDs match the CE hex list, e.g. 0x3E Statistician). Level is capped at that type's in-game max (9,999 / 950 / 250 / 150 / 100 / 50 / 1). Subdued flag included. |
| Rarity / item rank | Rarity 0–255. Grade (Common/Rare/Legendary), innocent slots and IW floor limit are derived from it the way the game's item constructor does it. Rank is shown. |
| Item level / Item World | Level 0–9,999. IW floor limit 0–99. |
| Move / Jump / Counter / Range / Critical (Apollo codes) | Editable, with Apollo/game ranges. |
| "Highlighted item" script | Live list of the inventory pool plus all party equipment, refreshed about 4×/s. Details stay live until you start editing (then Apply / Revert). |
| — | Search, type filter (Weapons/Armor/Accessories/Consumables/Other/Equipped), Add, Duplicate, Delete (confirmation sheet). |
| Mastery, evilities, reincarnation, appraise | Not item fields in D2's item record (mastery and evilities belong to characters), so not included. |

## Item record map (0x190 bytes, BE; pool `root+DD518`, equipment `char+0x10`)

| Offset | Field | How verified |
|---|---|---|
| `+04+8k` (k<6) | Innocent: u32 level, u16 type, u8 name variant (random 0–255), u8 subdued (0/1) | Lifted item constructor `func_00062CD0` (writes type at `+4`, `func_00032790` random at `+6`, `func_000615D8` level at `+0`) and recalc `func_000619CC` (loops `k < +D5`, reads `+4`/`+7`). Save statistics: 1,841 innocents, all types valid. |
| `+34` | u32 derived value (recalc writes it) | `func_000619CC` |
| `+38..+77` | 8 × s64 totals (recalc output) | `func_000619CC` writes; the live total changed from 62 to 68 after the edit |
| `+78..+B7` | 8 × s64 base stats | Constructor copies table `+4..+13` × rarity factor; AF / Apollo |
| `+B8 / BA / BC` | id / level / IW floor limit (29/59/99 by grade) | Constructor; the values occur 715/119/105 times in the save |
| `+C0` | grade+1 | Constructor |
| `+CC D2 D3 D4 D5 D6 D7 D8 D9 DC DF` | counter, rarity, type, **icon index**, innocent slots (grade+4), move, jump, rank, range, critical, grade | Constructor table→record copies (`+16→D4`, `+18→D3`, …). Grade = `func_00054AF8`: ≤7 Legendary, ≤31 Rare, else Common. |
| `+F1` | name (48, UTF-8) | AF |

Game tables come from TOC slots, not hard-coded heap addresses:

- **Item table** (`mitem.dat`): header `{u16 count, u32 recs}`, record 0xF0. Fields: id `+14`, icon `+16`, type `+18`, name `+22`, description `+52` (its `Wpn-Fist：` prefix gives the category and filter group), rank `+DF`.
- **Innocent table** (`HABIT.dat`): record 0x1A0. Max level `+0`, id `+4`, name `+8`.
- The live 1.40 game has **685 items and 73 innocent types** (the disc has 666; 1.40 and DLC add the rest). The table records sit above 256 MB (`0x456424c4`).

| | 1.00 | 1.40 |
|---|---|---|
| TOC / count helper | `3FDE60` / `1957C` | `47DF98` / `19678` |
| Item / innocent / inventory / save-manager slot | `-7664 / -74DC / -76AC / -4724` | `-75EC / -744C / -7634 / -4410` |
| Add / remove / recalc (signature-checked) | `CF178 / 5D3D8 / 60DB0` | `D4C60 / 5DF58 / 619CC` |

1.40 is verified live. The 1.00 column comes from the 1.00 lift (`func_00062128` → `-0x74DC`, `func_00060DB0`) plus ELF signature reads, but **I did not run it live** (that needs a separate 1.00 build). Bad signatures disable the matching action.

## Icons

Icons are read from the user's own disc at runtime:

1. `<PS3_VFS_ROOT>/PS3_GAME/USRDIR/Data/START.dat` is a NISPACK: 16-byte header, then 44-byte entries `{name[32], u32 off, u32 size, u32}`.
2. Its `item.txf` entry is uncompressed: a 16-byte header `{fmt, …, u16 w, u16 h, …, u32 size}`, with `fmt 0x0B` = **ARGB1555 big-endian**, 512×288.
3. That sheet holds 144 cells of 32×32. Item record `+D4` / table `+16` is the cell index; for example 0 = fist, 1 = sword, 8 = shield, 19 = ring.

The decoded sheet is cached as `~/Library/Application Support/DisgaeaD2Recomp/cache/item-icons-<size>-<mtime>.png`. No game assets are in git. If START.dat is missing, the list still works with names and the status line names the file that could not be read.

I also checked `ITEMSYMBOL.dat`: it holds LZS-compressed 3D symbol objects (DXT UI textures), not list icons.

## Threading, bridge and the one hunk in AS's file

- `d2_items_frame(ctx)` runs on PPU thread 1 once per vblank. It resolves the root through the count-helper pointer (same method as AF/AS) and drains the action queue (mutex). Each action is checked against generation, expected item id, the save-busy flag and the inventory-table alias.
- Actions use the game's own add/remove helpers and recalc. Edits write only the changed bytes.
- It publishes snapshots at about 4 Hz, and only while a viewer has asked for one in the last 2 s.
- UI threads only copy snapshots, read the catalog, and queue actions.
- **Minimal hunk in `port/src/d2_cheats.cpp`** (AS's file), both lines marked `// AT`: a weak declaration `extern "C" __attribute__((weak)) void d2_items_frame(void*);`, plus `if (d2_items_frame) d2_items_frame(ctx);` right after `in_hook = true;` in `ps3_guest_frame_hook`. It was needed because there is only one frame hook. **If AS rewrites that file, these two lines must stay.**

## Verification

- `d2.AT-items` (`port/tests/AT.items-test.cpp`, also clean under ASan/UBSan by hand) covers:
  - lossless decode/encode of a random record, and that encode touches only editable bytes;
  - grade thresholds; derived rarity fields; every range error;
  - innocent slot/type/max-level checks;
  - ARGB1555 TXF decode and NISPACK lookup;
  - the full action queue against a mock 1.40 guest: apply + recalc, stale-generation and wrong-ID rejection, add, unknown ID, duplicate, replace with compaction, remove, and discard while saving.
- Live run `port/runs/AT/save.log`: the UI changed Crap Beater (pool 0) as follows, Apply then wrote it and recalc ran (total ATK 62 → 68):

  | Field | Before | After |
  |---|---|---|
  | Level | 2 | 3 |
  | Base ATK | 44 | 45 |
  | Innocent added | — | Statistician Lv100 |

  The same run then did Add Yoshitsuna (939→940), Duplicate (→941) and Delete (→940). After that, HL was set through AS's bridge, which ran the real D2 save: `SAVE complete … callbacks result=00000000`.
- The saved `SAVEDATA.DAT` on the scratch copy holds lv 3, ATK 45/68, innocent `(100, 62)` and slot 939 = Yoshitsuna, with count 940. The original slot is unchanged. In the relaunch (`port/runs/AT/reload.log`) the editor reads `lv=3 ATK=45 totalATK=68 inn=[24:2 3:11 6:5 62:100] pool=940`.
- Screenshots in `port/runs/AT/`: `item-editor.png`, `item-editor-layout.png`, `item-editor-edited.png`, `item-picker.png`, `item-editor-weapons.png`.
- I used only `port/build-at` and a scratch HDD copy. The scratch path contains `AS-` because AS's test-save guard requires it; the copy was removed afterwards. The user's saves were not touched; only the icon cache was written.

## Files

- New: `port/src/d2_items.h`, `port/src/d2_items.cpp`, `port/src/d2_item_editor.m`, `port/tests/AT.items-test.cpp`, `codex/AT.report.md`.
- Edited:
  - `port/CMakeLists.txt`: `src/d2_items.cpp` in `add_executable`; `d2_item_editor.m` in the APPLE block.
  - `port/tests/CMakeLists.txt`: `d2_at_items` / `d2.AT-items`.
  - `port/src/d2_cheats.cpp`: the 2-line hunk above.

## Gaps

- **Bag vs warehouse:** D2 keeps a single 999-slot pool. I found no separate bag array in the save, and the game's compaction loops all 999 slots. The list therefore shows "Inventory #n" plus "Equipped" (party equipment, editable; add/remove/replace are pool-only).
- **Equipped edits:** the unit's own totals refresh only after re-equipping or re-entering the map.
- **Caps:** level 9,999, base stats 99,999,999 and floors ≤ 99 are series/Apollo caps. The game has no single clamp to read them from. Innocent caps come from the game's own table.
- **Unknown field meanings:** byte `+7` is treated as "subdued" because recalc counts it as `+7 + 1` occupancy. `+C0..C7` and `+186` are left untouched.
- **1.00:** runtime unverified (above).
- **Item World:** routes and current-floor progress are not mapped.
