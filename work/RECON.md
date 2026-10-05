# Disgaea D2 (BLUS31313) — phase 0 recon, 2026-10-04

- `EBOOT.elf`: decrypted from `EBOOT.BIN` with `rpcs3 --decrypt` (RPCS3 0.0.40, FW 4.46 from disc PUP).
- PPC64 BE, stripped, single binary, no game SPRX.
  - text 0x10000..0x3c6268 (~3.7 MB), data 0x3d0000 (filesz 0xb8298, memsz 0x1d139b0 — big BSS)
  - ~6.4k non-leaf functions (mflr r0 count); ~10k total is a fair guess.
- SPU: 2 embedded programs only, **no SPURS**:
  - `synth2.elf` @0x3a7380 (~40 KB) — Sony libsynth2 audio
  - `NisGraphics.spu.elf` @0x3b1300 (~19 KB) — NIS graphics helper, SDK 420 GCC 4.1.1
- Imports: cellGcmSys, cellResc, cellAudio, libsynth2, cellFs/sys_fs, cellSysutil, cellGame,
  cellSync, cellRtc, cellL10n, cellSysmodule, sysPrxForUser, sys_io,
  movie stack (cellPamf/cellDmux/libvdec/cellVpost/cellAdec/cellAtrac — `dis3_0.dat` is a PAMF movie),
  online/stubbable (sceNp2, sceNpTrophy, sceNpTus, cellNetCtl, sys_net, cellScreenShotUtility).
- Engine: NIS "NisLib" (NisGcm, NisGraphics, NisFios, NisMovie, NisSaveData, NisPad).
  Data archives are `NISPACK` (same as Disgaea PC tools: D5tools / UDT); textures `.txf`.
- References on disk: Vita3K has PCSE00360 (Disgaea 4 Return) and PCSE00022 (Disgaea 3 AoD).
  Disgaea 4 Complete+ (Steam) not installed in /Volumes/Data/SteamLibrary.
- `d2_strings.txt`: strings dump for diffing against D4.
