# Costume recipes

Each `*.d2costume.json` file here describes imported costumes **without any artwork**: which Disgaea RPG costume becomes which Disgaea D2 appearance, its display name, Status illustration, crops and Choose Color slot, plus fingerprints of the source files.

Nothing in these files is game data. To use one you need your own Disgaea D2 (BLUS31313, 1.40) dump and your own extracted Disgaea RPG assets:

```sh
tools/costume import costume-recipes/disgaea-rpg-starter-pack.d2costume.json
tools/costume play
```

To write one from your current private profile: `tools/costume export`, or **Export recipe** in the Sprite Workbench import queue.

See `codex/RPG.costumes.md` for the full guide.

Costume **packs** (`*.d2costumepack`, made with `tools/costume export --with-art`) also carry the finished artwork so the receiver needs no RPG assets. They contain game artwork and are deliberately not kept in this repository.
