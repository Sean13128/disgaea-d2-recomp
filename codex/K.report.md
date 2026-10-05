# K — movie playback

The real movie path is enabled by default; `D2_MOVIE_SKIP=1` retains I's clean skip. The generic SDK pipeline is implemented and builds. **Native VideoToolbox playback remains unverified:** this sandbox fails session creation with `-12911`, including an independent baseline H.264 clip. Run the host check below before treating movies as working.

## Root causes and changes

- Demux was a stub, with missing exports and incorrect callback/guest AU layouts. Added streaming MPEG-PS/PAMF demux, AVC access units delimited by AUD NALs, and ATRAC3plus ATS frames. PES boundaries are not picture boundaries: the full movie contains 2,793 video AUs but only 299 timestamped PES groups. Guest ES rings retain AUs until release; reset, flush, program-end and completion notifications use `ps3_invoke_guest`.
- Guest callbacks on different host workers shared one guest stack. The PPU bridge now uses the caller's stack for nested callbacks and separate, recyclable stacks for host workers. Callback function descriptors, arguments and active guest context are preserved.
- libvdec emitted dummy pictures. Added Annex-B → AVCC handling, SPS/VUI parsing, VideoToolbox decoding, temporal reordering, timestamp interpolation and stride-aware NV12 → planar YUV420 copies. Delayed pictures flush at EndSeq. Other platforms retain an unsupported decoder stub; no new third-party dependency.
- Vpost lacked conversion and three imported exports. Added firmware ABI layouts, YUV420 → RGBA/planar conversion, crop/scaling, BT.601/709, range and alpha handling. Vdec also supports ARGB/RGBA/UYVY/planar output.
- Adec did not connect PAMF audio to the existing decoder. Added ATRAC3plus ATS removal, header-driven 48 kHz stereo initialization, existing `at3p_decode`, guest-endian PCM formats and PCM metadata/callbacks. PAMF audio stream info now returns the firmware sample-rate enum, fixing D2's getStreamInfo failure.

## Files changed

- SDK `libs/codec/`: `cellDmux.c/.h`, `cellVdec.c/.h`, `cellVpost.c/.h`, `cellAdec.c/.h`, one field in `cellPamf.c`; new `pamf_demux.c/.h`, `avc_decoder.cpp/.h`, `avc_sps.c/.h`, `video_convert.c/.h`.
- SDK `CMakeLists.txt`: C++ codec compilation and Apple codec frameworks. `runtime/ppu/ppu_loader.cpp`: callback stacks only.
- Tests: new `libs/codec/tests/test_movie.cpp`, `test_vpost.c`, `runtime/ppu/tests/test_codec_callbacks.cpp`; one expected enum in I's `test_pamf.c`.
- Port `port/src/d2_movie.cpp`: default playback / skip opt-out. Deliverables: `patches/K-movie.diff`, this report, `codex/K.host-check.sh`.

The SDK patch contains only K's changes and depends on I's existing PAMF work. Reverse application check passes. Only `port/build-k` was used; no dump, other build directory, input/RSX/Resc code, commits or pushes were touched.

## Verification

- `port/runs/K-build.log:60`: final native executable linked successfully.
- `K-full-demux.log:8,23`: real SPS 1280×720 progressive 24000/1001 fps; full movie **2,793 video AUs, 2,733 decoded PCM blocks, zero errors**. Prime-sized input chunks split every kind of header.
- `K-es-hash.log:1`: all 290,440,372 AVC bytes match independent PES extraction, SHA256 `f7cabff416b79f6b39568df304c4e7d81ac52c7cbd0bee2afaa22463b9e68d3c`. Independent FFmpeg software decoding of that stream completed without errors (`K-full-video-reference.log`). FFmpeg is verification only.
- `K-sanitizer.log:15`: ASan/UBSan demux/audio run, 901 AUs / 880 PCM blocks, zero errors. `K-vpost-sanitizer.log:5–6`: conversion, matrices, UYVY, scaling, alpha, crop/canaries and actual decoded frame pass. Images `port/runs/K-decoded/vpost-390.png` and `vpost-900.png` were visually inspected; these use software-decoded input, not VideoToolbox.
- `K-callback.log:1`: real PPU guest dispatch, eight concurrent workers, nested callback canaries/context restoration and 200 recycled worker lifetimes pass. `K-pamf.log:8`: real-header regression passes.
- `K-native-final.log:275,277,288`: D2 opens real video/audio decoders and starts ATRAC3plus. Lines 312–313 fail at VideoToolbox session creation with `-12911`. Independent VideoToolbox baseline fails too (`K-vt-baseline.log:78–79`), pointing to this execution environment.
- `K-skip.log:253–254,1688`: opt-out finishes cleanly and reaches presented frame 900 in the requested 40-second run. Host script syntax and patch whitespace checks pass.

## Host check and remaining work

Run `bash codex/K.host-check.sh` from the real host. It builds only build-k, exercises actual VideoToolbox decoding of 900 movie frames and guest callback tests, then runs D2 on real Metal for 40 seconds. Unique `port/runs/K-host.*` folders retain codec/game logs, movie conversion captures, Metal captures and PNGs. The script uses grep and contains no rm.

Confirm VideoToolbox images, visible playback, audible movie audio, A/V synchronization and movie completion/skip/replay. Interlaced Vpost effects and non-AVC video codecs remain unsupported. No claim of end-to-end native playback is made from sandbox results.

Prior art: [Twisted Metal vdec HLE](https://github.com/sp00nznet/twistedmetal/blob/main/src/vdec_hle.cpp), [macOS runner PR #160](https://github.com/sp00nznet/ps3recomp/pull/160), and RPCS3 firmware codec headers for [Dmux](https://github.com/RPCS3/rpcs3/blob/master/rpcs3/Emu/Cell/Modules/cellDmux.h), [Vdec](https://github.com/RPCS3/rpcs3/blob/master/rpcs3/Emu/Cell/Modules/cellVdec.h), [Vpost](https://github.com/RPCS3/rpcs3/blob/master/rpcs3/Emu/Cell/Modules/cellVpost.h), and [ATRACX](https://github.com/RPCS3/rpcs3/blob/master/rpcs3/Emu/Cell/Modules/cellAtracXdec.h).
