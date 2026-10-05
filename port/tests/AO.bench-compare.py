#!/usr/bin/env python3
"""Run paired baseline/current synth benchmarks and require identical hashes."""
import argparse
import json
from pathlib import Path
import re
import statistics
import subprocess

p = argparse.ArgumentParser(description=__doc__)
p.add_argument('before', type=Path)
p.add_argument('after', type=Path)
p.add_argument('--output', type=Path, required=True)
p.add_argument('--rounds', default='300000')
a = p.parse_args()
bins = {'before': a.before, 'after': a.after}
trials = {k: [] for k in bins}
for i in range(5):
    for mode in (['before', 'after'] if i % 2 == 0 else ['after', 'before']):
        out = subprocess.check_output([str(bins[mode]), a.rounds], text=True)
        rows = {name: {'ns': float(ns), 'hash': h} for name, ns, h in
                re.findall(r'^(\S+).*ns/call=([\d.]+) state_fnv64=([0-9a-f]+)', out, re.M)}
        rows['PCM'] = {'hash': re.search(r'pcm_fnv64=([0-9a-f]+)', out)[1]}
        trials[mode].append(rows)
a.output.with_suffix('.json').write_text(json.dumps(trials, indent=2) + '\n')
lines = [f'Five paired trials, {a.rounds} calls/kernel, process CPU clock; median ns/call:']
for name in trials['before'][0]:
    assert len({t[name]['hash'] for mode in trials.values() for t in mode}) == 1, name
    if name == 'PCM':
        lines.append('stereo PCM: identical pcm_fnv64=' + trials['after'][0][name]['hash'])
        continue
    b = statistics.median(t[name]['ns'] for t in trials['before'])
    current = statistics.median(t[name]['ns'] for t in trials['after'])
    lines.append(f'{name}: before={b:.1f} after={current:.1f} reduction={100*(1-current/b):.1f}% hash={trials["after"][0][name]["hash"]}')
summary = '\n'.join(lines) + '\n'
a.output.write_text(summary)
print(summary, end='')
