#!/usr/bin/env python3
"""Probe the exact 1.40 ANM manager with an isolated VM and declared stubs.

This checks independent resource descriptors and filename generation, not ANM
decoding, GPU upload, menu behavior or gameplay. Requires the local lifted source,
matching 1.40 ELF, and clang++; no game or save files are changed.
"""
import argparse
import hashlib
import json
from pathlib import Path
import struct
import subprocess
import tempfile

from d2_character_export import _no_symlinks, nispack


def extract_function(path, name):
    source = path.read_text()
    start = source.index('void '+name+'(')
    end = source.index('\n}', start)+2
    return source[start:end]


def elf_format(path, toc_delta):
    data = path.read_bytes()
    if data[:6] != b'\x7fELF\x02\x02':
        raise ValueError('Expected big-endian ELF64')
    ph = struct.unpack_from('>Q', data, 32)[0]
    stride, count = struct.unpack_from('>HH', data, 54)
    segments = [struct.unpack_from('>II6Q', data, ph+i*stride) for i in range(count)]
    def read(address, size):
        for kind, flags, offset, va, pa, filesz, memsz, align in segments:
            if kind == 1 and va <= address and address+size <= va+filesz:
                return data[offset+address-va:offset+address-va+size]
        raise ValueError('Address absent from ELF: '+hex(address))
    entry = struct.unpack_from('>Q', data, 24)[0]
    if entry != 0x461000 or struct.unpack('>I', read(entry+4, 4))[0] != 0x47df98:
        raise ValueError('ELF does not match lifted 1.40 source')
    pointer = struct.unpack('>I', read(0x47df98+toc_delta, 4))[0]
    value = read(pointer, 64).split(b'\0')[0]
    return value.decode('ascii'), hashlib.sha256(data).hexdigest()


PREFIX = r'''
#include <cassert>
#include <cstdint>
#include <cstdio>
#include <cstring>
#include <iostream>
#include <string>
#include <vector>
static uint8_t mem[1024*1024];
struct ppu_context { uint64_t gpr[32]={}; uint32_t cr=0,ctr=0; uint64_t lr=0; };
static uint64_t readbe(uint64_t a,int n){assert(a+n<=sizeof(mem));uint64_t v=0;while(n--)v=(v<<8)|mem[a++];return v;}
static void writebe(uint64_t a,uint64_t v,int n){assert(a+n<=sizeof(mem));while(n){mem[a+--n]=v;v>>=8;}}
static uint64_t vm_read8(uint64_t a){return readbe(a,1);}
static uint64_t vm_read16(uint64_t a){return readbe(a,2);}
static uint64_t vm_read32(uint64_t a){return readbe(a,4);}
static uint64_t vm_read64(uint64_t a){return readbe(a,8);}
static void vm_write8(uint64_t a,uint64_t v){writebe(a,v,1);}
static void vm_write16(uint64_t a,uint64_t v){writebe(a,v,2);}
static void vm_write32(uint64_t a,uint64_t v){writebe(a,v,4);}
static void vm_write64(uint64_t a,uint64_t v){writebe(a,v,8);}
static uint64_t ppc_rldicl(uint64_t v,int sh,int mb){assert(sh==0);return v&(~uint64_t(0)>>mb);}
static uint32_t ppc_rlwinm(uint32_t v,int sh,int mb,int me){
 uint32_t rotated=sh?((v<<sh)|(v>>(32-sh))):v;
 return rotated&((~uint32_t(0)>>mb)&(~uint32_t(0)<<(31-me)));
}
#define DRAIN_TRAMPOLINE(ctx) ((void)0)
static std::vector<std::string> names;
// These dependencies are stubs. The manager's descriptor loop stays exact.
static void func_00180FEC(ppu_context*c){c->gpr[3]=0;}
static void func_001803D4(ppu_context*c){c->gpr[3]=1;}
static void func_001799A8(ppu_context*c){c->gpr[3]=0x7000;}
static void func_002E6518(ppu_context*){assert(false && "GPU upload outside probe scope");}
static void func_0033AD3C(ppu_context*c){
 assert(c->gpr[3]+128<=sizeof(mem));assert(c->gpr[4]+64<=sizeof(mem));
 int n=std::snprintf((char*)&mem[c->gpr[3]],128,(char*)&mem[c->gpr[4]],int(c->gpr[5]));
 assert(n>0&&n<128);c->gpr[3]=n;
}
static void func_00182F1C(ppu_context*c){
 assert(c->gpr[4]+128<=sizeof(mem));
 names.emplace_back((char*)&mem[c->gpr[4]]);c->gpr[3]=1234;
}
'''

SUFFIX = r'''
int main(int argc,char**argv){
 assert(argc==4);int resource=std::stoi(argv[1]);
 assert(resource>0&&resource<32768&&resource!=30);
 std::strcpy((char*)&mem[0x8000],argv[2]);std::strcpy((char*)&mem[0x8100],argv[3]);
 ppu_context c;c.gpr[1]=0x90000;c.gpr[2]=0x10000;
 vm_write32(c.gpr[2]-0x4088,0x8000);vm_write32(c.gpr[2]-0x407c,0x8100);
 vm_write32(0x100,0x1000);vm_write8(0x104,1);vm_write32(0x110,2);
 auto load=[&](int id,int flag=1){c.gpr[3]=0x100;c.gpr[4]=id;c.gpr[5]=1;c.gpr[6]=flag;func_00181438(&c);};
 load(30);assert(vm_read16(0x1000)==30&&vm_read16(0x1002)==1&&vm_read8(0x1010)==1);
 load(resource);assert(vm_read16(0x1024)==uint16_t(resource)&&vm_read16(0x1026)==1&&vm_read8(0x1034)==1);
 assert(names.size()==2&&names[0]=="anm00030.lzs");
 char expected[128];std::snprintf(expected,sizeof(expected),"anm%05d.lzs",resource);assert(names[1]==expected);
 load(30);assert(names.size()==2&&vm_read16(0x1002)==1&&vm_read16(0x1026)==1);
 load(30,0);
 assert(names.size()==2&&vm_read16(0x1002)==2&&vm_read16(0x1026)==1);
 // A full descriptor bank must leave the existing resources intact.
 uint8_t before[72];std::memcpy(before,&mem[0x1000],72);
 load(31);assert(names.size()==2&&std::memcmp(before,&mem[0x1000],72)==0);
 std::cout<<"PASS: original and alternate descriptors coexist; filenames "<<names[0]<<" and "<<names[1]
          <<"; repeat reuses original; full bank leaves both intact\n";
}
'''


def run(repo, resource, output, scratch):
    repo = _no_symlinks(repo.absolute())
    output = _no_symlinks(output.absolute())
    scratch = _no_symlinks(scratch.absolute())
    if not 1 <= resource < 32768 or resource == 30:
        raise ValueError('Candidate must be a positive signed-16 ID other than 30')
    if output.exists():
        raise ValueError('Output file must be new')
    source = repo/'port/src/recomp-140/ppu_recomp_008.cpp'
    elf = repo/'work/v140/EBOOT.elf'
    functions = [extract_function(source, name) for name in ('func_00180078','func_00181438')]
    lzs, elf_hash = elf_format(elf, -0x4088)
    plain, _ = elf_format(elf, -0x407c)
    if lzs != 'anm%05d.lzs' or plain != 'anm%05d.dat':
        raise ValueError('Unexpected native resource filename formats')
    game = repo/'Disgaea D2 A Brighter Darkness - [BLUS31313]'
    if game == output or game in output.parents or game == scratch or game in scratch.parents:
        raise ValueError('Output/scratch overlaps game dump')
    inventories = []
    for archive in sorted((game/'PS3_GAME/USRDIR/Data').glob('ANM_HI*.dat')):
        with archive.open('rb') as f:
            names = {r['name'] for r in nispack(f, archive.stat().st_size)}
        collisions = sorted({f'anm{resource:05d}.lzs', f'anm{resource:05d}.dat'} & names)
        inventories.append(dict(archive=str(archive), count=len(names), collisions=collisions))
    if not inventories or any(i['collisions'] for i in inventories):
        raise ValueError('Candidate absent scan or existing ANM_HI filename collision')
    scratch.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix='appearance-probe-', dir=scratch) as directory:
        code = Path(directory)/'probe.cpp'
        binary = Path(directory)/'probe'
        code.write_text(PREFIX+'\n'.join(functions)+SUFFIX)
        subprocess.run(['clang++','-std=c++17','-O1','-fsanitize=address,undefined',str(code),'-o',str(binary)],
                       check=True,capture_output=True,text=True)
        result = subprocess.run([str(binary),str(resource),lzs,plain],capture_output=True,text=True)
        if result.returncode:
            raise RuntimeError('Native probe failed: '+result.stderr.strip())
    report = dict(status='passed', candidate_resource=resource, output=result.stdout.strip(),
                  elf=str(elf), elf_sha256=elf_hash, native_filename_formats=[lzs,plain],
                  source=str(source), function_sha256=[hashlib.sha256(f.encode()).hexdigest() for f in functions],
                  archive_filename_scan=inventories,
                  stubs=['Suballocation returns slot 0','Manager mode returns 1','File manager returns sentinel',
                         'sprintf implemented with host snprintf','File size lookup records filename, returns 1234',
                         'GPU upload is an assertion failure'],
                  limitations=['Filename collision scan covers supplied ANM_HI archives only, not internal IDs or other sources.',
                               'Descriptor registration/lookup and native filename formats tested; no actual asset loading.',
                               'ANM internal resource binding, GPU upload, menu and gameplay unvalidated.'])
    output.parent.mkdir(parents=True,exist_ok=True)
    with output.open('x') as f:
        f.write(json.dumps(report,indent=2)+'\n')
    return report


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--repo',type=Path,default=Path.cwd())
    parser.add_argument('--resource',type=int,default=30000)
    parser.add_argument('--output',type=Path,required=True)
    parser.add_argument('--scratch',type=Path,required=True)
    args=parser.parse_args()
    print(json.dumps(run(args.repo,args.resource,args.output,args.scratch),indent=2))
