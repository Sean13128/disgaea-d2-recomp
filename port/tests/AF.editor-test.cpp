// Run the actual editor against bounded, big-endian mock guest RAM.
#include "../src/d2_cheats.cpp"
#include <cassert>
static std::vector<uint8_t> memory(8 * 1024 * 1024);
static bool captured;
extern "C" uint8_t vm_read8(uint64_t a) { return memory.at(a); }
extern "C" uint16_t vm_read16(uint64_t a) { return (uint16_t(vm_read8(a)) << 8) | vm_read8(a+1); }
extern "C" uint32_t vm_read32(uint64_t a) { return (uint32_t(vm_read16(a)) << 16) | vm_read16(a+2); }
extern "C" uint64_t vm_read64(uint64_t a) { return (uint64_t(vm_read32(a)) << 32) | vm_read32(a+4); }
extern "C" void vm_write8(uint64_t a,uint8_t v) { memory.at(a) = v; }
extern "C" void vm_write16(uint64_t a,uint16_t v) { vm_write8(a,v>>8); vm_write8(a+1,v); }
extern "C" void vm_write32(uint64_t a,uint32_t v) { vm_write16(a,v>>16); vm_write16(a+2,v); }
extern "C" void vm_write64(uint64_t a,uint64_t v) { vm_write32(a,v>>32); vm_write32(a+4,v); }
extern "C" uint16_t ps3_pad_host_buttons(void) { return 0; }
extern "C" void ps3_pad_overlay_capture(int active) { captured = active; }
extern "C" uint64_t cellGcmGetVBlankCount(void) { return 1; }
extern "C" uint64_t ppu_guest_call_ct(uint32_t code,uint32_t,uint64_t,uint64_t,uint64_t,uint64_t,uint64_t,uint64_t,uint64_t,uint64_t) { return code == 0x18e5c || code == 0x18f50 ? 0 : uint64_t(-1); }
extern "C" int32_t cellSaveDataAutoSave2(uint32_t,const char*,uint32_t,CellSaveDataSetBuf*,CellSaveDataStatCallback,CellSaveDataFileCallback,uint32_t,void*) { return -1; }
void d2_cheat_original_exp(ppu_context*) {}
void d2_cheat_original_shop(ppu_context*) {}
void d2_cheat_original_sp(ppu_context*) {}
static void init()
{
    data = json::parse(d2_cheats_data); profile = data["versions"][D2_CHEATS_VERSION == 140 ? 1 : 0];
    assert(profile["version"] == (D2_CHEATS_VERSION == 140 ? "1.40" : "1.00")); toc = profile["toc"];
    for (const auto& call : profile["calls"]) {
        unsigned index=0;for (const auto& word:call["signature"]) vm_write32(call["address"].get<uint32_t>()+4*index++,std::stoul(word.get<std::string>(),nullptr,16));
    }
    root = 0x10000; party_count = 1; initialized = true;
    vm_write16(root+0x1507ec,1); vm_write64(root+0x568,100);
    uint32_t c = character(0); vm_write16(c+0x1154,1); vm_write16(c+0x1158,1);
    for (unsigned i=0;i<6;++i) vm_write8(c+0x650+i,"Laharl"[i]);
}
int main(int argc,char** argv)
{
    assert(argc == 2); init();
    Field hl{"hl","HL",0x568,0,8,0,9999999999999ull,false};
    assert(apply(root+hl.offset,hl,UINT64_MAX)); assert(vm_read64(root+0x568)==hl.maximum);
    assert(!apply(root-1,hl,1));
    Field level{"level","Level",0x1154,0,2,1,9999,false};
    vm_write64(character(0)+8,100);assert(apply(character(0)+level.offset,level,0));assert(vm_read64(character(0)+8)==0); assert(vm_read16(character(0)+level.offset)==1);
    Field aptitude{"aptitude","Aptitude",0x1524,0x1504,2,0,300,false};
    assert(apply(character(0)+aptitude.offset,aptitude,999));
    assert(vm_read16(character(0)+0x1524)==300 && vm_read16(character(0)+0x1504)==300);
    profile["verified"] = false; assert(!apply(root+hl.offset,hl,0)); profile["verified"] = true;
    editing = true; edit_address = root+hl.offset; edit_root = root; edit_generation = generation;
    edit_field = hl; draft = 1; build_rows(); generation++;
    action(0x4000,4); assert(!editing && vm_read64(root+hl.offset)==hl.maximum);
    hp_lock = true; one_hit = true; uint32_t entity = 0x200000, record = 0x210000;
    vm_write64(record+0x1080,1000); vm_write64(record+0x1070,100);
    assert(d2_cheats_damage(entity,record,50)==1000);
    vm_write8(entity+0x6eb,1); assert(d2_cheats_damage(entity,record,50)==0);
    assert(d2_cheats_damage(entity,record,100)==100); // no damage: don't kill
    assert(d2_cheats_damage(entity,record,120)==120); // healing isn't an attack
    assert(d2_cheats_damage(entity,record,uint64_t(-10))==0);
    vm_write8(entity+0x6eb,2); assert(d2_cheats_damage(entity,record,50)==50);
    ppu_context ctx{}; exp_multiplier=1024;ctx.gpr[4]=UINT64_MAX;
    D2_CHEAT_EXP_FUNCTION(&ctx);assert(ctx.gpr[4]==99999999999ull);
    free_shop=true;ctx.gpr[5]=uint64_t(-1000);D2_CHEAT_SHOP_FUNCTION(&ctx);assert(ctx.gpr[5]==0);
    ctx.gpr[5]=1000;D2_CHEAT_SHOP_FUNCTION(&ctx);assert(ctx.gpr[5]==1000);
    sp_lock=true;vm_write64(record+0x1088,500);vm_write64(record+0x1078,2);
    ctx.lr=profile["sp_callers"][0]["return"];ctx.gpr[profile["sp_callers"][0]["entity_register"].get<unsigned>()]=entity;
    vm_write32(entity+0x1bc,record);vm_write8(entity+0x6eb,0);ctx.gpr[3]=record;ctx.gpr[4]=10;
    D2_CHEAT_SP_FUNCTION(&ctx);assert(ctx.gpr[4]==0 && vm_read64(record+0x1078)==500);
    vm_write8(entity+0x6eb,1);ctx.gpr[4]=10;D2_CHEAT_SP_FUNCTION(&ctx);assert(ctx.gpr[4]==10);
    assert(!ram(UINT64_MAX,8));
    auto path = std::filesystem::path(argv[1]) / "cheats/default.json";
    preset(true,path); assert(std::filesystem::exists(path));
    vm_write64(root+hl.offset,4);vm_write32(character(0)+0x1150,10);hp_lock=false;exp_multiplier=1;
    preset(false,path);assert(vm_read64(root+hl.offset)==hl.maximum && vm_read32(character(0)+0x1150)==0 && hp_lock && exp_multiplier==1024);
    json malformed; {std::ifstream in(path);in>>malformed;}
    malformed["general"]["hl"]=-1; {std::ofstream out(path);out<<malformed;}
    vm_write64(root+hl.offset,5);hp_lock=false;
    preset(false,path); assert(vm_read64(root+hl.offset)==5 && !hp_lock);
    page=1;subpage=0;selected=0;editing=false;display(true);
    assert(token && captured);SysOverlaySnapshot snapshot{};ps3_overlay_snapshot(&snapshot);
    assert(snapshot.count==1 && std::string(snapshot.items[0].label)=="Laharl  Lv 1");close();assert(!captured);
    assert(ps3_host_key_event(122,0,1,0));assert(requests.exchange(0)==1);
    assert(ps3_host_key_event(8,(1u<<20)|(1u<<17),1,0));assert(requests.exchange(0)==1);
    assert(!ps3_host_key_event(8,0,1,0));
    root=0;rows.push_back({"Save preset",5,0,{}});action(0x4000,0);assert(!editing);
    puts("[AF-test] clamps, bounds, version gating, stale edits, damage/EXP toggles, presets, roster, hotkeys: PASS");
    return 0;
}
