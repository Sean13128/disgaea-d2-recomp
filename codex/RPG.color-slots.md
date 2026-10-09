# Native Choose Color appearance experiment

The research runner now supports an explicit `color_slots` manifest catalog.
Normal Color retains the original appearance; Extra colors 1–4 can select four
imported costumes per character. Unassigned extra choices retain retail art.
Existing profiles without this catalog keep their prior class-wide selection.
The native unit color byte at +0x1183 drives body, face and Status illustration.
Class-only face draws and preview actors use their explicit color argument.
Choose Color's palette-only cursor update now rebinds the preview visual first.
The macOS Appearance picker is disabled for these classes to avoid conflicting
selection mechanisms. Native menu strings still read Extra color 1–4.

In Sprite Workbench, open Import queue, then choose **Build Choose Color profile**
on a completed import. This creates a separate profile containing its complete
costume catalog and copies its saves without modifying the source. Existing slot
assignments retain their numbers; new costumes fill empty choices. More than four
costumes for one class is rejected explicitly. The completed job displays every
slot assignment and has **Play Choose Color profile** and **Use for next playtest**.
Building does not automatically change the current profile.

Prepared launcher: `Playtest Choose Color.command`.
Profile: `work/appearance-profiles/colors-20261008-native-menu/stage.json`.

| Character | Extra color 1 | Extra color 2 |
| --- | --- | --- |
| Laharl | Dark Santa Laharl | retail |
| Etna | Liones Princess Etna | Standard RPG Etna |
| Flonne | Apprentice Angel Flonne | retail |
| Valvatorez | Yukata Valvatorez | retail |
| Fuka | RPG Fuka | retail |

Verification: all 22 related CTests passed; production C++ fixtures cover distinct
native colors, explicit preview colors overriding saved unit color, portrait/body
routing, preserving all unit bytes, and legacy importer builds. GUI tests cover
stable assignment, overflow, independent save copies, persistence and launch
routing. Real browser button created a six-costume profile with no JS errors.
Native Metal launch reached the castle showing original Laharl under Normal Color.
Native Assembly cursor/confirm and save/reload verification remain pending;
this is a research playtest, not an installed primary-app release. Slot expansion
beyond the five retail choices is not implemented.

The 180-second native follow-up exercised castle movement near the Assembly
counter, but did not enter its menu. No native cursor or save/reload result is
claimed. Evidence lives in `work/appearance-development/colors-20261008-menu-playtest`.

## Oversized costume frames — October 9

The owner confirmed native Choose Color selection works and supplied an Assembly
preview showing Santa Laharl's scarf cut off. The importer enlarged own cells
only as far as available atlas space allowed, leaving overflow cropped. Shared
animation rectangles are fixed, so they could crop larger costumes too.

The builder now fits remaining oversized art within the transparent cell rim,
after trying its existing enlargement. Related numbered frames share their
fitting scale; fully enlarged cells keep native-scale art. Pixel placement follows
the authored pivot as far as the cell bounds permit. Smaller artwork is unchanged.
This trades a small size reduction on affected frames for a complete silhouette.
Regression tests cover locked cells, common frames and consistent sequence scale.

All six appearances were rebuilt, with zero reported clipped pixels and exact
guest decoder matches. Corrected profile:
`work/appearance-profiles/colors-20261009-frame-fit/stage.json`.
The launcher now points here; its HDD0 copy matches all 495 payloads of the user's
latest closed October 8 profile. Original profile and sources were retained.
Evidence: `work/appearance-development/overflow-20261009/results.json`,
`laharl-idle-before-after.png`, and the corrected profile's `frame-fit-refresh.json`.

Native Metal smoke of the corrected profile reached the castle. Its loaded save
selected Original Laharl, so this proves profile loading, not the fitted costume's
appearance in the live Assembly menu. The corrected idle atlas crop visibly
retains the scarf tip; native menu retesting remains the next visual check.

2026-10-09: Choose Color row icons now follow the slot assignment (generic list
face lookups resolve the class from face identity when exactly one slot-managed
class owns it). Owner confirmed in game that the row icons and the enlarged
costume art are correct. Runner SHA256 6f08e4a6344427aeac5c663cee772cf4949fb1790ae1e54332d69aea415b77d0.
