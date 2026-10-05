#!/usr/bin/env python3
"""Benchmark exact generated synth kernel bodies with deterministic LS/GPR data."""
import argparse
from pathlib import Path
import re
import subprocess
import sys

p = argparse.ArgumentParser(description=__doc__)
p.add_argument('--source', type=Path, required=True)
p.add_argument('--headers', type=Path, required=True)
p.add_argument('--work', type=Path, required=True)
p.add_argument('--rounds', default='20000')
p.add_argument('--reference', type=Path, help='Require identical state hashes from an earlier run')
a = p.parse_args()
a.work.mkdir(parents=True, exist_ok=True)
text = a.source.read_text()
addresses = {'00006280': 'ao_mix', '000024E0': 'ao_scale', '00000D88': 'ao_clear', '00001010': 'ao_interp'}
bodies = []
# Includes any generated diagnostic fallback directly preceding a kernel.
for address, alias in addresses.items():
    pattern = r'(?:static )?void (\w*spu_func_' + address + r'(?:_uncached)?)\(spu_context\* ctx\) \{'
    for m in re.finditer(pattern, text):
        depth, end = 1, m.end()
        while depth:
            depth += (text[end] == '{') - (text[end] == '}')
            end += 1
        bodies.append(text[m.start():end])
        if not m[1].endswith('_uncached'):
            bodies.append(f'void {alias}(spu_context* ctx) {{ {m[1]}(ctx); }}')
joined = '\n'.join(bodies)
defined = set(re.findall(r'void (\w+)\(spu_context\* ctx\)', joined))
targets = set(re.findall(r'\b\w*spu_func_[0-9A-F]{8}\b', joined)) - defined
stubs = '\n'.join(f'void {t}(spu_context* ctx) {{ (void)ctx; }}' for t in sorted(targets))
unit = a.work / 'kernels.c'
unit.write_text('#include "spu_helpers.h"\n' + stubs + '\n' + joined + '\n')
exe = a.work / 'synth-bench'
cmd = ['clang', '-std=gnu17', '-O2', '-I' + str(a.headers.resolve()), str(unit),
       str(Path(__file__).with_suffix('.c')), '-o', str(exe)]
subprocess.run(cmd, check=True)
result = subprocess.run([str(exe), a.rounds], check=True, capture_output=True, text=True)
print(result.stdout, end='')
if a.reference:
    hashes = lambda s: dict(re.findall(r'^(\S+).*state_fnv64=([0-9a-f]+)', s, re.M))
    if hashes(result.stdout) != hashes(a.reference.read_text()):
        sys.exit('FAIL: synth state differs from reference')
    ref_pcm = re.findall(r'pcm_fnv64=([0-9a-f]+)', a.reference.read_text())
    if ref_pcm and re.findall(r'pcm_fnv64=([0-9a-f]+)', result.stdout) != ref_pcm:
        sys.exit('FAIL: synth PCM differs from reference')
    print('PASS: bit-identical synth PCM/register/LS/exit hashes versus reference')
