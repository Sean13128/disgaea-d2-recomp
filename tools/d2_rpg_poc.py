#!/usr/bin/env python3
"""Offline Etna format experiment. Writes a NEW output directory; never installs.

Requires Pillow and clang++. d2_character_export.py supplies the bounded readers.
Generated assets/lift excerpts are proprietary local research, not distributable.
"""
import argparse
import hashlib
import io
import json
from pathlib import Path
import struct
import subprocess
import tempfile
from collections import deque

from PIL import Image
import d2_character_export as d


def sha(data):
    return hashlib.sha256(data).hexdigest()


def literal_lzs(data):
    """Valid literal-only dat LZS; deliberately no compression/backreferences."""
    marker = 255
    body = data.replace(bytes([marker]), bytes([marker, marker]))
    return b'dat\0' + struct.pack('<III', len(data), len(body) + 12, marker) + body


def extract_function(path, name):
    source = path.read_text()
    start = source.index('void ' + name + '(')
    end = source.index('\n}', start) + 2
    return source[start:end]


def member(path, name):
    with path.open('rb') as f:
        entry = next(e for e in d.nispack(f, path.stat().st_size) if e['name'] == name)
        f.seek(entry['offset'])
        raw = f.read(entry['size'])
    return raw, dict(archive=str(path), **entry, sha256=sha(raw))


def remove_border_black(image):
    """Explicit exact-black border flood; retain enclosed black artwork."""
    image = image.convert('RGBA')
    w, h = image.size
    pixels = image.load()
    todo = deque([(x, y) for x in range(w) for y in (0, h - 1)] +
                 [(x, y) for y in range(h) for x in (0, w - 1)])
    while todo:
        x, y = todo.popleft()
        if not (0 <= x < w and 0 <= y < h) or pixels[x, y] != (0, 0, 0, 255):
            continue
        pixels[x, y] = (0, 0, 0, 0)
        todo.extend(((x - 1, y), (x + 1, y), (x, y - 1), (x, y + 1)))
    return image


def check_lifted_lookup(repo, table, scratch):
    """Compile the exact binder/lookup with isolated BE VM/bit-operation shims."""
    paths = [repo/'port/src/recomp-140/ppu_recomp_019.cpp',
             repo/'port/src/recomp-140/ppu_recomp_018.cpp']
    funcs = [extract_function(paths[0], 'func_0034FE34'),
             extract_function(paths[1], 'func_0034F8D8')]
    prefix = r'''
#include <cstdint>
#include <cassert>
#include <cstring>
#include <fstream>
#include <iterator>
#include <vector>
#include <iostream>
static uint8_t mem[1024*1024];
struct ppu_context { uint64_t gpr[32] = {}; uint32_t cr=0, ctr=0; };
uint64_t readbe(uint64_t a, int n) { assert(a+n<=sizeof(mem)); uint64_t v=0; while(n--)v=(v<<8)|mem[a++];return v; }
uint64_t vm_read16(uint64_t a){return readbe(a,2);}
uint64_t vm_read32(uint64_t a){return readbe(a,4);}
void writebe(uint64_t a,uint64_t v,int n){assert(a+n<=sizeof(mem));while(n){mem[a+--n]=v;v>>=8;}}
void vm_write16(uint64_t a,uint64_t v){writebe(a,v,2);}
void vm_write32(uint64_t a,uint64_t v){writebe(a,v,4);}
uint64_t ppc_rldicl(uint64_t v,int sh,int mb){assert(sh==0);return v&(~uint64_t(0)>>mb);}
uint32_t ppc_rlwinm(uint32_t v,int sh,int mb,int me){assert(sh==0);return v&((~uint32_t(0)>>mb)&(~uint32_t(0)<<(31-me)));}
'''
    suffix = r'''
int main(int argc,char**argv){
 assert(argc==2);std::ifstream f(argv[1],std::ios::binary);assert(f);
 std::vector<uint8_t> data((std::istreambuf_iterator<char>(f)),{});
 assert(data.size()+0x1000<sizeof(mem));std::memcpy(mem+0x1000,data.data(),data.size());
 ppu_context c;c.gpr[3]=0x100;c.gpr[4]=0x1000;func_0034FE34(&c);
 int count=vm_read16(0x100);assert(count==559);assert(vm_read32(0x104)==0x1004);
 auto lookup=[&](int id){c.gpr[3]=0x100;c.gpr[4]=id;func_0034F8D8(&c);return int32_t(c.gpr[3]);};
 for(int row=0;row<count;row++)assert(lookup(vm_read16(0x1004+row*0x2a4+0x194))==row);
 assert(lookup(32000)==558);assert(lookup(0)==-1);assert(lookup(31999)==-1);
 vm_write16(0x100,558);assert(lookup(32000)==-1);
 std::cout<<"PASS: exact 1.40 binder and lookup; 559 rows, appended ID32000 at row558, misses and original count checked\n";
}
'''
    code = scratch/'lookup.cpp'
    code.write_text(prefix + '\n'.join(funcs) + suffix)
    binary = scratch/'lookup'
    subprocess.run(['clang++', '-std=c++17', '-O1', '-fsanitize=address,undefined',
                    str(code), '-o', str(binary)], check=True, capture_output=True)
    result = subprocess.run([str(binary), str(table)], check=True, capture_output=True, text=True)
    return dict(status='passed', output=result.stdout.strip(),
                scope='Exact lifted binder/lookup only; isolated VM; no gameplay, serializer, recruitment or full engine run',
                sources=[dict(path=str(p), sha256=sha(p.read_bytes()), function_sha256=sha(f.encode()))
                         for p, f in zip(paths, funcs)])


def run(repo, sheet, output, scratch):
    # Refuse source/output symlinks, existing outputs and output inside inputs.
    for path in (repo, sheet, output, scratch):
        d._no_symlinks(path)
    if output.exists():
        raise ValueError('Output must be a new directory')
    root = repo/'Disgaea D2 A Brighter Darkness - [BLUS31313]/PS3_GAME/USRDIR/Data'
    if output == root or root in output.parents or output == sheet or sheet in output.parents:
        raise ValueError('Output overlaps source')
    source_bytes = sheet.read_bytes()
    char, char_ref = member(root/'START.dat', 'char.dat')
    body, body_ref = member(root/'ANM_HI.dat', 'anm00030.lzs')
    original = d.unlzs(body)
    pages = d.anm_pages(original, include_rgba=False)
    first = pages[0]
    assert (first['width'], first['height']) == (512, 512)
    rows = d.characters(char)
    etna = next(r for r in rows if r['id'] == 30)
    assert etna['body_animation_ids'][0] == 30
    assert 32000 not in {r['id'] for r in rows} and 31999 not in {r['id'] for r in rows}
    output.mkdir(parents=True)
    # Fixed crop is manually inspected #1-front / #1_stand from this supplied sheet.
    image = Image.open(io.BytesIO(source_bytes))
    if image.size != (856, 9198):
        raise ValueError('This experiment expects the inspected Liones Princess Etna sheet')
    crop = remove_border_black(image.crop((1, 18, 120, 208)))
    pose = crop.crop(crop.getbbox())
    pose.save(output/'source-pose.png')
    # Demonstrate the known TXF ARGB1555 route independently from ANM indexing.
    w, h = pose.size
    words = [((a >= 128) << 15) | ((r*31//255) << 10) | ((g*31//255) << 5) | (b*31//255)
             for r, g, b, a in struct.iter_unpack('4B', pose.tobytes())]
    txf = bytes([11, 0, 0, 0]) + struct.pack('>HHHHI', w, h, 1, 0, w*h*2) + struct.pack('>%dH'%len(words), *words)
    png, txf_info = d.txf_png(txf)
    (output/'pose-argb1555.txf').write_bytes(txf)
    (output/'pose-argb1555.png').write_bytes(png)
    # Keep every existing palette/header/animation descriptor and page geometry.
    # A manually chosen atlas region is NOT a decoded animation/frame mapping.
    height = 161
    scaled = pose.resize((round(w*height/h), height), Image.Resampling.NEAREST)
    cell = Image.new('RGBA', (110, 171))
    cell.paste(scaled, ((110-scaled.width)//2, 171-scaled.height))
    palette = first['colors']
    cache = {}
    squared_error = []
    indices = bytearray(first['indices'])
    for y in range(171):
        for x in range(110):
            pixel = cell.getpixel((x, y))
            if pixel not in cache:
                candidates = [i for i,c in enumerate(palette) if (c[3] == 0) == (pixel[3] == 0)]
                if not candidates:
                    raise ValueError('Donor lacks compatible alpha palette')
                cache[pixel] = min(candidates, key=lambda i: sum((palette[i][k]-pixel[k])**2 for k in range(4)))
            index = cache[pixel]
            indices[y*512+x] = index
            if pixel[3]:
                squared_error.append(sum((palette[index][k]-pixel[k])**2 for k in range(3))/3)
    changed = bytearray(original)
    off = first['data_offset']
    changed[off:off+len(indices)] = indices
    assert original[:off] == changed[:off] and original[off+len(indices):] == changed[off+len(indices):]
    for y in range(512):
        start = y*512 + (110 if y < 171 else 0)
        assert indices[start:(y+1)*512] == first['indices'][start:(y+1)*512]
    packed = literal_lzs(changed)
    assert d.unlzs(packed) == changed
    decoded = d.anm_pages(d.unlzs(packed), include_rgba=False)
    assert len(decoded) == len(pages) and bytes(decoded[0]['indices']) == bytes(indices)
    (output/'CONTAINER-TEST-anm00030.lzs').write_bytes(packed)
    (output/'donor-page.png').write_bytes(d.indexed_png(512,512,first['indices'],palette))
    (output/'converted-page.png').write_bytes(d.indexed_png(512,512,indices,palette))
    converted = Image.open(output/'converted-page.png').convert('RGBA').crop((0,0,110,171))
    converted.save(output/'converted-pose.png')
    # Offline appended clone retains donor dependencies; ID is test-only.
    newrow = bytearray.fromhex(etna['raw_hex'])
    struct.pack_into('>H',newrow,0x194,32000)
    newtable = struct.pack('>H',len(rows)+1) + char[2:] + newrow
    newpath = output/'LOOKUP-TEST-char.dat'
    newpath.write_bytes(newtable)
    assert len(d.characters(newtable)) == 559 and newtable[4:len(char)] == char[4:]
    lookup = check_lifted_lookup(repo, newpath, scratch)
    # Negative bounds checks and escape/roundtrip coverage.
    assert d.unlzs(literal_lzs(bytes(range(256))*2)) == bytes(range(256))*2
    for bad in (packed[:-1], b'dat\0'+b'\xff'*12):
        try:
            d.unlzs(bad)
        except ValueError:
            pass
        else:
            raise AssertionError('Malformed LZS accepted')
    assert member(root/'START.dat','char.dat')[0] == char
    assert member(root/'ANM_HI.dat','anm00030.lzs')[0] == body
    assert sheet.read_bytes() == source_bytes
    files = {p.name:dict(bytes=p.stat().st_size,sha256=sha(p.read_bytes())) for p in output.iterdir()}
    result = dict(status='offline-format-tests-passed; NOT installed or gameplay-validated',
                  source_sheet=dict(path=str(sheet),sha256=sha(source_bytes),size=image.size,
                                    crop=[1,18,120,208],alpha_policy='Exact opaque border-connected black made transparent; enclosed black preserved'),
                  sources=[char_ref,body_ref],body_pages=10,palettes=5,txf=txf_info,
                  anm=dict(original_bytes=len(body),test_bytes=len(packed),expanded_bytes=len(original),
                           changed_region=[0,0,110,171],metadata_and_palettes_unchanged=True,
                           texture_palette_pairs=len(pages),rgb_rmse=(sum(squared_error)/len(squared_error))**0.5,
                           limitation='One manually chosen atlas region; nearest existing palette; no decoded animation mapping, timing, attachment or runtime palette validation'),
                  class_lookup=lookup,source_members_unchanged=True,files=files,
                  blockers=['RPG sheet has pixels/labels, no original timing/pivots/animation metadata',
                            'D2 ANM frame/composition metadata remains undecoded',
                            'All class consumers, recruitment, visual selectors and save roundtrip unaudited',
                            'Literal-only LZS is much larger; memory/loader/archive limits untested'])
    (output/'validation.json').write_text(json.dumps(result,indent=2)+'\n')
    print(json.dumps(result,indent=2))


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--repo',type=Path,default=Path(__file__).resolve().parents[1])
    parser.add_argument('--sheet',type=Path,required=True)
    parser.add_argument('--output',type=Path,required=True)
    args = parser.parse_args()
    with tempfile.TemporaryDirectory(prefix='d2-rpg-',dir='/Volumes/Data/ai-tmp/codex') as scratch:
        run(args.repo.absolute(),args.sheet.absolute(),args.output.absolute(),Path(scratch))
