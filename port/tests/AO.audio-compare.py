#!/usr/bin/env python3
"""Report raw cellAudio hashes and exactly matching 256-frame stereo blocks.

Clocked captures include startup silence, scheduling gaps and timed pad events;
whole-file hashes need not match even when individual synth outputs do.
"""
import difflib
import hashlib
from pathlib import Path
import sys

captures = []
for filename in sys.argv[1:]:
    data = Path(filename).read_bytes()
    blocks = [data[i:i + 2048] for i in range(0, len(data) - 2047, 2048)]
    nonzero = [b for b in blocks if any(b)]
    ids = [hashlib.sha256(b).digest() for b in nonzero]
    captures.append((data, ids))
    print(f'{filename}: bytes={len(data)} blocks={len(blocks)} nonzero={len(nonzero)} sha256={hashlib.sha256(data).hexdigest()}')
if len(captures) == 2:
    a, b = captures
    matches = difflib.SequenceMatcher(None, a[1], b[1], autojunk=False).get_matching_blocks()
    longest = max(m.size for m in matches)
    print(f'whole-file-identical={a[0] == b[0]}; exact nonzero blocks in order={sum(m.size for m in matches)}; longest identical sequence={longest} blocks ({longest * 256 / 48000:.3f}s)')
