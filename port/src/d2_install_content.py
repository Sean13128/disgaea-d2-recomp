#!/usr/bin/env python3
"""Install extracted D2 packages or migrate installed content; never copy saves."""
import argparse
import pathlib
import shutil
import struct
import sys
import tempfile

REQUIRED_FLAGS = [f'flag{value:08d}.edat'
                  for start, count in ((10001, 18), (40001, 22), (50001, 5))
                  for value in range(start, start+count)]

def sfo(path):
    data = path.read_bytes()
    magic, version, keys, values, count = struct.unpack_from('<5I', data)
    if magic != 0x46535000 or not 20 + count * 16 <= keys < values <= len(data):
        raise ValueError('invalid PARAM.SFO')
    result = {}
    for i in range(count):
        key, fmt, size, maximum, offset = struct.unpack_from('<HHIII', data, 20 + i*16)
        if key >= values-keys or size > maximum or maximum > len(data)-values-offset:
            raise ValueError('invalid PARAM.SFO entry')
        end = data.index(b'\0', keys+key, values)
        if fmt == 0x204:
            result[data[keys+key:end].decode()] = data[values+offset:values+offset+size].rstrip(b'\0').decode()
    return result

def main():
    a = argparse.ArgumentParser(description=__doc__)
    a.add_argument('source', type=pathlib.Path, help='folder with update-140/dlc-pack, or installed hdd0')
    a.add_argument('--into', type=pathlib.Path)
    x = a.parse_args()
    root = x.source.resolve()
    sources = [(root/'update-140', 'BLUS31313'), (root/'dlc-pack', 'NPUB31321')]
    if (root/'game').is_dir():
        sources = [(root/'game'/title, title) for _, title in sources]
    try:
        for src, title in sources:
            meta = sfo(src/'PARAM.SFO')
            if meta.get('TITLE_ID') != title or not (src/'USRDIR').is_dir():
                raise ValueError(f'wrong/incomplete title: {src}')
            if title == 'BLUS31313':
                if meta.get('APP_VER') != '01.40' or not (src/'USRDIR/Data/START_7.dat').stat().st_size:
                    raise ValueError('requires the BLUS31313 1.40 update')
            else:
                for flag in REQUIRED_FLAGS:
                    if (src/'USRDIR/Data/flag'/flag).stat().st_size < 256:
                        raise ValueError(f'incomplete DLC flag: {flag}')
    except (OSError, ValueError, struct.error) as error:
        a.error(f'incomplete source: {error}')
    if x.into is None:
        project = pathlib.Path(__file__).resolve().parents[2]
        if not (project/'port/hdd0').is_dir():
            a.error('specify --into with an external hdd0 destination')
        runs = project/'port/runs'
        runs.mkdir(parents=True, exist_ok=True)
        dst = pathlib.Path(tempfile.mkdtemp(prefix='content.', dir=runs))/'hdd0'
        shutil.copytree(project/'port/hdd0', dst)
    else:
        dst = x.into.resolve()
        for parent in (dst, *dst.parents):
            if (parent/'PS3_GAME').is_dir() or parent.name == 'PS3_GAME':
                a.error('destination must be outside the game dump')
        dst.mkdir(parents=True, exist_ok=True)
    for src, title in sources:
        out = dst/'game'/title
        if src.resolve() == out.resolve():
            continue
        # Copy all content first; publish its metadata only after success.
        if any(p.is_symlink() for p in (out, *out.parents)) or any(p.is_symlink() for p in out.rglob('*')):
            a.error(f'destination content contains symlinks: {out}')
        out.mkdir(parents=True, exist_ok=True)
        shutil.copytree(src/'USRDIR', out/'USRDIR', dirs_exist_ok=True)
        shutil.copy2(src/'PARAM.SFO', out/'PARAM.SFO')
    print(dst)

if __name__ == '__main__':
    main()
