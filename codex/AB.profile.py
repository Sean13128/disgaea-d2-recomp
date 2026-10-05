#!/usr/bin/env python3
"""Attribute macOS sample's PPU main tree after removing blocking stacks."""
import collections
import re
import sys
from pathlib import Path

nodes = []
stack = []
active = False
for line in Path(sys.argv[1]).read_text().splitlines():
    if re.match(r'\s+\d+ Thread_', line):
        if active:
            break
        active = 'PPU main' in line
        continue
    if not active:
        continue
    match = re.match(r'^([ +!:|.]+)(\d+) (.+?)  \(in ', line)
    if not match:
        continue
    depth = len(match[1])
    count = int(match[2])
    symbol = match[3].split('(')[0]
    while stack and stack[-1]['depth'] >= depth:
        stack.pop()
    node = dict(depth=depth, count=count, own=count, symbol=symbol,
                path=[n['symbol'] for n in stack] + [symbol])
    if stack:
        stack[-1]['own'] -= count
    stack.append(node)
    nodes.append(node)
if not nodes:
    sys.exit('No PPU main samples found')
waits = ('gcm_progress_wait', 'ps3_poll_backoff', 'ps3_poll_wait',
         '_pthread_cond_wait', 'nanosleep', 'semaphore_wait', '__psynch_cvwait',
         'WaitForSingleObject', 'WaitForMultipleObjects', 'ps3_wait_address')
guests = collections.Counter()
hle = collections.Counter()
self_cpu = collections.Counter()
blocked = nonwait = 0
for n in nodes:
    own = max(0, n['own'])
    path = n['path']
    if any(any(w in s for w in waits) for s in path):
        blocked += own
        continue
    nonwait += own
    self_cpu[n['symbol']] += own
    guest = next((s for s in reversed(path) if s.startswith('func_')), '(outside guest)')
    guests[guest] += own
    call = next((s for s in reversed(path) if s.startswith(('cell', 'sys_', 'hle_'))), None)
    if call:
        hle[call] += own
print(f'PPU main: {blocked + nonwait} samples; blocking {blocked}; non-wait {nonwait}')
for title, values in [('Deepest guest attribution (non-wait)', guests),
                      ('HLE attribution (non-wait; subset of guest samples)', hle),
                      ('Host self samples (non-wait)', self_cpu)]:
    print(title + ':')
    for name, count in values.most_common(12):
        print(f'  {count:5d} {count / max(1, nonwait):6.2%} {name}')
