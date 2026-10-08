#!/usr/bin/env python3
"""Bounded dat-LZS compression and NISPACK rebuilds for local D2 overlays.

Never changes the source archive; outputs must be new. Game-specific member
semantics and active overlay precedence must be validated by the caller.
"""
import argparse
from collections import Counter, defaultdict, deque
import hashlib
import json
import os
from pathlib import Path
import struct
import tempfile

from d2_character_export import nispack, unlzs, _no_symlinks

MAX_MEMBER = 64 * 1024 * 1024


def compress_lzs(data):
    if len(data) > MAX_MEMBER:
        raise ValueError('Expanded LZS exceeds 64 MiB')
    counts = Counter(data)
    marker = min(range(256), key=lambda v: (counts[v], v))
    history = defaultdict(lambda: deque(maxlen=32))
    output = bytearray()
    pos = 0
    while pos < len(data):
        length = 0
        distance = 0
        if pos + 3 <= len(data):
            key = data[pos:pos+3]
            choices = history[key]
            while choices and pos - choices[0] > 254:
                choices.popleft()
            for previous in reversed(choices):
                # The guest decoder delegates copies to optimized memcpy,
                # which may copy backward or in wide chunks. References must
                # end before the destination, rather than relying on a
                # forward byte-loop expansion of overlapping matches.
                limit = min(255, len(data)-pos, pos-previous)
                if limit < 4:
                    continue
                candidate = 3
                while candidate < limit and data[previous+candidate] == data[pos+candidate]:
                    candidate += 1
                if candidate > length:
                    length, distance = candidate, pos-previous
        take = length if length >= 4 else 1
        if take > 1:
            # Encoded distance skips the marker value, which denotes a literal.
            encoded = distance + (distance >= marker)
            assert 1 <= distance <= 254 and encoded != marker and encoded <= 255
            output.extend((marker, encoded, take))
        else:
            value = data[pos]
            output.append(value)
            if value == marker:
                output.append(marker)
        for i in range(pos, pos+take):
            if i+3 <= len(data):
                history[data[i:i+3]].append(i)
        pos += take
    return b'dat\0' + struct.pack('<III', len(data), len(output)+12, marker) + output


def validate_name(name):
    try:
        raw = name.encode('ascii')
    except UnicodeEncodeError as exc:
        raise ValueError('Archive names must be ASCII') from exc
    if not raw or len(raw) > 31 or any(c in raw for c in (0, 47, 92)) or name in ('.', '..'):
        raise ValueError('Unsafe NISPACK member name')
    return raw.ljust(32, b'\0')


def file_hash(path):
    digest = hashlib.sha256()
    with path.open('rb') as f:
        for block in iter(lambda: f.read(1024*1024), b''):
            digest.update(block)
    return digest.hexdigest()


def rebuild(source, output, replacements, additions=None, alignment=2048, addition_unknown_words=None):
    source = _no_symlinks(source.absolute())
    output = _no_symlinks(output.absolute())
    if source == output or output.exists() or output.parent == source:
        raise ValueError('Output must be a new file distinct from the source')
    if alignment <= 0 or alignment > 65536 or alignment & (alignment-1):
        raise ValueError('Alignment must be a power of two at most 65536')
    additions = additions or {}
    addition_unknown_words = addition_unknown_words or {}
    if set(addition_unknown_words)-set(additions) or any(type(v) is not int or not 0 <= v <= 0xffffffff
                                                       for v in addition_unknown_words.values()):
        raise ValueError('Invalid explicit addition directory words')
    if set(replacements) & set(additions):
        raise ValueError('Replacement/addition overlap')
    for name in (*replacements, *additions):
        validate_name(name)
    patches = {}
    for name, path in {**replacements, **additions}.items():
        path = _no_symlinks(Path(path).absolute())
        if path.stat().st_size > MAX_MEMBER:
            raise ValueError('Replacement exceeds 64 MiB')
        patches[name] = path.read_bytes()
    before = file_hash(source)
    with source.open('rb') as src:
        rows = nispack(src, source.stat().st_size)
        src.seek(0)
        header = src.read(16)
        names = [r['name'] for r in rows]
        if len(set(names)) != len(names):
            raise ValueError('Duplicate source member names are ambiguous')
        if set(replacements)-set(names) or set(additions)&set(names):
            raise ValueError('Replacement absent or addition already exists')
        layout = []
        cursor = 16 + (len(rows)+len(additions))*44
        for row in rows + [dict(name=n, unknown_be32=addition_unknown_words.get(n,0), size=len(patches[n])) for n in additions]:
            cursor = (cursor+alignment-1) & -alignment
            size = len(patches[row['name']]) if row['name'] in patches else row['size']
            if cursor+size > 0xffffffff:
                raise ValueError('Archive exceeds 32-bit directory offsets')
            layout.append(dict(row, new_offset=cursor, new_size=size))
            cursor += size
        output.parent.mkdir(parents=True, exist_ok=True)
        temp_path = None
        try:
            with tempfile.NamedTemporaryFile(prefix='d2-pack-', dir=output.parent, delete=False) as dst:
                temp_path = Path(dst.name)
                dst.write(header[:12]+struct.pack('>I', len(layout)))
                for row in layout:
                    name_bytes = bytes.fromhex(row['name_hex']) if 'name_hex' in row else validate_name(row['name'])
                    dst.write(name_bytes+struct.pack('>III',row['new_offset'],row['new_size'],row['unknown_be32']))
                for row in layout:
                    dst.write(b'\0'*(row['new_offset']-dst.tell()))
                    if row['name'] in patches:
                        dst.write(patches[row['name']])
                    else:
                        src.seek(row['offset'])
                        remaining = row['size']
                        while remaining:
                            block = src.read(min(remaining,1024*1024))
                            if not block:
                                raise ValueError('Source truncated during rebuild')
                            dst.write(block)
                            remaining -= len(block)
                dst.flush()
                os.fsync(dst.fileno())
            if file_hash(source) != before:
                raise ValueError('Source changed during rebuild')
            # Read back every member and compare its bytes, including untouched
            # resources. Hash whole members without loading the whole archive.
            with temp_path.open('rb') as check:
                actual = nispack(check, temp_path.stat().st_size)
                for got, row in zip(actual, layout):
                    assert got['name'] == row['name'] and got['unknown_be32'] == row['unknown_be32']
                    check.seek(got['offset'])
                    if row['name'] in patches:
                        if check.read(got['size']) != patches[row['name']]:
                            raise ValueError('Replacement readback mismatch')
                    else:
                        src.seek(row['offset'])
                        remaining = row['size']
                        while remaining:
                            amount = min(remaining,1024*1024)
                            if check.read(amount) != src.read(amount):
                                raise ValueError('Untouched member readback mismatch')
                            remaining -= amount
            # Link publishes atomically and fails if output appeared meanwhile.
            os.link(temp_path, output)
        finally:
            if temp_path is not None:
                temp_path.unlink(missing_ok=True)
    return dict(source=str(source), source_sha256=before, output=str(output),
                output_sha256=file_hash(output), bytes=output.stat().st_size,
                count=len(layout), replaced=list(replacements), added=list(additions),
                unknown_word_policy='Preserved for existing members; explicit value or zero for additions, runtime meaning unverified',
                addition_unknown_words={n:addition_unknown_words.get(n,0) for n in additions},
                validation='Every member read back; untouched bytes and directory order preserved; source SHA256 unchanged')


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    commands = parser.add_subparsers(dest='command', required=True)
    pack = commands.add_parser('compress')
    pack.add_argument('source', type=Path)
    pack.add_argument('output', type=Path)
    archive = commands.add_parser('rebuild')
    archive.add_argument('source', type=Path)
    archive.add_argument('output', type=Path)
    archive.add_argument('--manifest', type=Path, required=True,
                         help='JSON with replacements/additions mapping member names to local file paths')
    args = parser.parse_args()
    if args.command == 'compress':
        source = _no_symlinks(args.source.absolute())
        target = _no_symlinks(args.output.absolute())
        if source.stat().st_size > MAX_MEMBER:
            raise ValueError('Expanded source exceeds 64 MiB')
        raw = source.read_bytes()
        packed = compress_lzs(raw)
        if unlzs(packed) != raw:
            raise ValueError('Compression roundtrip mismatch')
        with target.open('xb') as f:
            f.write(packed)
        print(json.dumps(dict(expanded_bytes=len(raw), packed_bytes=len(packed), roundtrip='passed')))
    else:
        manifest = json.loads(args.manifest.read_text())
        base = args.manifest.absolute().parent
        replacements = {k:base/Path(v) for k,v in manifest.get('replacements',{}).items()}
        additions = {k:base/Path(v) for k,v in manifest.get('additions',{}).items()}
        print(json.dumps(rebuild(args.source,args.output,replacements,additions,
                                 addition_unknown_words=manifest.get('addition_unknown_words')),indent=2))


if __name__ == '__main__':
    main()
