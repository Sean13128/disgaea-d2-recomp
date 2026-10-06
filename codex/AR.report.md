# AR: native vertex-program upload (1.40 `func_002FE4AC`)

Performance item #2 from `port/runs/performance-review-20261005`. Nothing is committed in either repo.

## What was replaced and why
`func_002FE4AC(r3 = CellGcmContextData, r4 = Cg program, r5 = ucode)` uploads a vertex program into the FIFO:
1. It reserves space. If `cur + words*4 + 0x1C > end`, it calls the flush callback (`[ctx+0xC]`, indirect call) and returns early if the callback fails.
2. It emits `TRANSFORM_PROGRAM_LOAD` (0x1E9C).
3. It emits `instr/8` packets of `0x00800B80` + 32 ucode words, then a remainder packet of `(instr%8)*4` words.
4. It emits the output mask (0x1FF0) and the timeout (0x1EF8, 0x20FFFF or 0x30FFFF).
5. For each uniform of type 0x1006/0x1007 that has a default value, it copies 16 bytes to the stack and calls `func_002FF1A0`.

The lift does steps 3 and 5 one word (or byte) at a time: about 66 accessor calls per 128-byte packet. That is where the 131 samples (~10% of active menu PPU work) went.

`port/src/d2_shader.cpp` defines `func_002FE4AC`, and configure renames the lift to `d2_original_002FE4AC` (`D2_NATIVE_OVERRIDES`, the same pattern as AQ). The native body does every non-copy access, call and register update in the lift's order, through the normal accessors. Only these copies are batched:
- each 128-byte ucode packet: one `vm_copy` plus one header `vm_write32`. The cursor is written once at the end instead of once per packet.
- the remainder packet: one `vm_copy`.
- the 16-byte uniform default copied to the stack: one `vm_copy`.

New SDK primitive `vm_copy(dst, src, n)` in `ps3recomp/runtime/ppu/ppu_loader.cpp`, next to `vm_fill`. Both now share `vm_bulk_commit`, which does the same commit as lifted stores: poll-store reset, SPU lock-line lock and notify for reserved lines, and `ps3_poll_notify` over the range. `vm_copy` returns 0 and touches nothing in these cases:
- any read diagnostic is armed (`PPU_RWATCH`, `PPU_FORCE_READ_ADDR`, `PT`, `YDKJ_RWATCH`, `PPU_RVAL`, `PPU_HOTMAP`, `PPU_SPINBT`, hot-read trace, `VM_SAMPLE_READS`);
- a store watch is armed, or a barrier-sync watch or null sweep is active;
- either range is below 0x10000, out of bounds, or reaches raw SPU MMIO;
- the source overlaps the 0x8000 GCM window (refpoll is at +0x2008), or the destination overlaps the label/control notify window;
- the source and destination overlap.

The caller then performs the lift's exact scalar accesses.

## Neighbours (not replaced)
- `func_002FE8FC` (26 samples in the review): no loop, about 16 accessor calls. A rewrite saves very little, so there is no clear win.
- `func_002FC938`: a `sys_timer_usleep` wait loop on `[r3+8]`. Its samples are waiting, not work. Its share grew after this change, as expected when there is more idle time.
- `func_002FF1A0` (40 samples): a 9-way jump-table emitter of a few words per uniform, with an indirect call on every branch. Rewriting it means 588 lines of exact semantics for a small per-call gain, so I left it.

## Semantic argument
- **Final context:** for the batched packet loop it is computed from the loop bounds and the last packet's data: r0, r5, r6, r7, r8, r9, r11 and CTR = 0, with r4 unchanged. r10 is dead because the caller recomputes it right after the loop, and the mutation test confirms it. For the remainder and stack copies, r0, r8, r10, r11 and CTR = 0 are computed the same way (r9 is recomputed). r24–r31, r1, LR and cr4 are restored exactly as in the lift's epilogue. Volatile registers and the other CR fields match the lift bit for bit. The test checks this against the whole `ppu_context`.
- **Preconditions for the batched packet path** (otherwise the code runs the scalar copy of the lifted loop):
  - the cursor word at `r31+8` is ≥ 0x10000, in bounds, outside the GCM window and below SPU MMIO, and it reads back the value just stored;
  - the destination range (`n*0x84`) and source range (`n*0x80`) both fit in 32 bits without wrapping and do not contain the cursor word;
  - the source and destination do not overlap.

  Under these conditions the lift's per-packet reload of `[r31+8]` always returns the running cursor, so the stores are the same bytes in the same packet order. If `vm_copy` declines partway through, the code writes the lift's cursor value after packet i-1 and finishes packet by packet with the scalar loop.
- **Ordering:**
  - The FIFO put pointer is never written by this function. Only the flush callback writes it, and the callback still runs before any command word, at the same point and with an identical context.
  - Within a packet the body is now stored before its header, and words are stored in memcpy order. All of these lie past put, so the RSX cannot read them before the next put update.
  - The intermediate cursor stores (N per upload in the lift) collapse into one. The cursor lives in the guest context struct. If that struct is inside the GCM notify window, the batched path is not used.
- **Calls:** the flush callback (`ps3_indirect_call` plus the trampoline drain) and `func_002FF1A0` (LR 0x002FE8F4 plus drain) happen in the same order, with the same registers and the same 16 stack bytes. The test logs and compares every call.
- **Not exactly preserved:** the number of SPU lock-line notify events and poll wakeups. The bulk commit notifies each reserved line, and the poll range, once instead of once per word (the same trade as AQ's `vm_fill`). Final memory is identical.

## Test evidence
`d2.AR-shader` (`port/tests/AR.shader-test.cpp`, `run.py` case `AR-shader`, ASan+UBSan, -O1):
- **Method:** it extracts the lifted body as the reference, then compares the full 4 MiB guest memory, the whole `ppu_context`, and a log of every call (registers + stack argument). The flush callback and `func_002FF1A0` are stubs that clobber volatile registers and emit FIFO words.
- **Result:** 1,874 uploads match.
- **Inputs:**
  - 0–512 instructions, every remainder size, attr values around 0x20, 0/1/5 uniforms;
  - FIFO near its end (just under or over the threshold, a successful wrap flush, a failing flush, an r3 return value with high bits set);
  - packets running off the VM, ucode aliasing the FIFO, the context struct inside the FIFO it fills, ucode off the VM;
  - an armed store watch (all-scalar path), a null-page cursor, and r5 with high bits set.
- **Mutation check:** wrong r6, wrong r10 byte, or a missing cursor write on partial fallback each fail the test. The surviving mutations were dead registers, which I then removed from the code.
- **Full ctest in `port/build-ar`:** all tests pass. This includes AQ-fill, which now runs through the refactored `vm_fill`.

## Microbench (Release -O2, no sanitizers, steady upload, no flush or uniforms; 3 runs)
| instructions | lift | native | speedup |
|---:|---:|---:|---:|
| 16 | 0.67–0.92 us | 0.15–0.17 us | 4–6x |
| 64 | 2.5–3.2 us | 0.28–0.40 us | 8–10x |
| 256 | 10.1–10.5 us | 0.70–0.93 us | 11–15x |

## Real Metal (`codex/AM.host-check.sh`, `AM_MANUAL=0`, `SDL_AUDIODRIVER=dummy`)
- **Scene:** the same automated route lands on the hub with the menu open. Both runs show the same frame (checked frame-3600). It is not the character screen.
- **Machine:** the load average was 7–10 because other workers were building.

| run | fps (last 30 s) | PPU main CPU (steady 5 s samples) | `func_002FE4AC` inclusive samples (5 s) | `func_002D11C0` incl. |
|---|---:|---:|---:|---:|
| baseline `port/build` (`runs/AM-host.0owJLn`) | 60.000 | ~13.7% | 102 | 159 |
| AR `port/build-ar` (`runs/AM-host.Xw6DtV`) | 59.967 | ~11.2% | 19 (4 in `vm_copy`) | 42 |
| repeat (lower load, reverse order), AR first (`runs/AM-host.0s8wpz`) | 60.000 | ~11.3% | 12 | 35 |
| repeat, baseline (`runs/AM-host.VpfzQm`) | 59.933 | ~13.6% | 99 | 146 |

- **Result:** PPU main dropped about 2.5 points (−18%), and the upload function's samples fell 5x. Flip rate is at 60 either way; the one-flip difference is within the noise AQ saw (59.90–59.97).
- **Confound:** the baseline is the user's `port/build` from 20:37, and the AR build also contains other workers' uncommitted tree state (AS cheats UI). Neither is on this hot path.

## Changed files (mine)
- `port/src/d2_shader.cpp` (new): the override.
- `port/CMakeLists.txt`:
  - `D2_NATIVE_OVERRIDES 002FE4AC 0033D91C`. The order must match lift file order because the found-list comparison is ordered.
  - `d2_shader.cpp` added to `D2_NATIVE_SOURCES`.
- `port/tests/AR.shader-test.cpp` (new).
- `port/tests/run.py`: the `AR-shader` case and the `--lift` help text. **The file also has AS's hunks** (`AS-ui`, editor-test change).
- `port/tests/CMakeLists.txt`: `d2.AR-shader`. **The file also has AS's `AS-ui` hunks.**
- `ps3recomp/runtime/ppu/ppu_loader.cpp`: `vm_bulk_commit`, `vm_bulk_store_ok`, `vm_copy`, and `vm_fill` refactored onto them with the same behaviour.
- `patches/AR-runtime.diff`: export of that SDK diff against SDK HEAD 77debac.
- `codex/AR.report.md` (this file).

## Left undone / risks
- The 1.00 lift is untouched (out of scope unless trivial; not checked in detail).
- `func_002FF1A0` and the fragment-program path are not done. `func_002D11C0` / `func_002D295C` (render batch) are the next targets.
- Collapsing the per-packet cursor stores and per-word SPU/poll notifications is a semantic relaxation. It is safe because nothing reads the cursor or beyond-put FIFO words concurrently, but it is not a word-for-word side-effect replay.
- Real-Metal numbers come from two pairs of runs (the second pair at load average ~3 and in reverse order). Both show the same ~2.3–2.5 point PPU main reduction.
