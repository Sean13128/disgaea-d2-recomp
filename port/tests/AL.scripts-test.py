#!/usr/bin/env python3
"""Asset-free script status/version/copy regressions; never build shared directories."""
import os
from pathlib import Path
import subprocess
import tempfile

root = Path(__file__).resolve().parents[2]
with tempfile.TemporaryDirectory(prefix='AL-scripts.', dir='/Volumes/Data/ai-tmp/codex') as tmp:
    work = Path(tmp)
    bin = work/'bin'; bin.mkdir()
    def executable(path, text):
        path.write_text('#!/bin/sh\n'+text); path.chmod(0o755)
    executable(bin/'cmake', 'exit 0\n')
    build = work/'build'; build.mkdir()
    executable(build/'DisgaeaD2Recomp', 'echo "ELF=$1"\n[ "$FAKE_STATUS" = timeout ] && exec sleep 5\nexit "${FAKE_STATUS:-0}"\n')
    saves = work/'source/home/00000001/savedata'; saves.mkdir(parents=True)
    (saves/'SLOT').mkdir()
    (saves/'SLOT/SAVEDATA.DAT').write_text('test save')
    env = dict(os.environ, PATH=f'{bin}:'+os.environ['PATH'], D2_BUILD_DIR=str(build),
               D2_RUNS_DIR=str(work/'runs'), D2_CAPTURE_HDD0=str(work/'source'))
    def run(script, expected, **override):
        p = subprocess.run(['sh', str(root/'port'/script)], env=dict(env, **override), capture_output=True, text=True)
        assert p.returncode == expected, (script, p.returncode, p.stdout, p.stderr)
        return p
    for version, elf in [('100','work/EBOOT.elf'),('140','work/v140/EBOOT.elf')]:
        (build/'CMakeCache.txt').write_text(f'D2_GAME_VERSION:STRING={version}\n')
        run('capture.sh', 0)
        latest = sorted((work/'runs').glob('capture.*/run.log'), key=lambda p:p.stat().st_mtime)[-1]
        assert latest.read_text().strip() == f'ELF={elf}'
        assert (latest.parent/'hdd0/home/00000001/savedata/SLOT/SAVEDATA.DAT').read_text() == 'test save'
        print(f'[AL-scripts] capture {version}: PASS')
    run('capture.sh', 37, FAKE_STATUS='37')
    run('run.sh', 37, FAKE_STATUS='37')
    run('capture.sh', 142, FAKE_STATUS='timeout', D2_CAPTURE_SECONDS='1')
    run('capture.sh', 1, D2_CAPTURE_HDD0=str(work/'missing'))
    executable(bin/'cp', 'exit 51\n')
    run('capture.sh', 1)
    (bin/'cp').unlink()
    blocked = work/'blocked'; blocked.write_text('not a directory')
    run('capture.sh', 1, D2_RUNS_DIR=str(blocked))
    executable(bin/'mktemp', 'exit 1\n')
    run('capture.sh', 1)
    print('[AL-scripts] runner errors, explicit timeout, missing saves, failed copy/output/temp: PASS')
