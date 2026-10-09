# Adding RPG costumes to D2 — quick guide

This is the short, current way to add a Disgaea RPG costume as an alternate look for a Disgaea D2 story character. It replaces the hand-mapping steps in `RPG.usage.md` (still valid, no longer needed).

Everything happens in a **private profile**: a copy of the game data and save under `work/appearance-profiles/`. The game dump, the original saves and the primary app are never changed. Costumes only work with the importer-enabled research build (`port/build-rpg-import/DisgaeaD2Recomp`).

## One-time setup

```sh
cd '/Volumes/Data/Applications/QuiverLauncher/Apps/Disgaea D2-RE'
python3 -m venv .venv-rpg && .venv-rpg/bin/python -m pip install -r tools/requirements-rpg.txt
```

The first `add` also needs to know where the extracted RPG assets are (`--rpg-source /path/to/assets/android`). It is remembered afterwards in `work/appearance.json`.

## Add a costume (about a minute)

1. Find the RPG ID of the costume, and optionally its Status-screen art:

   ```sh
   tools/costume find --name laharl            # battle sprites  -> --rpg-character
   tools/costume find --name laharl --story    # story portrait  -> --story-character
   ```

2. Add it:

   ```sh
   tools/costume add --character Laharl --rpg-character 54 --display-name "Dark Santa Laharl" --story-character 7901 --select
   ```

   This builds the body, the face icon and (with `--story-character`) the Status illustration, checks the result with the game's own decompressor, and writes a **new** profile folder containing all earlier costumes plus this one. `--select` makes it the look used at the next launch.

3. Look at the review sheet printed at the end (`…/costumes/<class>-<id>/review.png`, plus `face.png` and `illustration.png`). Each row shows the original D2 frame and the costume frame that replaced it.

4. Play: `tools/costume play`. In the castle, **Game → Appearance** switches the controlled character between Original and every registered costume, and remembers the choice.

Other commands: `tools/costume list` shows what is registered; `tools/costume choose --character Laharl --costume-id original` picks the next-launch look without starting the game.

Useful options for `add`: `--illustration-crop X0 Y0 X1 Y1` to frame the Status art yourself (the automatic crop centres on the head), `--face-crop …` for the small icon, `--no-face` to keep the original icon, `--profile new` to start again from the untouched game instead of extending the current profile, `--profile PATH/stage.json` to extend a specific one.

## Share costumes: packs and recipes

There are two files a costume can travel in. Neither changes anyone's game dump or saves; importing always makes a new private profile.

| | Costume pack `*.d2costumepack` | Costume recipe `*.d2costume.json` |
|---|---|---|
| Holds | The finished costumes: body, face icon, Status illustration | Only the choices: which RPG costume, names, crops, Choose Color slot |
| Receiver needs | A Disgaea D2 dump (BLUS31313 1.40) | The D2 dump **and** their own Disgaea RPG assets |
| Import time | About 25 s per costume | About 40–60 s per costume (rebuilt from scratch) |
| Contains game artwork | **Yes** | No |
| Where it lives | `costume-packs/`, ignored by Git; exchange privately | `costume-recipes/`, tracked in Git |

```sh
tools/costume export --with-art --name "My pack"      # costume-packs/my-pack.d2costumepack
tools/costume export --name "My pack"                 # costume-recipes/my-pack.d2costume.json
tools/costume import path/to/file                     # works for both kinds
tools/costume play
```

- **Import** adds the costumes to the profile you are using (so yours stay), in a new profile folder; costumes you already have are skipped. `--profile new` starts from the untouched game instead. If the file assigns Choose Color slots, or your profile already uses them, the result is a Choose Color profile; a slot that is already taken gets the next free one.
- **Packs are checked like untrusted files.** Member names come from validated IDs, sizes are bounded, every file must match its fingerprint, and the body must be *your* game's character with only pixels and cell geometry changed (animation tags, tracks, keys and transforms have to be byte-identical to your own; a sprite key may only be blanked; cells must stay inside their texture page). The illustration must match the original's layout exactly, the face must be a 96×96 PNG, and the compressed body is verified with the game's own decompressor. A pack built for another game version is refused. Still, only import packs from people you trust.
- **Packs carry game artwork.** They are for exchange between people who own the games. Never commit them or post them publicly; `costume-packs/` is ignored by Git for that reason. A pack also embeds the recipe details when they are known, so its receiver can export a recipe later.
- **Recipes** record SHA-256 fingerprints of the RPG files and the D2 body. When the reader's RPG files match, the recorded crops are reused and the result is byte-identical; when they differ, the import uses automatic crops and lists the costume under `different_sources`. Export refuses to overwrite without `--replace`; costumes made with the old manual tools have no import record and are skipped in recipes (packs include them).
- **Sprite Workbench**: completed imports in the import queue have **Export pack (with art)** and **Export recipe**; **Import a pack or recipe…** at the top of the queue opens a file chooser and adds the result to the queue with Use / Play buttons.

Both formats are validated before anything is built: unknown keys are dropped and malformed input is refused. `costume-recipes/disgaea-rpg-starter-pack.d2costume.json` holds the six costumes built so far.

## Which characters work

Supported by name (`--character`): Laharl, Etna, Flonne, Pure Flonne, Sicily, Xenolith, Barbara, Virunga, Lanzarote, Asagi, Axel, Valvatorez, Fenrich, Artina, Emizel, Petta, Pleinair, Fuka. The list and each character's RPG reference live in `tools/data/d2_rpg_reference_map.json`.

Accepted but weak: Rainier and Hoggmeiser (their RPG versions are enemy sprite sets with few poses, so most frames are substitutes) and Asagi (her D2 idle art differs from the RPG's, so idle frames are approximate). Checked in the game so far: Laharl, Etna, Flonne, and Valvatorez (castle only, before the idle fix below).

Not supported yet:

- DLC characters Adell, Rozalin, Mao, Raspberyl, Salvatore, Zetta, Desco, Porkmeister: their D2 art does not line up with the RPG art in the main archive.
- Priere, Overlord Priere, Eclair: a palette variant the tools do not decode.
- Generic classes and monsters: two-body layouts and shared face banks are not handled.

Any RPG costume **of a supported character** can be added. A costume belonging to a different character (for example a Laharl outfit on Etna) is not what this does.

## What is checked in the game

Checked natively on 2026-10-08 on profile `work/appearance-profiles/main` with Liones Princess Etna, Dark Santa Laharl and Apprentice Angel Flonne. **That profile was built just before the idle whole-figure fix (see handoff); rebuild it and repeat a short castle/battle check before treating this table as final.**

| Area | Result |
|---|---|
| Normal start: title → Continue → castle | Costume shown, field control works |
| Castle idle, walking in four directions | Works (Laharl, Etna, Flonne) |
| Live switch from Game → Appearance | Works; choice remembered across restarts |
| Characters list and Status screen | Costume icon and Status illustration for all three |
| Battle: deploy list, HUD icon, deploy, move | Works |
| Attack close-up, counter, damage, knock-down | Works for all three (attacker and target) |
| Battle → Give Up → title → Continue → castle | Costume kept in the same session |
| Save written and reloaded (disposable `AS-` copy) | New save is byte-identical to the original; reloads with costumes |

## Known limits

- One costume per character is active at a time.
- Live switching only works in the castle, for the character you control. Other characters change with `tools/costume choose` before launching.
- Story cut-in portraits and dialogue busts still show the original character. Not implemented. The RPG story masters do hold expression sets ("Emoji 01…09") for many costumes, so this is tool work rather than missing art.
- D2 frames with no RPG counterpart reuse the closest frame of the same costume (`fallback` rows in `review.png`): about 19 wind-up frames per character, and each character's unique special poses, which show a plain standing frame. See "Art gaps" below. Separate hand or cloth overlay pieces the costume does not have are hidden; `build.json` lists them under `substitutions`.
- Shared animation frames can be clipped by up to about 3% at the edges when a costume is much bulkier than the original (large hats, wings). Idle frames are enlarged automatically, so this only shows in a few action frames. `build.json` lists them under `clipped_over_1_percent`.
- The face icon atlas has been tested with 5 added icons; the widened atlas has room for 40.
- Recolour choices in the game show the same costume colours.

## Art gaps

Where the RPG simply has no drawing for something D2 shows. Only the first item would need new art.

- **Unique special poses** (D2 animation 7001 and similar). The costume shows a neutral standing frame instead. Counts from the pose templates: Laharl 3 (scarf-flaring laugh), Etna 3 (kneeling wink, flying kick, jump), Valvatorez 8–15 (including large transformation frames), Fuka 11, Asagi 2, Fenrich 1; none for Flonne, Pure Flonne, Sicily, Xenolith, Barbara, Virunga, Lanzarote, Axel, Artina, Emizel, Petta, Pleinair. Rainier (23) and Hoggmeiser (31) are mostly substitutes.
- **Wind-up frames**: about 19 shared frames per character (first frame of each weapon swing, jump, landing, launch) reuse the next frame. Barely visible; not worth drawing.
- **Cut-in and dialogue portraits**: not wired up; art exists in the RPG files for many costumes.
- **Face icons**: cropped automatically from the battle sprite. A hand-made 96×96 icon would be sharper (`--face-crop` only changes the crop).

## How it works (for maintainers)

- `tools/d2_rpg_template.py` — for each D2 character, compares the D2 body with the RPG version of the same character in its standard outfit and records which RPG pose, flip and pivot each D2 frame corresponds to. Idle frames whose cape, scarf or hair is keyed as separate cells are compared as the whole drawn figure (`idle_composites`), which gives the exact RPG idle frame and position. Shared frames use the vote file `tools/data/d2_humanoid_common_template.json` (18 characters). Result is cached in `work/appearance-templates/`.
- `tools/d2_rpg_autobuild.py` — repaints every frame from the costume using that template; `tools/d2_anm_cells.py` enlarges the character's own idle frames and hides baked-in cloth parts when the costume needs room.
- `tools/d2_appearance_add.py` (`tools/costume`) — runs extraction, template, build, decoder check, ID allocation (bodies 900–999, illustrations 10900–10999), face icon, illustration and registration in one go.
- `tools/d2_costume_recipe.py` — recipe export, validation and import, and the shared import chain (`tools/costume export` / `import`, workbench buttons). `tools/d2_costume_pack.py` — packs with artwork: export from a profile, strict reading (`read_pack`, `structure_check`) and installation through the same staging functions the importer uses. Tests: `port/tests/test_d2_costume_recipe.py`, `port/tests/test_d2_costume_pack.py`.
- `port/src/d2_appearance_trace.cpp` — the runtime side. The 2026-10-08 fix makes the temporary attack actor use the acting unit even when the reused actor still points at the previous unit; without it the target of an attack kept its original art.
- Tests: `ctest --test-dir port/build-rpg-import -R 'd2\.(rpg|appearance|native-lzs)'` (21 asset-free tests, including `d2.appearance-auto` for this pipeline). If a template rule changes, delete `work/appearance-templates/template-*` so templates are rebuilt.
