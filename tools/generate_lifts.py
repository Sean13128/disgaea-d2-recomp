#!/usr/bin/env python3
"""Recreate ignored PPU metadata/lifts and embedded SPU lifts from owned ELFs."""
import argparse
import hashlib
import json
import os
from pathlib import Path
import subprocess
import sys

ROOT = Path(__file__).resolve().parents[1]
parser = argparse.ArgumentParser(description=__doc__)
parser.add_argument('--sdk', type=Path, default=ROOT / 'ps3recomp')
parser.add_argument('--version', choices=['100', '140', 'all'], default='all')
parser.add_argument('--elf', type=Path, help='ELF input override (requires one version)')
parser.add_argument('--port-dir', type=Path, default=ROOT / 'port', help='output tree, also supports external storage')
args = parser.parse_args()
if args.elf and args.version == 'all':
    parser.error('--elf requires --version 100 or 140')
manifest = json.loads((ROOT / 'patches/LIFTS.json').read_text())
lock = json.loads((ROOT / 'patches' / manifest['sdk_lock']).read_text())
sdk = args.sdk.resolve()
# Require exactly the audited tracked tree, including its patched worktree.
# A bootstrap has base HEAD plus staged patch; the local audited revision also works.
git = lambda *a: subprocess.check_output(['git', '-C', str(sdk), *a], text=True).strip()
if git('write-tree') != lock['tree'] or git('diff', '--name-only'):
    sys.exit('SDK differs from SDK.lock; use tools/bootstrap_sdk.sh with a new directory')
versions = list(manifest['versions']) if args.version == 'all' else [args.version]
inputs = {}
for version in versions:
    config = manifest['versions'][version]
    elf = (args.elf or ROOT / config['elf']).resolve()
    if not elf.is_file() or hashlib.sha256(elf.read_bytes()).hexdigest() != config['elf_sha256']:
        sys.exit(f'ELF {version} SHA256 mismatch or missing file: {elf}')
    inputs[version] = elf
# Check all inputs before writing generated output. Each version has its own tree.
env = dict(os.environ, **manifest['environment'])
for version, elf in inputs.items():
    config = manifest['versions'][version]
    paths = {key: (args.port_dir / config[key]).resolve() for key in ('recomp', 'out', 'spu')}
    # Do not mix an old extraction/registry with this ELF. Refuse stale SPU files.
    if paths['spu'].exists() and any(paths['spu'].rglob('*.elf')):
        sys.exit(f'SPU extraction already exists: {paths["spu"]}; use a fresh --port-dir or remove that generated tree')
    values = dict(paths, elf=elf, stem=elf.stem)
    for command in manifest['commands']:
        cmd = [sys.executable, str(sdk / 'tools' / command[0])]
        cmd += [arg.format(**values) for arg in command[1:]]
        print('+ ' + ' '.join(cmd), flush=True)
        subprocess.run(cmd, env=env, check=True)
    # Generated files are intentionally not tracked; retain provenance beside them.
    receipt = dict(version=version, elf_sha256=config['elf_sha256'], sdk=lock,
                   environment=manifest['environment'], commands=manifest['commands'])
    (paths['out'] / 'generation.json').write_text(json.dumps(receipt, indent=2) + '\n')
    print(f'Lift generation PASS: version={version} sha256={config["elf_sha256"]}', flush=True)
