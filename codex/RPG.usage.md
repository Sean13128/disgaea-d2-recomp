# RPG appearance workflow

**2026-10-08: the quick way to add and play costumes is now `tools/costume` — see `codex/RPG.costumes.md`.** The manual steps below still work and document the underlying tools, but new costumes no longer need them. The current profile is `work/appearance-profiles/main` (see the handoff for its status).

The current private profile uses Liones Princess Etna (RPG character84) as an appearance for D2 Etna (class30). Native validation covers idle, movement, equipment changes and Prinny Raid, including its temporary skill actor. Damage/rolling/jump reactions, other skills/facings, portraits and save/reload acceptance remain unfinished. Game → Appearance supports live changes for the controlled castle character in the private importer build. Ordinary private play remembers those choices in the profile manifest; the CLI can also choose the next-launch default.

Start in this workspace:

```sh
cd '/Volumes/Data/Applications/QuiverLauncher/Apps/Disgaea D2-RE'
```

The Python asset tools use the versions in `tools/requirements-rpg.txt`. The play/choice tools use Python standard-library modules and the local exporter helpers. The native runner must be the importer-enabled1.40 research build; the ELF must be the verified `work/v140/EBOOT.elf`. Ordinary builds keep importer flags OFF.

To choose and play the existing private profile:

```sh
python3 tools/d2_appearance_choice.py imported --stage work/appearance-development/etna-distinct-inventory-native/stage.json
python3 tools/d2_appearance_play.py --stage work/appearance-development/etna-distinct-inventory-native/stage.json --runner port/build-rpg-import/DisgaeaD2Recomp --elf work/v140/EBOOT.elf --output work/appearance-development/etna-distinct-inventory-native/user-play-01
```

Use a new output directory each launch. With no duration or pad script, the launcher leaves normal keyboard/controller input enabled and waits for the player to quit. Choose Continue and the private save through the game's normal startup. Ctrl-C in the launching terminal stops the child if needed. There is no diagnostic stage warp or frame dumping by default. Saves and caches live in the stage's private hdd0/hdd1 directories; settings live in appearance-settings.json beside stage.json. Neither the source game dump nor the primary profile is selected as a runtime root.

To return to original artwork on the next launch:

```sh
python3 tools/d2_appearance_choice.py original --stage work/appearance-development/etna-distinct-inventory-native/stage.json
```

The appearance choice file is independent of personality, voice-selector and cached body fields. The original/imported native comparison retained every source/private save byte. A shared profile lock prevents test and play launchers from using the same save/cache concurrently. Each launch retains an immutable manifest snapshot. An optional `--duration 90` creates a bounded smoke test; it does not by itself verify loaded-save progression or complete gameplay.

To rebuild the latest reviewed body from original RGBA sources:

```sh
python3 tools/d2_rpg_palette.py --archive 'Disgaea D2 A Brighter Darkness - [BLUS31313]/PS3_GAME/USRDIR/Data/ANM_HI.dat' --composition work/appearance-development/etna84-oriented-build/composition.json --output work/appearance-development/etna84-user-build-01
python3 tools/d2_appearance_stage.py --output work/appearance-development/etna84-user-profile-01 --class-id 30 --resource 900 --anm work/appearance-development/etna84-user-build-01/anm00030.lzs --save-slot NPUB31321_NORMAL_01 --visual-alias --renderer-only
```

Both outputs must be new. The source-color mode re-encodes the donor textures and gives all native palette slots the same authored colors. Native recolor choices therefore display the same costume colors. Renderer-only staging copies the save without changing any byte and appends a visual definition/resource while retaining the original body. Renderer-only staging preserves both native body fields, including an occupied alternate slot. Legacy selector staging still requires an unused second field. Resource900 is a tested free filename/class candidate for this dump, rather than a universal allocation rule.

For another RPG character, first use `tools/d2_rpg_assets.py --character ID` to extract originals into a new directory. Select a corresponding regular RPG character as the visual reference for `tools/d2_rpg_map.py suggest`; review every selected pose, source crop, placement, mirror and quarter turn. Shared actions and character-specific idle tables can require separate mapping manifests. Build through a composition, inspect all exported palettes, and use `tools/d2_lzs_probe.py` against the expanded output before native staging. `tools/d2_rpg_clip.py` records original sprite-switch order and dependency identity; `tools/d2_rpg_coverage.py` identifies missing source poses without claiming D2 gameplay coverage. Current source coverage is69 of71 referenced poses, missing front/stand and front/attack_arrow02.

The diagnostics runner remains available for repeatable native acceptance checks. Its output contains process/result records, immutable configuration, input timing, logs and optional frames. It uses a conservative disk budget for requested captures. Preserve useful screenshots/videos, then remove only raw frames from completed runs. Tests and proof evidence are indexed in RPG.import.report.md and RPG.import-progress.md.


Multiple costumes can now share a private profile. `d2_appearance_inventory.py` extends an existing renderer-only profile into a **new** directory, retaining its saves, active costume, settings and existing visual records. Quit that profile before extending it; a live profile lock prevents copying saves during play. Additional costumes append independent visual records without consuming or modifying another native personality/body slot. Each RPG costume must still be converted against the chosen D2 donor before registration.

```sh
python3 tools/d2_appearance_inventory.py --stage work/appearance-development/etna84-action-test-native/stage.json --output work/appearance-development/etna84-multi-profile-01 --anm work/appearance-development/etna84-user-build-01/anm00030.lzs --class-id 30 --resource 902 --costume-id liones-second
python3 tools/d2_appearance_inventory.py --stage work/appearance-development/etna84-multi-profile-01/stage.json --list
python3 tools/d2_appearance_choice.py imported --stage work/appearance-development/etna84-multi-profile-01/stage.json --class-id 30 --costume-id liones-second
```

Use a distinct unused resource ID and a short lowercase costume name. The inherited first costume receives the name `resource-900`. `original` disables the active imported binding; choosing `imported` without a costume name restores the last selected costume. Launch the resulting stage with the same private play tool. Selection takes effect on the next launch. All supplied ANM_HI overlays receive the new resource; a fresh empty cache avoids stale member selection.

The catalog is bounded to128 costumes and128 active character bindings, with one active costume per character. New character bindings start disabled; registration does not require that character to occur in the current save. This is an importer bound, not a proven game capacity. Different characters are covered by authoring fixtures; Etna remains the only character with native artwork validation. In-game selection and live refresh remain outstanding.


A reviewed donor pose map can be reused for another RPG costume with matching named poses:

```sh
python3 tools/d2_rpg_retarget.py --archive 'Disgaea D2 A Brighter Darkness - [BLUS31313]/PS3_GAME/USRDIR/Data/ANM_HI.dat' --composition work/appearance-development/etna84-oriented-build/composition.json --appearance work/rpg-reference-etna6 --output work/appearance-development/etna6-user-proposals-01
```

The helper validates the previous map, retains its named pose/facing/mirror/quarter turn, recomputes the new sprite's opaque crop and fits it to the donor's bottom/center. It writes comparison sheets, component maps and a composition. Every proposal starts `selected:false`; inspect the previous/proposed crop in each review sheet before setting accepted entries to `selected:true` in mapping-N.json. Missing named poses remain in retarget.json and are never guessed. A matching pose name is a reusable correspondence, not proof that attachments or native pivots work. Distinct body proportions and partial hand assets need particular care. Explicit source holds in the template remain holds.

Build the reviewed composition with d2_rpg_palette.py, run the exact decoder check, then register the result with d2_appearance_inventory.py using a new resource/costume ID. This avoids repeating the pose-matching search for every costume of the same donor. Another D2 character still needs its own reviewed donor mapping; copying Etna's rectangle layout into a different donor is invalid.

The diagnostic multi-costume profile at work/appearance-development/etna-distinct-inventory-native contains `resource-900` (earlier Liones), `liones-oriented` (latest Liones) and `standard-rpg-etna` (original RPG Etna6). To choose either distinct appearance for the next private launch:

```sh
python3 tools/d2_appearance_choice.py imported --stage work/appearance-development/etna-distinct-inventory-native/stage.json --class-id 30 --costume-id liones-oriented
python3 tools/d2_appearance_choice.py imported --stage work/appearance-development/etna-distinct-inventory-native/stage.json --class-id 30 --costume-id standard-rpg-etna
```

The two commands illustrate alternatives; run the one you want. Catalog selection preserves source and private save fields. Neither source-reference coverage nor acceptance of review sheets proves the full D2 action set.


Overworld acceptance uses the same private diagnostic runner with `--scene hub`. This leaves the ordinary loaded castle in place and enables read-only map tracing instead of the battle warp. Normal play clears all inherited hub/warp diagnostics.

```sh
python3 tools/d2_appearance_run.py --stage work/appearance-development/etna-distinct-inventory-native/stage.json --runner port/build-rpg-import/DisgaeaD2Recomp --elf work/v140/EBOOT.elf --output work/appearance-development/etna-distinct-inventory-native/user-hub-check-01 --scene hub --hub-character 30 --duration 115 --frame-every 30 --pad-script '10:0x4000,14:0x4000,65:0x0010,70:0x0020,75:0x0040,80:0x0080'
```

The optional `--hub-character 30` selects one uniquely matching party class through native1.40 functions0002EBC8 and00295EF8 on the main PPU thread, after the hub is ready and announcements finish. It changes the controlled character in RAM for the diagnostic; it does not write the save. Without this option the runner leaves controlled-character selection alone. Ordinary character switching is a Dark Assembly action according to the [publisher-hosted Prima checklist](https://nisamerica.com/DisgaeaD2_free_Prima_checklist/Disgaea_checklists_V4.pdf); changing party order does not substitute for it. The diagnostic bypasses the Assembly interaction so the imported actor can be tested directly. This is separate from the still-pending in-game cosmetic selector.

Native castle actors are created without a gameplay-unit link. The importer recovers the selected unit only for the verified controlled-actor constructor chain E83BC→E832C→29804, after validating its stack return site, actor tag/class, unique party identity and independent visual definition. Leader identity and party records have different global pointers; the lookup follows each native getter. Unitless previews and unrelated NPC constructors remain outside this fallback. Validate separately loaded NPC/companion art, remaining facings and scene transitions before declaring complete overworld support.


Live appearance selection is available in the private importer-enabled runner under **Game → Appearance**. Load the private save, select Etna as the controlled castle character through the game's normal field-character mechanism, and wait for announcements to finish. The menu lists Original and registered costume display names. Requests are queued for the PPU main thread; stale, loading, battle, event and mismatched identity requests are rejected. The current native proof covers controlled Etna in castle30001. Ordinary private play remembers a successful menu choice for the next launch; pass `--session-only` to keep it temporary. Diagnostic runs remain temporary unless `--persist-choice` is explicit. The CLI can also set the next-launch default. No game personality or save fields are changed by the cosmetic request. This is the native app menu, not a new Dark Assembly/personality entry in the guest game's interface.

New costumes can supply `--display-name 'Liones Princess Etna'` to d2_appearance_inventory.py. Existing catalog entries may supply the same optional JSON field. Display names accept1..127 UTF-8 bytes without control characters; costumes without names appear as numbered choices. This metadata does not change animation resource identities. The current distinct-costume profile has friendly names for both Etna outfits and the earlier mapping.

A bounded native reproduction of the verified live-switch path is:

```sh
python3 tools/d2_appearance_run.py --stage work/appearance-development/etna-distinct-inventory-native/stage.json --runner port/build-rpg-import/DisgaeaD2Recomp --elf work/v140/EBOOT.elf --output work/appearance-development/etna-distinct-inventory-native/live-user-check-new --duration 120 --frame-every 60 --scene hub --hub-character 30 --live-sequence '65:standard-rpg-etna,80:original,95:liones-oriented'
```

Use a new output directory. The hub-character diagnostic invokes the native leader setter in RAM and bypasses the normal Assembly interaction. Live-sequence automation rebuilds the same menu snapshot and invokes its selection handler; it does not prove physical mouse interaction. Ordinary play clears inherited automation. The runner retains the event list, per-run manifest, logs and captures. The checked shorter teardown/rebuild preserves tested actor position, complete unit bytes and camera X/Z; full camera state, other scenes and persistence remain open. The actual session proof is live-switch-menu-native-02/live-costume-comparison.gif, with four excerpted native captures rather than real-time playback.


Remembered menu choices are native-tested for Etna: selecting Standard RPG Etna updated the private manifest, and a subsequent process loaded and visibly rendered it before any new selection. Original and Liones were then selected live and remembered, leaving the original Liones default restored. The gameplay save remains byte-identical. Proof: persist-native-standard-01/remembered-stage.json and persist-native-relaunch-02/stage-snapshot.json are equal; PNG/GIF/log/evidence files are retained beside them. The GIF excerpts three captures, not real-time playback. This is appearance persistence across a process restart using the existing save, not a newly written gameplay-save/reload or map-transition acceptance test.

Menu persistence and CLI choice share `.appearance-choice.lock`. The native writer uses a nonblocking lock and checks that the selected character's catalog and next-launch choice still match its launch/last-write state. It preserves changes to other characters and unrelated metadata. A concurrent change to the same character, lock contention or an invalid path leaves the live outfit active for the session and reports that the next-launch choice could not be updated. This prevents an older process from overwriting a newer CLI decision. The immutable launch snapshot remains unchanged. Only the private appearance manifest is replaced atomically; no gameplay save write occurs.


To test retention across the castle→battle transition, use `--scene hub --hub-character 30 --battle-after 85` with a live choice before that deadline. This diagnostic selects the castle leader first, then invokes the existing native stage101 copy/reset/event11 path after the configured delay and hub-message drain. The delay must be an integer from1 through duration−11. Ordinary play removes inherited delay/warp settings and continues to use the game's normal routing.

The verified reproduction is:

```sh
python3 tools/d2_appearance_run.py --stage work/appearance-development/etna-distinct-inventory-native/stage.json --runner port/build-rpg-import/DisgaeaD2Recomp --elf work/v140/EBOOT.elf --output work/appearance-development/etna-distinct-inventory-native/transition-user-check-new --duration 185 --frame-every 60 --scene hub --hub-character 30 --battle-after 85 --live-sequence '65:standard-rpg-etna,110:original' --pad-script '10:0x4000,14:0x4000,54:0x0040,55:0x0040,56:0x0040,57:0x0040' --pad-events '115:0x4000,117:0x0040,119:0x4000,125:0x4000,127:0x0010,129:0x0010,131:0x0010,133:0x4000,135:0x4000'
```

Use a new output. Standard is selected live in the castle, retained in the same process through stage101 loading, deployed, and moved off the base panel. The110-second Original attempt is deliberately not queued because battle switching is unavailable. No next-launch choice is changed without --persist-choice. Native proof: hub-battle-move-native-02/castle-to-battle.gif, battle-movement.gif, full PNGs and evidence/log/ctest files. The first GIF excerpts four scenes; the movement GIF preserves1-second capture cadence. This validates this diagnostic direction and map, not normal Dimension Guide interaction, return to castle, other scenes or live battle refresh.


For adaptive checks after scripted inputs finish, tools/d2_appearance_input.py queues a bounded controller press in a currently live private experiment:

```sh
python3 tools/d2_appearance_input.py --output work/appearance-development/etna-distinct-inventory-native/your-live-run --mask 0x4000
```

The default is four native polls. The client checks planned-input.json, process liveness, isolated snapshot mode and terminal status, refuses pending input, bounds masks/polls, avoids symlinks and records queued commands in input-presses.jsonl. Check captured game response before issuing the next menu action; a queued audit entry does not prove consumption. Current launchers write the planned schedule. Older experiments without that file cannot use this client without recording their exact known schedule first. A sandbox may deny signal-zero liveness checks against the unsandboxed native runner; native testing used the approved isolated-process execution context.

The inspected battle menu's **Give Up** prompt resets to the title screen and discards current progression. It is not a demonstrated battle→castle return path. The victory-route test rendered Standard RPG Etna through a normal spear attack and return to idle, reporting Miss, then ended during an enemy turn. A selected enemy showed150026865 HP. No victory or castle reload was observed. Return validation remains open; use a controlled baseline/difficulty comparison before attributing the combat result to appearance binding. Evidence: battle-castle-return-native-02/give-up-title-reset-prompt.png and victory-castle-return-native-03/normal-spear-attack.gif, normal-attack-inspection.png, enemy-status-high-hp.png and evidence.json.

Additional asset inspection confirms ANM31 contains secondary full-body poses (three indexed pages/five palettes), not the UI portrait. ANM10030 has a separate illustrated strip (one page/two palettes); its exact UI/scene consumer is not yet confirmed. Metadata and decoded original pages are in work/appearance-development/etna-portrait-inspection. The supplied RPG84 story sprite is460×680 within a1024×1024 ASTC atlas. Neither inspection constitutes an authored or native-validated portrait replacement.


Original-archive controls can now be built with the same private save:

```sh
python3 tools/d2_appearance_baseline.py --stage work/appearance-development/etna-distinct-inventory-native/stage.json --output work/appearance-development/etna-original-control-new
```

The output must be new. This tool locks the source profile, makes independent copies of the original game and the selected private HDD0, verifies every Data-file SHA256 against both source and copy, verifies original donor tables and byte-identical save data, and starts with empty HDD1. Its disabled binding uses the original class/body IDs; it adds no character rows or animation files. Imported choice and costume registration are rejected for control profiles. Pass the resulting stage.json to the ordinary bounded diagnostic runner. It still uses the native research runner, so this is an archive/binding control, not validation of an unmodified PS3 executable.


Use `--trace-resource 10030` on `d2_appearance_run.py` to investigate Etna's separate illustration asset, or `--trace-resource 31` for the secondary pose resource. The default remains the selected body resource. Diagnostic file IDs must be integers1..99999, covering the supplied five-digit ANM names independently of signed character/body alias IDs. This changes read-only tracing, preserves the appearance binding and records the chosen filter in result.json. The private runner must contain the current diagnostic source to observe models selecting the filtered library as well as models binding an external filtered texture.

Summarize a completed experiment and cross-check its library variants against an original ANM resource:

```sh
python3 tools/d2_appearance_asset_trace.py --run work/appearance-development/etna-pristine-combat-control/portrait-library-trace-03 --archive 'Disgaea D2 A Brighter Darkness - [BLUS31313]/PS3_GAME/USRDIR/Data/ANM_HI.dat' --output work/appearance-development/etna-pristine-combat-control/portrait-library-trace-03/asset-trace-user-check.json
```

The report separates requests, file reads, bank states, model-library selection and external texture binding. When metadata is supplied, it compares the model's variant against resource tags only when that call selects the exact supplied library. It does not equate an asset load, a bound resource or a recognized tag with visible coverage. Model handles may be reused. Each event references the preceding logged capture, not an exact presentation timestamp. Inspect actual screenshots and test restoration before treating illustration/menu/status artwork as accepted.

The completed illustration traces confirm loading of anm10030.lzs, but do not yet identify its visible consumer. Normal attack and Prinny Raid showed the existing status/attack-entry artwork without a matching10030 model-library or external texture observation. Use a visibly marked copy in a separate private profile as the next check; do not route/resize the RPG story illustration based solely on its filename. The secondary31 read atF9920 is a normalization range check, not a verified drawing consumer. New run results include the native executable SHA256 recorded before process launch; older results lack this provenance.


To identify an indexed resource's visible consumer, make a diagnostic copy with a palette RGB marker:

```sh
python3 tools/d2_appearance_asset_probe.py --stage work/appearance-development/etna-pristine-combat-control/stage.json --resource 10030 --output work/appearance-development/etna-marker-user-check-new
```

Output must be new, outside source/original profiles, with an existing parent. The tool locks the source, copies content/HDD0 independently, marks every supplied ANM_HI overlay containing the member, and starts with empty HDD1. It changes only palette RGB bytes, retaining alpha/indices/metadata/resource ID. Each rebuilt archive verifies untouched members; all source Data/save-root files and unrelated copied Data files are hash-checked. Existing source choices are retained, but imported CLI selection and costume registration are blocked for marker profiles. They are diagnostics, not costumes or pristine baselines. Multi-resource ANM containers are rejected because shared palette ownership has not been resolved. Marker defaults to magenta; `--rgb R G B` accepts three bytes. RGB markers can identify color consumers; absence of a visible change does not exclude alpha-only use.

The Etna Status-screen reproduction is:

```sh
python3 tools/d2_appearance_run.py --stage work/appearance-development/etna-illustration-marker-control/stage.json --runner port/build-rpg-import/DisgaeaD2Recomp --elf work/v140/EBOOT.elf --output work/appearance-development/etna-illustration-marker-control/status-user-check-new --duration 120 --frame-every 60 --scene battle --trace-resource 10030 --pad-events '65:0x4000,67:0x0040,69:0x4000,75:0x0040,77:0x0040,79:0x0040,81:0x0040,83:0x0040,85:0x0040,87:0x0040,89:0x4000'
```

After deployment, the native character command menu opens with Move selected; seven Down presses choose its Status entry. The marker appears in the large left illustration pane, with native library10030 selection traced at29348. The smaller battle/attack-entry/list icons did not acquire the marker in the inspected views. This establishes the Status illustration consumer, not an imported portrait, its final crop, live costume routing or all portrait/UI consumers. The attempted Triangle shortcut in selected-character-view-02 stayed in a Special Skill list; it is not evidence for a Status route.

Matched original/marker Status screenshots are retained in etna-illustration-marker-control/status-illustration-comparison.png. The illustration is now a confirmed Status consumer. Native resource40030 is a compound file containing blocks10/30/50, so diagnostics accept file IDs1..99999 independently of internal block IDs. Marker authoring rejects compound files and files whose single internal resource does not match the external ID. Optional trace reports record mismatched/compound IDs instead of inventing tag associations. Signed16 character/body alias limits remain unchanged. The separate30030 illustration's actual consumer and the small-icon source remain unverified.


Status illustrations are optional per-costume assets. Convert the supplied RPG artwork with a reviewed crop, retaining the donor's single-page geometry and native tags:

```sh
python3 tools/d2_appearance_illustration.py convert --archive 'Disgaea D2 A Brighter Darkness - [BLUS31313]/PS3_GAME/USRDIR/Data/ANM_HI.dat' --source work/rpg-original-etna84-story132-corrected/story/Sprite_-7446852261231724155_1.png --crop 155 280 285 680 --output work/appearance-development/etna84-illustration-user-build-new
python3 tools/d2_appearance_illustration.py attach --stage work/appearance-development/etna-distinct-inventory-native/stage.json --anm work/appearance-development/etna84-illustration-user-build-new/expanded.bin --class-id 30 --costume-id liones-oriented --resource 10902 --output work/appearance-development/etna-illustration-user-profile-new
```

Both outputs must be new with existing parents. Conversion uses aspect-preserving cover after the explicit crop and an opaque white matte by default (`--matte R G B`). It reuses the shared source-color palette encoder, keeps donor metadata/headers/dimensions, and assigns the same authored colors to all palette slots. This is one illustration pose reused across existing native tags; it does not add expressions or update small icons.

Attachment validates the original class196+10000 association in every character table, requires byte-identical donor metadata, rejects filename collisions across overlays, patches only the new internal resource ID, and adds the independent file to all supplied ANM_HI overlays. Character tables and gameplay saves are copied unchanged; source/unrelated Data and save-root hashes are checked. It retains other costumes, choices/settings/presets and starts with empty HDD1. The active costume gains `illustration_resource` and `illustration_donor` only if it matches the attached item; attaching to another item preserves the current choice. Status resources are explicitly allocated in10000..19999 for this resolved path, independently of the body alias ID.

The private1.40 runner wraps unit getter109350. It first obtains the original resource, then replaces that return value only for an enabled renderer-only binding with an exact illustration donor match, valid cached real-class record and independent body alias. It does not change the character record, unit/save fields or class-only illustration getter. Original disables the override; a costume without illustration fields reuses the donor art. CLI choice and native persistence copy/clear both optional fields together. Catalog mismatches, malformed IDs and duplicate/colliding resources are rejected.

Current native-validated profile: `work/appearance-development/etna-illustration-corrected-inventory-native/stage.json`. Liones uses body901 and corrected Status illustration10902; Standard uses body902 and falls back to the original10030 illustration. Live Original/Standard choices in the castle both carried into battle, where the Status pane showed original art. The default Liones choice remains unchanged because these diagnostic menu selections were session-only. Native portrait persistence itself has not been tested; updated field persistence is fixture-verified. Ordinary play still uses normal routing and remembers choices by default.


Shared ANM inspection: parse_anm now inspects texture/palette bounds using palette0 and reports total page_pairs, inspected_page_pairs and inspected_palettes separately. Containers may have more than256 palettes;256 is the per-palette color limit. The Python page-reader API accepts anm_pages(expanded, include_rgba=False, palette_indices=[index]) for bounded inspection of a reviewed palette binding. Default full expansion retains a32768 pair limit; selection still validates every palette header and extent. Palette0 across a compound container is not evidence of correct per-block palette routing. Local80000/80001/99997 metadata is retained in work/appearance-development/etna-portrait-inspection; these external file IDs contain different internal IDs, so single-resource conversion/marker restrictions still apply.


Source identity correction: battle character84 is Liones Princess Etna, but story bundle84 belongs to another character. Use the separate story master entry13201 (Etna in Elizabeth's Costume), whose img_base is132. The extractor now skips story artwork unless --story-character is supplied; it records the selected master row/hash and does not equate these namespaces. Example:

```sh
PYTHONPATH=/Volumes/Data/ai-tmp/codex/d2-map-01a119f7/python python3 tools/d2_rpg_assets.py --source ~/Downloads/assets/android --character 84 --story-character 13201 --output work/rpg-etna84-new-export
```

The old10901 art is rejected for character identity and disabled in the prior tight profile; its native captures prove routing behavior only. Corrected10902 art is native-tested for Status page1. The corrected profile inherits this explicit correction and preserves the original/body/Standard assets.

Face atlas converter (offline): tools/d2_face_atlas.py accepts compressed txf magic and format0 ARGB8888 with dimension/length guards. --donor points to an extracted packed wf_unique1.lzs, --output must be new. Optional --source and --crop append one96px row of four repeated face crops while preserving every original pixel. It produces atlas.lzs, expanded.txf, atlas.png, appended-row.png and validation.json. Current build etna84-face-atlas-appended-build passes exact guest decoding but is not attached or routed in the game. Fixed native unique1 lookup scans40 entries, so append alone cannot make it selectable; the4096px authoring bound allows42 total rows. Multiple costumes ultimately require a separate atlas path or another verified loading approach.


Causal face-row diagnostic (new private output):

```sh
python3 tools/d2_appearance_asset_probe.py --stage work/appearance-development/etna-pristine-combat-control/stage.json --output work/appearance-development/etna-face-marker-new --face-member wf_unique1.lzs --face-row 2
```

This changes only RGB in the selected96px row, preserving alpha and other rows in all supplied START overlays containing the member. The native confirmed consumers are Etna's deployment glyph/selected face and battle HUD face. The diagnostic remains blocked from ordinary costume selection; other UI/overworld consumers are unverified.

Use the column allocator for the multi-costume face catalog:

```sh
python3 tools/d2_face_atlas.py --donor work/appearance-development/etna-portrait-inspection/wf_unique1.lzs --source work/rpg-original-etna84/front/Sprite_216655389270242867_stand.png --crop 20 24 105 110 --allocate-cell --output work/appearance-development/etna-face-cell-new
```

It retains original face cells at the same XY and allocates x384/y0 in a new column. To allocate again from an already widened donor, supply --occupied-cells with a JSON list of existing [x,y] allocations. Unknown nonblank artwork in a candidate cell is rejected. Save the returned face_x/face_y/face_width/face_height with provenance for subsequent routing. Attach the resulting atlas to a copied private profile using the command below. Native renderer-only costume bindings now validate and consume a face_cell containing x/y/width/height/donor, and choice/persistence carries or clears it with the selected costume. Height stays unchanged, so the fixed40-entry retail row lookup need not grow with scoped costume UV routing. The authoring bound is4096px; native loading of480x3840 is confirmed, while wider atlas limits remain unvalidated.


Attach a reviewed face cell to one registered costume (creates a new private profile):

```sh
python3 tools/d2_appearance_face.py --stage work/appearance-development/etna-illustration-corrected-inventory-native/stage.json --atlas work/appearance-development/etna84-face-atlas-column-build/atlas.lzs --class-id 30 --costume-id liones-oriented --x 384 --y 0 --output work/appearance-development/etna-face-user-profile-new
```

The attachment checks the donor face in every supplied char table, preserves original face pixels at exact XY, rejects unrelated edits/occupied cells, replaces only the face member in supplied START overlays, and verifies source/save preservation. The new cell is a single reviewed pose reused across expression requests; native color variations reuse the authored source-color icon. Current working profile: work/appearance-development/etna-face-inventory-native/stage.json. Native face-panel-native-04 confirms the deployment-list glyph, selected panel and deployed battle HUD after adding the traced15CCAC unit-panel scope. Only these consumers and480x3840 bank size are native-confirmed.


Native controls in the same widened face profile: standard-face-fallback-native-05 and original-face-fallback-native-06 confirm retail icon fallback with Standard and Original bodies respectively. Liones is restored as the default. Each run retains deployment-face.png, battle-face.png, asset-trace.json, evidence.json, immutable snapshot and executable-hashed result. Native menu persistence with face fields still needs a dedicated run; fixture persistence passes.


Native remembered-field acceptance: face-persist-castle-native-07 retains choice-observations.jsonl and persistence-evidence.json; native Standard removes face/illustration fields, Original disables, Liones restores them without changing the catalog. Restart08 uses that final manifest hash. Castle Status page1 uses corrected10902 in09/10. Castle Characters-list icons remain original and queued linking is experimental; battle04/05/06 remain the icon acceptance evidence. Reproduce the castle menu/Status navigation in a new output with --scene hub --hub-character 30 and --pad-events '65:0x1000,67:0x4000,69:0x0040,71:0x4000,73:0x0040,75:0x0040,77:0x4000', duration95. This is a diagnostic castle startup, not normal Dimension Guide traversal or gameplay save/reload.


Castle icon acceptance supersedes the unresolved queue note above: native11 shows imported Etna list/submenu icon with other party faces unchanged; native12/13 prove Original-disabled-Liones and Standard-no-face fallback. The queue retains the explicit class ID from19E544/19E6A8 and validates original face, independent visual definition, bank and record identity before routing. The existing catalog selects one costume per class, rather than individual units sharing that class. These tested atlas columns are color variants; the fixed source-color importer uses one authored icon across them. No facial-expression completeness is implied. Latest working profile remains etna-face-inventory-native/stage.json with Liones enabled.


Latest working profile: work/appearance-development/etna-two-face-inventory-native/stage.json. Both Liones and Standard have independent imported face cells in the same bank. Liones remains the default; Standard retains original Status art. Older one-face controls remain separate and valid for their snapshots. To select Standard for a private normal play launch:

```sh
python3 tools/d2_appearance_choice.py imported --stage work/appearance-development/etna-two-face-inventory-native/stage.json --class-id 30 --costume-id standard-rpg-etna
```

For another cell, derive occupied coordinates from the current costumes' face_cell fields, allocate from this profile’s face-assets/wf_unique1.lzs with --occupied-cells, then attach to a costume without a face cell in a new private output. Each attachment preserves previous cells at exact XY. Native evidence: standard-two-face-castle-native-01, liones-two-face-battle-native-02 and standard-two-face-battle-native-03. Full hashes stay in stage.json; the attach CLI prints a compact summary. Existing imported face metadata cannot be silently overwritten; revisions require a deliberate future replacement workflow.


Observe the normal title/Continue/copied-save/castle menu route without warp or leader override:

```sh
python3 tools/d2_appearance_run.py --stage work/appearance-development/etna-two-face-inventory-native/stage.json --runner port/build-rpg-import/DisgaeaD2Recomp --elf work/v140/EBOOT.elf --output work/appearance-development/etna-two-face-inventory-native/your-normal-route-new --duration 105 --frame-every 120 --scene normal --pad-script '10:0x4000,14:0x4000,30:0x4000' --pad-events '65:0x4000,70:0x1000,72:0x4000,74:0x0040,76:0x4000,78:0x0040,80:0x0040,82:0x4000,94:0x2000,96:0x2000,98:0x2000'
```

This reproduced normal Continue → visitor notice → Characters → Liones Status → main castle menu in normal-menu-status-native-05. It uses ordinary controller events with the port’s native headless picker for the explicit private slot. The final three Cancel events leave the main menu open; field control, normal battle travel and writing/reloading a new gameplay save remain unvalidated. For user-controlled normal play, retain the existing d2_appearance_play.py workflow. --scene normal rejects hub leader/warp-delay/live-test options and removes movie-skip/warp environment flags.


Paused at the user’s request — 2026-10-08. No native importer/play process remains running. Resume only on user instruction; check fresh weekly usage before expensive work and retain at least60%. Last verified remaining allowance was72%. Current working profile and remaining acceptance are recorded in RPG.import.report.md and the final handoff in RPG.import-progress.md. Existing reproduction commands are retained; no additional validation or deployment is implied by this pause.
