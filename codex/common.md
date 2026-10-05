You are working on a static recompilation port of Disgaea D2 (PS3, BLUS31313) to native macOS arm64 using the ps3recomp SDK.
Root: /Volumes/Data/Applications/QuiverLauncher/Apps/Disgaea D2-RE . READ OPERATIONS.md there first: it has layout, build commands, patches, and findings.
Rules:
- Never modify the game dump folder "Disgaea D2 A Brighter Darkness - [BLUS31313]".
- Use YOUR OWN build dir (given below), configured exactly like port/build in OPERATIONS.md (copy the cmake line, change -B). Do not touch port/build or other workers' build dirs.
- Run the game with: cd root; PS3_VFS_ROOT="$PWD/Disgaea D2 A Brighter Darkness - [BLUS31313]" PS3_HDD0_ROOT="$PWD/port/hdd0" perl -e 'alarm shift; exec @ARGV' 40 ./port/<yourbuild>/DisgaeaD2Recomp work/EBOOT.elf > port/runs/<yourname>.log 2>&1   (logs are big; grep them, never cat them whole). If Metal cannot open a window in your sandbox, set PS3RECOMP_METAL_HEADLESS=1.
- Fix root causes in the shared place (SDK runtime) when the bug is generic; put game-specific overrides in port/stubs.cpp (or a new port/src/d2_*.cpp, added to port/CMakeLists.txt). Keep diffs minimal and match surrounding code style. Other workers edit concurrently: touch only files relevant to your task.
- Reference ports for prior art: gh repos sp00nznet/twistedmetal, shadowofthecolossus, simpsonsarcade-ps3, crazytaxi-ps3, ducktales; PR sp00nznet/ps3recomp#160 (macOS runner, Yakuza). Use `gh` to read them.
- Do not commit or push anything.
Finish with a concise report: root cause(s), files changed, how verified (log lines), what remains. Write it also to codex/<yourname>.report.md.
