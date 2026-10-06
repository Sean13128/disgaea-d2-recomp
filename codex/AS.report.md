# AS: cheat menu moved to the native macOS menu bar

The in-game cheat overlay has been removed. Cheats are now a top-level **Cheats** menu in the macOS menu bar and a native AppKit **Disgaea D2 Cheats** window. F1 / ⌘⇧C in the game window opens and closes that window; nothing is drawn in the game frame any more. Game access goes through a C bridge in `d2_cheats.h`. Host and UI threads only queue actions and copy snapshots. The PPU main thread resolves the save root, applies queued actions and publishes snapshots once per vblank, as before.

Verified on the real game for **1.40 and 1.00**. In each run, an HL value was entered in the native window and the PPU wrote it. A real save through D2's own callbacks put it in `SAVEDATA.DAT`, and a fresh launch from that HDD copy loaded it. Full ctest in `port/build-as` passes: **51/51**. No commits or pushes. `port/build`, `port/dist` and the user's real saves and settings were not touched.

## UI

**Menu bar → Cheats** (inserted right after *Game*; the old *Game → Cheats…* entry is removed):
- **Cheats Window…** ⌘⇧C (F1 in the game window does the same). **Close Cheats Window** ⌘W.
- Checkmark items: **Infinite HP**, **Infinite SP**, **One-Hit Kills**, **Free Item Shop**.
- **EXP Multiplier ▸** 1× … 1024×, as radio checkmarks. **Disable All Cheats**.
- **HL, Mana & Cheat Shop…** and **Characters…** open the window on the matching tab.
- **Item Editor…** calls the weak `d2_item_editor_show()`. It is disabled when that symbol is absent; AT now defines it.
- **Presets ▸** Save/Load Default and Preset 1–3, plus Manage Presets…. A Load item is disabled when its file does not exist.
- A disabled status line, e.g. `Game 1.40 · save loaded, 118 units`, `Waiting for the game…` or `Version not validated: read only`.
- Checkmarks and enabled states come from the latest snapshot. Opening the menu requests a fresh one.

**Window** (900×600, tabs, live refresh every 0.25 s while open):
- **General:**
  - The 9 General fields (HL, Bonus Gauge, gauge progress, Cheat Shop CP and five rates), each with its range shown.
  - The four cheat checkboxes, the EXP multiplier pop-up and Disable All.
- **Characters:** a roster table (#, name, Lv, class) and a detail pane for the selected unit with three sub-tabs:
  - **Stats:** all 35 character fields from the JSON (level, mana, EXP, HP/SP, effective and base stats, aptitudes, class, move/jump/counter/throw/critical).
  - **Skills:** an editable table of ID, level, EXP and boost.
  - **Equipment:** a slot pop-up showing item names, an item-field grid for the equipped record, and an "Open Item Editor…" button.
- **Presets:** four rows showing file state and modified date, with Save/Load. Load asks for confirmation.
- **Status bar:** readiness (green "● 1.40 · editing live save", "Saving/loading… edits paused", etc.) and the last PPU result, or a local validation error in red.

**Validation and keyboard:**
- Fields accept whole numbers only; commas and spaces are ignored. A value outside the field's JSON range is rejected with a beep and a red message, and the field reverts.
- Return or Tab applies a value. Tabbing through unchanged fields writes nothing.
- Values the game changes refresh live without stealing focus. A field the user is typing in is never overwritten.
- Fields become read-only while saving/loading, before a save is loaded, or on an unverified profile. View-only fields such as the item ID are never editable.
- The PPU clamps again (for example, HP/SP to the unit's max) and rejects stale edits.
- Keyboard: F1 or Esc closes the window (Esc only when no text field is being edited), the key-view loop is on, and the roster supports type-select.
- Closing the window gives keyboard focus back to the game window. The window follows the game's window level and works over native fullscreen.

**Screenshots** (real game, 1.40 slot 01, from the native window):
- `milestones/cheats-native-general.png`
- `milestones/cheats-native-characters-stats.png`
- `milestones/cheats-native-characters-skills.png`
- `milestones/cheats-native-characters-equipment.png`
- `milestones/cheats-native-presets.png`

Originals plus the 1.00 set are under `port/runs/AS-host-{140.Tcz6pP,100.T05ets}/shots/`. The images come from AppKit rendering the window's frame view (`cacheDisplayInRect`). `screencapture -l` fails here because this session has no Screen Recording permission ("could not create image from window"). In that render path, the unselected labels of NSTabView tabs don't draw. In the live window the tabs are normal NSTabView tabs. Instead of a menu screenshot, the Cheats menu as AppKit validated it is logged, e.g. `port/runs/AS-host-100.T05ets/edit.log`: `'Infinite HP' [checked]`, `'Game 1.00 · save loaded, 118 units' [disabled]`.

## Bridge API (`port/src/d2_cheats.h`)

The header comment documents the threading contract, the generation rule and the item subset.

| Function | Purpose |
|---|---|
| `d2_cheats_fields(scope, &out)` / `d2_cheats_field_index(scope, key)` | Field descriptors (key, label, min, max, size, readonly) parsed from `d2_cheats.v1.json`. Available at any time. Scopes are `D2_CHEATS_GENERAL/CHARACTER/ITEM`. Snapshot value arrays use this order. |
| `d2_cheats_snapshot(D2CheatsSnapshot*)` | Copies the last publish: serial, generation, supported/verified/ready, version, status, toggles, EXP multiplier, general values, roster (name/level/class ×128), selected-unit detail (fields, skills, 4 equipment records) and inventory count. |
| `d2_cheats_select_unit(unit)` | Picks the unit whose detail is published. |
| `d2_cheats_set_general / set_character / set_skill(unit, i, key) / set_toggle / set_exp_multiplier / disable_all / preset(save, slot)` | Queue actions. They return -1 for an unknown key or out-of-range argument and never touch guest memory. |
| **Items:** `d2_cheats_items_snapshot(D2CheatsItems*)`, `d2_cheats_set_item(slot, key, v, gen)`, `d2_cheats_set_equipment(unit, slot, key, v, gen)`, `d2_cheats_add_item(id)`, `d2_cheats_remove_item(slot, gen)` | Inventory pool snapshot (occupied slots, every item field) and item actions. Adding and removing use the existing signature-checked native helpers. |
| `d2_cheats_preset_path(slot)` | Preset file path. `D2_CHEATS_PRESET_DIR` overrides the folder (tests). |
| `d2_cheats_toggle_menu()` / `d2_cheats_window_toggle()` | Hotkey and menu entry points into the native window. |

Rules:
- Targeted edits pass the snapshot `generation`. The PPU rejects them if the root, party or inventory count changed, or a save/load happened since.
- Publishing runs at about 4 Hz while a window or menu reads snapshots, 1 Hz otherwise, and immediately after applying actions.
- The item list (about 450 KB) is built only while someone calls `d2_cheats_items_snapshot` (within the last 2 s).
- The queue is capped at 256 actions.

**Note on AT:** AT built its own item bridge (`d2_items.h`/`d2_items.cpp`, richer records with innocents, a catalog and icons). Its PPU tick runs through a weak `d2_items_frame(ctx)` call that AT inserted into my `ps3_guest_frame_hook`. I kept that call and removed my duplicate. The item functions in `d2_cheats.h` stay stable and tested, but AT's window doesn't use them today. The two could be merged later. AT's `d2_items.cpp` also duplicates per-version addresses from `d2_cheats.v1.json` (marked with a ponytail note).

## Overlay removal

These were deleted from `d2_cheats.cpp`: `build_rows/display/close/action`, page/row/edit state, the `requests` counter, the `D2_CHEATS_OPEN_PAGE` automation and the `sys_overlay.h` include. Nothing in D2 opens `SYS_OVERLAY_EDITOR` any more; host runs show no `sys overlay … D2 cheats` line.

The SDK side (`sys_overlay` editor mode, Metal editor raster/footer, the weak pad hotkey hook) is untouched: no SDK edits. The editor mode is now unused by D2, and its own SDK test (`d2.overlay`) still passes. `codex/AF.raster-test.cpp` (raster of the old overlay) and the stale copy `codex/AF.editor-test.cpp` were deleted; the maintained copy is `port/tests/AF.editor-test.cpp`. `codex/AF.host-check.sh` now forwards to `AS.host-check.sh`.

## Tests

- **`d2.editor-100` / `d2.editor-140`** (`port/tests/AF.editor-test.cpp`, ASan/UBSan). The AF assertions are kept: clamps, bounds, version gating, damage/EXP/shop/SP hooks, presets.
  - Overlay steps were replaced by bridge equivalents. Hotkeys F1 and ⌘⇧C now trigger the native window toggle; key repeat and plain C don't.
  - New `bridge_tests`:
    - descriptor counts (9/35/18) and the readonly flag;
    - host argument rejection, with nothing queued;
    - queue-only host calls (guest memory unchanged until the PPU service runs);
    - apply → publish;
    - stale-generation and not-ready rejection;
    - missing unit and skill slot;
    - skills (with boost clamp) and equipment;
    - items: published only for a viewer, edits applied, readonly ID, empty slot, removal guard;
    - presets in an override directory;
    - a host thread racing 2000 queued edits and snapshot reads against the service loop.
- **`d2.AS-ui`** (new, `port/tests/AS.ui-test.m`, real AppKit against a recording fake bridge):
  - the Cheats menu sits after Game;
  - checkmarks, multiplier radio and enabled states follow the snapshot;
  - menu actions queue the right bridge calls;
  - the Item Editor item is disabled when the weak symbol is absent;
  - Load Preset is disabled with no file;
  - the window opens via the toggle;
  - HL input "1,234,567" commits once with the snapshot generation; "12abc" and an over-maximum value are rejected with a message;
  - an unchanged value is not written, and live refresh works;
  - the roster drives `select_unit`;
  - character field, skill-table and equipment edits target the right unit/slot, and a skill level above 99 is rejected;
  - the item ID field is read-only;
  - not-ready makes fields read-only;
  - closing stops the timer.
- **`--settings-test`** (AG): asserts 7 top-level menus, Cheats right after Game, and no "Cheats…" left in Game. PASS.
- **Full ctest** `port/build-as`: 100% (51/51). The 1.00 build `port/build-as100` builds cleanly.
- **Real game:** `bash codex/AS.host-check.sh` (1.40) and `AS_VERSION=100 bash codex/AS.host-check.sh`. Both PASS: `port/runs/AS-host-140.Tcz6pP/evidence.txt` and `port/runs/AS-host-100.T05ets/evidence.txt`.
  - **Setup:** private copies of `port/hdd0`/`hdd1` in `/Volumes/Data/ai-tmp/claude/AS-host.*` (removed on exit), slot `NPUB31321_NORMAL_01`, `SDL_AUDIODRIVER=dummy`, 55 s runs, and it refuses to start while another `DisgaeaD2Recomp` runs.
  - **Edit run:** waits for the loaded 118-unit save. It types `993701507631` into the native HL field and activates *Infinite HP* through the Cheats menu item.
    - The PPU logs `write hl offset=000568 993701506631 -> 993701507631`, then `SAVE complete … result=00000000`.
    - The snapshot then reads back `HL=993701507631 hp_lock=1`.
    - The saved `SAVEDATA.DAT` holds the new HL.
  - **Reload run:** a fresh launch from that HDD copy logs `resolved … HL=993701507631 party=118` after `LOAD complete`.
  - Test automation needs an `AF-`/`AS-` HDD path, as before.

An early run caught a real pitfall. The UI first sees the game's pre-load default party (5 units, HL=300), and an automated edit and save there would save that state. Automation now waits for `D2_CHEATS_UI_WAIT_UNITS=118`, and test saves require the 118-unit save. Normal user edits at the title screen are harmless, because loading a save replaces that state.

## Files changed (mine)

- `port/src/d2_cheats.h`: new bridge API and documentation.
- `port/src/d2_cheats.cpp`: overlay removed; bridge queue/publish/perform added; `apply` takes unit/skill; preset path override; `AS-` test HDDs; `D2_CHEATS_TEST_SAVE_WHEN_HL`. AT's `d2_items_frame` call is kept.
- `port/src/d2_cheats_ui.m` (new): Cheats menu, window, opt-in automation (`D2_CHEATS_UI_OPEN/TEST_HL/TEST_MENU/SHOT_DIR/WAIT_UNITS`).
- `port/src/d2_settings.m`: installs the Cheats menu via weak `d2_cheats_menu_install`; drops Game → Cheats…; settings test updated.
- `port/src/d2_bundle.cmake`: adds `d2_cheats_ui.m` (ARC) and `-U` for `d2_cheats_menu_install` / `d2_item_editor_show`. `port/CMakeLists.txt` is not edited by me.
- `port/tests/AF.editor-test.cpp`, `port/tests/AS.ui-test.m` (new), plus my hunks in `port/tests/run.py` (`AS-ui` target; editor test no longer links `sys_overlay.o`) and `port/tests/CMakeLists.txt` (`AS-ui` as an AppKit/host-ui test).
- `codex/AS.host-check.sh` (new), `codex/AF.host-check.sh` (forwarder), deleted `codex/AF.raster-test.cpp` and `codex/AF.editor-test.cpp`, `milestones/cheats-native-*.png`, this report.
- Unchanged: `port/d2_cheats.v1.json`, the SDK, d2_fill, the override code, AR/AT files.

## Known gaps

- No real interactive keyboard/mouse session was driven: the HL commit is programmatic `sendAction` on the real field, and the menu item is activated programmatically. No Screen Recording permission, so no window-server screenshots and no captured menu image (validated menu state is logged instead).
- OPERATIONS.md still describes F1 as an overlay ("Menu bar"/F1 lines). That is for the lead to update: "Cheats menu in the menu bar; F1/⌘⇧C opens the native Cheats window".
- Skill table cells and the class field take raw IDs; there are no name lists. Character name editing, adding/removing skills and equip/unequip remain unmapped, as in AF.
- The bridge's item functions duplicate what AT's `d2_items` provides; consolidating them is open.
- The SDK `sys_overlay` editor mode is now dead code for D2. It was left in place to avoid SDK churn and can be removed upstream later.
