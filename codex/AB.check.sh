#!/bin/bash
# All binaries are isolated in build-ab; legacy sync fixtures plus copy ordering.
set -euo pipefail
cd "$(dirname "$0")/.."
mkdir -p port/build-ab
python3 - <<'PY'
from pathlib import Path
import subprocess
out = Path('port/build-ab')
base = ['clang', '-std=gnu17', '-O2', '-ffunction-sections', '-fdata-sections',
        '-I', 'ps3recomp/include', '-I', 'ps3recomp/libs/video',
        '-I', 'ps3recomp/runtime/platform', '-Wl,-dead_strip']
platform = ['ps3recomp/runtime/platform/win32_compat.c', 'ps3recomp/runtime/platform/guest_poll.c']
video = ['ps3recomp/libs/video/' + n + '.c' for n in
         ['rsx_dispatch', 'rsx_vertex_compact', 'rsx_texture_layout', 'rsx_vp_decompiler', 'rsx_fp_decompiler']]
jobs = [(name+'-sync', ['codex/'+name+'.sync-test.c', 'codex/AA.sync-stubs.c']+platform) for name in ['Q','T','Y','AA','AB']]
jobs += [('draw', ['ps3recomp/libs/video/tests/test_rsx_draw_engine.c', 'ps3recomp/libs/video/rsx_draw_engine.c']+video),
         ('hash', ['codex/X.hash-test.c']+video),
         ('vertex', ['codex/AA.vertex-test.c']+video),
         ('cache', ['codex/AA.cache-test.c']+video)]
for name, sources in jobs:
    with open('codex/AB.'+name+'-build.log', 'w') as log:
        subprocess.run(base+sources+['-o', str(out/('AB-'+name))], stdout=log, stderr=log, check=True)
    with open('codex/AB.'+name+'-test.log', 'w') as log:
        subprocess.run([str(out/('AB-'+name))], stdout=log, stderr=log, check=True)
    print(name+': PASS', flush=True)
name = 'snapshot-sanitized'
with open('codex/AB.'+name+'-build.log', 'w') as log:
    subprocess.run(base+['-fsanitize=address,undefined', '-g', 'codex/AB.sync-test.c', 'codex/AA.sync-stubs.c']+platform+['-o', str(out/('AB-'+name))], stdout=log, stderr=log, check=True)
with open('codex/AB.'+name+'-test.log', 'w') as log:
    subprocess.run([str(out/('AB-'+name))], stdout=log, stderr=log, check=True)
print(name+': PASS', flush=True)
PY
