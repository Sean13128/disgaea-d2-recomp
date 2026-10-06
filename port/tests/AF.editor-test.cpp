// Run the actual editor and its host bridge against bounded, big-endian mock guest RAM.
#include "../src/d2_cheats.cpp"
#include <cassert>
#include <thread>
static std::vector<uint8_t> memory(8 * 1024 * 1024);
static unsigned window_toggles;
extern "C" void d2_cheats_window_toggle(void) { window_toggles++; }
extern "C" void d2_items_frame(void*) {}
extern "C" uint8_t vm_read8(uint64_t a) { return memory.at(a); }
extern "C" uint16_t vm_read16(uint64_t a) { return (uint16_t(vm_read8(a)) << 8) | vm_read8(a+1); }
extern "C" uint32_t vm_read32(uint64_t a) { return (uint32_t(vm_read16(a)) << 16) | vm_read16(a+2); }
extern "C" uint64_t vm_read64(uint64_t a) { return (uint64_t(vm_read32(a)) << 32) | vm_read32(a+4); }
extern "C" void vm_write8(uint64_t a,uint8_t v) { memory.at(a) = v; }
extern "C" void vm_write16(uint64_t a,uint16_t v) { vm_write8(a,v>>8); vm_write8(a+1,v); }
extern "C" void vm_write32(uint64_t a,uint32_t v) { vm_write16(a,v>>16); vm_write16(a+2,v); }
extern "C" void vm_write64(uint64_t a,uint64_t v) { vm_write32(a,v>>32); vm_write32(a+4,v); }
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
static void bridge_tests(const char* work)
{
    const D2CheatsField* f;
    assert(d2_cheats_fields(D2_CHEATS_GENERAL,&f)==9 && !std::strcmp(f[0].key,"hl") && f[0].maximum==9999999999999ull);
    assert(d2_cheats_fields(D2_CHEATS_CHARACTER,&f)==35 && d2_cheats_fields(D2_CHEATS_ITEM,&f)==18 && !d2_cheats_fields(7,&f));
    int id = d2_cheats_field_index(D2_CHEATS_ITEM,"id"), level = d2_cheats_field_index(D2_CHEATS_ITEM,"level");
    int atk = d2_cheats_field_index(D2_CHEATS_ITEM,"stat_2"), mana = d2_cheats_field_index(D2_CHEATS_CHARACTER,"mana");
    d2_cheats_fields(D2_CHEATS_ITEM,&f);
    assert(id>=0 && level>=0 && atk>=0 && mana>=0 && f[id].readonly && d2_cheats_field_index(D2_CHEATS_GENERAL,"nope")==-1);
    // Host-side argument validation never queues.
    assert(d2_cheats_set_general("nope",1,0)==-1 && d2_cheats_set_character(128,"mana",1,0)==-1);
    assert(d2_cheats_set_skill(0,0,"skill_name",1,0)==-1 && d2_cheats_set_item(999,"level",1,0)==-1);
    assert(d2_cheats_set_equipment(0,4,"level",1,0)==-1 && d2_cheats_add_item(0)==-1 && d2_cheats_remove_item(999,0)==-1);
    assert(d2_cheats_set_toggle("god",1)==-1 && d2_cheats_set_exp_multiplier(3)==-1 && d2_cheats_set_exp_multiplier(2048)==-1);
    assert(d2_cheats_preset(1,4)==-1 && !*d2_cheats_preset_path(9));
    { std::lock_guard<std::mutex> hold(bridge_lock); assert(queue.empty()); }
    // Queued only: guest memory changes on the PPU service pass, then a snapshot publishes it.
    D2CheatsSnapshot snap{}; d2_cheats_snapshot(&snap); uint64_t before = snap.serial;
    assert(!d2_cheats_set_general("hl",12345,generation) && vm_read64(root+0x568)!=12345);
    assert(!d2_cheats_set_character(0,"mana",77,generation) && !d2_cheats_set_character(5,"mana",1,generation));
    assert(!d2_cheats_set_toggle("one_hit",1) && !d2_cheats_set_toggle("hp_lock",0) && !d2_cheats_set_exp_multiplier(8));
    one_hit = false; service(true);
    assert(vm_read64(root+0x568)==12345 && vm_read32(character(0)+0x1150)==77 && one_hit && !hp_lock && exp_multiplier==8);
    assert(status.find("multiplier")!=std::string::npos || status.find("Unit")!=std::string::npos);
    assert(d2_cheats_snapshot(&snap) && snap.serial>before && snap.general[0]==12345 && snap.one_hit && snap.exp_multiplier==8);
    assert(snap.party_count==1 && !std::strcmp(snap.party[0].name,"Laharl") && snap.party[0].level==1 && snap.ready && snap.verified);
    // Unit 5 does not exist: rejected on the PPU with a status, not applied.
    assert(!d2_cheats_set_character(5,"mana",1,generation)); service(true); assert(status=="Unit no longer exists.");
    // Not ready (save/load in progress): queued edits are dropped with a reason.
    assert(!d2_cheats_set_general("hl",1,generation)); service(false);
    assert(vm_read64(root+0x568)==12345 && status.find("disabled")!=std::string::npos);
    // Selected unit detail: skills and equipment.
    uint32_t c = character(0); vm_write8(c+0x117B,1); vm_write16(c+0xB6C,10);
    for (unsigned i=0;i<5;++i) vm_write8(c+0x10+0x190+0xF1+i,"Sword"[i]); vm_write16(c+0x10+0x190+0xB8,1);
    d2_cheats_select_unit(0); service(true); d2_cheats_snapshot(&snap);
    assert(snap.unit==0 && snap.skill_count==1 && snap.skills[0].id==10 && snap.character[mana]==77);
    assert(snap.equipment[1].id==1 && !std::strcmp(snap.equipment[1].name,"Sword") && !snap.equipment[0].id);
    assert(!d2_cheats_set_skill(0,0,"skill_level",7,snap.generation) && !d2_cheats_set_skill(0,0,"skill_boost",99,snap.generation));
    assert(!d2_cheats_set_equipment(0,1,"stat_2",42,snap.generation)); service(true);
    assert(vm_read8(c+0xE6C)==7 && vm_read8(c+0xD6C)==9 && vm_read64(c+0x10+0x190+0x88)==42); // boost clamped to 9
    assert(!d2_cheats_set_skill(0,3,"skill_level",1,generation)); service(true); assert(status=="Skill slot no longer exists.");
    d2_cheats_snapshot(&snap); assert(snap.skills[0].level==7 && snap.equipment[1].values[atk]==42);
    // Items: published only while an item viewer polls; readonly identity; empty slots rejected.
    auto items = std::make_unique<D2CheatsItems>();
    assert(!d2_cheats_items_snapshot(items.get()) && !items->count);
    uint32_t a = inventory(3); vm_write16(a+0xB8,109); vm_write16(a+0xBA,2); vm_write16(root+0x13EE08,1);
    for (unsigned i=0;i<4;++i) vm_write8(a+0xF1+i,"Ring"[i]);
    generation++; service(true); assert(!d2_cheats_set_general("hl",12345,generation)); service(true);
    assert(d2_cheats_items_snapshot(items.get()) && items->count==1 && items->inventory_count==1 && items->generation==generation);
    assert(items->items[0].slot==3 && items->items[0].id==109 && items->items[0].values[level]==2 && !std::strcmp(items->items[0].name,"Ring"));
    assert(!d2_cheats_set_item(3,"level",5,items->generation)); service(true); assert(vm_read16(a+0xBA)==5);
    assert(!d2_cheats_set_item(3,"id",7,generation)); service(true); assert(vm_read16(a+0xB8)==109 && status.find("view only")!=std::string::npos);
    assert(!d2_cheats_set_item(4,"level",5,generation)); service(true); assert(status=="Inventory slot is empty.");
    assert(!d2_cheats_remove_item(3,generation)); service(true); // inventory table not mapped in the mock
    assert(vm_read16(a+0xB8)==109 && status.find("removal rejected")!=std::string::npos);
    d2_cheats_items_snapshot(items.get()); assert(items->items[0].values[level]==5);
    // Presets through the bridge stay inside D2_CHEATS_PRESET_DIR.
    auto dir = std::filesystem::path(work) / "bridge-presets"; setenv("D2_CHEATS_PRESET_DIR",dir.c_str(),1);
    assert(std::string(d2_cheats_preset_path(2))==(dir / "preset-2.json").string());
    assert(!d2_cheats_preset(1,2)); service(true); assert(std::filesystem::exists(dir / "preset-2.json"));
    vm_write64(root+0x568,1); assert(!d2_cheats_preset(0,2)); service(true); assert(vm_read64(root+0x568)==12345);
    assert(!d2_cheats_disable_all()); service(true); assert(!one_hit && exp_multiplier==1);
    // A host thread races queue/snapshot calls against the PPU service loop.
    std::atomic<bool> done{false};
    std::thread host([&] {
        D2CheatsSnapshot s{};
        for (uint64_t v = 1; v <= 2000; ++v) { while (d2_cheats_set_general("cp",v % 10000,D2_CHEATS_ANY_GENERATION)) std::this_thread::yield(); d2_cheats_snapshot(&s); }
        done = true;
    });
    while (!done) { service(true); std::this_thread::yield(); }
    host.join(); service(true);
    assert(vm_read16(root+0x1508A0)==2000 && d2_cheats_snapshot(&snap) && snap.general[d2_cheats_field_index(0,"cp")]==2000);
    puts("[AF-test] bridge: descriptors, argument checks, queue-only host calls, PPU apply/publish, stale/not-ready rejection, skills, equipment, items, presets, threaded queue: PASS");
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
    { uint64_t seen = generation; generation++; // stale bridge edit: save/inventory changed
      assert(!d2_cheats_set_general("hl",1,seen)); service(true);
      assert(vm_read64(root+hl.offset)==hl.maximum && status.find("rejected")!=std::string::npos); }
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
    assert(ps3_host_key_event(122,0,1,0) && window_toggles==1);
    assert(ps3_host_key_event(8,(1u<<20)|(1u<<17),1,0) && window_toggles==2);
    assert(ps3_host_key_event(122,0,1,1) && window_toggles==2); // key repeat
    assert(!ps3_host_key_event(8,0,1,0) && window_toggles==2);
    bridge_tests(argv[1]);
    root=0; assert(!d2_cheats_preset(1,0)); service(false); assert(status.find("Load a save")!=std::string::npos);
    puts("[AF-test] clamps, bounds, version gating, stale edits, damage/EXP toggles, presets, hotkeys -> native window: PASS");
    return 0;
}
