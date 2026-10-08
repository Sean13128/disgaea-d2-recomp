#!/usr/bin/env python3
"""Compile and execute an asset-free fixture in its own build directory."""
import argparse
import ast
import json
import os
from pathlib import Path
import subprocess
import sys

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[1]
parser = argparse.ArgumentParser(description=__doc__)
parser.add_argument('test')
parser.add_argument('--sdk', type=Path, required=True)
parser.add_argument('--work', type=Path, required=True)
parser.add_argument('--runtime', type=Path, help='selected CMake SDK runtime library for loader tests')
parser.add_argument('--lift', type=Path, help='lifted PPU source directory (AQ-fill, AR-shader)')
args = parser.parse_args()
sdk, work = args.sdk.resolve(), args.work.resolve()
work.mkdir(parents=True, exist_ok=True)
name = args.test
exe = work / 'fixture'
env = dict(os.environ, PS3RECOMP_DIR=str(sdk), D2_TEST_TMPDIR=str(work))

def run(cmd):
    with (work / 'build.log').open('a') as log:
        result = subprocess.run(list(map(str, cmd)), env=env, cwd=work, stdout=log, stderr=log)
    if result.returncode:
        print((work / 'build.log').read_text()[-10000:], file=sys.stderr)
        sys.exit(result.returncode)

inc = [sdk, sdk/'include', sdk/'libs/video', sdk/'libs/system', sdk/'runtime/platform', sdk/'runtime/ppu', sdk/'runtime/spu', work]
brew = Path(os.environ.get('HOMEBREW_PREFIX', '/opt/homebrew'))
if brew.exists():
    inc.append(brew/'include')
flags = ['-O1', '-g', '-ffunction-sections', '-fdata-sections', '-pthread']
flags += [f'-I{p}' for p in inc]
flags += ['-Wl,-dead_strip'] if sys.platform == 'darwin' else ['-Wl,--gc-sections', '-lm']
gpu = name in ('metal', 'metal-overlay', 'hotkey', 'AL-metal', 'AN-metal')
if not gpu:
    flags += ['-fsanitize=address,undefined', '-fno-omit-frame-pointer']
video = [sdk/'libs/video'/f'{n}.c' for n in ('rsx_dispatch', 'rsx_vertex_compact', 'rsx_texture_layout', 'rsx_vp_decompiler', 'rsx_fp_decompiler')]
platform = [sdk/'runtime/platform'/f'{n}.c' for n in ('win32_compat', 'guest_poll')]
def emit_ppu_header():
    # Use the selected SDK's asset-free header preamble; no game lift/build needed.
    namespace = {}
    module = ast.parse((sdk/'tools/ppu_lifter.py').read_text())
    for node in module.body:
        if isinstance(node, ast.Assign) and any(isinstance(t, ast.Name) and t.id in ('FENCE_PREAMBLE', 'HEADER_PREAMBLE') for t in node.targets):
            exec(compile(ast.Module(body=[node], type_ignores=[]), '<sdk-header>', 'exec'), namespace)
    (work/'ppu_recomp.h').write_text(namespace['HEADER_PREAMBLE'])
source = lambda n: HERE/n
cc = os.environ.get('CC', 'clang')
cxx = os.environ.get('CXX', 'clang++')
cmd = [cc, '-std=gnu17', *flags]
run_args = []
if name == 'repro-guards':
    sys.exit(subprocess.run([sys.executable, source('repro-test.py'), '--sdk', sdk, '--work', work], env=env).returncode)
elif name == 'AN-summary':
    sys.exit(subprocess.run([sys.executable, source('AN.summary-test.py')], cwd=work, env=env).returncode)
elif name == 'DI-ui':
    (work/'d2_launcher_paths.h').write_text('#define D2_PROJECT_ROOT "/nonexistent/diagnostics-fixture"\n')
    cmd += ['-fobjc-arc', source('DI.ui-test.m'), '-I', sdk/'libs/audio', '-framework', 'AppKit', '-Wl,-U,_d2_cheats_menu_install']
elif name == 'DI-integration':
    cmd += ['-fobjc-arc', source('DI.integration-test.m'), '-framework', 'AppKit']
elif name == 'DI-collector':
    cmd += ['-fobjc-arc', source('DI.collector-test.m'), '-framework', 'AppKit', '-Wl,-U,_d2_flags_diagnostics_snapshot']
elif name == 'AN-flags':
    cmd += ['-fobjc-arc', source('AN.flags-test.m'), '-framework', 'AppKit']
    run_args = [work]
elif name.startswith('AN-location-'):
    emit_ppu_header()
    version = int(name.rsplit('-', 1)[1])
    cmd = [cxx, '-std=c++20', *flags, f'-DD2_GAME_VERSION={version}', source('AN.location-test.cpp')]
elif name == 'AL-scripts':
    sys.exit(subprocess.run([sys.executable, source('AL.scripts-test.py')], cwd=work, env=env).returncode)
elif name == 'edat-cache':
    sys.exit(subprocess.run([sys.executable, sdk/'libs/filesystem/tests/test_edat_cache.py'], cwd=work, env=env).returncode)
elif name in ('edat', 'save-import'):
    script = source('AD.edat-test.py' if name == 'edat' else 'AC.save-import-test.py')
    sys.exit(subprocess.run([sys.executable, script], cwd=work, env=env).returncode)
elif name.endswith('-sync'):
    cmd += [source(name.replace('-sync', '.sync-test.c')), source('AA.sync-stubs.c'), *platform]
elif name == 'AG2-fifo':
    cmd += [source('AG2.fifo-test.c'), *platform, sdk/'libs/video/cellResc.c']
elif name in ('draw', 'AG2-engine'):
    fixture = sdk/'libs/video/tests/test_rsx_draw_engine.c' if name == 'draw' else source('AG2.engine-test.c')
    cmd += [fixture, sdk/'libs/video/rsx_draw_engine.c', *video]
elif name in ('hash', 'vertex', 'cache'):
    fixture = {'hash':'X.hash-test.c', 'vertex':'AA.vertex-test.c', 'cache':'AA.cache-test.c'}[name]
    cmd += [source(fixture), *video]
elif name == 'AP-atrac-stream':
    cmd += [sdk/'libs/codec/tests/test_atrac_stream_switch.c']
elif name == 'AP-audio-gain':
    cmd += [sdk/'libs/audio/tests/test_audio_host_gain.c', f'-L{brew}/lib', '-lSDL2']
elif name == 'AP-audio-init':
    emit_ppu_header()
    cmd = [cxx, '-std=c++20', *flags, '-DD2_GAME_VERSION=140', source('AP.audio-init-test.cpp')]
elif name == 'AZ-gcm-put':
    cmd += [source('AZ.gcm-put-test.c'), *platform]
elif name == 'AZ-audio-wait':
    cmd += [sdk/'libs/audio/tests/test_audio_wait.c', f'-L{brew}/lib', '-lSDL2']
elif name == 'audio-clock':
    cmd += [source('Z.audio-clock.c'), f'-L{brew}/lib', '-lSDL2']
elif name == 'filesystem':
    cmd += [source('AD.fs-test.c')]
    run_args = [work]
elif name == 'AL-lifecycle':
    cmd += [source('AL.lifecycle-test.c'), sdk/'runtime/platform/guest_poll.c']
elif name == 'AL-save-stop':
    cmd += [source('AL.save-stop-test.c')]
    run_args = [work]
elif name == 'savedata-transaction':
    cmd += [sdk/'libs/system/tests/test_savedata_transaction.c']
elif name.startswith('savedata-'):
    cmd += [sdk/'libs/system/tests'/f'test_{name.replace("-", "_")}.c']
elif name in ('overlay', 'system-overlay'):
    fixture = source('AF.overlay-test.c') if name == 'overlay' else sdk/'libs/system/tests/test_sys_overlay.c'
    cmd += [fixture, sdk/'libs/system/sys_overlay.c']
    if name == 'system-overlay':
        cmd += [sdk/'libs/system/cellMsgDialog.c', sdk/'libs/system/cellSysutil.c']
elif name.startswith('editor-'):
    version = int(name.split('-')[1])
    emit_ppu_header()
    data = (ROOT/'port/d2_cheats.v1.json').read_text()
    profile = json.loads(data)['versions'][version == 140]
    header = (ROOT/'port/src/d2_cheats_data.h.in').read_text().replace('@D2_CHEATS_JSON@', data)
    for hook in ('exp', 'sp', 'shop'):
        header = header.replace(f'@D2_CHEAT_{hook}_ADDR@', profile['hooks'][hook])
    (work/'d2_cheats_data.h').write_text(header)
    cmd = [cxx, '-std=c++20', *flags, f'-DD2_CHEATS_VERSION={version}', source('AF.editor-test.cpp')]
    run_args = [work]
elif name == 'loader-validation':
    if args.runtime is None or not args.runtime.is_file():
        sys.exit('Build the selected game target before running its loader regression')
    emit_ppu_header()
    cmd = [cxx, '-std=c++20', *flags, sdk/'runtime/ppu/tests/test_loader_validation.cpp',
           sdk/'runtime/ppu/ppu_loader.cpp', args.runtime]
    cmd += ['-framework', 'CoreFoundation', '-framework', 'Cocoa', '-framework', 'Metal',
            '-framework', 'QuartzCore', '-framework', 'CoreText', f'-L{brew}/lib', '-lSDL2']
    run_args = [work/'synthetic.elf']
elif name == 'AQ-fill':
    if args.runtime is None or not args.runtime.is_file() or args.lift is None:
        sys.exit('AQ-fill needs --runtime and --lift')
    # The lift's helper preamble plus the one body, renamed as CMake renames it.
    sig = 'void func_0033D91C(ppu_context* ctx) {'
    text = next(t for t in (f.read_text() for f in sorted(args.lift.glob('ppu_recomp_*.cpp'))) if sig in t)
    start = text.index(sig)
    body = text[start:text.index('\n}\n', start) + 3].replace('func_0033D91C', 'd2_original_0033D91C', 1)
    (work/'fill_lift.cpp').write_text(text[:text.index('\nvoid func_')] + '\n' + body)
    cmd = [cxx, '-std=c++20', *flags, '-I', args.lift, source('AQ.fill-test.cpp'), work/'fill_lift.cpp',
           ROOT/'port/src/d2_fill.cpp', sdk/'runtime/ppu/ppu_loader.cpp', args.runtime]
    cmd += ['-framework', 'CoreFoundation', '-framework', 'Cocoa', '-framework', 'Metal',
            '-framework', 'QuartzCore', '-framework', 'CoreText', f'-L{brew}/lib', '-lSDL2']
elif name == 'AR-shader':
    if args.runtime is None or not args.runtime.is_file() or args.lift is None:
        sys.exit('AR-shader needs --runtime and --lift')
    sig = 'void func_002FE4AC(ppu_context* ctx) {'
    text = next(t for t in (f.read_text() for f in sorted(args.lift.glob('ppu_recomp_*.cpp'))) if sig in t)
    start = text.index(sig)
    body = text[start:text.index('\n}\n', start) + 3].replace('func_002FE4AC', 'd2_original_002FE4AC', 1)
    (work/'shader_lift.cpp').write_text(text[:text.index('\nvoid func_')] + '\n' + body)
    cmd = [cxx, '-std=c++20', *flags, '-I', args.lift, source('AR.shader-test.cpp'), work/'shader_lift.cpp',
           ROOT/'port/src/d2_shader.cpp', sdk/'runtime/ppu/ppu_loader.cpp', args.runtime]
    cmd += ['-framework', 'CoreFoundation', '-framework', 'Cocoa', '-framework', 'Metal',
            '-framework', 'QuartzCore', '-framework', 'CoreText', f'-L{brew}/lib', '-lSDL2']
elif name == 'guest-poll':
    cmd += [sdk/'runtime/platform/tests/test_guest_poll.c', sdk/'runtime/platform/guest_poll.c']
elif name == 'spu-cache':
    sys.exit(subprocess.run([sys.executable, sdk/'runtime/spu/tests/test_spu_register_cache.py', '--work', work], env=env).returncode)
elif name == 'spu-lanes':
    cmd += [sdk/'runtime/spu/tests/test_spu_vector_lanes.c']
elif name in ('spu-vectors', 'spu-shuffle'):
    fixture = 'test_spu_vectors.c' if name == 'spu-vectors' else 'test_spu_shufb.c'
    cmd += [sdk/'runtime/spu/tests'/fixture]
elif name in ('metal', 'AL-metal', 'AN-metal'):
    fixture = source({'metal': 'AG.metal-test.m', 'AL-metal': 'AL.metal-test.m', 'AN-metal': 'AN.metal-test.m'}[name])
    cmd += ['-fobjc-arc', fixture, sdk/'libs/video/rsx_texture_layout.c']
    cmd += ['-framework', 'Metal', '-framework', 'Cocoa', '-framework', 'QuartzCore', '-framework', 'CoreText']
    if name == 'AN-metal':
        run_args = [work]
elif name == 'metal-overlay':
    cmd += ['-fobjc-arc', sdk/'libs/video/tests/test_metal_overlay.m', sdk/'libs/video/rsx_metal_overlay.m', sdk/'libs/system/sys_overlay.c']
    cmd += ['-framework', 'Metal', '-framework', 'AppKit', '-framework', 'QuartzCore', '-framework', 'CoreText']
    (work/'port/runs').mkdir(parents=True, exist_ok=True)
    run_args = ['--metal']
elif name == 'AS-ui':
    cmd += ['-fobjc-arc', '-I', ROOT/'port/src', source('AS.ui-test.m'), '-framework', 'AppKit', '-Wl,-U,_d2_item_editor_show']
elif name == 'AT-innocent-menu':
    cmd += ['-fobjc-arc', source('AT.innocent-menu-test.m'), '-framework', 'AppKit']
elif name == 'hotkey':
    cmd += ['-fobjc-arc', source('AF.hotkey-test.m'), sdk/'libs/input/cellPad.c', sdk/'libs/input/pad_macos.m']
    cmd += ['-framework', 'AppKit', '-framework', 'Foundation', f'-L{brew}/lib', '-lSDL2']
else:
    parser.error(f'Unknown test: {name}')
run([*cmd, '-o', exe])
result = subprocess.run([str(exe), *map(str, run_args)], env=env, cwd=work)
if result.returncode == 77:
    print(f'SKIP: {name} requires an available Metal device')
elif result.returncode == 0:
    print(f'PASS: {name}')
sys.exit(result.returncode if result.returncode >= 0 else 128 - result.returncode)
