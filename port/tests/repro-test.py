#!/usr/bin/env python3
"""Asset-free failure-path checks for the maintained bootstrap/generation tools."""
import argparse
import hashlib
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile

parser = argparse.ArgumentParser()
parser.add_argument('--sdk', type=Path, required=True)
parser.add_argument('--work', type=Path, required=True)
args = parser.parse_args()
root = Path(__file__).resolve().parents[2]
with tempfile.TemporaryDirectory(prefix='repro-', dir=args.work) as temp:
    project = Path(temp)/'project'
    (project/'tools').mkdir(parents=True)
    (project/'patches').mkdir()
    for name in ('bootstrap_sdk.sh', 'generate_lifts.sh', 'generate_lifts.py'):
        shutil.copy2(root/'tools'/name, project/'tools'/name)
    lock = json.loads((root/'patches/SDK.lock').read_text())
    manifest = json.loads((root/'patches/LIFTS.json').read_text())
    # A changed patch must fail before any git/network invocation.
    (project/'patches'/lock['patch']).write_bytes(b'corrupt patch')
    (project/'patches/SDK.lock').write_text(json.dumps(lock))
    env = dict(os.environ, PYTHON=sys.executable)
    def rejected(command, message):
        result = subprocess.run(list(map(str, command)), env=env, capture_output=True, text=True)
        assert result.returncode != 0, result.stdout
        assert message in result.stderr, result.stderr
        print(f'PASS: rejected {message}')
    bootstrap = project/'tools/bootstrap_sdk.sh'
    rejected([bootstrap, Path(temp)/'new-sdk'], 'SDK patch SHA256 mismatch')
    # A matching checksum still must never overwrite an existing SDK.
    lock['patch_sha256'] = hashlib.sha256(b'corrupt patch').hexdigest()
    (project/'patches/SDK.lock').write_text(json.dumps(lock))
    rejected([bootstrap, args.sdk], 'Refusing existing SDK directory')
    # Use the actual SDK's indexed tree, so ELF validation can be tested even
    # against a developer SDK. No real game file is read by this fixture.
    sdk = args.sdk.resolve()
    lock['tree'] = subprocess.check_output(['git', '-C', str(sdk), 'write-tree'], text=True).strip()
    (project/'patches/SDK.lock').write_text(json.dumps(lock))
    (project/'patches/LIFTS.json').write_text(json.dumps(manifest))
    elf = Path(temp)/'synthetic.elf'
    elf.write_bytes(b'not a decrypted game executable')
    command = [project/'tools/generate_lifts.sh', '--sdk', sdk, '--version', '100', '--elf', elf, '--port-dir', Path(temp)/'lifts']
    dirty = subprocess.check_output(['git', '-C', str(sdk), 'diff', '--name-only'], text=True).strip()
    rejected(command, 'SDK differs from SDK.lock' if dirty else 'ELF 100 SHA256 mismatch')
    assert not (Path(temp)/'lifts').exists()
