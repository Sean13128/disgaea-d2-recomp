# Disgaea D2 SPU images (BLUS31313)

Extracted from `work/EBOOT.elf` using the SDK pipeline. The game dump is never
modified. The port's existing `SPU_DIR` CMake integration compiles both lifts
and `spu_workloads.c`; its constructor registers their functions and fingerprints.

| Image | EBOOT file offset | Bytes | Entry | ELF fingerprint | Image ID |
|---|---:|---:|---:|---|---:|
| NisGraphics.spu.elf | 0x003B1300 | 20,116 | 0xD0 | 0x9E876934B7F179D6 | 1 |
| synth2.elf | 0x003A7380 | 40,804 | 0xF0 | 0x5009AA16A26A8923 | 2 |

Regenerate from the project root:

```sh
.venv/bin/python ps3recomp/tools/extract_spu_images.py work/EBOOT.elf --output port/spu/images
mv port/spu/images/spu_0000_at_003A7380.elf port/spu/images/synth2.elf
mv port/spu/images/spu_0001_at_003B1300.elf port/spu/images/NisGraphics.spu.elf
.venv/bin/python ps3recomp/tools/build_spu_workloads.py \
  --images port/spu/images --lifted port/spu --out port/spu/spu_workloads.c \
  --register-fn d2_spu_register_all --constructor --title 'Disgaea D2 BLUS31313' --relift
```

`build_spu_workloads.py` invokes `spu_lifter.py --auto-functions` with separate
symbol prefixes, fixes include paths, and also registers executable-segment
fingerprints for proxy-DMA image loads. The older `gen_spu_workloads.py` has
hard-coded title paths and is not used.

NisGraphics lifts 152 functions without unsupported instructions; synth2 lifts
561 functions. Its eight `.word` warnings are in the floating-point constant
table near LS 0x9400/0x94A0 (e.g. 0x3D800000), which the detector also classifies
as code. Task D added the resumable LV2 receive-event continuation at LS
0x9320: queue 2 commands now reach synth2 and its port 0x3A completions wake
the PPU on queue 1. See `codex/D.report.md` for boot and audio-clock checks.

For DMA/mailbox diagnostics use `SPU_MFC_TRACE=2 SPU_MBOXTRACE=1`. NisGraphics
uses plain LV2 SPU thread groups, not SPURS: all six threads run concurrently
on the SDK's lifted-thread path. In the initial boot stall they DMA-poll their
16-byte PPU command descriptors into LS 0x5100, testing descriptor word +8 for
work. The SDK's former default 256-repeat DMA watchdog killed these valid idle
workers; it is now opt-in (`SPU_DMA_REPEAT_LIMIT`, zero/unset disables it).
