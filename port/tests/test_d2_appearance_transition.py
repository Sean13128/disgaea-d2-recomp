"""Production delayed hub/battle probe against mocked native call boundaries."""
import os
from pathlib import Path
import shutil
import subprocess
import tempfile
import unittest
from test_d2_appearance_binding import HEADER

HARNESS=r'''
#include "warp.cpp"
#include <cassert>
uint8_t memory[0x800000]={};
uint64_t milliseconds=0;
unsigned frame=1,sets=0,drains=0,starts=0,messages=0;
void (*hook)(ppu_context*)=nullptr;
uint64_t d2_warp_test_milliseconds(){return milliseconds;}
extern "C" unsigned ppu_boot_frames_presented(){return frame;}
extern "C" int32_t cellPadGetData(uint32_t,CellPadData*){return 0;}
extern "C" void ps3_hle_register_ctx(uint32_t,const char*,void (*fn)(ppu_context*)){hook=fn;}
extern "C" uint64_t ppu_guest_call_ct(uint32_t code,uint32_t,uint64_t a,uint64_t b,uint64_t,uint64_t,uint64_t,uint64_t,uint64_t,uint64_t){
 if(code==0x33c48)return messages;
 if(code==0x2ebc8){assert(a==2);++sets;return 0;}
 if(code==0x295ef8){assert(sets==1);return 0;}
 if(code==0x33cbc){++drains;messages=1;return 0;}
 if(code==0x2e2e4){assert(a==0x100000 && b==0);vm_write16(a+0xd3bba,101);return 0;}
 if(code==0x1eb69c){assert(a==0);return 0;}
 assert(code==0x8f0fc && a==11 && b==0);++starts;return 0;
}
int main(int argc,char**){
 d2_register_debug_warp();
 if(argc>1){assert(!hook);return 0;}
 assert(hook);
 constexpr unsigned game=0x100000,graphics=0x200000,scene=0x500000,event=0x520000,camera=0x250000;
 vm_write32(D2_TOC-GAME_TOC,game);vm_write32(D2_TOC-GRAPHICS_TOC,graphics);vm_write32(D2_TOC-CAMERA_TOC,camera);
 vm_write32(D2_TOC-0x3fc4,scene);vm_write32(D2_TOC-0x37c8,event);vm_write32(scene+8,12);
 vm_write16(game+0xd3bba,30001);vm_write16(game+0x1507ec,1);
 vm_write16(game+0x598+0x1158,30);vm_write16(game+0x598+0x1202,2);
 vm_write16(game+0xd3bf0+0x28,101);
 ppu_context ctx;ctx.thread_id=2;hook(&ctx);assert(sets==0);
 ctx.thread_id=1;frame=1000;hook(&ctx);assert(sets==0);
 frame=1360;milliseconds=10000;hook(&ctx);assert(sets==1 && drains==0 && starts==0);
 frame=1600;milliseconds=84999;hook(&ctx);assert(sets==1 && drains==0 && starts==0);
 milliseconds=85000;hook(&ctx);assert(drains==1 && starts==0);
 hook(&ctx);assert(starts==0);messages=0;hook(&ctx);assert(starts==1);
 hook(&ctx);assert(starts==1 && sets==1 && drains==1);
}
'''
class TransitionTests(unittest.TestCase):
    def test_sequence_deadline_messages_thread_gate_and_conflicting_configuration(self):
        compiler=shutil.which('clang++') or shutil.which('c++')
        if not compiler:self.skipTest('Existing C++ compiler unavailable')
        with tempfile.TemporaryDirectory(prefix='d2-transition-',dir=os.path.realpath(tempfile.gettempdir())) as tmp:
            p=Path(tmp)
            (p/'ppu_recomp.h').write_text(HEADER+'\ninline void vm_write8(uint64_t a,unsigned v){assert(a<sizeof(memory));memory[a]=v;}\n')
            shutil.copyfile(Path(__file__).parents[1]/'src/d2_debug_warp.cpp',p/'warp.cpp')
            (p/'main.cpp').write_text(HARNESS)
            for version in (140,100):
                exe=p/f'test-{version}'
                subprocess.run([compiler,'-std=c++20','-DD2_WARP_TEST',f'-DD2_GAME_VERSION={version}',
                    '-I'+str(p),str(p/'main.cpp'),'-o',str(exe)],check=True,capture_output=True)
                env=dict(os.environ,D2_WARP_STAGE='1',D2_HUB_CHARACTER='30',D2_WARP_DELAY_SECONDS='85')
                if version==100:
                    subprocess.run([str(exe),'rejected'],env=env,check=True,capture_output=True);continue
                subprocess.run([str(exe)],env=env,check=True,capture_output=True)
                for delay in (None,'0','601','nan'):
                    check=dict(env)
                    if delay is None:check.pop('D2_WARP_DELAY_SECONDS')
                    else:check['D2_WARP_DELAY_SECONDS']=delay
                    subprocess.run([str(exe),'rejected'],env=check,check=True,capture_output=True)
                check=dict(env);check.pop('D2_WARP_STAGE')
                subprocess.run([str(exe),'rejected'],env=check,check=True,capture_output=True)
if __name__=='__main__':unittest.main()
