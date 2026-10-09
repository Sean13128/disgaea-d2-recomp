> **Status — October 8, 2026:** Completed research handoff from the stopped character-export task; this is not proof of a finished artwork export or safe character injection. The owner stopped all subagents. Work remains paused. The original research files, indices and recorded verification are preserved in `CE.research-evidence.zip` beside this document. Counts and findings below describe the research scope, not completeness of the interrupted Desktop export. See `CE.report.md` for that distinction.

# Disgaea D2 — character-addition constraints

## Decision

**Arbitrary absent IDs are not established as addable. “Only replacement is possible” is also not established.** The actual 1.00/1.40 class-table binding and lookup are count-driven, not a fixed 558-row lookup. An additional well-formed definition is structurally conceivable, but that is not proof that creation, derived selectors, scripts, artwork, save compatibility and all dependent buffers support it. The shipped tables have **558 defined rows, no uncounted record slack**, and an invalid ID can become an unchecked cached index.

Existing dummy-named rows are a narrower *research* target, not certified free/safe replacement slots. **66 dummy-named records were found; zero IDs were proven unused.** One existing ID, **2235**, has no raw two-byte occurrence in a deliberately bounded non-character START-table scan. That is an unreferenced-in-this-scan candidate only.

## Scope and evidence conventions

Repository root: `/Volumes/Data/Applications/QuiverLauncher/Apps/Disgaea D2-RE`.

- `R100` below means `port/src/recomp`; `R140` means `port/src/recomp-140`. Every cited function is an actual local lifted routine, not executed guest code.
- Disc data: `Disgaea D2 A Brighter Darkness - [BLUS31313]/PS3_GAME/USRDIR/Data`.
- Update examined: `port/hdd0/game/BLUS31313/USRDIR/Data/START_7.dat` — this is the path actually present/consumed, not an assumed NPUB path.
- Scope: seven disc `ANM_HI*.dat` archives, seven disc `START*.dat` archives, the above update START archive, and local 1.00/1.40 ELF/lifted sources. This is **not** a complete map/stage/script/compressed-artwork reference audit or a live mount/unlock-state inspection.
- All source archives were opened `rb`. Full SHA-256 before indexing, after indexing and after research match for **15 archives**; initial/final hashes also match for **two ELF files**. See `input_hash_verification.json`. Outputs are scratch research only. No saves were opened; no repo/SDK edits, staging, commits, build, packaging, game launch or injection occurred.
- `source_evidence.json` / `.md` retain exact function/excerpt paths, line numbers and source-file hashes. `findings.json` is the machine-readable decision/constraints summary.

## 1. Proven archive/table layout and exact content

The native NISPACK reader corroborates the directory geometry: 16-byte header, BE32 count at +12, 44-byte entries, filename[32], BE32 offset at entry+32 and size at +36 (`port/src/d2_items.cpp:131–139`, `d2_items_nispack_find`). The extra word at entry+40 is retained but its meaning is not assigned.

Four indexed entries named **`char.dat`** were present:

| Archive | Entry archive offset (decimal) | Entry size | Header | Count / unique IDs |
|---|---:|---:|---|---:|
| START.dat | 16,513,024 | 377,212 | `02 2e 00 00` | 558 / 558 |
| START_1.dat | 176,128 | 377,212 | same | 558 / 558 |
| START_2.dat | 163,840 | 377,212 | same | 558 / 558 |
| START_4.dat | 161,792 | 377,212 | same | 558 / 558 |

Their exact length is `4 + 558 * 0x2A4`. There are **zero tail bytes, zero zero-ID rows, zero blank-name rows and no duplicate IDs** in each table. The ID sets and row order are identical across all four. START/START_1/START_2 payloads are byte-identical; START_4 differs in exactly **100 rows**, without adding IDs. This does **not** establish which overlay is mounted or whether named content is installed/unlocked. Full per-row offsets/hashes/IDs are in `character_table_records.json`.

The update START_7 contains only `mitem.dat` at `0x800` (164,404 bytes) and `saveicon.dat` at `0x29000` (2,804 bytes): **no `char.dat` override in this examined archive** (`archive_index.json`). Do not generalize this to all update content.

### `char.dat` format

- File +0: BE16 row count; +2/+3 are `00 00` in these copies and ignored by the traced binder.
- Records begin at file+4; **stride `0x2A4` (676)**.
- Record **+`0x194`: BE16 class-definition ID**, not row index.
- Record **+`0x196`: animation-base selector**, sign-extended as int16 by traced consumers.
- Record **+`0x19E`: secondary selector key**, also sign-extended in its lookup path; exact portrait attribution remains incomplete.
- Record +`0x1FC`: name string; +`0x230`: title string. Source name copy: `R140/ppu_recomp_005.cpp:43499–43503`, `func_0010E77C`; title copy of `0x44` bytes: same file:43940–43945, `func_0010EE50`. The initial JSON decoder reads a 48-byte window for each; checking the larger adjacent-field windows found **no clipped strings** in these tables. These offsets do not constitute a complete class schema.

Binding independently proves the four-byte header: `R100/ppu_recomp_018.cpp:44289–44294`, `func_003400E4`, and `R140/ppu_recomp_019.cpp:589–594`, `func_0034FE34`, install `{BE16 count, records_pointer=file_buffer+4}`. Actual lookup proves the ID offset and stride: `R100/ppu_recomp_018.cpp:43858–43889`, `func_0033FBB8`; `R140/ppu_recomp_018.cpp:50065–50097`, `func_0034F8D8`.

Observed IDs span **10–9001**: row0 ID10 Laharl, row1 ID20 Laharl, row2 ID30 Etna; rows556/557 are ID9000/9001 “Conversation Guy” / “Conversation Guy (M)”. There are **8,434 absent integers within that span**. Those holes are not allocated records, free engine slots, or a safe ID pool. Full IDs and gap intervals are emitted, rather than inferring ID=row.

## 2. Lookup/buffer behavior: what adding a row would and would not solve

**Proven:** both lookups reject zero, scan the runtime header count, compare ID fields and return a row index or `-1`. 1.40 explicitly narrows the lookup input to 16 bits. The traced binder has no inline 558-element array and the lookup has no 558 clamp.

The table loader resolves filenames/size and allocates file-sized buffers before binding. `func_00350168` calls the file loader at `R140/ppu_recomp_019.cpp:1556–1591` and the class binder at :1692–1698. `R140/ppu_recomp_001.cpp:24342–24369`, `func_00050754`, obtains length with `func_00182F1C`, passes that length to allocation and reads it; archive-length selection is at `R140/ppu_recomp_008.cpp:26885–26970`. ELF TOC/string evidence identifies `char.dat` in this configuration (`work/v140/EBOOT.elf`, filename VA `0x3E7208`; `table_probe_notes.json`). This is evidence against a fixed char.dat-sized local copy, **not a global memory-capacity guarantee**.

**Concrete invalid-ID hazard:** `R140/ppu_recomp_000.cpp:20289–20300`, `func_00020CAC`, takes the unit ID at +`0x1158`, looks it up and stores the result as BE16 at +`0x115C`. A miss becomes `0xFFFF`. `func_00015E18` at the same file:6980–6986 subsequently computes `records + cached_index * 0x2A4` without checking the index/count. Thus merely setting an absent ID is not an addition mechanism and can produce an out-of-table address. The 16-bit storage width must not be presented as 65,536 usable IDs/rows; other consumers sign-extend IDs/selector fields and sentinel semantics matter.

A search for literal `0x22E` found UI coordinates and structure offsets, not a proven class-capacity constant. Conversely, failure to find such a clamp is **not an exhaustive audit of differently expressed limits, row-indexed bitsets/caches, creation lists, AI, scripts or related tables**. All downstream capacities remain a requirement before an addition could be certified. Duplicate IDs would also be ambiguous because the lookup returns the first match.

## 3. Existing dummy records and bounded “unreferenced” evidence

| Stored dummy-name family | Count | Existing ID pattern |
|---|---:|---|
| `固有キャラダミー` (unique-character dummy) | 6 | 650, 660, 670, 680, 690, 700 |
| `汎用人間ダミー` (generic-human dummy) | 30 | 1230–1235, 1240–1245, 1250–1255, 1260–1265, 1270–1275 |
| `汎用魔物ダミー` (generic-monster dummy) | 30 | 2210–2215, 2220–2225, 2230–2235, 2240–2245, 2250–2255 |

These are **defined, populated records**, not blank allocation slack. `candidate_reference_scan.json` records exact row/ID offsets and all bounded raw BE16-hit counts; `findings.json` adds decoded selector evidence.

Specific examples in disc START.dat:

- Row56, ID650: record at **`0xFC8BE4`**, ID field **`0xFC8D78`**; +0x194..+0x19F bytes `028a028a0007001101ea02ee`. Its zero-variant resource would be `anm10650.lzs`, not present in the seven examined ANM_HI directories. Raw secondary key750 is absent from the static selector list. Neither observation proves the record is unreachable or all artwork absent.
- Row366, ID2235: record **`0xFFBE7C`**, ID field **`0xFFC010`**; bytes `08bb08b60007001108b608bb`. Animation base2230 is shared, not ID2235; zero-variant **`anm12230.lzs`** is present in disc ANM_HI.dat at archive offset **223,860,736**, size **2,650**. Raw secondary key2235 is present in the static list. These are dependency leads, not validated complete artwork.

ID2235 has **zero raw BE16 hits** outside char.dat in the indexed START `.dat` payloads. All other dummy candidates have hits. The scan deliberately excludes class rows, compressed `.lzs`, stage/map archives and ELF/source constants, and does not decode bytecode or reference semantics. A raw hit can be a stat/string/offset; zero hits can miss computed, table-relative or differently encoded references. Therefore **“bounded unreferenced candidate” is the strongest justified label; “proven unused” count is zero.**

## 4. Distinct runtime budgets — not interchangeable class capacities

### Roster and save-layout evidence

The guest free-roster calculation is **128 − signed16(root+0x1507EC) − signed16(root+0x1507EE)**: `R100/ppu_recomp_000.cpp:35661–35671`, `func_0002E2FC`, and `R140/ppu_recomp_000.cpp:35365–35375`, `func_0002E218`. This proves a **128 combined roster-slot budget**, with two counters/partitions; it does not cap the number of class definitions at128.

Persistent-unit addressing uses **root+`0x598` + slot*`0x1A60`** (`port/src/d2_cheats.cpp:88,103–110`; guest initialization `R140/ppu_recomp_000.cpp:13533–13537`, `func_0001AF60`). The local profile documents a **1,498,152-byte save layout** and the same stride (`port/d2_cheats.v1.json:9–14`). This is source/profile evidence only: no save bytes, serializers/checksums across modified table sets, reload compatibility, or roster expansion were tested. More definitions need not imply more simultaneous saved units, but that distinction does not prove new definitions save correctly.

### Battle actors

There is a **160-slot descriptor search, indices0–159**, independent of the roster: `R140/ppu_recomp_000.cpp:6211–6228`, `func_00015490`, and 1.00 counterpart `R100/ppu_recomp_000.cpp:6143–6178`, `func_000152B0`. Descriptor addressing has stride **`0x13C`** (`R140/ppu_recomp_000.cpp:6197–6210`, `func_00015464`; insertion at :27411 onward, `func_00027124`). This is not proof of160 player-deployable units or unrestricted simultaneous enemies. Player sortie/deployment limits, map-specific actors and the complete battle-memory budget remain unresolved.

### Animation loading/cache descriptors

Both versions initialize four managers with fixed descriptor counts **138 / 1047 / 1000 / 50**, with index-base values **10 / 149 / 1197 / 2198**: `R100/ppu_recomp_008.cpp:20590–20620`, `func_00177744`; `R140/ppu_recomp_008.cpp:24533–24566`, `func_00180F74` (also preserved in `animation_init_evidence.json`). The allocator stores capacity at manager+`0x10`, allocates **count*`0x24`** and initializes those descriptors (`R140/ppu_recomp_008.cpp:24473–24530`, `func_00180EA8`). The load path scans that capacity, reuses a matching active resource or searches a free descriptor (`func_00181438`, same file:24911–24981); these are **2,235 descriptors across groups**, not2,235 character IDs or arbitrary interchangeable slots.

Sprite mapping uses signed class-record +`0x196` plus **10,000**, conditionally plus unit variant byte+`0x1183` (`R140/ppu_recomp_005.cpp:37283–37325`, `func_00109350`; 1.00 `func_00101BAC` at `R100/ppu_recomp_005.cpp:31141`). The loader formats `anm%05d.lzs` or `anm%05d.dat` depending on its load flag (`R140/ppu_recomp_008.cpp:25043–25066`, `func_00181438`; exact ELF strings in `animation_init_evidence.json`). The examined ANM_HI directories contain **2,301 entries / 2,056 distinct numeric anm*.lzs names**; directory duplicates reflect shipped archive content, not installation state or a proven engine maximum. Animation payload completeness, effects/attachments and memory/texture budgets were not validated.

### Secondary selector / portrait boundary

A separate static BE16 key list is initialized with **870 entries**, **869 distinct keys** (9999 repeats), byte-identical between 1.00 and1.40. Initializers: `R100/ppu_recomp_001.cpp:28778–28787`, `func_00053DEC`; `R140/ppu_recomp_001.cpp:28958–28965`, `func_000548D4`. Exact ELF VAs/file offsets/bytes are in `secondary_visual_keys.json`.

The class+`0x19E` key is conditionally normalized/variant-adjusted and searched in this list; failure returns `-1` (`R140/ppu_recomp_005.cpp:40023–40106`, `func_0010B8B0`). Unit refresh stores the result at+`0x118C` (:20295–20300 cited above). For dummy candidates, **61/66 raw +0x19E keys** occur in the list. That membership does not validate the adjusted selector for every variant.

This is a proven additional fixed selector dependency. **It is not yet proven to be a total portrait count or a complete portrait-atlas load limit.** The connection from this selector to specific face/bust texture/atlas loaders, expression variants, renderer capacity and complete portrait assets remains unresolved; do not label870 “free portrait slots.” A new class could reuse an existing key in principle, but compatibility is unverified.

## 5. Safe next research step — no implementation

Perform a **read-only typed dependency closure for the existing row366 / ID2235**, using nearby known monster rows as controls. Trace precisely which loader/bytecode fields are class IDs versus animation/secondary keys; extend the bounded scan to scoped stage/event/AI records and offline-decode the relevant artwork descriptors; finish the secondary-selector-to-portrait-renderer path. Separately enumerate *all* direct and cached class-table consumers for row-indexed capacities and create/recruit/reincarnate ID-range branches. Keep sources read-only and hash each newly consumed archive before/after.

This tests whether the promising existing placeholder is actually reachable/referenced and visually complete; **it is not permission to overwrite2235, assign a missing ID, append a row, inject data, modify a save, or launch gameplay**. Until that audit closes, recommend neither arbitrary-ID addition nor “safe dummy replacement.”

## Artifact map

- `RESEARCH_REPORT.md` — this report.
- `findings.json` — observed table counts/IDs, source refs, capacities, candidates and explicit unknowns.
- `archive_index.json`, `character_table_records.json` — directory and per-row offsets/hashes.
- `candidate_reference_scan.json`, `related_table_geometry.json` — bounded raw-reference evidence and geometry-only related-table leads.
- `animation_directory_summary.json`, `secondary_visual_keys.json`, `table_probe_notes.json` — resource-directory counts and ELF key/config evidence.
- `source_evidence.json` / `.md` — exact lifted-source excerpts and hashes.
- `input_hash_verification.json` —15archive+2ELF end-to-end hashes.
- `archive_probe.py`, `record_probe.py` — bounded read-only probes; exclusive-create scratch outputs.