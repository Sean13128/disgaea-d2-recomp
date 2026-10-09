# Sprite Workbench

Open `Sprite Workbench.command` in the project folder. It opens a local browser GUI; reopening the launcher reuses the running workbench. The source folders and character indexes are remembered under `work/sprite-workbench/`.

## Browse and compare

1. Open **Asset folders**, browse to the extracted Disgaea RPG `assets/android` folder and the D2 game dump or `PS3_GAME/USRDIR/Data`, then index each library.
2. Search **RPG costumes** by name or numeric battle ID. Selecting a costume suggests a supported D2 character by name; inspect the pairing and use **D2 characters** to choose the target yourself.
3. Inspect **Character poses** side by side, step through the thumbnails, zoom or fit, and switch either pane to **Sprite parts** or **Atlas pages**. D2 idle frames combine supported parallel body/cape/scarf/hair tracks; raw components remain separate in Sprite parts. D2 also has a palette selector. **Match pose** uses an existing, matching donor template when available; no new template is generated just for browsing.
4. For imported Status art, search the separate story-character list, select the exact story ID, and inspect its preview. Battle and story IDs are separate; the tool does not infer a story ID from a battle ID.

Raw D2 sprite regions may be separate parts of a composed character; the default pose view excludes known detached parts and composes supported idle frames. These are static sprite/atlas inspections, not reconstructed animation playback. Unsupported D2 characters and incomplete RPG asset sets remain browsable where their images decode, but cannot be queued for import. Decode errors are reported in activity.

## Import

Select an RPG costume and its corresponding supported D2 target, give it a costume name, optionally select Status art, and click **Add to import queue**. The tool calls the existing importer, validates the selected D2 donor against the destination profile, and creates a new profile under `work/appearance-profiles/studio-*`. It preserves source assets, source profiles and original saves.

The default destination extends the latest private profile. Multiple queued imports extend the preceding result, so earlier costumes are retained. An explicit profile path pins a different base; `new` starts from the original project dump. Imported resource allocation and decoder verification are handled by the established importer.

Open **Import queue → Review sprites** to inspect the comparison sheet, face icon, optional Status illustration, fallback counts and resulting profile path. **Use for next playtest** selects that costume in its new private profile and makes that profile current for `tools/costume play`. **Play this costume** selects it and launches that exact private profile with the research runner. It does not replace the installed game. Existing fixed-profile playtest launchers still open the profile written into their command.

The desired in-game **Choose Color** costume selection is recorded in `RPG.character-plan.md` and remains future runtime work. The workbench uses the current research importer's private-profile selection.

## Development and verification

Backend: `tools/d2_sprite_workbench.py`, Python standard-library HTTP server bound to `127.0.0.1` with same-origin mutation checks, serialized background jobs, content-addressed preview PNGs and persistent JSON character indexes. Frontend: `tools/sprite_workbench/`, plain HTML/CSS/JavaScript. Uses existing Pillow/UnityPy dependencies; no new framework or package installation.

CLI: `tools/sprite-workbench --no-open --port 8769` for testing. Default launch chooses an available local port. Closing its terminal stops the service after queued work finishes.

Asset-free checks: `port/tests/test_d2_sprite_workbench.py` / CTest `d2.sprite-workbench`. Extraction cache identity includes the source masters and selected bundles, so numeric character IDs from different asset dumps cannot silently share artwork.

## Choose Color profiles

Completed imports now offer **Build Choose Color profile**. This copies the
entire private profile and assigns up to four appearances per character to
Extra colors 1–4, keeping Normal Color as Original. The completed build shows
all assignments and offers **Play Choose Color profile**. See
`codex/RPG.color-slots.md` for current implementation and validation limits.

## Export recipe (2026-10-09)

Completed imports and Choose Color profiles in the import queue have an **Export recipe** button. It writes a costume recipe for every costume in that profile to `costume-recipes/<name>.d2costume.json` (numbered if the name is taken) and reveals it in Finder. The recipe holds names, IDs, crops, Choose Color slots and source fingerprints only: no artwork, game data or local paths. Others rebuild it with `tools/costume import FILE` from their own game files. Server route: `POST /api/export {job, reveal}`; logic lives in `tools/d2_costume_recipe.py`. Restart the workbench server after updating the tools so the route exists.

## Packs with art, and importing files (2026-10-09)

- **Export pack (with art)** on a completed import, Choose Color profile or file import writes `costume-packs/<name>.d2costumepack` (never overwrites; numbered when taken) and reveals it in Finder. `POST /api/export {job, reveal, art:true}`.
- **Import a pack or recipe…** at the top of the import queue opens a native file chooser and queues `tools/d2_appearance_add.py import FILE` as a job of kind `pack`; the finished job lists the costumes and any Choose Color slots and offers Use for next playtest, Play this profile and both exports. `POST /api/import-file {choose:true}` (or `{path}`); only `.d2costumepack` and `.d2costume.json` files are accepted. Job records persist across restarts like imports.
- Packs contain game artwork and are for private exchange; `costume-packs/` is ignored by Git.
