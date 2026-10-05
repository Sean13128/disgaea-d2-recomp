#!/bin/bash
# CPU replay plus optional offscreen-Metal replay, using only build-aa.
set -euo pipefail
cd "$(dirname "$0")/.."
capture=${1:?usage: bash codex/AA.replay-check.sh hallway.fifo [--metal-null]}
python3 - "$capture" "${2:-}" <<'PYBUILD'
from pathlib import Path
import shlex, subprocess, sys
out = Path('port/build-aa')
sources = ['ps3recomp/libs/video/'+x+'.c' for x in
           ['rsx_commands','rsx_dispatch','rsx_texture_layout','rsx_vp_decompiler','rsx_fp_decompiler']]
sources += ['ps3recomp/runtime/platform/win32_compat.c','ps3recomp/runtime/platform/guest_poll.c']
base = ['clang','-std=gnu17','-O3','-Wno-macro-redefined','-Wno-unused-function',
        '-DAA_LIVE_DRAIN','-ffunction-sections','-fdata-sections','-Wl,-dead_strip','-I','ps3recomp/include','-I','ps3recomp/libs/video']
for baseline in [True, False]:
    name = 'AA-replay-baseline' if baseline else 'AA-replay'
    extra = ['-DAA_BASELINE_DRAIN', '-DAA_GCM_SOURCE="'+str((out/'baseline/cellGcmSys.c').resolve())+'"', '-DAA_ENGINE_SOURCE="'+str((out/'baseline/rsx_draw_engine.c').resolve())+'"'] if baseline else []
    compact = str(out/'baseline/rsx_vertex_compact.c') if baseline else 'ps3recomp/libs/video/rsx_vertex_compact.c'
    if baseline and not Path(compact).exists():
        print('Pre-AA snapshot absent; skipping baseline comparison', flush=True)
        continue
    with open(out/(name+'.build.log'), 'w') as log:
        subprocess.run(base+extra+['codex/AA.replay.c','codex/AA.replay-drain.c',compact]+sources+['-o',str(out/name)],stdout=log,stderr=log,check=True)
    subprocess.run([str(out/name),sys.argv[1]],check=True)
if sys.argv[2] == '--metal-null':
    lines = subprocess.run(['ninja','-C',str(out),'-t','commands','DisgaeaD2Recomp'],capture_output=True,text=True,check=True).stdout.splitlines()
    link = shlex.split([line for line in lines if ' -o DisgaeaD2Recomp ' in line][-1])
    libs = link[link.index('ps3recomp_sdk/libps3recomp_runtime.a'):]
    libs = [str(out/x) if x.startswith('ps3recomp_sdk/') else x for x in libs if x not in ['&&',':']]
    with open(out/'AA-replay-metal.build.log','w') as log:
        subprocess.run(base+['-DAA_WITH_METAL','-ffunction-sections','-fdata-sections','-c','codex/AA.replay.c','-o',str(out/'AA-replay-metal.o')],stdout=log,stderr=log,check=True)
        subprocess.run(base+['-DAA_WITH_METAL','-c','codex/AA.replay-drain.c','-o',str(out/'AA-replay-drain-metal.o')],stdout=log,stderr=log,check=True)
        subprocess.run(['clang++',str(out/'AA-replay-metal.o'),str(out/'AA-replay-drain-metal.o'),'-Wl,-dead_strip','-o',str(out/'AA-replay-metal')]+libs,stdout=log,stderr=log,check=True)
    result = subprocess.run([str(out/'AA-replay-metal'),sys.argv[1],'--metal-null','20'])
    sys.exit(result.returncode)
PYBUILD
