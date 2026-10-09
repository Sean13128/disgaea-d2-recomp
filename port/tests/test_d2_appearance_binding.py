"""Run production binding wrappers against a bounded, asset-free guest VM.

Mocks supply only original guest function boundaries. They do not duplicate
the binding logic. Whole-game loading and rendering remain separate checks.
"""
import json
import fcntl
import os
from pathlib import Path
import shutil
import subprocess
import tempfile
import unittest

HEADER = r'''
#pragma once
#include <cstdint>
#include <cassert>
struct ppu_context { uint64_t gpr[32]={},lr=0; unsigned thread_id=1; };
extern uint8_t memory[0x800000];
inline uint8_t vm_read8(uint64_t a){assert(a<sizeof(memory));return memory[a];}
inline uint16_t vm_read16(uint64_t a){return (vm_read8(a)<<8)|vm_read8(a+1);}
inline uint32_t vm_read32(uint64_t a){return (uint32_t(vm_read16(a))<<16)|vm_read16(a+2);}
inline void vm_write16(uint64_t a,unsigned v){assert(a+1<sizeof(memory));memory[a]=v>>8;memory[a+1]=v;}
inline void vm_write32(uint64_t a,unsigned v){vm_write16(a,v>>16);vm_write16(a+2,v);}
'''
HARNESS = r'''
#include "binding.cpp"
#include <cstring>
uint8_t memory[0x800000]={};
extern "C" uint64_t ppu_guest_call_ct(uint32_t,uint32_t,uint64_t,uint64_t,uint64_t,uint64_t,uint64_t,uint64_t,uint64_t,uint64_t){return 0;}
constexpr unsigned unit=0x80000,manager=0x20000,table=0x30000,descriptor=0x40000;
unsigned expected_alias=0;
void d2_appearance_original_illustration(ppu_context* c){c->gpr[3]=10030;}
void d2_appearance_original_color_preview(ppu_context*){}
void d2_appearance_original_face_coordinates(ppu_context* c){vm_write32(c->gpr[6],96*c->gpr[5]);vm_write32(c->gpr[7],192);c->gpr[3]=0;}
void d2_appearance_original_unit_face(ppu_context* c){
 ppu_context inner;inner.gpr[3]=0;inner.gpr[4]=30;inner.gpr[5]=c->gpr[10];inner.gpr[6]=0x5f000;inner.gpr[7]=0x5f004;
 func_00149E80(&inner);c->gpr[3]=vm_read32(0x5f000);c->gpr[4]=vm_read32(0x5f004);
}
void d2_appearance_original_class_face(ppu_context* c){d2_appearance_original_unit_face(c);}
void d2_appearance_original_class_face_alt(ppu_context* c){d2_appearance_original_unit_face(c);}
void d2_appearance_original_class_small_face(ppu_context* c){d2_appearance_original_unit_face(c);}
void d2_appearance_original_class_small_face_alt(ppu_context* c){d2_appearance_original_unit_face(c);}
void d2_appearance_original_unit_face_large(ppu_context* c){d2_appearance_original_unit_face(c);}
void d2_appearance_original_unit_panel_face(ppu_context* c){d2_appearance_original_unit_face(c);}
void d2_appearance_original_ui_face_draw(ppu_context* c){d2_appearance_original_unit_face(c);}
void d2_appearance_original_ui_face_record(ppu_context* c){vm_write16(c->gpr[3]+0x800,1);vm_write32(c->gpr[3]+4,c->gpr[5]);vm_write32(c->gpr[3]+8,c->gpr[6]);}
void d2_appearance_original_class_queued_face(ppu_context*) {
 ppu_context c;c.gpr[3]=0x63000;c.gpr[5]=0x64000;c.gpr[6]=0x65000;func_00193AC0(&c);
 vm_write32(0x65000,0x63000);vm_write32(0x65000+0x38,30);vm_write32(0x65000+0x3c,vm_read8(unit+0x1183));
}
void d2_appearance_original_class_queued_face_alt(ppu_context* c){d2_appearance_original_class_queued_face(c);}
void d2_appearance_original_unit_list_face(ppu_context* c){d2_appearance_original_unit_face(c);}
void d2_appearance_original_unit_list_face_alt(ppu_context* c){d2_appearance_original_unit_face(c);}
void d2_appearance_original_unit_small_face(ppu_context* c){d2_appearance_original_unit_face(c);}
void d2_appearance_original_unit_small_face_alt(ppu_context* c){d2_appearance_original_unit_face(c);}
void d2_appearance_original_select(ppu_context*){}
void d2_appearance_original_update(ppu_context*){}
void d2_appearance_original_record(ppu_context*){}
void d2_appearance_original_request(ppu_context*){}
void d2_appearance_original_file_size(ppu_context*){}
void d2_appearance_original_allocate(ppu_context*){}
void d2_appearance_original_file_read(ppu_context*){}
void d2_appearance_original_load_update(ppu_context*){}
void d2_appearance_original_model_select(ppu_context*){}
void d2_appearance_original_texture_bind(ppu_context*){}
void d2_appearance_original_write_body(ppu_context* c){vm_write16(c->gpr[3]+0x11d8+2*c->gpr[4],c->gpr[5]);}
void d2_appearance_original_read_body(ppu_context* c){c->gpr[3]=vm_read16(c->gpr[3]+0x11d8+2*c->gpr[4]);}
void d2_appearance_original_category(ppu_context* c){c->gpr[3]=(c->gpr[3]==30);}
void d2_appearance_original_body_kind(ppu_context* c){c->gpr[3]=(c->gpr[3]==30);}
void d2_appearance_original_motion(ppu_context* c){c->gpr[3]=vm_read16(c->gpr[4]+0x196)+4;}
void d2_appearance_original_visual(ppu_context* c){
 assert(c->gpr[4]==(expected_alias?30000:30));
 if(expected_alias){
  ppu_context inner;inner.gpr[3]=30000;inner.lr=0x299d4;func_00106E34(&inner);assert(inner.gpr[3]==1);
  inner.gpr[3]=30000;inner.lr=0x299f0;func_00106E84(&inner);assert(inner.gpr[3]==1);
  inner.gpr[3]=30000;inner.lr=0x1234;func_00106E84(&inner);assert(inner.gpr[3]==0);
  inner.gpr[4]=table+676;func_00016548(&inner);assert(inner.gpr[3]==34);
 }
}
int main(int argc,char** argv){
 bool renderer_only=std::strcmp(argv[1],"renderer")==0;
 bool enabled=std::strcmp(argv[1],"enabled")==0 || renderer_only;
 vm_write32(0x47df98-0x7e68,manager);vm_write16(manager,2);vm_write32(manager+4,table);
 vm_write16(table+0x194,30);vm_write16(table+0x196,30);vm_write16(table+0x1be,30000);
 vm_write16(table+676+0x194,30000);vm_write16(table+676+0x196,30000);vm_write16(table+676+0x1bc,30000);
 vm_write16(unit+0x1158,30);memory[unit+0x117a]=renderer_only?0:1;vm_write16(unit+0x11da,31);
 vm_write16(unit+0x1202,1);
 vm_write32(descriptor+0x1bc,unit);
 ppu_context c;c.gpr[3]=unit;c.gpr[4]=0;c.gpr[5]=30;func_00015A98(&c);
 assert(vm_read16(unit+0x11d8)==(enabled && !renderer_only?30000:30));assert(vm_read16(unit+0x11da)==31);
 c.gpr[3]=unit;c.gpr[4]=0;func_00015AB0(&c);assert(c.gpr[3]==(enabled && !renderer_only?30000:30));
 c.gpr[3]=unit;c.gpr[4]=1;func_00015AB0(&c);assert(c.gpr[3]==31);
 uint8_t snapshot[0x1a60];std::memcpy(snapshot,memory+unit,sizeof(snapshot));
 expected_alias=enabled;c.gpr[3]=descriptor;c.gpr[4]=30;func_00029804(&c);
 assert(std::memcmp(snapshot,memory+unit,sizeof(snapshot))==0);
 // Skill clone: only the verified copy callsite may use the saved source unit.
 vm_write32(descriptor+0x1bc,0);c.gpr[29]=unit;c.lr=0xa8fe0;
 c.gpr[3]=descriptor;c.gpr[4]=30;func_00029804(&c);
 assert(std::memcmp(snapshot,memory+unit,sizeof(snapshot))==0);
 // The temporary actor is reused: a link left by the previous actor (another
 // class) must not hide the saved source unit, nor be trusted elsewhere.
 constexpr unsigned other=0x90000;vm_write16(other+0x1158,31);vm_write16(other+0x1202,1);
 vm_write32(descriptor+0x1bc,other);
 c.gpr[3]=descriptor;c.gpr[4]=30;func_00029804(&c);
 assert(std::memcmp(snapshot,memory+unit,sizeof(snapshot))==0);
 expected_alias=0;c.lr=0xa8fb4;c.gpr[3]=descriptor;c.gpr[4]=30;func_00029804(&c);
 vm_write32(descriptor+0x1bc,0);
 expected_alias=0;c.lr=0xa8fb4;c.gpr[3]=descriptor;c.gpr[4]=30;func_00029804(&c);
 // The controlled castle actor can recover its source only along E83BC.
 constexpr unsigned game=unit-0x598,control=game-0x10,stack=0x50000;
 vm_write32(0x47df98-0x7ca4,control);vm_write32(0x47df98-0x4f48,game);vm_write16(game+0x1507ec,1);vm_write16(control+0x150aa6,1);
 vm_write32(stack+0xa0,0);vm_write32(stack+0xa4,0xe83f8);
 vm_write32(descriptor+0x3d8,2);vm_write16(descriptor+0x21c,30);
 c.gpr[1]=stack;c.lr=0xe836c;expected_alias=enabled && renderer_only;
 c.gpr[3]=descriptor;c.gpr[4]=30;func_00029804(&c);
 assert(std::memcmp(snapshot,memory+unit,sizeof(snapshot))==0);
 expected_alias=0;vm_write32(stack+0xa4,0x288988);
 c.gpr[3]=descriptor;c.gpr[4]=30;func_00029804(&c);
 vm_write32(stack+0xa4,0xe83f8);vm_write16(control+0x150aa6,2);
 c.gpr[3]=descriptor;c.gpr[4]=30;func_00029804(&c);
 vm_write16(control+0x150aa6,1);vm_write16(game+0x1507ec,129);
 c.gpr[3]=descriptor;c.gpr[4]=30;func_00029804(&c);
 vm_write16(game+0x1507ec,2);vm_write16(unit+0x1a60+0x1202,1);vm_write16(unit+0x1a60+0x1158,30);
 c.gpr[3]=descriptor;c.gpr[4]=30;func_00029804(&c);
 vm_write16(game+0x1507ec,1);vm_write32(descriptor+0x3d8,1);
 c.gpr[3]=descriptor;c.gpr[4]=30;func_00029804(&c);
 vm_write32(descriptor+0x3d8,2);vm_write16(control+0x150aa6,0x8000);vm_write16(unit+0x1202,0x8000);
 c.gpr[3]=descriptor;c.gpr[4]=30;func_00029804(&c);
 vm_write16(unit+0x1202,1);
 vm_write16(control+0x150aa6,1);vm_write16(descriptor+0x21c,31);
 c.gpr[3]=descriptor;c.gpr[4]=30;func_00029804(&c);
 vm_write32(descriptor+0x1bc,unit);
 // Category inheritance cannot escape the constructor scope.
 c.gpr[3]=30000;c.lr=0x299f0;func_00106E84(&c);assert(c.gpr[3]==0);
 expected_alias=enabled && renderer_only;memory[unit+0x117a]=0;c.gpr[3]=descriptor;c.gpr[4]=30;func_00029804(&c);
 expected_alias=0;
 memory[unit+0x117a]=1;vm_write16(unit+0x115c,2);c.gpr[3]=descriptor;c.gpr[4]=30;func_00029804(&c);
 expected_alias=enabled && renderer_only;
 vm_write16(unit+0x115c,0);vm_write16(table+0x1be,30001);c.gpr[3]=descriptor;c.gpr[4]=30;func_00029804(&c);
 // Independent aliases must still name the selected body in both fields.
 expected_alias=0;vm_write16(table+676+0x1bc,30001);
 c.gpr[3]=descriptor;c.gpr[4]=30;func_00029804(&c);
}
'''


SESSION_HARNESS = HARNESS.split('void d2_appearance_original_visual')[0] + r'''
#include <thread>
#include <atomic>
unsigned expected_resource=0;
bool mutate_during_constructor=false;
void d2_appearance_original_visual(ppu_context* c){
 assert(c->gpr[4]==(expected_resource?expected_resource:30));
 if (!expected_resource) return;
 // A selection changed during construction must not change its scoped resource.
 if(mutate_during_constructor)
  assert(select_session_costume(30,"",binding_generation()));
 ppu_context inner;inner.gpr[3]=expected_resource;inner.lr=0x299d4;
 func_00106E34(&inner);assert(inner.gpr[3]==1);
 inner.gpr[4]=table+(expected_resource==30000?1:2)*676;
 func_00016548(&inner);assert(inner.gpr[3]==34);
 inner.gpr[3]=0x60000;inner.gpr[4]=1;inner.gpr[5]=1001;inner.lr=0x29348;func_002E89D8(&inner);
 inner.gpr[3]=0x60000;inner.gpr[4]=0;inner.gpr[5]=1;inner.gpr[6]=expected_resource;inner.lr=0x293ac;func_002E8D78(&inner);
}
int main(int argc,char**){
 if(argc>1){assert(!binding_for(30));return 0;}
 vm_write32(0x47df98-0x7e68,manager);vm_write16(manager,3);vm_write32(manager+4,table);
 vm_write16(table+0x194,30);vm_write16(table+0x196,30);vm_write16(table+0x1be,31);
 for(unsigned i=1;i<3;++i){
  unsigned row=table+i*676,resource=29999+i;
  vm_write16(row+0x194,resource);vm_write16(row+0x196,resource);vm_write16(row+0x1bc,resource);
 }
 vm_write16(unit+0x1158,30);vm_write16(unit+0x11d8,30);vm_write16(unit+0x11da,31);
 vm_write32(descriptor+0x1bc,unit);
 uint8_t snapshot[0x1a60];std::memcpy(snapshot,memory+unit,sizeof(snapshot));
 ppu_context c;
 auto construct=[&](unsigned resource){expected_resource=resource;c.gpr[3]=descriptor;c.gpr[4]=30;func_00029804(&c);};
 // A separately loaded portrait must be observed outside the body constructor.
 for(unsigned i=0;i<2;++i){
  ppu_context portrait;portrait.gpr[3]=0x70000+i*0x1000;portrait.gpr[4]=2;
  portrait.gpr[5]=1;portrait.gpr[6]=10030+i;portrait.lr=0x1234;
  auto before=portrait;func_002E8D78(&portrait);
  assert(std::memcmp(before.gpr,portrait.gpr,sizeof(portrait.gpr))==0);
  portrait.gpr[4]=8100;portrait.gpr[5]=0;func_002E89D8(&portrait);
 }
 for(unsigned i=0;i<3;++i){
  unsigned ids[]={10030,40030,99997};
  ppu_context library;library.gpr[3]=0x72000+i*0x1000;library.gpr[4]=ids[i];library.gpr[5]=8000;library.lr=0x29348;
  auto library_before=library;func_002E89D8(&library);
  assert(std::memcmp(library_before.gpr,library.gpr,sizeof(library.gpr))==0);
 }
 construct(30000);
 // Assembly/color preview actors have no unit, but an explicit requested class.
 vm_write32(descriptor+0x1bc,0);
 for(unsigned caller:{0x36108u,0x382b8u,0x2a274u}) {
  expected_resource=30000;ppu_context preview;preview.gpr[3]=descriptor;preview.gpr[4]=30;preview.lr=caller;
  func_00029804(&preview);assert(active_visual.resource==0);
  vm_write16(table+676+0x1bc,30001);expected_resource=0;
  preview.gpr[3]=descriptor;preview.gpr[4]=30;func_00029804(&preview);
  vm_write16(table+676+0x1bc,30000);
 }
 {expected_resource=0;ppu_context preview;preview.gpr[3]=descriptor;preview.gpr[4]=30;preview.lr=0x1234;func_00029804(&preview);}
 vm_write32(descriptor+0x1bc,unit);
 auto picture=[&](){uint8_t before[0x1a60];std::memcpy(before,memory+unit,sizeof(before));ppu_context p;p.gpr[3]=unit;func_00109350(&p);assert(std::memcmp(before,memory+unit,sizeof(before))==0);return p.gpr[3];};
 assert(picture()==10901);
 vm_write16(table+0x19e,30);vm_write32(0x47df98-0x47f0,0x60000);vm_write32(0x60000,0x61000);
 vm_write16(0x61000+0x2c,480);vm_write16(0x61000+0x2e,192);
 auto face=[&](bool expected){uint8_t before[0x1a60];std::memcpy(before,memory+unit,sizeof(before));ppu_context f;f.gpr[9]=unit;func_0015ACDC(&f);assert(f.gpr[3]==(expected?384:0));assert(f.gpr[4]==(expected?0:192));assert(face_unit==0);assert(std::memcmp(before,memory+unit,sizeof(before))==0);};
 face(true);
 // All five native colors route by explicit class. Extra color 4 cannot
 // accidentally display the costume at x=384 in another character's row.
 for(auto draw:{func_0015B22C,func_0015B390,func_0015B4EC,func_0015B5E0}) {
  for(unsigned color=0;color<=4;++color) {
   ppu_context f;f.gpr[9]=30;f.gpr[10]=color;draw(&f);
   assert(f.gpr[3]==384 && f.gpr[4]==0 && face_class==0 && face_unit==0);
  }
  ppu_context f;f.gpr[9]=31;f.gpr[10]=4;draw(&f);assert(f.gpr[3]==0 && f.gpr[4]==192);
 }
 auto raw_color=[&](unsigned group){ppu_context f;f.gpr[3]=group;f.gpr[4]=31;f.gpr[5]=4;f.gpr[6]=0x5f000;f.gpr[7]=0x5f004;func_00149E80(&f);return vm_read32(0x5f000);};
 assert(raw_color(0)==0);assert(raw_color(1)==384);
 vm_write16(0x61000+0x2c,384);assert(raw_color(0)==384);vm_write16(0x61000+0x2c,480);
 {ppu_context panel;panel.gpr[6]=unit;func_0015CCAC(&panel);assert(panel.gpr[3]==384 && panel.gpr[4]==0 && face_unit==0);}
 {ppu_context f;f.gpr[7]=unit;func_0007C550(&f);assert(f.gpr[3]==384 && f.gpr[4]==0 && face_unit==0);}
 vm_write32(0x64000,0x001964c0);
 {ppu_context queue;queue.gpr[9]=30;func_0019E544(&queue);assert(face_class==0);}
 auto queued=[&](bool expected){uint8_t before[0x1a60];std::memcpy(before,memory+unit,sizeof(before));ppu_context draw;draw.gpr[3]=0x65000;func_001964C0(&draw);assert(draw.gpr[3]==(expected?384:0));assert(draw.gpr[4]==(expected?0:192));assert(face_unit==0);assert(std::memcmp(before,memory+unit,sizeof(before))==0);};
 queued(true);
 vm_write16(table+676+0x1bc,30001);queued(false);vm_write16(table+676+0x1bc,30000);
 vm_write16(0x61000+0x2c,384);queued(false);vm_write16(0x61000+0x2c,480);
 {FaceClassScope outer(30);{FaceClassScope inner(31);assert(face_class==31);}assert(face_class==30);}
 assert(face_class==0);
 vm_write16(table+0x19e,31);queued(false);vm_write16(table+0x19e,30);
 vm_write32(0x65000+0x38,10);queued(false);vm_write32(0x65000+0x38,30);
 vm_write32(0x63000+4,0);queued(false);vm_write32(0x63000+4,0x64000);
 {ppu_context replacement;replacement.gpr[3]=0x63000;replacement.gpr[5]=0x64000;replacement.gpr[6]=0x65000;func_00193AC0(&replacement);}
 queued(false); // Unscoped record reuse must clear the earlier class link.
 {ppu_context queue;queue.gpr[9]=31;func_0019E6A8(&queue);}queued(false);
 {ppu_context queue;queue.gpr[9]=30;func_0019E6A8(&queue);}queued(true);
 
 assert(face_for(unit,1,30)[2]==0);assert(face_for(unit,0,31)[2]==0);
 vm_write16(0x61000+0x2c,384);face(false);vm_write16(0x61000+0x2c,480);
 vm_write16(unit+0x115c,9);face(false);vm_write16(unit+0x115c,0);
 { FaceScope outer(unit);{FaceScope inner(0);assert(face_unit==0);}assert(face_unit==unit); }
 assert(face_unit==0);
 assert(illustration_for(unit,10031)==10031);
 vm_write16(unit+0x115c,9);assert(picture()==10030);vm_write16(unit+0x115c,0);
 // Disabling a costume with an assigned face must fall back without dropping its catalog cell.
 assert(select_session_costume(30,"",binding_generation()));face(false);queued(false);
 assert(select_session_costume(30,"first",binding_generation()));face(true);queued(true);
 assert(!face_for_class(30,1,30)[2]);assert(!face_for_class(31,0,30)[2]);
 auto initial=binding_generation();
 assert(!select_session_costume(30,"unknown",initial));
 assert(!select_session_costume(31,"second",initial));
 assert(binding_generation()==initial);
 assert(select_session_costume(30,"second",initial));construct(30001);assert(picture()==10030);face(false);
 assert(!select_session_costume(30,"first",initial));construct(30001);
 assert(select_session_costume(30,"",binding_generation()));construct(0);assert(picture()==10030);face(false);
 assert(select_session_costume(30,"first",binding_generation()));
 mutate_during_constructor=true;construct(30000);mutate_during_constructor=false;construct(0);
 // Registry readers can run concurrently with selection without escaping refs.
 std::atomic<bool> done=false;
 std::thread reader([&]{while(!done){auto b=binding_for(30);assert(b && (b->resource==30000 || b->resource==30001));}});
 for(unsigned i=0;i<10000;++i)
  assert(select_session_costume(30,i%2?"first":"second",binding_generation()));
 done=true;reader.join();
 assert(std::memcmp(snapshot,memory+unit,sizeof(snapshot))==0);
 assert(vm_read16(table+0x1be)==31);
}
'''


LIVE_HARNESS = SESSION_HARNESS.split('int main')[0].replace(
 'extern "C" uint64_t ppu_guest_call_ct(uint32_t,uint32_t,uint64_t,uint64_t,uint64_t,uint64_t,uint64_t,uint64_t,uint64_t,uint64_t){return 0;}', '') + r'''
unsigned rebuilds=0,messages=0;bool damage_position=false;
extern "C" uint64_t ppu_guest_call_ct(uint32_t code,uint32_t,uint64_t actor,uint64_t,uint64_t,uint64_t,uint64_t,uint64_t,uint64_t,uint64_t){
 if(code==0x33c48)return messages;
 assert(actor==descriptor);
 if(code==0xe849c){vm_write32(actor+0x3d8,0);vm_write16(actor+0x21c,0);return 0;}
 assert(code==0xe83bc);++rebuilds;
 vm_write32(actor+0x3d8,2);vm_write16(actor+0x21c,30);
 ppu_context c;c.gpr[3]=actor;c.gpr[4]=30;func_00029804(&c);vm_write16(actor+0x21c,c.gpr[4]);if(damage_position)vm_write32(actor+4,0);return 0;
}
int main(){
 constexpr unsigned party=unit-0x598,control=party-0x10,scene=0x60000,event=0x62000,camera=0x68000;
 vm_write32(0x47df98-0x7e68,manager);vm_write16(manager,3);vm_write32(manager+4,table);
 vm_write16(table+0x194,30);vm_write16(table+0x196,30);vm_write16(table+0x1be,31);
 for(unsigned i=1;i<3;++i){unsigned row=table+i*676,id=29999+i;
  vm_write16(row+0x194,id);vm_write16(row+0x196,id);vm_write16(row+0x1bc,id);}
 vm_write16(unit+0x1158,30);vm_write16(unit+0x1202,1);vm_write16(unit+0x11d8,30);vm_write16(unit+0x11da,31);
 vm_write32(descriptor+0x1bc,unit);vm_write32(descriptor+0x1a4,1);vm_write32(descriptor+0x3d8,2);vm_write16(descriptor+0x21c,30000);
 for(unsigned i=0;i<4;++i)vm_write32(descriptor+4+i*4,0x12300000+i);
 vm_write32(0x47df98-0x4f48,party);vm_write32(0x47df98-0x7ca4,control);
 vm_write32(0x47df98-0x3794,camera);vm_write32(camera+0x1f00,0x44556677);vm_write32(camera+0x1f04,0x55667788);
 vm_write32(0x47df98-0x3fc4,scene);vm_write32(0x47df98-0x37c8,event);vm_write32(0x47df98-0xfc0,descriptor);
 vm_write16(party+0x1507ec,1);vm_write16(control+0x150aa6,1);vm_write16(party+0xd3bba,30001);vm_write32(scene+8,12);
 uint8_t saved[0x1a60];std::memcpy(saved,memory+unit,sizeof saved);
 ppu_context ctx;D2AppearanceSnapshot snapshot;
 auto tick=[&](int ready=1){d2_appearance_frame(&ctx,ready);d2_appearance_snapshot(&snapshot);};
 tick();assert(snapshot.ready && snapshot.count==3 && snapshot.class_id==30 && snapshot.active==1);
 assert(!d2_appearance_request(31,"second",snapshot.generation));
 assert(!d2_appearance_request(30,"unknown",snapshot.generation));
 assert(d2_appearance_request(30,"second",snapshot.generation));
 assert(!d2_appearance_request(30,"first",snapshot.generation));
 tick(0);assert(!snapshot.ready && rebuilds==0);tick();
 auto stale=snapshot.generation;messages=1;tick();assert(!snapshot.ready);messages=0;tick();
 assert(!d2_appearance_request(30,"second",stale));
 assert(d2_appearance_request(30,"second",snapshot.generation));expected_resource=30001;tick();
 assert(rebuilds==1 && snapshot.ready && snapshot.active==2);
 assert(d2_appearance_request(30,"",snapshot.generation));expected_resource=0;tick();
 assert(rebuilds==2 && snapshot.active==0);
 assert(d2_appearance_request(30,"first",snapshot.generation));expected_resource=30000;tick();
 assert(rebuilds==3 && snapshot.active==1);
 // Queued requests expire on map transition, duplicate identity or event entry.
 assert(d2_appearance_request(30,"second",snapshot.generation));vm_write16(party+0xd3bba,101);tick();
 assert(!snapshot.ready && rebuilds==3);vm_write16(party+0xd3bba,30001);tick();
 assert(d2_appearance_request(30,"second",snapshot.generation));vm_write32(event+0x13314,1);tick();
 assert(!snapshot.ready && rebuilds==3);vm_write32(event+0x13314,0);tick();
 assert(d2_appearance_request(30,"second",snapshot.generation));vm_write16(party+0x1507ec,2);
 vm_write16(unit+0x1a60+0x1202,1);tick();assert(!snapshot.ready && rebuilds==3);
 vm_write16(party+0x1507ec,1);tick();
 assert(d2_appearance_request(30,"second",snapshot.generation));vm_write16(table+2*676+0x1bc,30002);tick();
 assert(rebuilds==3 && snapshot.active==1);vm_write16(table+2*676+0x1bc,30001);
 // Wrong thread cannot consume the pending action or publish new state.
 assert(d2_appearance_request(30,"second",snapshot.generation));ctx.thread_id=2;tick();assert(rebuilds==3);
 ctx.thread_id=1;expected_resource=30001;tick();assert(rebuilds==4);
 assert(std::memcmp(saved,memory+unit,sizeof saved)==0);
 for(unsigned i=0;i<4;++i)assert(vm_read32(descriptor+4+i*4)==0x12300000+i);
 assert(d2_appearance_request(30,"",snapshot.generation));expected_resource=0;damage_position=true;tick();
 assert(!snapshot.ready && std::strstr(snapshot.status,"protected state"));
 assert(!d2_appearance_request(30,"first",snapshot.generation));
}
'''


PERSIST_HARNESS = SESSION_HARNESS.split('int main')[0] + r'''
int main(int argc,char**){
 assert(persistent_choices());
 auto path=std::getenv("D2_APPEARANCE_PERSIST_PATH");
 if(argc>1){assert(!persist_choice(30,"second"));return 0;}
 auto load=[&](){std::ifstream f(path);return nlohmann::json::parse(f);};
 auto store=[&](const auto& data){std::ofstream f(path);f<<data.dump(2)<<"\n";};
 assert(persist_choice(30,"second"));auto data=load();
 assert(data.at("appearances")[0].at("costume_id")=="second");
 assert(!data["appearances"][0].contains("illustration_resource"));
 assert(!data["appearances"][0].contains("face_cell"));
 // Another character's external selection and unrelated metadata are preserved.
 data["appearances"][1]["enabled"]=false;data["unrelated"]["keep"]="external update";store(data);
 assert(persist_choice(30,""));data=load();
 assert(data["appearances"][0]["enabled"]==false && data["appearances"][0]["costume_id"]=="second");
 assert(data["appearances"][1]["enabled"]==false && data["unrelated"]["keep"]=="external update");
 assert(persist_choice(30,"first"));data=load();
 assert(data["appearances"][0]["enabled"]==true && data["appearances"][0]["costume_id"]=="first");
 assert(data["appearances"][0]["illustration_resource"]==10901);
 assert(data["appearances"][0]["face_cell"]["x"]==384);
 data["appearances"][0]["enabled"]=false;store(data);
 auto external=data;
 assert(!persist_choice(30,"second"));assert(load()==external);
}
'''


class NativeBindingTests(unittest.TestCase):
    def test_private_roots_selection_identity_and_scoped_motion(self):
        compiler=shutil.which('clang++') or shutil.which('c++')
        includes=[Path('/opt/homebrew/include'),Path('/usr/local/include'),Path('/usr/include')]
        include=next((p for p in includes if (p/'nlohmann/json.hpp').exists()),None)
        if not compiler or not include:self.skipTest('C++ compiler or existing nlohmann header unavailable')
        with tempfile.TemporaryDirectory(prefix='d2-native-binding-') as tmp:
            p=Path(tmp)
            (p/'ppu_recomp.h').write_text(HEADER)
            for name in ('d2_appearance.h','d2_appearance_live.inc','d2_appearance_persist.inc'):
                shutil.copyfile(Path(__file__).parents[1]/'src'/name,p/name)
            shutil.copyfile(Path(__file__).parents[1]/'src/d2_appearance_trace.cpp',p/'binding.cpp')
            (p/'main.cpp').write_text(HARNESS)
            subprocess.run([compiler,'-std=c++20','-DD2_APPEARANCE_IMPORTER=1','-I'+str(include),
                            '-I'+str(p),str(p/'main.cpp'),'-o',str(p/'test')],check=True,capture_output=True)
            roots={k:str(p/k) for k in ('PS3_VFS_ROOT','PS3_HDD0_ROOT','PS3_HDD1_ROOT')}
            for root in roots.values():Path(root).mkdir()
            manifest=p/'stage.json';manifest.write_text(json.dumps(dict(mode='isolated-runtime-experiment',
                class_id=30,selector=1,new_resource=30000,visual_class_id=30000,runtime_environment=roots)))
            env=dict(os.environ,**roots,D2_APPEARANCE_MANIFEST=str(manifest));env.pop('D2_APPEARANCE_TRACE',None)
            subprocess.run([str(p/'test'),'enabled'],env=env,check=True,capture_output=True)
            data=json.loads(manifest.read_text());data['selection_mode']='renderer-only'
            manifest.write_text(json.dumps(data))
            subprocess.run([str(p/'test'),'renderer'],env=env,check=True,capture_output=True)
            data['enabled']=False;manifest.write_text(json.dumps(data))
            subprocess.run([str(p/'test'),'disabled'],env=env,check=True,capture_output=True)
            data.pop('enabled')
            data['selection_mode']='unknown';manifest.write_text(json.dumps(data))
            subprocess.run([str(p/'test'),'disabled'],env=env,check=True,capture_output=True)
            data['selection_mode']='selector';manifest.write_text(json.dumps(data))
            env['PS3_HDD0_ROOT']=str(p/'wrong-root')
            subprocess.run([str(p/'test'),'disabled'],env=env,check=True,capture_output=True)
            env.pop('D2_APPEARANCE_MANIFEST')
            subprocess.run([str(p/'test'),'disabled'],env=env,check=True,capture_output=True)
            subprocess.run([compiler,'-std=c++20','-DD2_APPEARANCE_IMPORTER=0','-I'+str(p),
                            str(p/'main.cpp'),'-o',str(p/'disabled')],check=True,capture_output=True)
            env.update(roots);env['D2_APPEARANCE_MANIFEST']=str(manifest)
            subprocess.run([str(p/'disabled'),'disabled'],env=env,check=True,capture_output=True)

    def check_session_harness(self,harness,invalid_catalogs=True,color_slots=None):
        compiler=shutil.which('clang++') or shutil.which('c++')
        includes=[Path('/opt/homebrew/include'),Path('/usr/local/include'),Path('/usr/include')]
        include=next((p for p in includes if (p/'nlohmann/json.hpp').exists()),None)
        if not compiler or not include:self.skipTest('C++ compiler or existing nlohmann header unavailable')
        with tempfile.TemporaryDirectory(prefix='d2-session-binding-') as tmp:
            p=Path(tmp)
            (p/'ppu_recomp.h').write_text(HEADER)
            for name in ('d2_appearance.h','d2_appearance_live.inc','d2_appearance_persist.inc'):
                shutil.copyfile(Path(__file__).parents[1]/'src'/name,p/name)
            shutil.copyfile(Path(__file__).parents[1]/'src/d2_appearance_trace.cpp',p/'binding.cpp')
            (p/'main.cpp').write_text(harness)
            subprocess.run([compiler,'-std=c++20','-DD2_APPEARANCE_IMPORTER=1','-I'+str(include),
                            '-I'+str(p),str(p/'main.cpp'),'-o',str(p/'test')],check=True,capture_output=True)
            roots={k:str(p/k) for k in ('PS3_VFS_ROOT','PS3_HDD0_ROOT','PS3_HDD1_ROOT')}
            for root in roots.values():Path(root).mkdir()
            first=dict(class_id=30,selector=1,new_resource=30000,visual_class_id=30000,
                       selection_mode='renderer-only',costume_id='first',display_name='First costume',illustration_resource=10901,illustration_donor=10030,face_cell=dict(x=384,y=0,width=480,height=192,donor=30))
            second=dict(first,new_resource=30001,visual_class_id=30001,costume_id='second');second.pop('illustration_resource',None);second.pop('illustration_donor',None);second.pop('face_cell',None)
            data=dict(mode='isolated-runtime-experiment',runtime_environment=roots,
                      appearances=[first],costumes=[first,second])
            if color_slots is not None:data['color_slots']=color_slots
            manifest=p/'stage.json';manifest.write_text(json.dumps(data))
            before=manifest.read_bytes()
            env=dict(os.environ,**roots,D2_APPEARANCE_MANIFEST=str(manifest));env.pop('D2_APPEARANCE_TRACE',None)
            subprocess.run([str(p/'test')],env=env,check=True,capture_output=True)
            self.assertEqual(before,manifest.read_bytes())
            if not invalid_catalogs:return
            observed=subprocess.run([str(p/'test')],env=dict(env,D2_APPEARANCE_TRACE='30000'),check=True,capture_output=True,text=True)
            self.assertIn('model_select model=00060000 library=1',observed.stderr)
            self.assertIn('texture_bind model=00060000 group=0 flags=1 resource=30001',observed.stderr)
            portraits=subprocess.run([str(p/'test')],env=dict(env,D2_APPEARANCE_TRACE='10030'),check=True,capture_output=True,text=True)
            self.assertIn('texture_bind model=00070000 group=2 flags=1 resource=10030',portraits.stderr)
            self.assertIn('model_select model=00070000 library=8100',portraits.stderr)
            self.assertNotIn('model=00071000',portraits.stderr)
            self.assertIn('model_select model=00072000 library=10030 variant=8000',portraits.stderr)
            for resource,model in ((40030,'00073000'),(99997,'00074000')):
                high=subprocess.run([str(p/'test')],env=dict(env,D2_APPEARANCE_TRACE=str(resource)),check=True,capture_output=True,text=True)
                self.assertIn(f'model_select model={model} library={resource} variant=8000',high.stderr)
            # Invalid catalogs fail closed instead of silently exposing bad choices.
            for catalog in ([first,first],[],[dict(first,costume_id='../bad')],
                            [dict(first,class_id=31)],[dict(first,selection_mode='selector')],
                            [second],[first]*129,[first,dict(second,new_resource=30000)],
                            [first,dict(second,visual_class_id=30000)],[dict(first,costume_id='-bad')],[dict(first,display_name='bad\nname')],[dict(first,display_name='x'*128)],[dict(first,new_resource=30000+2**32)],
                            [dict(first,selector=1+2**32)],[dict(first,visual_class_id=True)], [dict(first,illustration_resource=True)],[dict(first,illustration_donor=9999)], [dict(first,illustration_resource=10901+2**32)], [dict(first,illustration_resource=10030)],
                            [dict(first,face_cell=dict(first['face_cell'],x=True))], [dict(first,face_cell=dict(first['face_cell'],x=0))],
                            [dict(first,face_cell=dict(first['face_cell'],donor=500))], [dict(first,face_cell=dict(first['face_cell'],width=2**32+480))],
                            [first,dict(second,face_cell=first['face_cell'])]):
                manifest.write_text(json.dumps(dict(data,costumes=catalog)))
                subprocess.run([str(p/'test'),'rejected'],env=env,check=True,capture_output=True)

    def test_native_colors_select_independent_costumes_without_unit_writes(self):
        harness=SESSION_HARNESS.split('int main')[0]+r'''
int main(){
 vm_write32(0x47df98-0x7e68,manager);vm_write16(manager,3);vm_write32(manager+4,table);
 vm_write16(table+0x194,30);vm_write16(table+0x196,30);vm_write16(table+0x19e,30);
 for(unsigned i=1;i<3;++i){unsigned row=table+i*676,id=29999+i;vm_write16(row+0x194,id);vm_write16(row+0x196,id);vm_write16(row+0x1bc,id);}
 vm_write16(unit+0x1158,30);vm_write32(descriptor+0x1bc,unit);
 vm_write32(0x47df98-0x47f0,0x60000);vm_write32(0x60000,0x61000);
 vm_write16(0x61000+0x2c,480);vm_write16(0x61000+0x2e,192);
 for(unsigned color=0;color<6;++color){
  memory[unit+0x1183]=color;uint8_t before[0x1a60];memcpy(before,memory+unit,sizeof(before));
  unsigned expected=color==1?30000:color==2?30001:0;
  expected_resource=expected;ppu_context c;c.gpr[3]=descriptor;c.gpr[4]=30;c.lr=0x1234;func_00029804(&c);
  assert(illustration_for(unit,10030)==(color==1?10901:10030));
  assert(face_for(unit,0,30)[2]==(color==1?480:0));
  assert(memcmp(before,memory+unit,sizeof(before))==0);
  // Explicit menu color must beat a descriptor linked to a different saved color.
  for(unsigned preview=0;preview<5;++preview){
   expected_resource=preview==1?30000:preview==2?30001:0;
   c.gpr[3]=descriptor;c.gpr[4]=30;c.gpr[5]=preview;c.lr=0x2a274;func_00029804(&c);
   assert(face_for_class(30,0,30,preview)[2]==(preview==1?480:0));
  }
 }
 // Generic list rows (Choose Color) look a face up with no unit or class: the
 // face identity and color alone select the slot's icon, and nothing else does.
 auto bare=[&](unsigned group,unsigned face,unsigned color){ppu_context f;f.gpr[3]=group;f.gpr[4]=face;f.gpr[5]=color;f.gpr[6]=0x5f000;f.gpr[7]=0x5f004;f.lr=0x15ae54;
  vm_write32(0x5f000,0xdead);vm_write32(0x5f004,0xdead);func_00149E80(&f);return std::pair<unsigned,unsigned>(vm_read32(0x5f000),vm_read32(0x5f004));};
 using cell=std::pair<unsigned,unsigned>;
 assert(bare(0,30,1)==cell(384,0));
 // Unassigned choices, a costume without an icon, other groups and other faces stay retail.
 assert(bare(0,30,0)==cell(0,192) && bare(0,30,2)==cell(192,192) && bare(0,30,3)==cell(288,192) && bare(0,30,4)==cell(0,192));
 assert(bare(1,30,1)==cell(96,192) && bare(0,31,1)==cell(96,192));
 assert(color_slot_class_for_face(0,30)==30 && !color_slot_class_for_face(1,30) && !color_slot_class_for_face(0,31));
 // An appended costume row copies its donor's face; it is not slot-managed and must not make the face ambiguous.
 vm_write16(table+2*676+0x19e,30);assert(color_slot_class_for_face(0,30)==30);
 assert(!binding_for_color(31,1));
 assert(select_session_costume(30,"",binding_generation()));
 assert(binding_for_color(30,1)->resource==30000); // Interim picker cannot override native slots.
}
'''
        self.check_session_harness(harness,False,[dict(class_id=30,color=1,costume_id='first'),dict(class_id=30,color=2,costume_id='second')])

    def test_session_catalog_switches_stale_requests_and_constructor_snapshot(self):
        self.check_session_harness(SESSION_HARNESS)

    def test_live_queue_scene_guards_and_actor_refresh(self):
        self.check_session_harness(LIVE_HARNESS,False)

    def test_persistence_preserves_other_classes_and_rejects_conflicts_locks_symlinks(self):
        compiler=shutil.which('clang++') or shutil.which('c++')
        include=Path('/opt/homebrew/include')
        if not compiler or not (include/'nlohmann/json.hpp').exists():self.skipTest('Existing C++ dependencies unavailable')
        with tempfile.TemporaryDirectory(prefix='d2-persist-binding-',dir=os.path.realpath(tempfile.gettempdir())) as tmp:
            p=Path(tmp)
            (p/'ppu_recomp.h').write_text(HEADER)
            for name in ('d2_appearance.h','d2_appearance_live.inc','d2_appearance_persist.inc'):
                shutil.copyfile(Path(__file__).parents[1]/'src'/name,p/name)
            shutil.copyfile(Path(__file__).parents[1]/'src/d2_appearance_trace.cpp',p/'binding.cpp')
            (p/'main.cpp').write_text(PERSIST_HARNESS)
            subprocess.run([compiler,'-std=c++20','-DD2_APPEARANCE_IMPORTER=1','-I'+str(include),
                '-I'+str(p),str(p/'main.cpp'),'-o',str(p/'test')],check=True,capture_output=True)
            roots={k:str(p/k) for k in ('PS3_VFS_ROOT','PS3_HDD0_ROOT','PS3_HDD1_ROOT')}
            for root in roots.values():Path(root).mkdir()
            first=dict(class_id=30,selector=1,new_resource=30000,visual_class_id=30000,selection_mode='renderer-only',costume_id='first',illustration_resource=10901,illustration_donor=10030,face_cell=dict(x=384,y=0,width=480,height=192,donor=30))
            second=dict(first,new_resource=30001,visual_class_id=30001,costume_id='second');second.pop('illustration_resource',None);second.pop('illustration_donor',None);second.pop('face_cell')
            other=dict(first,class_id=410,new_resource=31000,visual_class_id=31000,costume_id='other');other.pop('illustration_resource');other.pop('illustration_donor');other.pop('face_cell')
            data=dict(mode='isolated-runtime-experiment',runtime_environment=roots,appearances=[first,other],
                      costumes=[first,second,other],unrelated=dict(keep='original'))
            snapshot=p/'snapshot.json';snapshot.write_text(json.dumps(data));path=p/'stage.json';path.write_text(json.dumps(data))
            save=Path(roots['PS3_HDD0_ROOT'])/'save';save.write_bytes(b'gameplay save')
            env=dict(os.environ,**roots,D2_APPEARANCE_MANIFEST=str(snapshot),D2_APPEARANCE_PERSIST='1',D2_APPEARANCE_PERSIST_PATH=str(path))
            env.pop('D2_APPEARANCE_TRACE',None)
            subprocess.run([str(p/'test')],env=env,check=True,capture_output=True)
            self.assertEqual(save.read_bytes(),b'gameplay save');self.assertEqual(json.loads(snapshot.read_text()),data)
            self.assertEqual(list(p.glob('.appearance-choice-*')),[])
            # Locked choice, symlink target, symlink lock, and external path fail closed.
            path.write_text(json.dumps(data));before=path.read_bytes()
            lock=p/'.appearance-choice.lock'
            with lock.open('a') as stream:
                fcntl.flock(stream.fileno(),fcntl.LOCK_EX)
                subprocess.run([str(p/'test'),'rejected'],env=env,check=True,capture_output=True)
            self.assertEqual(path.read_bytes(),before)
            outside=p/'other-directory';outside.mkdir();target=outside/'stage.json';target.write_bytes(before)
            path.unlink();path.symlink_to(target)
            subprocess.run([str(p/'test'),'rejected'],env=env,check=True,capture_output=True)
            self.assertEqual(target.read_bytes(),before);path.unlink();path.write_bytes(before)
            lock.unlink();lock.symlink_to(target)
            subprocess.run([str(p/'test'),'rejected'],env=env,check=True,capture_output=True)
            self.assertEqual(path.read_bytes(),before);self.assertEqual(target.read_bytes(),before)
            lock.unlink()
            env['D2_APPEARANCE_PERSIST_PATH']=str(target)
            subprocess.run([str(p/'test'),'rejected'],env=env,check=True,capture_output=True)
            self.assertEqual(target.read_bytes(),before)


if __name__=='__main__':unittest.main()
