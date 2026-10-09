# Adding Disgaea RPG characters to Disgaea D2

## User intent — costume selection through Choose Color (2026-10-08)

The owner wants imported appearances to replace the existing per-character color variants in the in-game **Choose Color** menu. Each character should have multiple selectable appearances (for example, Original, Dark Santa Laharl, and additional Laharl costumes), selected through that normal in-game workflow. The separate macOS **Game → Appearance** picker, changing the castle leader, and terminal commands are the current interim implementation; they are not the intended final user experience.

Future implementation should route each choice consistently to its body, face icon, Status illustration, and menu preview, and investigate how to preserve the selection through the native save/load workflow. Start by assessing replacement of the existing five menu choices; the desired number of costumes per character is not fixed at five. Expansion beyond those entries and engine/save limits remain unverified. Do not describe native Choose Color costume integration as already implemented or promise an unlimited number of choices.

This records the owner's direction for future work. This documentation request does not authorize starting implementation, a build, installation, commit, or push.

October 8, 2026. Target: this native macOS recompilation of BLUS31313, primarily version 1.40.

**A conversion pipeline is feasible. A complete playable addition remains unproven.** The actual lifted 1.40 character binder and lookup accept an appended 559th definition in an isolated executable test. D2 therefore does not require replacement merely because its shipped character table has 558 rows. Recruitment, animation composition, dependent selectors and save compatibility still need work. The simplest first gameplay experiment is an Etna appearance replacement in an isolated content overlay, retaining her existing gameplay dependencies. An independent Liones Princess Etna would follow after those dependencies are audited.

The supplied RPG sheet supports an offline one-pose conversion experiment, which passed. It is not an installed mod or a playable character. All installed content, saves and runtime code remain unchanged. The source members used in the experiment were reread and compared byte for byte.

**Updated first target: an alternate appearance for existing Etna.** A follow-up isolated test confirms that the actual body-selection function can choose a second resource while preserving her class ID. Validate this existing selector and menu path before using a whole-resource replacement or appending a definition. The findings and revised acceptance criteria appear below.

**Overworld requirement (user clarification):** Every imported appearance must cover its hub/castle/field sprites as well as battles. Inspect the actual overworld resource/actor paths; convert any separately loaded body, character-specific or companion art that those paths require. Native acceptance must show overworld idle, walking and available facings, scene transitions, and restoration of original artwork. Existing idle/walk mappings and battle screenshots are insufficient evidence for this requirement.

## Available files and export completeness

The two Desktop folders are interrupted artwork exports. Neither contains `manifest.json`, `characters.json`, or a hash-named raw copy of any of the four examined `char.dat` payloads. The name “verified” does not establish completeness.

| Desktop folder suffix | Raw blobs | Metadata blobs | PNG files | Approximate payload bytes |
| --- | ---: | ---: | ---: | ---: |
| `2026-10-07` | 448 | 418 | 14,910 | 430,593,136 |
| `2026-10-07 - verified` | 1,726 | 1,630 | 39,253 | 1,437,065,952 |

The PNGs are texture pages, including palette alternatives, rather than reconstructed animation frames. Their filenames are content hashes. Metadata blobs retain binary ANM prefixes, not JSON animation descriptions. Four selected resources were matched against freshly decoded source archives; every present sample matched its expected SHA256. This is a sample audit, not certification of every exported PNG. Etna’s body member, metadata and first page are present and match in the larger folder. Some PNGs exist even where the corresponding raw member is absent because identical page content can occur in multiple resources.

The selected source is `~/Desktop/PC _ Computer - Disgaea RPG - Unique Characters (Humans) - Liones Princess Etna.png`, an 856×9198 RGBA sheet, SHA256 `8f9170a4e3b659b718a3e82f8083147a31de4982eac276ba1d9abf4290701ae2`. Its visible labels distinguish front and back views, standing, waiting, walking and attack poses, including separate hand or weapon parts. These labels help classification but do not supply timing, pivots or D2 action indices. The black cell backgrounds and blue labeling background are opaque. `Majin.gif` is excluded; the user identified it as a separate Disgaea 1 sheet.

Fresh inventory and sample hashes: [inspection.json](</Volumes/Data/Applications/QuiverLauncher/Apps/Disgaea D2-RE/work/d2-rpg-poc-2026-10-08/inspection.json>). Earlier static research: [CE.constraints.md](</Volumes/Data/Applications/QuiverLauncher/Apps/Disgaea D2-RE/codex/CE.constraints.md>), backed by the local `codex/CE.research-evidence.zip`.

## Confirmed formats and field meanings

| Layer | Confirmed representation | Remaining work |
| --- | --- | --- |
| START and ANM_HI archives | NISPACK: 16-byte header; BE32 entry count at +12; 44-byte directory entries with 32-byte name, offset, size and one retained unknown word | Establish active archive precedence; preserve directory order, alignment and unknown words when repacking |
| Character definitions | `char.dat`: BE16 count, four-byte header, 676-byte records | Complete gameplay schema and audit every consumer before append deployment |
| Compressed artwork | `.lzs` with `dat\0` signature; little-endian expanded size, packed size and escape marker; literals and overlapping backreferences | A production compressor and guest-loader validation |
| ANM textures | Empirically decoded indexed format 9: one byte per pixel, associated BE ARGB8888 palette data | Frame rectangles, offsets, transformations, layering, durations and events are not decoded |
| TXF image format 0x0B | BE ARGB1555 with 16-byte header; 5 bits per RGB channel and binary alpha | Suitable for the tested standalone image route; it is not the body ANM format |
| Other asset containers | Prior exporter retains unsupported PAK, OBF, FFM and other TXF formats raw | Decode only when an actual dependency requires them |

NISPACK and TXF are corroborated by [the native reader](</Volumes/Data/Applications/QuiverLauncher/Apps/Disgaea D2-RE/port/src/d2_items.cpp:131>). LZS is supported by lifted `func_001840E0` and its wrapper/reversal helper; ANM texture parsing is empirical and has not been shown equivalent to the guest conversion jobs. [The exporter](</Volumes/Data/Applications/QuiverLauncher/Apps/Disgaea D2-RE/tools/d2_character_export.py>) records that distinction.

Four disc archives contain `char.dat`: START, START_1, START_2 and START_4. Each has 558 unique IDs and length 377,212 bytes, exactly `4 + 558 * 0x2A4`; there is no uncounted row slack. The first three are identical. Earlier research identifies 100 changed rows in START_4, with the same ID set/order. The examined installed START_7 has no character override. Active runtime precedence is still unresolved.

Confirmed record fields are class ID at +0x194, signed animation-base selector at +0x196, secondary visual key at +0x19E, body resource fields at +0x1BC/+0x1BE for the traced selector cases, name at +0x1FC and title at +0x230. Other fields must remain byte-preserved until their consumers identify them; they cannot safely be labeled as arbitrary stats or skills from appearance alone.

Etna, row 2 / ID30, has body fields `[30, 0]`. Her body resource is **`anm00030.lzs`**: nine 512×512 pages, one 512×256 page and five 256-entry palettes, giving 50 exported page/palette combinations. Its source offset is 164,528,128 in ANM_HI.dat; compressed size is 639,429 bytes and decoded size 2,499,472 bytes. The first page visibly contains body poses. `anm10030.lzs` instead visibly contains portrait parts on a 128×544 page with two palettes. Do not use the class ID, row index, body field and derived visual selector interchangeably. The +0x1BC consumer is [func_00109E44](</Volumes/Data/Applications/QuiverLauncher/Apps/Disgaea D2-RE/port/src/recomp-140/ppu_recomp_005.cpp:38089>); the separate +0x196 plus 10,000 path is [func_00109350](</Volumes/Data/Applications/QuiverLauncher/Apps/Disgaea D2-RE/port/src/recomp-140/ppu_recomp_005.cpp:37283>).

## Addition and replacement constraints

The [binder](</Volumes/Data/Applications/QuiverLauncher/Apps/Disgaea D2-RE/port/src/recomp-140/ppu_recomp_019.cpp:589>) stores the header count and record pointer. The [lookup](</Volumes/Data/Applications/QuiverLauncher/Apps/Disgaea D2-RE/port/src/recomp-140/ppu_recomp_018.cpp:50065>) scans that count by class ID. The new test compiles those exact lifted functions, with isolated big-endian memory and bit-operation shims, under AddressSanitizer and UndefinedBehaviorSanitizer. It finds every original definition and an appended Etna clone, test ID32000, at row558. With the original count restored, that ID is absent. ID32000 is a laboratory choice, not an approved production ID.

This confirms only table binding and lookup. The prior loader trace allocates a file-sized buffer, which also favors structural expansion, but says nothing about every downstream array or selector. A missing ID becomes cached index `0xFFFF`; [the record getter](</Volumes/Data/Applications/QuiverLauncher/Apps/Disgaea D2-RE/port/src/recomp-140/ppu_recomp_000.cpp:6980>) subsequently multiplies the cached index without checking the count. Setting an absent ID in a unit is unsafe and does not create a definition.

| Constraint | Confirmed evidence | Practical interpretation |
| --- | --- | --- |
| Combined roster | 128 minus two signed counters, [func_0002E218](</Volumes/Data/Applications/QuiverLauncher/Apps/Disgaea D2-RE/port/src/recomp-140/ppu_recomp_000.cpp:35365>) | More definitions do not expand the saved roster |
| Persistent unit records | Prior source/profile research identifies stride 0x1A60 and save layout 1,498,152 bytes | Keep existing roster capacity; test serialization and reload separately |
| Battle descriptors | Prior research identifies 160 descriptors of stride 0x13C | This is not a 160-unit player deployment allowance |
| Animation managers | Four capacities 138, 1047, 1000 and 50, [func_00180F74](</Volumes/Data/Applications/QuiverLauncher/Apps/Disgaea D2-RE/port/src/recomp-140/ppu_recomp_008.cpp:24533>) | Cache groups are not interchangeable character slots |
| Secondary visual selector | Fixed initialization count 870; prior ELF audit finds 869 distinct keys | A new definition must use a valid selector or extend its consumers; 870 is not proven portrait capacity |
| IDs and selectors | Several consumers narrow or sign-extend 16-bit fields | Do not treat 65,536 encodings as usable IDs or arbitrary safe resources |
| Placeholder records | Earlier audit finds 66 dummy-named populated definitions and zero proven-unused IDs | Replacing a dummy needs dependency closure; ID2235 only lacks hits in a bounded raw scan |

A replacement preserves an existing identity and its recruitment/save references but affects every unit sharing the resource. An additional definition can preserve Etna while creating a second playable identity, provided recruitment, selector/resource allocation, related tables and serialization are made compatible. Native hooks are possible in this project, but their required scope has not been established. Replacing a dummy is a third approach, with its own reachability audit; it is not automatically safer than a controlled known-character replacement.

## Sprite conversion and required assets

Build an explicit mapping manifest from each RPG crop to a D2 action, facing, frame or part. Preserve foot anchors, weapon grips and mirrored orientation; scaling each frame by its own tight bounding box would make the character jump or change size. RPG front/back labels do not establish every D2 facing. Missing views or motions require deliberate reuse, mirroring or new artwork, with visual review of asymmetrical clothing and weapons.

Audit the donor’s motions for standing, waiting, walking, attacks for each supported weapon, casting, damage, incapacitation/death, lifting/throwing/carried states and mount-related behavior. These are validation targets, not confirmed ANM action numbers. Decode frame timing and attachment events before assuming that a static sequence can replace them. Reusing Etna’s existing moves and effects is simpler than importing RPG-specific skills or effects.

Preserve indexed palette semantics. A palette change can recolor all pages sharing it, and alternate palettes may be selected at runtime. The initial proof keeps all five donor palettes, so its imported pose loses some color precision. A production appearance needs a coordinated palette across all imported poses and compatible variants, or a separately validated higher-color texture route. ARGB1555 also loses smooth alpha and reduces channel precision; a successful standalone TXF conversion does not authorize switching the body ANM to that format.

An independent character also needs a usable name/title, portrait/menu/status artwork and expressions as required by D2; compatible class stats/growth/aptitudes, equipment rules, skills/evilities, descriptions, recruitment/unlock logic and AI if enemies use it. Voices, weapon effects and cut-in assets can initially reuse Etna’s confirmed dependencies if the game accepts that configuration. No RPG balance or ID values should be copied blindly into D2.

Local related-table leads include `charPersonal.dat`, `charhelp.dat`, `CharTitle.dat`, `magic.dat`, `mskill.dat`, `HABIT.dat`, `Feature.dat`, `enemymagic.dat`, `enemyskill.dat`, `WISH.dat`, `senator.dat`, `BattleEvent.dat` and `script.dat`. Their names and geometry are evidence of files to trace, not a complete decoded schema or proof that every file needs a new row. Follow actual consumers to determine which tables store class IDs, selectors, indices or computed values.

## Relevant tools and prior art

Use the local bounded exporter for NISPACK indexing, character rows, LZS and texture pages; its source references match this PS3 build. The new [offline experiment tool](</Volumes/Data/Applications/QuiverLauncher/Apps/Disgaea D2-RE/tools/d2_rpg_poc.py>) uses existing Pillow and clang++, without adding dependencies.

[D5tools](https://github.com/BTAxis/D5tools) offers Disgaea 5 PC NISPACK extraction/repacking and database tooling. Its schemas and archive transformations are prior art, not verified D2 encoders. [Unofficial Disgaea tools](https://github.com/ProgSys/pg_disatools) provide Disgaea PC sprite editing and TX2 conversion. Its [custom-character workflow](https://github.com/ProgSys/pg_disatools/wiki/Adding-Custom-Characters) is useful architectural precedent for recruitment and save-ID handling; its format and hooks are specific to another game. Compare its animation structures against D2 bytes before adopting them. [Makai Kit](https://github.com/HybridEidolon/makaikit) supplies mod loaders and database patching for newer titles, providing an overlay design example rather than a D2 loader.

If original RPG bundles become available, [UnityPy](https://github.com/K0lb3/UnityPy) can extract Texture2D/Sprite images and structured asset data; [AssetStudio](https://github.com/Perfare/AssetStudio) also exports Unity assets, but its original repository is archived. These capabilities do not prove compatibility with a particular RPG dump. The supplied flattened PNG works without either tool, but original assets might recover pivots or timing that the sheet lacks. No compatible RPG bundle was supplied for inspection.

## Implementation stages and acceptance criteria

1. **Finish a focused manifest.** Re-export only needed character tables, Etna body/portrait resources and dependency leads, preserving paths, offsets and hashes. Establish actual mounted archive precedence in the 1.40 runtime. Acceptance: every donor field resolves to the correct active member; no guessed association from filenames alone.
2. **Decode and preview D2 animations.** Parse frame/part metadata using lifted consumers and validated community structures. Reconstruct several unmodified donor animations and compare them with gameplay recordings. Acceptance: correct timing, pivots, layers, palette choice and attachments; a byte-preserving round trip of unmodified assets.
3. **Complete the RPG motion mapping.** Crop labels/backgrounds away; map poses and parts to donor motions with fixed anchors and a consistent palette. Resolve missing poses explicitly. Acceptance: all required action/facing combinations render in an offline preview, with no clipping, floating feet, incorrect weapons or unlabeled omissions.
4. **Test an Etna appearance overlay.** Add an opt-in loose-member override at the actual member-load boundary or a copied content tree; do not overwrite the disc dump. Reusing donor descriptors is preferred if the full pose mapping fits. Keep the existing character definition and gameplay dependencies. Acceptance: idle/walk/attack/cast/damage/lift/throw/mount and portrait checks in game, correct palettes, no corrupt textures or loader failures. Measure decoded memory/texture use; replace literal-only LZS with a tested compressor if needed.
5. **Audit and append a separate definition.** Enumerate all class-table and cached-index consumers, fixed arrays/bitsets, signed/range branches, creation lists and selector tables. Allocate a collision-free stable ID/resource set and clone only verified donor gameplay fields. Add a supported recruitment path using the existing unit initialization logic. Acceptance: new and original Etna coexist, all dependencies resolve, recruitment/reincarnation and menus work, and invalid IDs fail safely.
6. **Validate persistence and package rollback.** Use a disposable save copy/profile, never the user's only save. Test save/reload, map transitions, battle entry/exit and mod removal behavior. Retain the 128 roster budget. Acceptance: identity, equipment, learned skills and progression persist; the overlay is removable and unmodified content still works. A mod with independent IDs needs an explicit policy for saves containing those IDs.

If the append audit finds a fixed class capacity, decide whether to extend that specific consumer or use an audited replacement slot. The lookup test alone cannot settle this choice. The immediate next engineering task is stage 2; broad gameplay installation before frame composition is understood would provide weak evidence and risk misleading visual results.

## Proof of concept results and limits

Artifacts are in [the local experiment folder](</Volumes/Data/Applications/QuiverLauncher/Apps/Disgaea D2-RE/work/d2-rpg-poc-2026-10-08>), with [validation.json](</Volumes/Data/Applications/QuiverLauncher/Apps/Disgaea D2-RE/work/d2-rpg-poc-2026-10-08/validation.json>) retaining input/output hashes and exact lift hashes.

The inspected stand crop excludes the blue cell border. Exact border-connected opaque black is removed while enclosed black remains. The resulting pose is 76×150 pixels. It round-trips through the existing TXF ARGB1555 decoder. A resized copy occupies a manually selected 110×171 region of body page zero, quantized to the existing palette. RGB RMSE is approximately 10.13 on the 0–255 scale for nontransparent pixels; this measures the experiment's palette loss, not a final visual-quality guarantee.

The altered ANM retains every descriptor, texture header, palette and index outside the chosen region. Literal-only LZS expands back to the altered bytes exactly, and all 50 page/palette combinations parse. The test member is 2,500,668 bytes versus 639,429 originally; its unchanged expanded length does not prove compressed-buffer or archive limits are sufficient. The atlas region is chosen from the visible page, not a decoded frame definition. **It must not be installed as a complete Etna replacement.**

The separate appended-table test passes actual lifted binding/lookup with sanitizers and confirms all 559 row lookups, zero/missing-ID rejection and removal of the new ID when the count is restored. It is an Etna clone with reused visual selectors and name, not a fully authored independent character. The animation test and table test are separate artifacts; they are not wired together as a playable mod.

The existing exporter regression suite passes all 13 tests after a narrow fix exposing the already-implemented pixel verifier as `--pixels`. Tests hardcode an older scratch location outside this session's writable roots, so verification redirected TemporaryDirectory to this task's permitted scratch directory in memory; test files were not edited. The initial run found that scratch-path restriction and the missing CLI flag. There was no game launch, deployment, save edit, commit or push.

To reproduce the offline experiment from the project directory, choose a new output directory; the tool refuses an existing destination:

```sh
python3 -B tools/d2_rpg_poc.py \
  --sheet '~/Desktop/PC _ Computer - Disgaea RPG - Unique Characters (Humans) - Liones Princess Etna.png' \
  --output work/d2-rpg-poc-rerun
```

This requires the local game dump, lifted 1.40 sources, Pillow and clang++. It creates neither an archive overlay nor a save. The existing partial Desktop folders cannot pass the full export verifier because they lack manifests; sample matches do not repair that completeness gap.

Weekly usage was checked before research/conversion and near completion: 11% used, 89% remaining in the verified 10,080-minute window, above the required 60% reserve. The standalone `agent-usage` display mislabeled that window as five-hour; the app's raw duration identifies it as weekly. Continue only while weekly values remain verifiable, and stop expensive work conservatively before 40% used. A percentage rounded to an integer cannot promise an exact per-action cost.

## Alternate appearance validation

The existing body selector is a stronger initial integration target than an independent character. `func_00109E44` reads the signed byte at unit+0x117A, then selects a BE16 body resource from class-record+0x1BC plus twice that selector. In the inspected Etna ID30 row, selector zero yields resource30 and selector one yields zero. Several shipped classes populate multiple resources; the freshly observed unique-character examples are Rosalin410/411 and Demon Lord Priere520/521. These observations identify populated alternate resource fields, not universally available cosmetic menu slots.

The follow-up test compiles the exact lifted `func_00109E44` with AddressSanitizer and UndefinedBehaviorSanitizer. It uses the inspected Etna record, an isolated unit buffer, a record-getter stub and zero-returning flag-query stubs. With a test alternate resource placed at +0x1BE, selector zero returns30 and selector one returns30000 while the unit class ID remains30. No resource30000 is supplied or certified collision-free; it is a diagnostic value. [appearance-probe.json](</Volumes/Data/Applications/QuiverLauncher/Apps/Disgaea D2-RE/work/d2-rpg-poc-2026-10-08/appearance-probe.json>) records the exact function hash and test scope.

Menu routines `func_0027B448` and `func_0027B644` write unit+0x117A, and a nearby routine scans 74-byte entries matching the unit class-family key and reads a selector at entry+4. `charPersonal.dat` has matching 74-byte geometry and labels such as Cool, Quietly Burning and Muscly. This makes the personality table a concrete menu-dependency lead; the precise table binding, eligibility rules, voice consequences and user-visible appearance UI still need confirmation. The selector also has consumers outside the body loader, so it must not yet be classified as purely cosmetic. Color variants use additional fields and are a separate path.

Validate the route in this order:

1. Trace the menu table binding, option filtering, refresh calls and every relevant selector consumer. Determine whether Etna can expose another choice through data alone or needs a small eligibility/menu hook. Verify that selecting it preserves gameplay fields and has understood personality/voice effects.
2. Use existing compatible artwork as a control in an isolated content overlay. Demonstrate normal-to-alternate-to-normal switching through the existing UI, with correct resource lifetime and no stale sprites. Keep her original resource available. This establishes integration independently of RPG conversion quality.
3. Supply the fully mapped Liones Princess Etna animation resource in the validated alternate slot. Reuse existing portraits initially if acceptable, then coordinate portrait and palette selection deliberately. The one-pose container experiment is insufficient for this step.
4. Confirm the choice persists through map transitions and save/reload in a disposable profile, while class ID, equipment, stats and learned skills remain unchanged. Check battles, lift/throw and mount states as in the main plan.

This route avoids a new class definition and recruitment identity, reducing the first integration scope. It does not eliminate animation conversion, resource-ID allocation, palette handling, menu eligibility or persistence tests. The full-game appearance option remains unvalidated; the body-selection primitive is tested.

## Original RPG assets recovered

The subsequently supplied `~/Downloads/assets/android` contains original UnityFS bundles identifying Unity 2019.4.9f1. Its `masters/character` record identifies **character84 as Liones Princess Etna**. Focused extraction with UnityPy 1.25.4 produced [the local original asset folder](</Volumes/Data/Applications/QuiverLauncher/Apps/Disgaea D2-RE/work/rpg-original-etna84>) and [a source and output manifest](</Volumes/Data/Applications/QuiverLauncher/Apps/Disgaea D2-RE/work/rpg-original-etna84/manifest.json>).

The character-specific sources are `atlas/chara/battle/front/front84`, `back/back84`, `wait_front/front84`, `wait_back/back84` and `atlas/chara/story/84`, plus `prefabs/characters/84`. They yield 52 front sprites, 48 back sprites, five idle sprites for each facing and one portrait. Battle atlases are 1024×1024; idle atlases are 512×512. Decoded RGBA preserves the original available transparency, with named crops, rectangles and pivots. The source textures use ASTC 6×6 compression (format 50, labeled ASTC_RGB_6x6 by UnityPy); decoding cannot recover artwork before that lossy compression.

The prefab contains 42 animation clips, an AnimatorController, hierarchy and transform data, six embedded textures and 23 sprites. Embedded assets include shared dependencies and must not all be attributed to Etna84. Complete typed metadata and exact raw object bytes are retained. The clips specify a 60 Hz sample rate; front/back idle durations are approximately 0.85 seconds and front/back walk durations approximately 0.5167 seconds. Curve/binding data is exported but has not yet been evaluated into complete composed animation frames.

All selected images decoded without errors. Source hashes for all six bundles and exported file hashes were rechecked. Two prefab dependencies are missing at their recorded paths, `images/no_naming/effect/arrow02` and `images/no_naming/shadow`; their absence does not prevent atlas extraction but must be resolved or replaced if full RPG playback requires them. Other dependencies exist but were not all loaded and validated.

Use these originals for further conversion. The earlier flattened-sheet alpha cleanup and missing source pivots/timing are superseded for this character by recovered source data. Remaining work is interpreting Unity animation curves and layering, matching them to D2 action/frame metadata, and validating the alternate-appearance integration. [The focused extractor](</Volumes/Data/Applications/QuiverLauncher/Apps/Disgaea D2-RE/tools/d2_rpg_assets.py>) reproduces this output with UnityPy in an isolated environment. No installed game or save was changed.


Face icon path, updated2026-10-08: native RGB marking confirms START/wf_unique1 row2 supplies Etna deployment and battle HUD icons. Body30 and Status10030 markers did not change this face. Character-record19E selects a face identity, with fixed per-group tables and96px atlas coordinates computed by149E80. Future costumes should retain all retail cells, author separate cells in appended atlas columns, and select coordinates only inside validated unit draw scopes. This provides many authoring cells while preserving Original and other characters. Merely changing shared Etna row2 would globally replace original icon artwork; merely appending rows does not extend the fixed lookup. Column allocation and exact guest decompression are implemented offline, while native loading/costume routing/persistence/other consumers remain unverified. The corrected RPG story association is storycharacter13201/img_base132 for battle character84; story84 is Nekomata and must never be treated as matching art based on ID alone.


2026-10-08 implementation update: face-cell attachment, catalog/choice/native-persistence fields and scoped native coordinate routing are implemented. Face-panel-native-04 visually confirms Liones Etna’s deployment-list glyph, selected panel and battle HUD at480x3840. Standard-face-fallback-native-05 confirms Standard RPG body with original face in the widened bank; Original-face-fallback-native-06 confirms Original body/palette and retail face. Original atlas pixels and source/save checks pass. One pose is reused for expressions; expression authoring and all other UI consumers remain required. Scalable authoring supports extra columns, but only480-wide runtime is proven; other face groups and larger textures remain unvalidated. Required overworld coverage is unchanged: castle idle/cardinal movement accepted, remaining facings/events/actions/normal transitions/save and other characters unproven.


Latest audit: native optional face/portrait selection persistence passes recorded live castle changes and restart manifest equality. Castle Status page1 shows corrected Liones portrait. Castle Characters-list icons remain original: its queued callback1964C0 receives face/color at38/3C via19AF94, but actual class/unit ownership in the list builder remains unresolved. Experimental host link is bounded and fixture-validated, not accepted natively; AF7C0 r7 is a verified unit helper for a different panel context. Resolve explicit construction identity before marking castle icons complete. Weekly73% remains.


Latest acceptance supersedes the previous queued-icon limitation: explicit class scopes19E544/19E6A8 with bounded host queue links and independent class/face/visual/bank guards render Liones in the castle Characters list (native11). Disabled Liones and Standard without face metadata retain retail icons (native12/13). Native and fixture evidence shows other party faces/source saves preserved; Liones default restored. The columns in these observed UI routes select native color variants, not demonstrated facial-expression animation; a single fixed-color icon matches current importer color policy. Broader overworld/actions, other UI consumers/characters, normal transitions and gameplay save/reload remain incomplete.


Multi-costume face scaling update: etna-two-face-inventory-native holds Liones cell384,0 and Standard cell384,96 in the same480x3840 bank, with all original/previous pixels preserved. Standard is native-accepted in castle Characters and battle deployment/HUD; Liones’s prior icon and corrected Status survive the second attachment. Multi-overlay/two-costume preservation and selection regression passes. Other characters/face groups, wider banks, full action/overworld and normal transition/save acceptance remain required.


Normal-flow acceptance update: --scene normal observations now prove title Continue → specified copied postgame save → castle Characters/imported icon → corrected Liones Status → main castle menu, without warp/leader override/movie-skip flags. Current saved leader is Laharl; ordinary Etna overworld selection remains to be exercised through Dark Assembly ([NIS/Prima checklist](https://nisamerica.com/DisgaeaD2_free_Prima_checklist/Disgaea_checklists_V4.pdf), A Main Character Is You! row). This does not prove normal battle travel/return or a new gameplay save/reload. Weekly72% remains.


Paused at the user’s request — 2026-10-08. No native importer/play process remains running. Resume only on user instruction; check fresh weekly usage before expensive work and retain at least60%. Last verified remaining allowance was72%. Current working profile and remaining acceptance are recorded in RPG.import.report.md and the final handoff in RPG.import-progress.md. Existing reproduction commands are retained; no additional validation or deployment is implied by this pause.
