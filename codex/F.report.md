# F — black-frame investigation

Two SDK bugs explain the black output. Both are fixed; actual GPU output still needs verification outside the sandbox.

## Root causes and fixes

1. **Missing NV0039 texture uploads.** D2 sends main-memory → local-VRAM copies on libgcm's default subchannel 1. The SDK treated that channel as 3D and had no NV0039 transfer implementation. `port/runs/F-sub1.log:235–254` records the source/destination DMA contexts, offsets, length, format and notify, all previously unhandled. Consequently index textures and their palettes were zero; `F.log:3016` shows an entirely transparent black palette. The fragment shader with 80 instructions samples an index texture and a palette, so this guarantees black output.

   Added NV0039 copies with mapped-address validation, signed row pitches, byte strides and an overlap-safe input snapshot. Bytes are copied unchanged. Subchannel 1 defaults to NV0039; standard NV4097/NV0039 object rebindings and existing environment overrides are respected. This follows the canonical bindings/methods in RPCS3's [gcm enums](https://github.com/RPCS3/rpcs3/blob/master/rpcs3/Emu/RSX/gcm_enums.h), [object setup](https://github.com/RPCS3/rpcs3/blob/master/rpcs3/Emu/RSX/rsx_methods.cpp), and [NV0039 implementation](https://github.com/RPCS3/rpcs3/blob/master/rpcs3/Emu/RSX/NV47/HW/nv0039.cpp). Implementation here was written independently in SDK style. Reviewed PR #160 and Twisted Metal's boot path for prior art.

2. **Transfer commands corrupted 3D registers.** The engine mirror stripped subchannel bits from every command. NV0039 FORMAT (`0x324 = 0x101`) became COLOR_MASK; LINE_COUNT (`0x320 = 1`) became BLEND_EQUATION. NV308A SIZE_OUT (`0x308 = 0x10004`) became ALPHA_FUNC. `F.log:3032` records mask `00000101`, blend equation `0001` and alpha function `10004`. Restricted the register-engine mirror to 3D commands and the existing driver flip methods. `F-check.log:2277` now has all-channel mask `01010101`, ADD blending `8006` and enabled NOTEQUAL alpha test `0205`.

Added Metal command-buffer completion error logging: successful pipeline creation/draw submission alone does not prove successful GPU execution.

## Other paths checked

| Path | Evidence / conclusion for observed D2 draws |
|---|---|
| Texture formats | `F-check.log:787–827`: linear B8 (`A1`, R8 index data) and linear A8R8G8B8 (`A5`, decoded RGBA palettes), identity remap `AAE4`, one mip. No swizzle or compressed-format conversion implicated. |
| Samplers | Nearest min/mag; index unit repeats, palette unit clamps. Normalized coordinates; available mip range clamps to the single uploaded level. |
| Vertex fetch | Compact layout mask `0109`, stride 48: guest attributes 0/3/8 become Metal slots 0/1/2. Four nondegenerate vertices and six indices; sensible positions, color and UVs (`F-check.log:1109–1120`). |
| Constants | Nonzero decoded floats, including 512×256 texture dimensions (`:1121–1125`). Engine collects constants before pipeline-cache lookup; Metal binds vertex constants at buffer 0 and fragment constants at buffer 1. |
| Viewport/depth | Full 1280×720 viewport/scissor; clip transform maps guest z=2/3 to ~0.833. Depth clears to 1 and uses LEQUAL. Culling disabled. |
| Target/flip | Draw target and presented target both handle 1 (`:2277`, `:2755`); observed local color surface at offset 0. No mismatched flipped buffer identified. |
| Black overlays | The short fragment shader draws a texture multiplied by color; an early fullscreen black fade can be intentional. Later frames are the meaningful check. |

## Files changed

- SDK: `libs/video/cellGcmSys.c`, `rsx_draw_engine.c/.h`, `rsx_metal_backend.m`. F-only SDK patch: `patches/F-rendering.diff` (excludes concurrent workers' changes).
- Port: `src/d2_draw_trace.cpp`, `main.cpp`, `CMakeLists.txt`. Opt-in `D2_DRAW_TRACE` forwards the real Metal backend or records through a GPU-free backend when Metal is absent. Captures decoded textures, compact shaders, vertices, indices, constants, states and draw/present targets. Default runs are unaffected.
- Checks: `codex/F.validate.cpp`, `F.validate.py`, `F.metal-check.sh`.

The legacy LD_DRAW_DUMP/VTX_DUMP/LD_TEXRGBA_DUMP switches are in the D3D12 live path, so they cannot capture this Metal register-engine path. The new wrapper captures the actual inputs to that engine. GPU-free captures do **not** render pixels.

## Verification

- Configured and built only `port/build-f` with the documented flags; final build succeeded (`port/runs/F.build-final.log`).
- Actual FIFO integration fixture passes pitched/negative-pitch/byte-stride/overlapping copies, unmapped-address rejection, transfer/3D state isolation and explicit subchannel-1 3D rebinding: `port/runs/F-fifo-test.log:21`. Reproduce with `python3 codex/F.validate.py` after building.
- Existing draw-engine tests: `port/runs/F-engine-test.log:126`, “all checks passed”. Texture-layout tests: `port/runs/F-texture-test.log:1`, “all passed”. SDK diff whitespace and shell syntax checks passed.
- Fresh-HDD1, 40-second sandbox run: copies of 4096, 327680 and 308224 bytes (`F-check.log:176,697,763`). Index image has 59,644 nonzero pixels; palette has 103 colored / 106 nonzero-alpha entries (`:795,798`), compared with all-zero before. Later menu textures/palettes also contain data (`:10126–10150`). Frame 120 has 10 draws (`:2755`), frame 600 has 19 (`:14245`), and presentation reaches 1860 (`:29074`). Loading progress also includes concurrent worker changes; it is not attributed solely to F.

## Outside-sandbox check / remaining work

Run `bash codex/F.metal-check.sh` on the real host. It rebuilds only build-f, runs for 60 seconds with a fresh private HDD1, and retains everything without `rm`. Artifacts go to a unique `port/runs/F-metal.XXXX` directory; the script prints its location and the cache path.

Look for `[F-trace] Metal`, successful guest pipelines, nonzero palette/image statistics and **later numbered `frames/f*.ppm` with nonblack pixels / recognizable artwork**. `pixels.txt` counts pixels for frames and texture dumps; index-texture PPMs are grayscale indices, not colored artwork. Pillow, if installed, also produces PNGs. Early black frames are expected during fades. Review `summary.txt` and grep `run.log` for `command buffer failed` or Metal validation errors. Raw per-draw buffers and HLSL/MSL are in `draws/`; Metal shaders are in `shaders/`.

The sandbox reports no Metal device (`F-check.log:94`), so a visible-frame claim is still pending. If real Metal remains black despite nonzero textures and valid state, these captures will isolate the next GPU-specific issue. Generic arbitrary object binding and NV0039 notify interrupts remain incomplete; D2's observed transfers use the supported standard binding and notify=0. Game dump, port/build and other workers' build directories were untouched. No commits or pushes.
