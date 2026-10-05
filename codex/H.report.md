# Task H — ATRAC streaming and macOS audio

Fixed in the SDK. D2 starts BGM with **102,400 bytes loaded into a 262,144-byte guest buffer**, while the RIFF data spans **3,690,664 bytes**. The old implementation indexed that buffer as a complete file and always reported ALLDATA_IS_ON_MEMORY. Missing refill NIDs silently returned success. This explains the real-Metal decoder error flood after the initial data ran out.

The runtime now tracks staging-ring capacity, file-relative refill offsets, submitted compressed ranges, remaining frames, underruns, seek preroll and loops. Submitted compressed bytes survive guest-buffer reuse in a host cache; a second guest buffer is unnecessary. Implemented all four requested NIDs: GetStreamDataInfo `2BFFF084`, AddStreamData `46CFC013`, IsSecondBufferNeeded `99EFE171`, GetBufferInfoForResetting `99FB73D1`. The generated build-h table registers them. Added GetInternalErrorInfo; decoder failures return an error instead of invented silence.

Two additional integration defects were fixed: FFmpeg's bit reader requires packet padding (ASan reproduced an overread at the last frame), and allocation rebuilds global VLC/DSP/FFT tables while other contexts may decode. The bridge now pads packets and excludes allocation from concurrent decoding, while allowing parallel decodes.

Format selection, RIFF byte order and decoder delay were correct. A read-only SOUND scan found 8,271 ATRAC3plus GUIDs, all 48 kHz: 106 stereo and 8,165 mono (`H-format-scan.log:2–3`). Plain ATRAC3 remains unsupported; no D2 RIFF fixture needs it. The HLE cache reserves the compressed file's size per active handle; it does not emulate the console's physical second-buffer layout.

Files changed:

- SDK: `libs/codec/cellAtrac.c`, `cellAtrac.h`, `tests/test_cellAtrac.c`; `third_party/at3_standalone/at3_bridge.cpp`, `README.txt`; `libs/audio/cellAudio.c` (SDL driver/format/queue-error logging and existing audio diagnostics enabled on POSIX).
- Deliverables: `patches/H-atrac.diff`, `codex/H.validate.sh`, `H.decoder-threads.cpp`, `H.audio-host.c`, `H.host-check.sh`, this report. The patch includes only H changes, preserving D's clock fix; reverse-apply and whitespace checks pass.

Verification (logs under `port/runs/`):

- Only `port/build-h` configured/built with OPERATIONS.md's flags; `H.build-final.log:9` links. Both 40-second game runs ended with expected alarm exit 142.
- `H-final.log:15010`: real D2 streaming SetData. Lines 15565/19456: guest refills of 159,744/211,112 bytes, advancing to offset 473,256. Lines 16756/21752: decode calls 101/301, PCM peaks 0.2004/0.3247. **Zero ATRAC decoder error lines.**
- `H-bgm-validation.log:5–11`: complete 153.7-second BGM, 7,377,991 samples/channel, RMS 0.229, peak 1.017. 2,418 split-frame refills produce identical PCM to full-memory decoding. Underrun retries, loop/reset, uncached seeks and looping through an uncached seek gap pass with zero comparison error.
- `H-voice-validation.log:4–7`: mono voice, 493,312 samples (10.3 seconds), RMS 0.132; streaming/seek pass. Both real-data fixtures pass AddressSanitizer and UndefinedBehaviorSanitizer without decoder errors. Reproduce with `zsh codex/H.validate.sh`.
- `H-threads.log:1`: three workers, 36 allocations, 3,600 frames, identical PCM. Existing mixer regression passes: final line of `H-audio-ring.log`, “audio ring: 3 sizes, 3 wraps each passed”.
- WAVs: `H-bgm.wav`, `H-voice.wav`, `H-game-mix.wav`. The actual game cellAudio mix contains 39.47 seconds, RMS 0.027455, peak 0.438987, no non-finite samples (`H-mix-analysis.log:1`). `H-final.log:18385,21315`: 187.5 blocks/sec, only 1.2% silent during BGM.

Remaining: physical speaker output is unverified. The sandbox cannot open CoreAudio (`H-audio-host-sandbox.log:1`, DeviceIsAlive error 560947818). Claude should run **`zsh codex/H.host-check.sh` on the real host**. Confirm the five-second 440 Hz tone is audible and `H-host-audio.log` reports `driver=coreaudio`; then confirm audible D2 BGM, successful coreaudio/48000/stereo/float output, nonzero peaks, roughly 187.5 blocks/sec, and no ATRAC errors in `H-host.log`. The tone exercises the actual SDK guest-float mixer and SDL backend. The script uses only build-h and its own temporary HDD1 cache.

No game dump changes, commits or pushes. General gameplay/rendering progress remains outside this task.
