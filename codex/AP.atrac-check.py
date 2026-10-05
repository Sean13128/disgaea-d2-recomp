#!/usr/bin/env python3
"""Read real D2 BGM packs; extract fixtures only into the supplied scratch dir."""
import argparse, mmap, os, struct, subprocess
from pathlib import Path
p=argparse.ArgumentParser(description=__doc__)
p.add_argument('work',type=Path)
p.add_argument('--baseline-source',type=Path)
a=p.parse_args(); root=Path(__file__).resolve().parents[1]; sdk=root/'ps3recomp'
work=a.work.resolve(); work.mkdir(parents=True,exist_ok=True)
wanted={4925440:'hub',5230592:'switch',5130240:'map30005'}
for pack in sorted((root/'Disgaea D2 A Brighter Darkness - [BLUS31313]/PS3_GAME/USRDIR/Data/SOUND/SndPakBgm').glob('*.pak')):
    with pack.open('rb') as f, mmap.mmap(f.fileno(),0,access=mmap.ACCESS_READ) as m:
        at=0
        while wanted and (at:=m.find(b'RIFF',at))>=0:
            n=struct.unpack_from('<I',m,at+4)[0]+8; end=None; off=at+12
            if m[at+8:at+12]==b'WAVE' and at+n<=len(m):
                while off+8<=at+n:
                    tag=m[off:off+4]; size=struct.unpack_from('<I',m,off+4)[0]
                    if tag==b'fact' and size>=8:
                        samples,delay=struct.unpack_from('<II',m,off+8); end=samples+delay+0x170
                    if tag==b'data': break
                    off+=8+size+(size&1)
                if end in wanted:
                    name=wanted.pop(end); (work/(name+'.at3')).write_bytes(m[at:at+n])
                    print(f'{name}: {pack.name} offset={at:#x} bytes={n} end={end}',flush=True)
            at+=4
assert not wanted,wanted
extra=['-DAP_BASELINE',f'-DATRAC_SOURCE="{a.baseline_source.resolve()}"'] if a.baseline_source else []
flags=['-O1','-g','-fsanitize=address,undefined','-fno-omit-frame-pointer']
subprocess.run(['clang','-std=gnu17',*flags,'-DAP_REAL_ATRAC',*extra,f'-I{sdk}/include','-c',sdk/'libs/codec/tests/test_atrac_stream_switch.c','-o',work/'test.o'],check=True)
subprocess.run(['clang++','-std=c++17',*flags,'-w',f'-I{sdk}/third_party/at3_standalone',*sorted((sdk/'third_party/at3_standalone').glob('*.cpp')),work/'test.o','-o',work/'real-atrac'],check=True)
subprocess.run([work/'real-atrac',*(work/(n+'.at3') for n in ('hub','switch','map30005'))],check=True)
