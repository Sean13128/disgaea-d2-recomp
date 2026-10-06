# AC — retail save interoperability

Status: **complete**. Retail post-game save decrypted, authenticated with all available public-key hashes, and loaded into a stable native-port castle hub. Existing saves and game dump untouched.

## Root cause and secure file ID

Retail `SAVEDATA.DAT` is the console's protected file, not the RPCS3/plain bytes expected by this port. PFD supplies the useful length: this importer requires **1,498,152** useful bytes, padded to **1,498,160** in encrypted form. The runtime intentionally reads/writes both SECUREFILE (type 0) and NORMALFILE as ordinary host files. `cellSaveData.c:353` copies the guest secure ID into its host FileSet; `process_file_op` does no console cryptography and uses SFO `*filename` flags for secure-file metadata. No runtime change is needed.

**D2 secure file ID: `0f0f0f0f0f0f0f0f0f0f0f0f0f0f0f0f`.** Static source: lifted load callback `func_00164C3C` (`port/src/recomp/ppu_recomp_007.cpp:48360`) reads `*(TOC - 0x46c0) + 0x40` and copies 16 bytes to FileSet `+0x0c`. Save callback `func_00164D74` uses the same source (`:48557`). With TOC `0x3fde60`, the ELF TOC entry is `0x396c58`, so the ID lives at guest address **`0x396c98`**. Read-only ELF PT_LOAD mapping confirms all 16 bytes are `0f`. No logging changes or modifications to the game dump/lift were necessary.

## Implementation and references

- [tools/d2_save_import.py](../tools/d2_save_import.py): Python 3 + the existing `.venv` pycryptodome. Parses PFD v3/v4 and bounded PSF metadata. Verifies PFD top/bottom hashes and every entry chain, secure-file HMAC-SHA1, and PARAM.SFO hashes using the public SFO key and authentication ID. Console-ID and disc-key file hashes are explicitly reported unavailable; no private account/console keys are needed.
- PFD signature and 64-byte entry keys use AES-128-CBC with public syscon key `d413b89663e1fe9f75143d3bb4565274`. The entry-key IV is the first 16 bytes of the secure-ID-derived 20-byte hash key (insert `0b`, `0f`, `0e`, `0a` at indices 1, 2, 5, 8). File block `i` decrypts as `AES_DEC_K(cipher_i) XOR AES_ENC_K(be64(i) || zero64)`; K is the first 16 bytes of the unwrapped entry key. Trim to PFD's recorded true size after decryption.
- Keep ICON0.PNG byte-exact and preserve all SFO fields/opaque allocations except updating SAVEDATA_DIRECTORY and secure-file flags. Omit PARAM.PFD from the resulting plain save. Exclusively reserve a free `NPUB31321_NORMAL_00..99` slot. Default target is a fresh copy of `port/hdd0` under `port/runs/AC-import-*/hdd0`; `--into` explicitly selects a target. Existing saves/source/dump are not overwritten; unsafe source/target symlinks and dump/source overlap are rejected.
- [codex/AC.save-import-test.py](AC.save-import-test.py): synthetic encryption/PFD fixtures and integrity/safety regressions, with an optional independent flatz C-tool encrypt/decrypt cross-check.
- [codex/AC.host-check.sh](AC.host-check.sh): importer → isolated hdd0 → `build-ac` headless Continue at 75 seconds, with gameplay state tracing. Requires LOAD completion, a full secure-file read and a **final** hub map. `AC_FAST=1` uses the requested 40-second run with 10/14-second input. Both skip movies for deterministic timing and isolate hdd1.
- `.gitignore`: only AC importer and test/helper script whitelist additions. No SDK/runtime or other worker source changes; no commits/pushes.

Algorithms/format read with `gh`:

- [flatz pfdtool mirror, pfd.c](https://github.com/SteffenL/pfdtool/blob/ac6c042a2778e775a72cb6d583694873a774cfd8/src/pfd.c), plus `pfd_internal.h` and `pfd.h`: wrapping, counter transform, PFD tables, entry/file HMACs. The original `flatz/pfdtool` repo is unavailable; this mirror retains the implementation.
- [bucanero's flatz tools mirror](https://github.com/bucanero/pfd_sfo_tools/tree/9e34653e0ac558f12d58f7cacd28d8be79353793/pfdtool): compiled unchanged in disposable task scratch for independent verification.
- [Apollo pfd.c](https://github.com/bucanero/apollo-ps3/blob/4d1859dd35c2a971dec78633c7e6061d5ff427d1/source/pfd.c) and [pfd_util.c](https://github.com/bucanero/apollo-ps3/blob/4d1859dd35c2a971dec78633c7e6061d5ff427d1/source/pfd_util.c): public keys (after `setup_key` XOR decoding), standalone protected-file import.
- [apollo-lib decrypt.c](https://github.com/bucanero/apollo-lib/blob/94970dae3d83090d5a2883f2cd589e214ff36dba/source/decrypt.c) inspected; PFD handling resides in Apollo PS3, not this library. [ps3recomp PR #160](https://github.com/sp00nznet/ps3recomp/pull/160) read for macOS runner prior art.

## Verification

- Built **only `port/build-ac`**, using OPERATIONS.md's configuration from the `port` cwd (`AC-configure.log`, `AC-build.log`, final native arm64 link). `port/build` and other worker build dirs untouched.
- `port/runs/AC-unit.log:1–12`: **12 tests PASS**, including v3/v4, a forced hash-bucket collision chain, fixed-width console strings, tampered ciphertext/SFO/PFD rejection, truncation rejection, free-slot selection, all-slots-full failure, metadata/source preservation, default-copy behavior and symlink/dump protections.
- `AC-unit.log:4`: synthetic **1,498,152-byte** payload decrypts byte-exact with flatz's independently compiled C pfdtool, and its re-encryption is byte-exact with Python output. Python also imports the C-updated PFD successfully. `:17` reports `OK`.
- Synthetic console container built from a **read-only copy of the existing native save** and then imported through the normal CLI. `port/runs/AC-load.oKnell/import.log`: PFD v4 top/bottom/entry HMACs OK; PARAM.SFO[0]/[3] and SAVEDATA.DAT HMACs OK; output size **1,498,152**, SHA256 `c1351c186ae8605b7c83f524f7b1b21f62e01715f314c9ed222a8942109983fc`; chosen slot `NPUB31321_NORMAL_01`.
- `port/runs/AC-load.oKnell/run.log:1589`: `file op=0 type=0 name='SAVEDATA.DAT' off=0 size=1498152 buf=1498152 -> 1498152`; `:1590`: **LOAD complete for 'NPUB31321_NORMAL_01'**; `:1670` and later: **map_id=30003**, stable castle gameplay. No cellMsgDialog, guest fault, or unexpected termination; exit 142 is the requested 40-second alarm.
- Requested **75-second Continue** check also PASSes: `port/runs/AC-load.eZFgnu/run.log:5659` sends Cross at 75 s; `:5706–5707` reads all 1,498,152 bytes and completes LOAD; `:5789` reaches map **30003**, still there at `:8149`. Exit 142 is the 115-second alarm. Original native save/source SHA256s remain unchanged.
- **Actual GameFAQs retail save:** `port/runs/AC-retail-import.log:1–4`: PFD v4 top/bottom/all entry HMACs, PARAM.SFO[0]/[3], and SAVEDATA.DAT HMACs **PASS**. Output size **1,498,152** bytes; SHA256 **`9f5a847eb6f1804536986a93682a8304cd613f3d3ad4c702c6d087ba4e27fc30`**. Metadata: `Post Game Lv 9999`, play time `335：09：45`. ICON0 and all original SFO fields/opaque allocations are byte-exact except the slot/secure flags.
- **Actual retail in-game load:** `port/runs/AC-load.bGQIYd/run.log:5660`: sole Cross press at **75 s**; `:5707`: secure-file READ **1498152 → 1498152**; `:5708`: **LOAD complete for 'NPUB31321_NORMAL_01'**; `:5792`, `:6003` through `:7270`: **stable map_id=30001** through the end of the 115-second run. No cellMsgDialog/corrupt-save diagnostic or guest fault; exit **142** is the alarm. The earlier 75/79/85 script returned to title after extra button presses, so the helper now sends a single Continue and checks the final map, not just a transient hub state.
- Tested retail output is in **`port/runs/AC-import-6auq0npv/hdd0/home/00000001/savedata/NPUB31321_NORMAL_01/`** (see `AC-load.bGQIYd/import.log` for the canonical hdd0 path). Original `port/hdd0` saves and the encrypted source still have unchanged SHA256s.
- `:96–99`: Metal unavailable in sandbox, software FIFO fallback active. No frame dumps are claimed; map state is affirmative gameplay evidence beyond SaveData completion.
- Python compilation, shell syntax and `git diff --check` PASS.

## Usage / remaining

```sh
.venv/bin/python tools/d2_save_import.py saves-import/na-postgame/NPUB31321_NORMAL_04
bash codex/AC.host-check.sh saves-import/na-postgame/NPUB31321_NORMAL_04
# Explicitly select a live target only if desired (still uses a free slot):
.venv/bin/python tools/d2_save_import.py SOURCE --into port/hdd0
```

The approved [XYZexal NA save, download 23628](https://gamefaqs.gamespot.com/ps3/687861-disgaea-d2-a-brighter-darkness/saves) was downloaded from GameFAQs' public save page. The 1,589,736-byte ZIP passed CRC checks and matched all four expected file sizes; retained at `saves-import/AC-approved-23628.zip` and extracted to the requested `saves-import/na-postgame/NPUB31321_NORMAL_04/`. The old 6,040-byte HTML `.zip` was left untouched. `port/runs/AC-wait.log` records arrival after **20 minutes**, then the retail check.

Remaining: real Metal visual inspection/DLC-character and late-battle stress testing; this sandbox has no Metal device. No corrupt-save diagnostic was logged and stable gameplay map state is verified, but no screenshot claim is made. Optional reverse console export/resigning is not implemented. No live-save import was performed; explicitly use `--into port/hdd0` only if desired.
