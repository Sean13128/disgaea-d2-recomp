# DI — native Diagnostics window handoff

## Outcome and scope

Implemented Game → Diagnostics… as a native checked toggle opening a separate reusable AppKit window. Closing, toggling off, or game-window teardown invalidates its poll timer; a pending cache request may finish, but its generation cannot update a closed/reopened window. Requests are throttled to at most once per second, including across reopen, and coalesced to one outstanding request.

The window reuses `d2_flags.m`'s existing serial CPU history and 4096-event frame ring. It does not start a second Mach sampler, read guest RAM, capture screenshots, write flags, or modify SDK code. AppKit mutations stay on main; snapshot construction is dispatched asynchronously to the existing flags queue. The frame hook has no new work or allocations. The existing F2 sampler remains always-on as before; zero hidden-window requests does not mean that pre-existing sampler stops.

`OPERATIONS.md` was already locally modified at entry and was not edited here. The Idle checkbox remains unchecked. No full application build, game launch, packaging, commit, push, personal-save access, export work, or flags/resolution investigation was performed. Existing SDK `libs/audio/cellAudio.c`, `libs/video/rsx_metal_overlay.m`, and untracked `gamedata/` remain untouched.

## Telemetry and attribution

- Guest flips and display presentations have independent short/long FPS and actual window lengths. Missing stream observations are unavailable, not fabricated zero FPS. Frame latest-completed intervals, ongoing age, and maximum intervals are in milliseconds. Maxima include the active age, which may exceed the nominal ten-second window.
- The shared frame helper preserves F2's existing fields/semantics when called without diagnostics metadata. Diagnostics retains active ages even if that stream's last event has been evicted. Latest intervals then remain unavailable; incomplete bounded-ring windows explicitly warn that rates/maxima can be lower bounds.
- CPU derives from existing cached host user+system time deltas over the displayed actual interval. Mach thread IDs remain stable through name changes/reordering; UI selection follows IDs. Fresh identities stay visible with warmup rather than disappearing; missing/uninitialized/failed/stale cache states are unavailable. Regressed/nonfinite counters are unknown. Samples older than three seconds are unavailable.
- Candidate role attribution uses exact known names, never arbitrary substring matching. PPU main, the two known D2 SPU group names, and RSX render/submit/copy candidates receive distinct subtotals with measured/observed coverage. All other successful cached thread observations remain visible as Other / unknown. Missing CPU contributions are not zero-filled.
- In-window limits explicitly identify a single loaded guest, unavailable active guest PID/state and exact PS3 thread mapping, unknown other PPU workers, unavailable host-audio attribution, stale/reused names, and host CPU rather than guest instructions/GPU time or instantaneous running/waiting state.

### Actual source trace

- `ps3recomp/runtime/ppu/ppu_loader.cpp:3940`: guest main names itself `PPU main`; `ppu_run` services one loaded guest executable with AppKit on main.
- `ps3recomp/runtime/syscalls/sys_ppu_thread.c:128-130`: guest child workers register lifecycle state and name themselves from the guest-supplied PPU name. `sys_ppu_thread_rename` updates the guest table but does not rename its Darwin host thread; cached names can be stale.
- `ps3recomp/runtime/syscalls/lv2_register.c:689-691`: lifted SPUs register as lifecycle workers and use the group name. Existing D2 group-create logs (`port/runs/U-warp4.log:157,212`) show `NisGraphicsSpu_Group` and `_synth2 Group`.
- `ps3recomp/runtime/platform/guest_poll.c:140-153,386-398`: lifecycle registration stores pthread/join state, not an exported typed guest-ID registry; `ps3_poll_thread_start` calls Darwin `pthread_setname_np`. Registration also includes RSX submit, so it cannot alone establish guest identity.
- **Actual port**, `port/main.cpp:237-239,436`: the frame-clock thread names itself `RSX render`. The SDK template differs; attribution includes the port's actual name. SDK `cellGcmSys.c:1750-1751` and `cellGcm_fifo_snapshot.h:140` name RSX submit/copy.
- `ps3recomp/libs/audio/cellAudio.c:886-946`: POSIX mixer starts with pthread_create and sets QoS but no host name/identity snapshot. Its CPU cannot safely be separated from other unnamed workers without a runtime API change. No SDK edit was made.
- `ps3recomp/libs/video/rsx_metal_backend.m:3690-3691`: the existing hook counts accepted guest submissions and submitted drawable presents, not physical scan-out/GPU completion. This distinction is visible in the window.

## Incremental TDD evidence

Each production slice followed an observed runtime assertion failure, then the minimal implementation and passing rerun. `DI-collector` failed for the missing getter; cached CPU available/window/new-thread behavior; failed/stale CPU states; directional frame metadata; and an uninitialized cache incorrectly reported as warmup. `DI-ui` failed for the absent Game menu item; absent separate window; missing visible snapshot requests; missing native labelled telemetry; absent per-thread table; game teardown leaving the window open; missing submitted-presentation/scan-out limits; and the initially unclassified actual `RSX render` name. These were exit 134 assertion failures during tool execution, not assumed RED results.

The initial weak missing-getter fixture produced a Darwin link error before RED. Adding its explicit `-Wl,-U,_d2_flags_diagnostics_snapshot` fixed the harness and exposed the intended runtime assertion. The real integration fixture initially expected exact 60/30 FPS despite AppKit construction advancing its rolling window; its assertion was corrected to parse real formatted rates and check distinct, nonzero bounded rates. No production output was substituted for either issue.

## Verified results

Configured standalone asset-free tests, not the game build:

```sh
cmake -S port/tests -B ~/.hermes/cache/scratch/d2-idle-debug/ctest \
  -DPS3RECOMP_DIR='/Volumes/Data/Applications/QuiverLauncher/Apps/Disgaea D2-RE/ps3recomp'
ctest --test-dir ~/.hermes/cache/scratch/d2-idle-debug/ctest \
  --output-on-failure -j 1 -R 'd2\.(DI|AN)-|d2\.(AS-ui|AT-innocent-menu|hotkey)$'
```

Final run: **11/11 passed, zero failures/skips, 16.91 seconds**. Includes all five existing AN flags tests (including real synthetic Metal), hotkey, AS UI, Innocent menu, and the three new DI fixtures. `git diff --check` passed. Fixtures use ASan/UBSan at O1 except pre-existing GPU fixtures.

Actual final collector output:

```text
blocked-queue enqueue 0.011 ms (<5)
requests=256 callbacks=256; 128 threads/4096 events;
enqueue-to-callback mean=0.234 ms p95=0.312 ms max=0.531 ms;
Mach enumerations=0 new timers=0
```

This is a bounded synthetic cache/getter measurement, not a live gameplay, render-lock contention, power, or FPS impact measurement.

Actual real UI+getter integration output:

```text
128 rows; requests=3 callbacks=3; ≥1s spacing;
1000 visible burst polls throttled;
1000 hidden polls + 1.1s closed run loop: hidden requests=0;
Mach enumerations=0 new samplers=0
```

It also verifies no requests during 1.1 seconds of application hiding. The separate real menu/UI fixture verifies outstanding-request coalescing, safe close/reopen/toggle, old-generation completion rejection, zero hidden requests across two 1.1-second closed intervals, row CPU/status rendering and identity-preserving updates, label fitting bounds, and game teardown.

Full final output is retained at `~/.hermes/cache/scratch/d2-idle-debug/ctest/Testing/Temporary/LastTest.log`.

## Files

New: `port/src/d2_diagnostics.h`, `port/src/d2_diagnostics.m`, `port/tests/DI.collector-test.m`, `port/tests/DI.ui-test.m`, `port/tests/DI.integration-test.m`, and this report.

Modified: `port/src/d2_flags.h`, `port/src/d2_flags.m`, `port/src/d2_settings.m`, `port/src/d2_bundle.cmake`, `port/tests/CMakeLists.txt`, `port/tests/run.py`.

The default-profile maintenance skill was updated with the reusable cache/fixture workflow, Darwin weak-symbol harness pitfall, and the need to trace actual port naming rather than only SDK templates.

## Remaining acceptance boundary

Parent verification completed the full target rebuild and clean serial CTest: **62/62 pass**. Independent review returned `passed:true` with no blocking security, logic or concurrency findings. Owner explicitly approved publishing this version and tracking exact guest/audio attribution separately. `DisgaeaD2Dist` was published; signature, Diagnostics/Skills markers, diagnostic exports and code-section identity were verified against the tested build. Published `__TEXT,__text` SHA256: `2953aca1dd7a3a3e0ba758b4d6d5975f525f04653bf29a11cf4eb17fc7461b79`. Redundant native save-removal implementation/stub is absent. No push.

Fixtures do not prove live gameplay overhead or human visual/accessibility navigation. Exact guest PID/state/thread identities and host-audio worker CPU attribution are unavailable from the inspected APIs and are explicitly labelled in the UI; obtaining them would require the separately tracked runtime telemetry export. Successful cached Mach observations only are displayed; per-thread Mach observation failures are not separately exported by the existing sampler. No claim of negligible live overhead or complete guest attribution is made.

Nonblocking review suggestions: add nonfinite-counter/minimized-window/F2 schema-parity assertions; optionally suspend/resume the existing UI timer on application hiding or minimization. Currently the timer stays scheduled in those states but skips snapshot requests; closing the window invalidates it. Existing F2 telemetry sampling is unchanged.
