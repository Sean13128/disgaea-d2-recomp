# CE — read-only character/artwork exporter

## Current status — October 8, 2026: PAUSED / INCOMPLETE

The owner requested that all subagents stop. The exporter worker was interrupted and its background real-data export process was terminated. No workers remain; no restart or continuation is authorized. This report update preserves the handoff, not a completed export.

- Both Desktop folders, `Disgaea D2 Character Research - 2026-10-07` and `Disgaea D2 Character Research - 2026-10-07 - verified`, are partial. Inspection found only `raw`, `png`, `anm_metadata` and Finder metadata at the top level, with no final manifest. The `- verified` name is not supported by completed verification. Files were left unchanged.
- The first run timed out; its retry was still running when the owner stopped the worker. Final structured dump, mappings, end-to-end source-hash checks and real-export verification have not been accepted. Do not represent the fixture passes below as a complete export or as verification of the final draft after subsequent optimization.
- `tools/d2_character_export.py` and this report are uncommitted; `tools/tests/test_d2_character_export.py` exists but is ignored by `.gitignore:73`. The exporter has no independent security/logic review yet. No app build/publication, game launch, staging, commit or push was performed for this documentation update.
- Completed capacity research is preserved separately in `CE.constraints.md`; `CE.research-evidence.zip` contains the original report, indices, findings, source excerpts, recorded verification and bounded probes. The ZIP is retained locally but ignored by `.gitignore:13`, so it is not yet versioned and must be explicitly considered in any later publication/review. Merely preserving the probes does not authorize running them.

### Documentation audit

Checked 15 research-artifact hashes against the research manifest, matched 33 stored source excerpts and their whole-file hashes to current local sources (ignoring blank margins around excerpts), and checked the evidence ZIP's integrity and every archived file against the originals. The research worker described 34 excerpts, but its actual source-evidence array contains 33; the parent audit confirms 33, not 34. Recorded before/final hashes match for 15 archives and two ELFs; original game archives/ELFs were **not** rehashed during this documentation-only update. This is a documentation/evidence check, not independent verification of every reverse-engineering conclusion or the unfinished exporter. No saves were accessed.

### If the owner later requests continuation

First inspect the draft and partial outputs; do not blindly rerun into either existing folder. Bound the expensive decoding work, provide useful progress/timeout behavior, and test the current implementation before a fresh full export. Require a completed manifest, programmatic coverage/count checks, before/after source verification and independent review before marking the Idle item complete. Keep source game files/saves read-only; no injection is authorized. No next task starts automatically.

Scope: tools/d2_character_export.py, tools/tests/test_d2_character_export.py, this log, fresh Desktop output; scratch probes only in ~/.hermes/cache/scratch/d2-character-export. No game launch, saves, SDK/port edits, staging, commits, network asset upload or injection.

## Work log (incremental)
- Read MEMORY.md, OPERATIONS.md Idle export item, codex/common.md, maintenance/TDD skills; repository status initially clean. Graphify graph absent; graph generation is outside permitted write scope, using direct local source inspection.
- Inventoried disc START.dat + START_1..6 and ANM_HI.dat + ANM_HI_1..6. Actual installed update is port/hdd0/game/BLUS31313/USRDIR/Data/START_7.dat, not NPUB31321; matching update-package copy also present. DLC Data directories contain flag subdirectories; no flags/EDAT contents or credentials opened. START_7 contains mitem.dat and saveicon.dat, no char.dat.
- Verified NISPACK/TXF basis in port/src/d2_items.cpp:131–160. Verified actual class lookups func_0033FBB8 (1.00), func_0034F8D8 (1.40): class ID at record +0x194, stride 0x2A4; do not confuse ID with row index. Loader/name/art consumer tracing in progress.
- Archive inventory RED (missing nispack) → GREEN; character record RED (missing characters) → GREEN; archive corrupt/truncated/table-overlap tests pass.
- TXF PNG slice: RED `TXF PNG decoder missing`, then GREEN 4/4. Verified BE ARGB1555 and exact transparent pixel RGBA fixture.
- dat LZS slice: RED `source-backed dat LZS decoder missing`, then GREEN 5/5. Actual 1.40 func_001840E0 plus reversing helper func_00161F34 and wrapper +4 prove LE lengths, escape byte, distance adjustment, overlap copies. Strict expanded bounds and exact byte count.
- ANM indexed pages slice: RED `ANM page decoder missing`, then GREEN 6/6. Local header/offset/texture-count/palette-count/payload evidence supports empirical ANM indexed pages (not a proven lifted SPU/job decoder); all exact header texture×palette combinations exported, never guessed active colors or assembled frames.
- Source-field artwork mapping slice: RED `lifted body field missing`, then GREEN 7/7. +0x1BC/+0x1BE consumed by 1.40 func_00109E44; exact anm%05d.lzs resource stem, not row index or class-ID fallback. Runtime selector/overrides/active archive remain unknown.
- Artifact slice: RED `export orchestrator missing`, then GREEN 8/8 (real fixture export, PNG+JSON+CSV+raw records, verifier, unchanged source hash, traversal-like member name safe).
- Output safety slice: RED budget exception was ValueError (could be mistaken for unsupported decoder), changed to OSError so output failure propagates; final GREEN 9/9. Existing output, overlap, symlink sources/ancestors and EDAT paths refused. Ancestor/leaf symlink checks plus O_NOFOLLOW and exclusive file creation; deterministic/hash paths only.
- Discovery: 16 archives (14 disc + installed START_7 + matching update-package copy); five Data roots checked without traversing flag, savedata, SOUND or patch_licence. No loose non-EDAT DLC data. Source game archive bytes ~713 MB.
- First full Desktop run exceeded tool's 420-second foreground wall timeout during a000 ANM_HI.dat. That process stopped; partial folder has no manifest and is NOT a completed export. The worker recorded 430,593,136 bytes at that point. A retry followed optimization of bounded LZS overlap copying; that retry was later terminated at the owner's stop. Final completion/verifier evidence was not obtained.
