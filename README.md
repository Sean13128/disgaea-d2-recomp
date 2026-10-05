# Disgaea D2 — native macOS port (static recompilation)

Disgaea D2: A Brighter Darkness (PS3, BLUS31313) recompiled to native arm64 macOS with
[ps3recomp](https://github.com/sp00nznet/ps3recomp), rendering through Metal.

**No game data is in this repo.** You need your own disc dump and a decrypted `EBOOT.elf`.

- Status, metrics and the full engineering log: [OPERATIONS.md](OPERATIONS.md)
- SDK changes: `patches/ps3recomp-d2-macos.diff` (apply to ps3recomp `a679051`)
- Play: `port/play.sh` · diagnose: `port/capture.sh` · app bundle: `cmake --build port/build --target DisgaeaD2Dist`
- Build steps and layout: see "Layout" and "Build configure line" in OPERATIONS.md
