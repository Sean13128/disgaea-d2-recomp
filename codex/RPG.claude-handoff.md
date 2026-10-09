# Disgaea RPG appearance importer Claude handoff

## Native-size idle frames, steady idle, Choose Color slot for new costumes — 2026-10-09 afternoon (Claude)

Owner playtest of a new import (Thunderlord Laharl, RPG 99): the costume did not appear, and the idle figure was smaller and shifted a few pixels with the cloak. Three causes, three fixes, plus a fourth found while checking the other costumes. **Nothing below is committed or pushed.**

1. **Not visible.** A profile extended from a Choose Color profile keeps `color_slots`, and classes with slots ignore the class-wide selection, so a new costume without a slot can never be shown. `d2_appearance_add.assign_color_slot` now gives a new costume the class's next free Extra color (1–4) when the profile has slots; the summary and `added.json` carry `color_slot` / `color_note`, and the workbench queue shows "Choose Color: pick Extra color N …". Profiles without slots are untouched.
2. **Shrunk idle frames.** After the whole-figure idle fix the own 512×512 sheet could not hold ten full idle frames, so Codex's `fit_overflow` scaled them (Thunderlord 0.67–0.83, Dark Santa 0.86, Pleinair 0.72, Etna 0.83–0.90) and clamped them to the cell, which also made them wander. `d2_anm_cells.plan` now retries with the sheet 2× and 4× taller (`MAX_PAGE_HEIGHT` 2048) before shrinking margins; `resize_pages` rewrites the texture header, payload offsets and payload size. **Finding:** each `sheet_refs` row is `(index×4, base, width, height, 2064, 4096)` and the renderer scales texture coordinates by that height; a taller texture with the old row renders as garbage (first test), so the row is patched too. `d2_costume_pack.structure_check` accepts a pack body whose sheets are taller than the donor's only when headers, sheet table and all non-geometry tables equal the donor resized the same way.
3. **Back idle sliding sideways.** RPG 99's `wait_back` canvases are 170×200 while the reference character's are 170×180. The canvas-mismatch fallback stood every frame on its own opaque outline (centre/bottom), so the body moved up to 16 px as the cloak changed shape. `d2_rpg_autobuild.steady_mismatched` now applies one correction per animation (same block, pose stem, flip, turn, canvas size): none along an axis whose canvas length equals the reference's, otherwise the median of the per-frame corrections. Result for Thunderlord: `[0, -10]` for all five frames; feet at the same x in every idle frame, front and back.

Verification: offline renderer `work/appearance-development/claude-resume/scripts/idle_render.py ANM_HI.dat MEMBER ID OUT.png` draws every idle moment of a built body in one character-space frame and prints the foot position; before the fix back-idle feet were at x 15/25/31/27/30, after it 18 in all five (front idle was already constant). Native hub run `runs/h03-steady` (profile `tall-check3`); **owner watched it and answered "perfect"** (2026-10-09 12:36 CDT). `d2.appearance-auto` has 19 methods (new: taller sheet keeps native size, foreign-canvas frames share one correction, pinned and multi-page pivot groups, next free Choose Color slot); pack tests cover taller sheets and a stale sheet-table height; all 24 importer/workbench/recipe/pack CTests pass; runner unchanged (`6f08e4a6…`).

4. **Cells that could not grow (found on Fuka).** `plan` skipped whole pivot groups in two cases that are in fact workable. (a) "Pivot entry is shared with a scaled, rotated or attachment transform": the pivot must stay, but growth to the right and downwards needs no pivot change, so plain-sprite cells of such a group now grow that way only (`result['pinned']`, reported as `cell_growth.right_down_only`; cells that are themselves drawn scaled, used by non-sprite keys or without art stay untouched; not in symmetric mode). (b) "Pivot group spans several pages": pages joined by a group are now planned together with one margin per group (cell keys carry the page). If one page of such a group has no room for the full enlargement, only that group is left alone and the rest is replanned. Fuka before: front idle fitted to 0.83, 16 fitted own frames, 4 skipped groups; after: every idle frame full size, only rectangles 46/47 skipped (rectangle 47 sits on a 128-pixel-wide sheet and would need 137), which are stand-in frames of her special pose (animation 7001) and are shifted up to 17 px instead of scaled. New test `test_pinned_pivots_grow_right_and_down_and_groups_may_span_pages`.

**Owner's working set rebuilt:** `work/appearance-profiles/studio-20261009-fullsize` (recipe import of his eight costumes), now the remembered current profile and the target of `Playtest Choose Color.command`. Slots: Etna 1 Liones Princess, 2 Standard RPG; Laharl 1 Dark Santa, 2 Thunderlord; Flonne 1; Valvatorez 1; Fuka 1; Pleinair 1. His save slot 01 was carried over from `studio-20261009-121051-659a299c` (the profile's fresh copy is kept under `claude-resume/`). An intermediate build without fix 4, `studio-20261009-native`, is in the Trash. Sheets made taller: Laharl page 0 → 1024, Valvatorez pages 1 → 1024 and 11 → 2048, Pleinair and Flonne page 0 → 1024, Fuka page 11 → 1024.

Local artefacts: `costume-packs/disgaea-rpg-starter-pack.d2costumepack` re-exported from the new profile (eight costumes, 3.1 MB, taller sheets; the previous six-costume pack is `claude-resume/starter-pack.before-native.d2costumepack`). The tracked recipe `costume-recipes/disgaea-rpg-starter-pack.d2costume.json` still lists six; `claude-resume/current-8.d2costume.json` is the eight-costume recipe.

Not seen in game: Fuka's rebuilt idle. It is checked with `idle_render.py` only (feet within one pixel in all twelve idle frames, full size). Two native attempts with `--scene hub --hub-character 340` on a Fuka-only scratch profile (`runs/h04-fuka`, `runs/h05-fuka`) stopped rendering right after Continue (last frame about 640, black), so that diagnostic does not work for class 340 with this save; the Laharl runs without `--hub-character` were fine. Owner asked to look at Fuka in his own game.

Cleanup the owner approved ("those can go"), moved to the macOS Trash on the Data volume, not erased: Claude scratch profiles `p1-liones`, `p2-etna2`, `p3-laharl`, `p4-laharl-grown`, `m`, `m-1..3`, `main`, `main-1..3`, `AS-save-test`, `icon-check`, `tall-check`, `tall-check2`, `tall-check3`, `fuka-check`, `pack-check-native`, `studio-20261009-native`, `20261008-171537-yukata-valvatorez`; Codex intermediates `playtest-20261008-1730-step1..4`; captured frame folders of all runs; `work/appearance-templates.old`. Roughly 80 GB returns when the owner empties the Trash. Kept: `colors-*`, the three older `studio-*` profiles, `studio-20261009-fullsize` (in use), `playtest-20261008-1730`, run logs.

Pack round trip with taller sheets: the eight-costume pack imported into a scratch profile gave byte-identical bodies, illustrations, face bank, character tables and slots. The workbench server was restarted so imports from the page use the new builder.

Open: commit and push of everything in this section (owner's word needed); the tracked starter recipe still lists six costumes.

## Published — 2026-10-09 (Claude, on the owner's instruction)

Pre-push scan (`work/appearance-development/claude-resume/prepush-scan.txt`): no images, archives, game data or credentials among the files to upload. Before committing:

- The owner's macOS user name appeared in two **unpushed** commits (`OPERATIONS.md`, `codex/DI.report.md`) and three working notes. The unpushed commits were rewritten in a temporary worktree so only those path strings changed (now `~`); authorship, dates and messages are unchanged. Old tips remain on the local-only branch `backup/pre-scrub-20261009` (do not push it).
- Nine tests and `tools/d2_rpg_poc.py` hard-coded a scratch folder on this Mac; they now use the resolved system temp folder, and `port/tests/CMakeLists.txt` gives every test a plain `TMPDIR` inside the build tree, because macOS temp paths are symlinked and the path guards refuse them. With no `TMPDIR` set, 85 of 89 asset-free tests pass; the four failures are unrelated to this work (`d2.edat`, `d2.save-import`, `d2.edat-cache` need the Python `Crypto` module, `d2.DI-ui` fails to link here).
- `tools/requirements-rpg.txt` was ignored by `.gitignore` although the guide installs from it; it is now tracked. `Playtest Choose Color.command` (points at one local profile) is no longer whitelisted.

Committed as two commits on `main`: the costume importer work, and the paused character-export notes with the October 8 `OPERATIONS.md` handoff. Costume packs, profiles, RPG assets and the game dump stay local and ignored.

## Costume packs with artwork, and file import in the workbench — 2026-10-09 midday (Claude)

Owner request: the export should also be able to carry the images, so a user receives a character pack and just imports it; packs are not hosted on GitHub, users make and exchange their own. Recipes (below) remain the no-artwork format that lives in Git.

- New `tools/d2_costume_pack.py`, format `d2-costume-pack` v1, files `*.d2costumepack` (zip): `pack.json` plus, per costume, `costumes/<class>-<id>/body.anm` (expanded body, rebound to the donor ID), `face.png` (96×96 cell cut from the face bank) and `illustration.anm` (rebound to the donor illustration ID). The manifest carries fingerprints, Choose Color slot, the D2 body fingerprint, and the recipe details when known.
- Export: `tools/costume export --with-art [--name N] [--output F] [--replace]` → `costume-packs/` (explicitly ignored in `.gitignore`). Works for every costume in a profile, including ones without an import record.
- Import: `tools/costume import FILE` accepts packs and recipes (zip signature decides). **Default profile changed for both**: it extends the profile in use (`--profile current`, falling back to `new`); `--profile new` starts from the untouched dump. `chain_import` in `d2_costume_recipe.py` is the shared chain (skip existing costumes, Choose Color slots, cleanup, restore on failure).
- Untrusted-input handling for packs: member names derived from validated IDs only, exact member set, size limits (256 MiB pack, 48 MiB per animation, 512 KiB face, 1 MiB manifest), SHA-256 per member, D2 body fingerprint must match the reader's dump, `structure_check` (reader's donor vs. pack body: everything byte-identical except pixel payload, rectangle x/y/w/h kept inside their page, anchors, and sprite keys blanked to rectangle 0), face must be a 96×96 PNG, illustration goes through the existing donor-layout check in `d2_appearance_illustration.attach`, and the locally compressed body is verified with the exact guest decoder probe when a compiler is present.
- Workbench: **Export pack (with art)** next to Export recipe; **Import a pack or recipe…** at the top of the import queue (native file chooser → job kind `pack`, persisted, with Use / Play / export buttons). Static page and script are now served `Cache-Control: no-cache` (they were cached for an hour, which hid new buttons); media stays cacheable. Server restarted on 8769 with `.venv-rpg/bin/python`.

Verification: new `port/tests/test_d2_costume_pack.py` (4 tests: structure rules, hostile archives, import chain, version/structure refusal) and two more workbench tests; all 24 importer/workbench/recipe/pack CTests pass; runner unchanged. Real round trip: `export --with-art` of `colors-20261009-frame-fit` (2.3 MB for six costumes, 3 s), then `import --profile new` into a scratch profile in 169 s without touching RPG assets; bodies 900–905, illustrations 10900–10903, face bank, character tables and color slots are byte-identical to the source profile. Scratch profile deleted, `work/appearance.json` restored. In Chrome against the live server: both new buttons render, Export pack wrote the file and showed the notice with no console errors; the file chooser itself was not driven (native dialog), the route behind it was exercised with a path (bad suffix refused; a pack whose costumes are all present fails with a clear message).

Kept: `costume-packs/disgaea-rpg-starter-pack.d2costumepack` (local only, ignored by Git) and `costume-recipes/disgaea-rpg-starter-pack.d2costume.json` (tracked candidate).

## Costume recipes (shareable export without artwork) — 2026-10-09 midday (Claude)

Owner decision: RPG sprites and anything built from them stay off GitHub; costumes are shared as **recipes**. New `tools/d2_costume_recipe.py` (format `d2-costume-recipe` v1, files `*.d2costume.json`): per costume it records D2 class and name, costume ID and display name, RPG character ID, story-art ID, face and Status crops, grow mode, Choose Color slot, SHA-256 fingerprints of the look-deciding RPG files (relative names only) and of the D2 body. No pixels, game data or local paths; `write()` refuses text containing a local path and never overwrites without `--replace`.

- CLI: `tools/costume export [--profile P] [--name N] [--output F] [--replace]` and `tools/costume import FILE [--profile new|P] [--output DIR]` (`d2_appearance_add.py` gained `build_parser()`, `export`, `import_`; `added.json` now carries an `options` block for future exports, older records are read from their steps).
- Import chains the one-command add per costume, reuses recorded crops only when the reader's RPG files match the fingerprints (otherwise automatic crops and a `different_sources` list), builds a Choose Color profile when slots are present, removes its intermediate folders, restores `current_profile` on failure.
- Workbench: **Export recipe** on completed import / Choose Color jobs (`POST /api/export {job, reveal}`), saving to `costume-recipes/` and revealing the file in Finder. Server restarted on port 8769 with the new route.
- Tracked content: `costume-recipes/README.md` and `costume-recipes/disgaea-rpg-starter-pack.d2costume.json` (the six current costumes, 7 KB). `.gitignore` whitelists only `*.d2costume.json` and the README in that folder.

Verification: `port/tests/test_d2_costume_recipe.py` (9 tests, registered as `d2.costume-recipe`) plus a workbench export test; all 23 importer/workbench/recipe CTests pass; runner unchanged (`6f08e4a6…`). Real round trip: exporting `colors-20261009-frame-fit` and importing the recipe into a scratch profile took 239 s for six costumes and produced byte-identical body and illustration members (900–905, 10900–10903), face bank, character tables and color slots; the scratch profile was deleted and `work/appearance.json` restored. The Export recipe button was clicked in Chrome against the live server: file written, notice shown, no console errors.

Still to do before the push the owner asked for: scan everything that would be staged for stray images or game data, decide which `codex/*.md` and launcher `.command` files belong in the repo (they contain local absolute paths), then commit and push on the owner's word. Not done: a recipe **import** button in the workbench (CLI only), and cleanup of old test profiles under `work/appearance-profiles/`.

## Choose Color list icons — 2026-10-09 morning (Claude)

Owner reported the Choose Color rows still showed the retail face for every entry. Cause: the rows are drawn by the generic list path (`func_00068FF0` → `func_00094B00` → `func_0015AD84` → `func_00149E80`) with only face identity and color, no unit or class scope. Fix in `port/src/d2_appearance_trace.cpp`: `color_slot_class_for_face(group, face)` resolves the class when exactly one slot-managed class owns the face, and `func_00149E80` uses it when neither a unit nor a class scope is set. Appended costume rows that copy the donor face are ignored; other groups, other faces, unassigned colors and costumes without an icon stay retail. New assertions in `test_native_colors_select_independent_costumes_without_unit_writes`. All 22 importer/workbench CTests pass. Runner rebuilt: SHA256 `6f08e4a6344427aeac5c663cee772cf4949fb1790ae1e54332d69aea415b77d0`; the previous binary is kept as `port/build-rpg-import/DisgaeaD2Recomp.before-icon-d9a2e30a`.

**Owner-confirmed in game (2026-10-09 08:20 CDT, `Playtest Choose Color.command`)**: Choose Color row icons now show the costume faces, and the enlarged ("extended") costume art displays as intended. Claude's own scripted attempt to reach the Assembly menu did not get past the clerk, so there is no captured frame; the confirmation is the owner's.

Coordination: Codex was editing `tools/d2_rpg_autobuild.py` / `tools/d2_appearance_add.py` and writing `work/appearance-development/overflow-20261009/` at the same time. Claude did not touch those files or rebuild any costume profile this morning. Disposable profile `work/appearance-profiles/icon-check` and run `runs/g01-icons` can be deleted. Nothing committed.

## October 9 — oversized frame clipping fixed

Owner confirmed the native Choose Color workflow works; Assembly screenshot
showed Santa Laharl scarf clipped in the preview. Existing own-cell growth ran
out of atlas room and cropped overflow. `tools/d2_rpg_autobuild.py` now fits
remaining oversized art inside the one-pixel transparent rim after cell growth,
sharing scale across related numbered frames. Grown own frames and fixed shared
frames are grouped separately so successfully enlarged art stays at native scale.
Fit is about source pivot, clamped to cell bounds; affected frames may be smaller.
All 6 costumes rebuilt with zero clipped pixels, exact guest decoder matches.
15 auto-pipeline methods and palette/retarget CTests passed.
New private profile `colors-20261009-frame-fit/stage.json`, fixed launcher
`Playtest Choose Color.command` updated. Latest closed source profile HDD0 copied
byte-identically (495 files); source assets/profile retained. Evidence under
`work/appearance-development/overflow-20261009`, plus profile frame-fit-refresh.
No native runner code/build changes needed. Future imports use this fix.

## Native Choose Color implementation — 2026-10-08 late evening

See `codex/RPG.color-slots.md`. The research runner now accepts explicit
`color_slots` assignments (class_id/color/costume_id). Unit color +0x1183
routes body, face and illustration; explicit menu colors route class portraits
and preview constructors, including wrapper caller 0x2A274. Native cursor
func_0026C044 rebinds its preview via 0x2A25C before the retail palette update.
Mac Appearance picker is disabled for assigned classes. No source save patch.
Workbench completed imports now offer Build Choose Color profile, then show
slot mapping and Play Choose Color profile. Stable existing slots are preserved;
overflow beyond four imported costumes raises an error. Retail menu labels remain.

All 22 related CTests passed (production binding five methods; workbench twelve).
Real browser check created `colors-20261008-220015-baa8f3e1/stage.json` with six
assignments, no JS errors. Fixed launcher `Playtest Choose Color.command` uses
`colors-20261008-native-menu/stage.json`. Native Metal smoke reached the castle
showing Original Laharl. Assembly cursor/confirm/save-reload still unverified.
Runner SHA256 d9a2e30afb11898a97faabf1367a4cf94c468f33195e56f33987d234ae829952.
Workbench server restarted on 8769 (exec session 11997). Current default profile
was preserved; generating a slot profile does not remember/select it implicitly.
Keep this experimental until native menu and persistence checks are completed.

## Sprite workbench — 2026-10-08

The owner requested GUI tools to index RPG and D2 assets, compare sprites side by side and choose imports. Implemented local browser workbench: `tools/d2_sprite_workbench.py`, `tools/sprite_workbench/`, `tools/sprite-workbench`, and `Sprite Workbench.command`. See `codex/RPG.workbench.md` for usage, support boundaries and verification. Source libraries persist under `work/sprite-workbench/`; imports create new `studio-*` private profiles. `d2_appearance_add.extracted` now keys caches by source masters and selected bundle hashes to prevent cross-dump ID collisions. This GUI uses the established importer; it does not implement native Choose Color costume selection. Verified against 489 RPG characters and 558 D2 records. Full 22-target asset/importer/workbench suite passes (the workbench target contains nine methods). Browser tests exercised search, side-by-side sprites, pose matching, atlases, palettes, persisted review and explicit selection with no JavaScript errors. A real GUI import created RPG Fuka (body 905) in `work/appearance-profiles/studio-20261008-190618-024f3509/stage.json`, now the current profile after testing “Use for next playtest”. It retains the five earlier costumes and both save slots match the current playtest source profile; the slot-01 hash differs from the historic initial-save hash because the user subsequently played/saved. Native Fuka gameplay remains untested.

## User intent — costume selection through Choose Color (2026-10-08)

The owner wants imported appearances to replace the existing per-character color variants in the in-game **Choose Color** menu. Each character should have multiple selectable appearances (for example, Original, Dark Santa Laharl, and additional Laharl costumes), selected through that normal in-game workflow. The separate macOS **Game → Appearance** picker, changing the castle leader, and terminal commands are the current interim implementation; they are not the intended final user experience.

Future implementation should route each choice consistently to its body, face icon, Status illustration, and menu preview, and investigate how to preserve the selection through the native save/load workflow. Start by assessing replacement of the existing five menu choices; the desired number of costumes per character is not fixed at five. Expansion beyond those entries and engine/save limits remain unverified. Do not describe native Choose Color costume integration as already implemented or promise an unlimited number of choices.

This records the owner's direction for future work. This documentation request does not authorize starting implementation, a build, installation, commit, or push.

## Codex playtest follow-up — 2026-10-08 (supersedes profile/build status below)

User requested the latest playtest build, then reported mixed icons and previews in Dark Assembly / Choose Color. All five costumes were rebuilt using the post-idle-fix `survey3` templates into `work/appearance-profiles/playtest-20261008-1730/stage.json`, now selected by `work/appearance.json`. Prior templates are backed up under `work/appearance-development/codex-playtest-20261008-1730/previous-templates/`. Launcher: `Playtest RPG Costumes.command`; original installation and saves untouched.

Runtime follow-up: scoped synchronous class face routes at 15B22C/15B390/15B4EC/15B5E0; prevent unbound Extra color 4 (x=384) from reading an unrelated appended costume cell in the expanded group-0 bank; allow validated class-only menu preview aliases at construction callsites 36108/382B8, with unique donor/visual-row validation and scoped donor inheritance. New regressions cover all five colors, another class, original bank/other group, missing visual metadata, and unrelated preview callsites. Full 21-target importer suite passes. Rebuilt runner SHA256 `2b3615f130877be66f1b311eda65eac53efded6e312434edd1929293d5805fd9`.

Native Metal check loads title → Continue → castle, shows imported Laharl and permits movement/NPC interaction. The bounded check did not reach Assembly/color picker; their rendering remains pending user retest, despite passing targeted regression tests. Evidence and build receipt: `work/appearance-development/codex-color-routing-20261008/`. The initial sandbox run used the null backend (no Metal device) and is not visual evidence. No commit, push or primary installation.


## Current state — 2026-10-08 evening (Claude session; supersedes older sections below where they differ)

The user resumed the work with the goal: finish custom appearances and make new ones quick to add. The session stopped at the usage limit with one fix not yet applied to the built profiles. Short user guide: `codex/RPG.costumes.md`.

**What now exists**

- One-command pipeline: `tools/costume add --character Etna --rpg-character 84 --display-name "Liones Princess Etna" --story-character 13201 --select` (wrapper around `tools/d2_appearance_add.py`; also `find`, `list`, `choose`, `play`). No manual pose mapping. 30–80 s per costume. New files: `tools/d2_rpg_template.py`, `tools/d2_rpg_autobuild.py`, `tools/d2_anm_cells.py`, `tools/d2_appearance_add.py`, `tools/costume`, `tools/data/d2_humanoid_common_template.json`, `tools/data/d2_rpg_reference_map.json`, `port/tests/test_d2_appearance_auto.py` (13 tests, registered as `d2.appearance-auto`).
- Runtime fix in `port/src/d2_appearance_trace.cpp` (`func_00029804`): at caller `0x000A8FE0` the saved r29 unit is authoritative and a unit link of another class is never trusted. Before it, the target of an attack close-up kept original art. Covered by an added case in `test_d2_appearance_binding.py`. An "unbound visual" diagnostic line reports any bound class constructed without a resolvable unit.
- `tools/d2_appearance_run.py --save-when-hl VALUE` (castle scenes, `AS-`/`AF-` profile copies only) with a test.
- Research runner rebuilt: `port/build-rpg-import/DisgaeaD2Recomp` SHA256 `64b6684a649fe25f9942a9b8ceaac9c05e4fec2d61cdddf936c7944c0ee04d47`. The handoff-time binary is kept beside it as `DisgaeaD2Recomp.handoff-0d7f4815`.
- Profiles in `work/appearance-profiles/`: `main` (Liones Princess Etna 900/10900, Standard RPG Etna 901, Dark Santa Laharl 902/10901, Apprentice Angel Flonne 903/10902; all with face icons) and `20261008-171537-yukata-valvatorez` (= main + Yukata Valvatorez 904/10903, added through the wrapper as a timing proof). `work/appearance.json` points at the Valvatorez profile as current.

**Native acceptance on `main` (2026-10-08, runs `work/appearance-profiles/runs/n06…f05`)**: normal start title → Continue → castle with field control; castle idle/walk for Laharl, Etna, Flonne; Status illustrations and list icons for all three; battle deploy/move/HUD icons; attack close-ups with attacker and target in costume (Flonne→Laharl, Etna→Laharl, Laharl counters); battle → Give Up → title → Continue → castle in one process; save written by the test hook on disposable copy `AS-save-test` is byte-identical to the source save and reloads with costumes bound. Yukata Valvatorez renders in the castle (`f05-valvatorez`). Normal Dimension Guide travel and a victory return are still untested; Give Up resets to title by design.

**Unfinished — do these first**

1. `tools/d2_rpg_template.py` gained `idle_composites` (idle body plus separately keyed cape/scarf compared as a whole figure) and a stay-in-idle-set fallback, after Valvatorez showed wrong idle frames. Unit test passes. **`main` and the Valvatorez profile were built before this change.** `work/appearance-templates/` still holds old-code templates for 10, 30, 50, 230 (earlier ones are in `work/appearance-templates.old/`). Delete those templates, rebuild the profile (`work/appearance-development/claude-resume/scripts/build_final.sh NEWTAG` rebuilds the four costumes from the untouched dump; then re-add Valvatorez), and repeat a short castle + battle check, especially Laharl and Valvatorez idle.
2. New-code templates for all 20 mapped characters are in `work/appearance-development/claude-resume/survey3/` (summary: `scripts/survey.py survey3`). They can be copied into `work/appearance-templates/` to make first adds faster. Remaining inexact idle: Asagi (all 12, IoU 0.70–0.80), Emizel (4), Pure Flonne (1), Fenrich (2). Rainier and Hoggmeiser have only 25–26 exact frames and should be treated as weak.
3. Re-run the full suite: `ctest --test-dir port/build-rpg-import -R 'd2\.(rpg|appearance|native-lzs)'` with `TMPDIR=/Volumes/Data/ai-tmp/claude/d2-appearance-resume/tmp` (21/21 passed before the template change; only `test_d2_appearance_auto.py` was re-run after it).
4. Clean up with the owner's agreement: `work/appearance-profiles/{p1-liones,p2-etna2,p3-laharl,p4-laharl-grown,m,m-1,m-2,m-3,main-1,main-2,main-3,AS-save-test}`, `runs/*/frames`, `work/appearance-templates.old`, `work/review/step-*.png`. Each profile is 2.5–3.3 GB.
5. Nothing from this session is committed. Local commit `5ebb05e` ("Checkpoint: alternate-appearance importer") predates these changes; origin is 3 commits behind. `.gitignore` now whitelists `tools/costume` and `tools/data/`. Unrelated uncommitted work (`OPERATIONS.md`, `codex/CE.*`, SDK edits) was left alone. Do not commit, push or install into the primary app without the owner's say-so.

**Known limits and art gaps**: see `codex/RPG.costumes.md` (one active costume per character, castle-only live switch, cut-in/dialogue portraits original, unique special poses fall back to a standing frame, DLC/generic/monster classes unsupported).

**Working method that held up**: write scripts with the Linux-side shell under `work/appearance-development/claude-resume/scripts/` and run them on the Mac by path; long jobs with `nohup … &` and poll logs; `native.sh STAGE OUT [options]` for bounded runs, `seq.sh RUN "MASK:WAIT …"` / `press.sh` for interactive stepping (frames land in `work/review/`), `zoom.py` for contact sheets, `copyprofile.sh SRC DST` for disposable copies, `savecmp.py` for save comparison. The game ignores SIGTERM; stop a run with `kill -9` on the game PID (the Python launcher then writes its result). The Claude usage meter could not be read by `agent-usage`; no Codex allowance was used.

---

Updated 2026-10-08. Recipient: Claude continuing work in `/Volumes/Data/Applications/QuiverLauncher/Apps/Disgaea D2-RE`.

The goal is to import Disgaea RPG characters into Disgaea D2, initially through alternate appearances. A functioning importer and native proof of concept exist for Liones Princess Etna and Standard RPG Etna. Full gameplay acceptance, support for additional characters, adding new playable classes, and original PS3 integration remain incomplete. Do not treat the two Etna costumes as completed general character support.

## Pause and operating constraints

The user explicitly paused the goal. This handoff does not authorize resuming implementation or native experiments; wait for a user instruction to resume. No importer or native test/play processes remained running at the pause check. All latest runs were terminal.

Keep at least **60% of the weekly usage allowance remaining**. Last verified allowance was **72% remaining**, a historical measurement. Run `agent-usage` before expensive work and inspect account limits if needed. The CLI has mislabeled the 10080-minute weekly window as a five-hour window; identify the weekly window by duration. Missing or stale values are unknown. If usage cannot be verified, leave expensive work stopped and report uncertainty. Do not consume a reset.

Preserve unrelated work, especially `OPERATIONS.md`, `codex/CE.*`, other builds and SDK changes. No primary installation, commit or push has been performed. Use new private profiles and output directories for experiments. Use a unique disposable directory under `/Volumes/Data/ai-tmp/codex`, checking free space before bulky writes. Previous disposable work is in `/Volumes/Data/ai-tmp/codex/d2-live-01a119f7`; do not delete unrelated files.

## Current implementation and acceptance

| Area | Implemented and verified | Remaining limits |
| --- | --- | --- |
| Source extraction | Original RPG Unity bundles, sprites and animation-reference timelines extracted; source manifests retained. | Source coverage does not prove D2 action completeness. |
| Sprite conversion | Pose mapping, mirrors/quarter turns, coordinated source colors, D2 body authoring and exact decoder validation. D2 animation structures and dimensions preserved. | Full actions, facings and attachments need native tests. Two named source pose gaps remain. |
| Appearance catalog | Private renderer-only catalog with Original, Liones and Standard; independent resource/visual rows; remembered next-launch selection and immutable launch snapshots. | One choice per class, rather than per individual unit sharing that class. No guest Dark Assembly costume integration. |
| Live switching | Castle Original/Standard/Liones switching and restoration, with scoped unit/position/camera preservation checks. | Battle and other-scene live refresh need further acceptance. |
| Overworld | Controlled Etna idle and cardinal movement accepted on diagnostic castle map30001. | Normal Etna leader selection, broader facings, transitions and separately loaded visuals remain required. |
| Battle | Imported deployment and movement; selected equipment interactions; Prinny Raid and limited spear attack clone routing. | All actions/weapons/damage reactions are not validated. Misses and unusually high enemy HP also occur in original controls; cause unresolved. |
| UI face icons | Independent Liones and Standard cells in one480×3840 bank, rendered in castle Characters and battle UI; original party icons preserved. | Other UI consumers, face groups, characters and wider native banks unvalidated. |
| Status illustration | Correct Liones illustration10902 rendered through normal Status menu. Standard uses original Status illustration. | Other portraits, attack-entry art, voice and secondary assets require coverage. |
| Normal startup | Title Continue → copied postgame save → castle Characters → Liones Status → main castle menu, without warp or leader override. | Final Cancel sequence leaves main menu open. Normal field control, battle travel and new gameplay save/reload remain unproven. |
| Preservation | Recorded source/private HDD0 hashes unchanged; original atlas cells preserved; disabled/missing optional metadata falls back. | No new gameplay save was written in the latest acceptance. Appearance-setting persistence is separate from gameplay save/reload. |
| Platform | Working native research port using the inspected1.40 ELF. | Original PS3 packaging and new playable classes remain unproven. |

Overall progress: usable, partially validated Etna appearance importer. Remaining work is chiefly full gameplay/asset coverage, generalization and platform integration; a percentage would imply precision that the outstanding work does not support.

## Current profile and source identity

Working manifest: `work/appearance-development/etna-two-face-inventory-native/stage.json`. Liones is enabled/default.

- Liones: body901, face cell384,0, Status10902.
- Standard RPG Etna: body902, face cell384,96; original Status10030 fallback.
- Legacy resource900 is a prior Liones revision without imported face metadata.
- Both authored faces share the480×3840 bank. Two cells are accepted natively; larger banks are not.

The requested character is **Liones Princess Etna**, RPG battle character84. Desktop `Majin.gif` is a separate Disgaea1 sheet and must not be used for this target. Original RPG assets were downloaded and extracted by the user; retained exports/manifests identify the assets used by the tools.

Do not infer story art identity from battle ID. Story master8401/img_base84 is an event Nekomata and was rejected. Correct Liones art is story master13201/img_base132, Etna in Elizabeth’s costume, exported to `work/rpg-original-etna84-story132-corrected`. Standard Etna source is character6 in `work/rpg-reference-etna6`; its authored face uses `front/Sprite_6799384036533390439_stand.png`, crop16,16,116,112.

## Files and technical boundaries

Read `codex/RPG.usage.md` for exact commands, `codex/RPG.import-progress.md` for chronological evidence and corrections, `codex/RPG.import.report.md` for status, and `codex/RPG.character-plan.md` for coverage requirements. Older entries are historical; later acceptance supersedes them.

- `tools/d2_appearance_run.py`: bounded native observations, input/captures, private roots and immutable snapshots. `--scene normal` clears inherited warp/leader/live-test/movie-skip flags and rejects incompatible scene options. Headless save picker, muted audio and read-only tracing remain host diagnostics.
- `tools/d2_appearance_play.py`: ordinary interactive private launch workflow.
- `tools/d2_appearance_inventory.py`: private multi-costume catalog/profile construction.
- `tools/d2_face_atlas.py`: packed `txf\0` → expanded TXF0 ARGB8888; validates headers/channels/dimensions. Allocates blank96px cells in extra columns while preserving prior pixels. Occupied coordinates must be supplied. Fixed native row lookup makes extra-column authoring preferable to appended rows.
- `tools/d2_appearance_face.py`: attaches an authored face to a copied private profile, preserving existing cells/overlays and checking provenance/save hashes. Existing face metadata cannot silently be overwritten; deliberate revision workflow remains future work.
- `port/src/d2_appearance_trace.cpp`: guarded actual-unit face routing plus explicit class-scoped queued UI routing. Class constructors19E544/19E6A8 identify ownership; configuration193AC0 and draw1964C0 validate owner/callback/slot/class/face/visual/bank identity. Do not replace these guards with global face-ID substitution or guessed unit pointers.

The observed face columns select **native color variants**, not proven expression animation. Imported icons use fixed source colors, consistent with body palette policy. Old artifacts may retain obsolete expression terminology.

Native unit stride is0x1A60; class1158, cached record115C, color1183, body slots11D8/11DA. Character records have BE count558, header4 and stride676; class ID194, body196, face19E, visual aliases1BC/1BE. Current catalog bounds and asset-authoring capacity do not establish native engine limits. Secondary body31, character-specific page9 and compound40030 must not be mistaken for the Status illustration.

## Retained evidence and validation

Under `work/appearance-development/etna-two-face-inventory-native/`:

- `standard-two-face-castle-native-01`: Standard castle icon and original Status fallback.
- `liones-two-face-battle-native-02`: Liones battle icon and corrected Status remain intact after second-cell attachment.
- `standard-two-face-battle-native-03`: Standard battle body and separate imported UI icon.
- `normal-startup-route-native-04`: normal Continue, loaded-save notice, Laharl castle lead and imported Characters icon.
- `normal-menu-status-native-05`: normal corrected Liones Status and return to main castle menu.

Retain result/evidence JSON, immutable snapshots, runtime logs, pad audits and reviewed PNGs. Terminal raw PPM captures were removed to reclaim space. Latest runs ended through bounded timeout/forced termination; do not claim graceful shutdown.

Prior full importer suite passed23 CTest targets. Two-face attachment/atlas checks passed three attachment and four atlas test methods. The latest normal-scene runner regression passed. Documentation update passed `git diff --check`. These are recorded results, not checks newly rerun by this handoff.

Latest normal runner SHA256: `0d7f4815cdcec6c001cc546aa8adc69bbd3f64169aae4cafdb069aea6eb4184e`.

Normal-run immutable snapshot SHA256: `8057b5355a545d1d3aca3ba685092bef83e732f61eb1fccd5a78896ec67dc096`.

ELF: `work/v140/EBOOT.elf`, SHA256 `0ec183e580a270b0bb1b3a554794a9e4ec2d57a2be251ebdcf81fe21b78d225c`.

Source gameplay `SAVEDATA.DAT` SHA256: `9f5a847eb6f1804536986a93682a8304cd613f3d3ad4c702c6d087ba4e27fc30`. Latest normal acceptance checked2094 recorded source/private HDD0 files without changes.

## Recommended work after explicit resume

1. Verify fresh weekly usage and current profile/evidence. Avoid rebuilding or repeating accepted tests without a new reason.
2. Validate ordinary Etna base control through Dark Assembly. The [official NIS/Prima checklist](https://nisamerica.com/DisgaeaD2_free_Prima_checklist/Disgaea_checklists_V4.pdf), “A Main Character Is You!” row, specifies Episode3 availability,10Mana and no senate vote. Inspect actual menus rather than guessing controller shortcuts.
3. Validate normal castle → battle → castle, including appearance continuity, Original restoration and field control after menus close.
4. Inspect private save-directory routing before writing a new gameplay save; `PS3_SAVEDATA_DIR` selects a specific slot. Validate save and reload in isolated copies, preserve the source and distinguish expected private writes from accidental source changes.
5. Complete D2 actions, facings, weapons and required overworld/secondary/companion/event assets. Source-reference coverage69/71 has gaps `front/stand` and `front/attack_arrow02`; explicit reviewed holds exist for two idle gaps. Test actual native action behavior rather than counting mapped poses.
6. Import another character after auditing its donor-specific animation/asset requirements. Validate other face groups and any wider banks needed. Keep confirmed runtime limits separate from authoring limits.
7. Investigate new playable class insertion and original PS3 integration as separate unresolved feasibility branches. The current successful appearance route does not establish either.

Update acceptance records after each material result. Preserve failed experiments and label assumptions, blockers and platform scope explicitly. Continue the alternate-appearance route unless the user changes priorities.
