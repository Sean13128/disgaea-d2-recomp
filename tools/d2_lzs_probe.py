#!/usr/bin/env python3
"""Compare a dat-LZS stream with exact lifted 1.40 decode/copy functions.

CPU register/VM helpers are bounded harness code; the decoder, byte reversal
and optimized copy are the unmodified guest functions. No game execution.
"""
import argparse
import hashlib
import json
from pathlib import Path
import subprocess
import tempfile

from d2_appearance_probe import extract_function
from d2_character_export import _no_symlinks

PREFIX=r'''
#include <cassert>
#include <cstdint>
#include <cstring>
#include <fstream>
#include <iostream>
#include <iterator>
#include <vector>
static uint8_t mem[20*1024*1024];
struct ppu_context { uint64_t gpr[32]={}; uint32_t cr=0,ctr=0; uint64_t lr=0; };
static uint64_t readbe(uint64_t a,int n){assert(a+n<=sizeof(mem));uint64_t v=0;while(n--)v=(v<<8)|mem[a++];return v;}
static void writebe(uint64_t a,uint64_t v,int n){assert(a+n<=sizeof(mem));while(n){mem[a+--n]=v;v>>=8;}}
static uint64_t vm_read8(uint64_t a){return readbe(a,1);}
static uint64_t vm_read32(uint64_t a){return readbe(a,4);}
static uint64_t vm_read64(uint64_t a){return readbe(a,8);}
static void vm_write8(uint64_t a,uint64_t v){writebe(a,v,1);}
static void vm_write16(uint64_t a,uint64_t v){writebe(a,v,2);}
static void vm_write32(uint64_t a,uint64_t v){writebe(a,v,4);}
static void vm_write64(uint64_t a,uint64_t v){writebe(a,v,8);}
static uint64_t rol(uint64_t v,unsigned s){return s?(v<<s)|(v>>(64-s)):v;}
static uint64_t ppc_rldicl(uint64_t v,int sh,int mb){return rol(v,sh)&(~uint64_t(0)>>mb);}
static uint64_t ppc_rldicr(uint64_t v,int sh,int me){return rol(v,sh)&(~uint64_t(0)<<(63-me));}
static uint32_t ppc_rlwinm(uint32_t v,int sh,int mb,int me){
 uint32_t rotated=sh?((v<<sh)|(v>>(32-sh))):v;
 return rotated&((~uint32_t(0)>>mb)&(~uint32_t(0)<<(31-me)));
}
#define DRAIN_TRAMPOLINE(ctx) ((void)0)
void func_00161F34(ppu_context*);
void func_00335FE4(ppu_context*);
'''
SUFFIX=r'''
int main(int argc,char** argv){
 std::ifstream input(argv[1],std::ios::binary),reference(argv[2],std::ios::binary);
 std::vector<uint8_t> packed((std::istreambuf_iterator<char>(input)),{});
 std::vector<uint8_t> expected((std::istreambuf_iterator<char>(reference)),{});
 assert(packed.size()<=8*1024*1024 && expected.size()<=8*1024*1024);
 std::memcpy(mem+0x10000,packed.data(),packed.size());
 ppu_context c;c.gpr[1]=0x1100000;c.gpr[3]=0x10004;c.gpr[4]=0x810000;
 func_001840E0(&c);
 size_t first=0;while(first<expected.size() && mem[0x810000+first]==expected[first])++first;
 std::cout<<"{\"returned_bytes\":"<<c.gpr[3]<<",\"expected_bytes\":"<<expected.size()
          <<",\"first_difference\":"<<first<<",\"matches\":"
          <<(first==expected.size() && c.gpr[3]==expected.size()?"true":"false")<<"}\n";
}
'''


def probe(repo,packed,expected,scratch):
    repo=_no_symlinks(Path(repo).absolute());packed=_no_symlinks(Path(packed).absolute())
    expected=_no_symlinks(Path(expected).absolute());scratch=_no_symlinks(Path(scratch).absolute())
    if packed.stat().st_size>8*1024**2 or expected.stat().st_size>8*1024**2:
        raise ValueError('Probe inputs exceed 8 MiB')
    functions=[]
    for index,name in [('008','func_001840E0'),('007','func_00161F34'),('018','func_00335FE4')]:
        functions.append(extract_function(repo/f'port/src/recomp-140/ppu_recomp_{index}.cpp',name))
    scratch.mkdir(parents=True,exist_ok=True)
    with tempfile.TemporaryDirectory(prefix='lzs-native-',dir=scratch) as tmp:
        p=Path(tmp);code=p/'probe.cpp';binary=p/'probe';code.write_text(PREFIX+'\n'.join(functions)+SUFFIX)
        subprocess.run(['clang++','-std=c++17','-O1','-fsanitize=address,undefined',str(code),'-o',str(binary)],
                       check=True,capture_output=True)
        result=subprocess.run([str(binary),str(packed),str(expected)],check=True,capture_output=True,text=True)
    report=json.loads(result.stdout)
    report['guest_functions']=['001840E0','00161F34','00335FE4']
    report['packed_sha256']=hashlib.sha256(packed.read_bytes()).hexdigest()
    report['expected_sha256']=hashlib.sha256(expected.read_bytes()).hexdigest()
    return report


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--repo',type=Path,default=Path.cwd())
    parser.add_argument('--packed',type=Path,required=True)
    parser.add_argument('--expected',type=Path,required=True)
    parser.add_argument('--scratch',type=Path,required=True)
    args=parser.parse_args();result=probe(**vars(args));print(json.dumps(result,indent=2))
    raise SystemExit(0 if result['matches'] else 1)
