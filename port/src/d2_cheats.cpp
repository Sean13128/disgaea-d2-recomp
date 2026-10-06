/* D2 state editor. Host UI only queues actions through the d2_cheats.h bridge;
 * the PPU main thread owns resolution, snapshots and writes, once per observed
 * vblank. The native AppKit UI lives in d2_cheats_ui.m; nothing draws in-game. */
#include "ppu_recomp.h"
#include "d2_cheats.h"
#ifdef __APPLE__
extern "C" __attribute__((weak)) int d2_flags_key_event(unsigned, int, int) { return 0; }
#endif
#include "d2_cheats_data.h"
#include "cellSaveData.h"
#include <nlohmann/json.hpp>
#include <algorithm>
#include <atomic>
#include <chrono>
#include <cstddef>
#include <cstring>
#include <memory>
#include <mutex>
#include <cstdio>
#include <cstdlib>
#include <filesystem>
#include <fstream>
#include <string>
#include <vector>
#include <tuple>

extern "C" uint64_t cellGcmGetVBlankCount(void);
extern "C" uint64_t ppu_guest_call_ct(uint32_t, uint32_t, uint64_t, uint64_t,
    uint64_t, uint64_t, uint64_t, uint64_t, uint64_t, uint64_t);
using nlohmann::json;
namespace {
json data, profile;
uint32_t root, toc, pointer_slot;
unsigned party_count, item_count;
uint64_t last_tick;
bool initialized, in_hook, hp_lock, sp_lock, one_hit, free_shop;
unsigned exp_multiplier = 1;
uint64_t generation, stable_tick;
std::string status;
struct Field { std::string key, label; uint32_t offset, mirror; unsigned size;
    uint64_t minimum, maximum; bool readonly; };
Field make_field(const json& f)
{
    return {f["key"], f["label"], f["offset"], f.value("mirror", 0u), f["size"], f["min"], f["max"], f.value("readonly", false)};
}
uint64_t call(const char* key, uint64_t a=0, uint64_t b=0, uint64_t c=0, uint64_t d=0)
{
    const auto& calls = profile["calls"];
    if (!calls.contains(key)) return uint64_t(-1);
    const auto& entry = calls[key]; uint32_t code = entry["address"];
    unsigned i = 0;
    for (const auto& word : entry["signature"]) {
        uint32_t expected = std::stoul(word.get<std::string>(),nullptr,16);
        if (vm_read32(code + i++ * 4) != expected) return uint64_t(-1);
    }
    return ppu_guest_call_ct(code,toc,a,b,c,d,0,0,0,0);
}

bool ram(uint64_t address, uint32_t length)
{
    return address >= 0x10000 && address <= 0x10000000 && length <= 0x10000000 - address;
}
uint32_t slot(const char* key) { return vm_read32(toc + profile["slots"][key].get<int>()); }
bool save_busy()
{
    uint32_t manager = slot("save_manager");
    return ram(manager,0x700) && vm_read8(manager + 0x14);
}
uint64_t read(uint32_t address, unsigned size)
{
    switch (size) {
    case 1: return vm_read8(address);
    case 2: return vm_read16(address);
    case 4: return vm_read32(address);
    default: return vm_read64(address);
    }
}
void write(uint32_t address, unsigned size, uint64_t value)
{
    switch (size) {
    case 1: vm_write8(address, value); break;
    case 2: vm_write16(address, value); break;
    case 4: vm_write32(address, value); break;
    default: vm_write64(address, value); break;
    }
}
uint32_t character(unsigned index) { return root + 0x598 + index * 0x1A60; }
uint32_t inventory(unsigned index) { return root + 0xDD518 + index * 0x190; }
std::string name(uint32_t address, unsigned limit = 48)
{
    std::string result;
    for (unsigned i = 0; i < limit; ++i) {
        unsigned c = vm_read8(address + i);
        if (!c) break;
        result += c < 32 ? '?' : char(c);
    }
    return result;
}
bool validate(uint32_t candidate)
{
    if (!ram(candidate, 1498152) || (candidate & 7)) return false;
    unsigned count = vm_read16(candidate + 0x1507EC);
    if (!count || count > 128 || vm_read16(candidate + 0x13EE08) > 999 ||
        vm_read64(candidate + 0x568) > 9999999999999ull) return false;
    for (unsigned i = 0; i < std::min(count, 4u); ++i) {
        uint32_t c = candidate + 0x598 + i * 0x1A60;
        unsigned level = vm_read16(c + 0x1154);
        if (!level || level > 9999 || !vm_read16(c + 0x1158) ||
            vm_read32(c + 0x1150) > 9999999 || name(c + 0x650).empty()) return false;
    }
    return true;
}
bool resolve(ppu_context* ctx)
{
    uint32_t current_toc = uint32_t(ctx->gpr[2]);
    if (current_toc != toc) return false;
    uint32_t candidate = vm_read32(pointer_slot);
    if (!validate(candidate)) { root = 0; return false; }
    if (root != candidate || party_count != vm_read16(candidate + 0x1507EC) ||
        item_count != vm_read16(candidate + 0x13EE08)) {
        generation++; stable_tick = last_tick;
        root = candidate;
        std::fprintf(stderr, "[D2 cheats] resolved version=%s pointer=%08x root=%08x HL=%llu party=%u\n",
            profile["version"].get<std::string>().c_str(), pointer_slot, root,
            (unsigned long long)vm_read64(root + 0x568), vm_read16(root + 0x1507EC));
        std::fprintf(stderr,"[D2 cheats] inventory=%u first='%s' id=%u level=%u HP=%llu base_ATK=%llu\n",
            vm_read16(root + 0x13EE08),name(inventory(0) + 0xF1).c_str(),vm_read16(inventory(0) + 0xB8),
            vm_read16(inventory(0) + 0xBA),(unsigned long long)vm_read64(inventory(0) + 0x78),
            (unsigned long long)vm_read64(character(0) + 0x10D0));
        for (unsigned i = 0; i < vm_read16(root + 0x1507EC); ++i) {
            uint32_t c = character(i);
            std::fprintf(stderr, "[D2 cheats] unit=%u name='%s' level=%u mana=%u\n", i,
                name(c + 0x650).c_str(), vm_read16(c + 0x1154), vm_read32(c + 0x1150));
        }
    }
    party_count = vm_read16(root + 0x1507EC);
    item_count = vm_read16(root + 0x13EE08);
    return true;
}
bool writable(uint32_t address, const Field& field)
{
    if (!profile.value("verified",false) || !root || save_busy() || !validate(root) || !ram(address, field.size) || field.readonly) return false;
    // Never accept absolute addresses from presets or stale selection pointers.
    return address >= root && uint64_t(address) + field.size <= uint64_t(root) + 1498152;
}
bool inventory_ready()
{
    uint32_t table = slot("inventory_table");
    return root && ram(table,8) && vm_read32(table) == inventory(0);
}
bool apply(uint32_t address, const Field& field, uint64_t value, unsigned unit = 0, unsigned skill = 0)
{
    if (!writable(address, field)) { status = "State changed; edit rejected."; return false; }
    value = std::clamp(value, field.minimum, field.maximum);
    if (field.key == "class") {
        uint32_t table = slot("class_table");
        if (!ram(table,8) || (int32_t)call("class_lookup",table,value,1) < 0) {
            status = "Class ID is absent from the loaded class table."; return false;
        }
    }
    if (field.key == "skill_id") {
        // Replacing an existing skill preserves the parallel array/count invariant.
        for (unsigned i = 0; i < vm_read8(character(unit) + 0x117B); ++i)
            if (i != skill && vm_read16(character(unit) + 0xB6C + i * 2) == value) {
                status = "This unit already has that skill."; return false;
            }
        bool known = false;
        for (unsigned u = 0; u < party_count; ++u)
            for (unsigned i = 0; i < vm_read8(character(u) + 0x117B); ++i)
                known |= vm_read16(character(u) + 0xB6C + i * 2) == value;
        if (!known) { status = "Use a skill ID present in the loaded roster."; return false; }
    }
    if (field.key == "add_item") {
        unsigned count = vm_read16(root + 0x13EE08);
        uint32_t table = slot("item_table");
        if (count >= 999 || !inventory_ready() || !ram(table,8) || (int32_t)call("item_lookup",table,value,1) < 0) {
            status = "Item table rejected this ID, or inventory is full."; return false;
        }
        call("add_item",0,0,value,uint64_t(-1));
        unsigned after = vm_read16(root + 0x13EE08);
        std::fprintf(stderr,"[D2 cheats] add item id=%llu count=%u -> %u\n",(unsigned long long)value,count,after);
        if (after == count + 1) generation++;
        status = after == count + 1 ? "Item added; reopen the game inventory." : "Game rejected item insertion.";
        return after == count + 1;
    }
    if (field.key == "level" && field.offset == 0x1154) {
        uint32_t c = address - field.offset;
        uint64_t exp = call("exp_threshold",vm_read16(c + 0x115C),value);
        if (exp > 99999999999ull) { status = "Level EXP table rejected this edit."; return false; }
        vm_write64(c + 8,exp);
    }
    uint64_t before = read(address, field.size);
    write(address, field.size, value);
    if (field.mirror) write(address - field.offset + field.mirror, field.size, value);
    std::fprintf(stderr, "[D2 cheats] write %s offset=%06x %llu -> %llu (PPU/vblank=%llu)\n",
        field.key.c_str(), address - root, (unsigned long long)before,
        (unsigned long long)value, (unsigned long long)last_tick);
    if (field.key == "class") { call("class_refresh",address - field.offset); status = "Class updated. Re-enter map to refresh the model."; }
    else if (field.key.rfind("base_",0) == 0) status = "Base stat applied. Re-enter map to refresh totals, then save.";
    else status = "Applied. Save in-game to keep this edit.";
    return true;
}
std::filesystem::path preset_path(unsigned slot = 0)
{
    // D2_CHEATS_PRESET_DIR keeps tests away from the user's presets.
    const char* dir = std::getenv("D2_CHEATS_PRESET_DIR");
    const char* home = std::getenv("HOME");
    std::filesystem::path base = dir && *dir ? std::filesystem::path(dir) :
        home && *home ? std::filesystem::path(home) / "Library/Application Support/DisgaeaD2Recomp/cheats" :
        throw std::runtime_error("HOME unavailable");
    return base / (slot ? "preset-" + std::to_string(slot) + ".json" : std::string("default.json"));
}
void preset(bool save, std::filesystem::path path = {})
{
    try {
        if (path.empty()) path = preset_path();
        if (save) {
            json p{{"schema",1},{"title","BLUS31313"},{"primary_name",name(character(0) + 0x650)},{"primary_mana",vm_read32(character(0) + 0x1150)},{"hp_lock",hp_lock},{"sp_lock",sp_lock},{"one_hit",one_hit},{"free_shop",free_shop},{"exp_multiplier",exp_multiplier}};
            for (const auto& f : data["fields"]) if (f["scope"] == "general" && !f.value("readonly", false))
                p["general"][f["key"].get<std::string>()] = read(root + f["offset"].get<uint32_t>(), f["size"]);
            std::filesystem::create_directories(path.parent_path());
            auto temp = path; temp += ".tmp";
            { std::ofstream out(temp); out << p.dump(2) << '\n'; out.flush();
              if (!out) throw std::runtime_error("preset write failed"); }
            std::filesystem::rename(temp, path);
            status = "Preset saved: " + path.filename().string();
        } else {
            if (std::filesystem::file_size(path) > 65536) throw std::runtime_error("preset too large");
            std::ifstream in(path); json p; in >> p;
            if (p.at("schema") != 1 || p.at("title") != "BLUS31313") throw std::runtime_error("wrong preset format");
            // Validate the entire document before changing any guest values.
            std::vector<std::tuple<uint32_t,Field,uint64_t>> pending;
            for (const auto& f : data["fields"]) if (f["scope"] == "general") {
                std::string key = f["key"];
                if (!p.value("general",json::object()).contains(key)) continue;
                if (!p["general"][key].is_number_unsigned()) throw std::runtime_error("invalid preset value");
                Field field = make_field(f); field.mirror = 0; field.readonly = false;
                pending.push_back({root + field.offset,field,p["general"][key].get<uint64_t>()});
            }
            if (p.contains("primary_mana")) {
                if (!p["primary_mana"].is_number_unsigned() || p.at("primary_name") != name(character(0) + 0x650))
                    throw std::runtime_error("primary unit Mana mismatch / invalid value");
                Field mana{"mana","Mana",0x1150,0,4,0,9999999,false};
                pending.push_back({character(0) + mana.offset,mana,p["primary_mana"].get<uint64_t>()});
            }
            bool hp = p.at("hp_lock").get<bool>(), sp = p.at("sp_lock").get<bool>();
            bool hit = p.value("one_hit",false), shop = p.value("free_shop",false);
            unsigned multiplier = p.value("exp_multiplier",1u);
            if (!multiplier || multiplier > 1024 || (multiplier & (multiplier - 1))) throw std::runtime_error("invalid multiplier");
            for (const auto& [a,f,v] : pending)
                if (!writable(a,f)) throw std::runtime_error("state unavailable / version not validated");
            for (const auto& [a,f,v] : pending) apply(a,f,v);
            hp_lock = hp; sp_lock = sp; one_hit = hit; free_shop = shop; exp_multiplier = multiplier; status = "Preset loaded: " + path.filename().string();
        }
    } catch (const std::exception& e) { status = std::string("Preset: ") + e.what(); }
}
void test_save(ppu_context* ctx)
{
    const char* hdd = std::getenv("PS3_HDD0_ROOT");
    // Test automation is limited to an AF copy of the HDD; never original saves.
    if (!hdd || (std::string(hdd).find("AF-") == std::string::npos && std::string(hdd).find("AS-") == std::string::npos)) {
        std::fprintf(stderr,"[D2 cheats] test save rejected: use an AF-/AS- HDD copy\n"); return;
    }
    uint32_t manager = slot("save_manager");
    uint32_t stat_opd = slot("save_stat"), file_opd = slot("save_file");
    if (!ram(manager,0x700) || !ram(stat_opd,8) || !ram(file_opd,8) || vm_read8(manager + 0x14)) {
        std::fprintf(stderr,"[D2 cheats] test save rejected: manager busy/invalid\n"); return;
    }
    uint32_t old_buffer = vm_read32(manager + 0x4C), old_size = vm_read32(manager + 0x50);
    vm_write32(manager + 0x4C,root); vm_write32(manager + 0x50,1498152);
    uint64_t old_sp = ctx->gpr[1];
    uint32_t set_buf = uint32_t(old_sp) - 0x100;
    ctx->gpr[1] = old_sp - 0x400; // callbacks descend below the borrowed buffer
    uint8_t old_stack[32];
    for (unsigned i = 0; i < 32; ++i) { old_stack[i] = vm_read8(set_buf + i); vm_write8(set_buf + i,0); }
    vm_write32(set_buf,100); vm_write32(set_buf + 4,7);
    vm_write32(manager + 0x580,3); vm_write32(manager + 0x584,1);
    vm_write32(manager + 0x588,slot("save_metadata"));
    vm_write32(manager + 0x58C,0); vm_write32(manager + 0x590,0); vm_write32(manager + 0x594,0);
    vm_write32(manager + 0x5D0,0);
    int32_t result = cellSaveDataAutoSave2(1,"NPUB31321_NORMAL_01",2,reinterpret_cast<CellSaveDataSetBuf*>(uintptr_t(set_buf)),
        reinterpret_cast<CellSaveDataStatCallback>(uintptr_t(stat_opd)),
        reinterpret_cast<CellSaveDataFileCallback>(uintptr_t(file_opd)),uint32_t(-1),nullptr);
    ctx->gpr[1] = old_sp;
    for (unsigned i = 0; i < 32; ++i) vm_write8(set_buf + i,old_stack[i]);
    vm_write32(manager + 0x4C,old_buffer); vm_write32(manager + 0x50,old_size);
    std::fprintf(stderr,"[D2 cheats] test save actual D2 stat/file callbacks result=%08x HL=%llu\n",
        uint32_t(result),(unsigned long long)vm_read64(root + 0x568));
}

// ---- Bridge (d2_cheats.h). Host threads only touch this section's queue and
// published copies, under bridge_lock; everything else is PPU-thread state.
enum Kind { SET_GENERAL, SET_CHARACTER, SET_SKILL, SET_ITEM, SET_EQUIP, ADD_ITEM, REMOVE_ITEM,
    TOGGLE, EXP_MULTIPLIER, DISABLE_ALL, PRESET };
struct Action { Kind kind; std::string key; unsigned a, b; uint64_t value, gen; };
std::mutex bridge_lock;
std::vector<Action> queue;
D2CheatsSnapshot published, scratch;
std::unique_ptr<D2CheatsItems> published_items, scratch_items;
uint64_t serial;
std::atomic<int> selected_unit{-1};
std::atomic<int64_t> viewed_ms{-1000000}, items_viewed_ms{-1000000};
int64_t now_ms()
{
    return std::chrono::duration_cast<std::chrono::milliseconds>(
        std::chrono::steady_clock::now().time_since_epoch()).count();
}
const char* scope_name(int scope) { return scope == D2_CHEATS_GENERAL ? "general" : scope == D2_CHEATS_CHARACTER ? "character" : "item"; }
struct Catalog { std::vector<json> raw[3]; std::vector<D2CheatsField> fields[3]; };
// Parsed independently of d2_register_cheats so the UI can lay out at any time.
const Catalog& catalog()
{
    static const Catalog c = [] {
        Catalog c; json all = json::parse(d2_cheats_data);
        for (int scope = 0; scope < 3; ++scope)
            for (const auto& f : all["fields"]) if (f["scope"] == scope_name(scope) && c.raw[scope].size() < D2_CHEATS_MAX_FIELDS) {
                D2CheatsField d{};
                std::snprintf(d.key, sizeof d.key, "%s", f["key"].get<std::string>().c_str());
                std::snprintf(d.label, sizeof d.label, "%s", f["label"].get<std::string>().c_str());
                d.minimum = f["min"]; d.maximum = f["max"]; d.size = f["size"]; d.readonly = f.value("readonly", false);
                c.raw[scope].push_back(f); c.fields[scope].push_back(d);
            }
        return c;
    }();
    return c;
}
int field_index(int scope, const char* key)
{
    if (scope < 0 || scope > 2 || !key) return -1;
    const auto& f = catalog().fields[scope];
    for (size_t i = 0; i < f.size(); ++i) if (!std::strcmp(f[i].key, key)) return int(i);
    return -1;
}
bool skill_field(const std::string& key, unsigned skill, Field& out)
{
    if (key == "skill_id") out = {key,"Skill ID",0xB6C + skill * 2,0,2,1,32767,false};
    else if (key == "skill_level") out = {key,"Skill level",0xE6C + skill,0,1,0,99,false};
    else if (key == "skill_exp") out = {key,"Skill EXP",0x76C + skill * 4,0,4,0,999999999,false};
    else if (key == "skill_boost") out = {key,"Skill boost",0xD6C + skill,0,1,0,9,false};
    else return false;
    return true;
}
int enqueue(Action a)
{
    std::lock_guard<std::mutex> hold(bridge_lock);
    if (queue.size() >= 256) return -1; // a stalled guest must not grow this forever
    queue.push_back(std::move(a));
    return 0;
}
void read_item(uint32_t address, unsigned slot, D2CheatsItem& out)
{
    out.slot = slot; out.id = vm_read16(address + 0xB8);
    std::snprintf(out.name, sizeof out.name, "%s", name(address + 0xF1).c_str());
    const auto& raw = catalog().raw[D2_CHEATS_ITEM];
    for (size_t i = 0; i < raw.size(); ++i) out.values[i] = read(address + raw[i]["offset"].get<uint32_t>(), raw[i]["size"]);
}
void perform(const Action& a, bool ready)
{
    bool targeted = a.kind <= SET_EQUIP || a.kind == REMOVE_ITEM;
    if (a.kind == TOGGLE) {
        bool on = a.value != 0;
        if (a.key == "hp_lock") hp_lock = on; else if (a.key == "sp_lock") sp_lock = on;
        else if (a.key == "one_hit") one_hit = on; else free_shop = on;
        status = std::string(on ? "Enabled " : "Disabled ") + a.key + ".";
        return;
    }
    if (a.kind == EXP_MULTIPLIER) { exp_multiplier = unsigned(a.value); status = "EXP multiplier " + std::to_string(a.value) + "x."; return; }
    if (a.kind == DISABLE_ALL) { hp_lock = sp_lock = one_hit = free_shop = false; exp_multiplier = 1; status = "Continuous cheats disabled."; return; }
    if (!ready || !profile.value("verified",false)) {
        status = !root ? "Load a save first; edit not applied." : "Editing is disabled during save/load or on an unverified version.";
        return;
    }
    if (targeted && a.gen != D2_CHEATS_ANY_GENERATION && a.gen != generation) {
        status = "Game state changed since this value was shown; edit rejected. Try again."; return;
    }
    auto lookup = [&](int scope, Field& f) {
        int i = field_index(scope, a.key.c_str());
        if (i < 0) { status = "Unknown field " + a.key + "."; return false; }
        f = make_field(catalog().raw[scope][i]);
        if (f.readonly) { status = f.label + " is view only."; return false; }
        return true;
    };
    Field f;
    switch (a.kind) {
    case SET_GENERAL: if (lookup(D2_CHEATS_GENERAL, f)) apply(root + f.offset, f, a.value); break;
    case SET_CHARACTER:
        if (a.a >= party_count) { status = "Unit no longer exists."; break; }
        if (!lookup(D2_CHEATS_CHARACTER, f)) break;
        if (f.key == "hp") f.maximum = std::min(f.maximum, vm_read64(character(a.a) + 0x1080));
        if (f.key == "sp") f.maximum = std::min(f.maximum, vm_read64(character(a.a) + 0x1088));
        apply(character(a.a) + f.offset, f, a.value, a.a);
        break;
    case SET_SKILL:
        if (a.a >= party_count || a.b >= vm_read8(character(a.a) + 0x117B)) { status = "Skill slot no longer exists."; break; }
        if (skill_field(a.key, a.b, f)) apply(character(a.a) + f.offset, f, a.value, a.a, a.b);
        break;
    case SET_ITEM:
        if (a.a >= 999 || !vm_read16(inventory(a.a) + 0xB8)) { status = "Inventory slot is empty."; break; }
        if (lookup(D2_CHEATS_ITEM, f)) apply(inventory(a.a) + f.offset, f, a.value);
        break;
    case SET_EQUIP:
        if (a.a >= party_count || a.b >= D2_CHEATS_EQUIP_SLOTS) { status = "Equipment slot no longer exists."; break; }
        if (lookup(D2_CHEATS_ITEM, f)) apply(character(a.a) + 0x10 + a.b * 0x190 + f.offset, f, a.value, a.a);
        break;
    case ADD_ITEM: { Field add{"add_item","Add item ID",0,0,2,1,32767,false}; apply(root, add, a.value); break; }
    case REMOVE_ITEM: {
        unsigned before = vm_read16(root + 0x13EE08);
        if (!before || a.a >= 999 || !inventory_ready() || !vm_read16(inventory(a.a) + 0xB8)) {
            status = "Inventory changed; removal rejected."; break;
        }
        call("remove_item",0,a.a);
        unsigned after = vm_read16(root + 0x13EE08);
        std::fprintf(stderr,"[D2 cheats] remove slot=%u count=%u -> %u\n",a.a,before,after);
        if (after + 1 == before) generation++;
        status = after + 1 == before ? "Item removed." : "Game rejected removal.";
        break;
    }
    case PRESET: preset(a.value != 0, preset_path(a.a)); break;
    default: break;
    }
}
void publish(bool ready)
{
    D2CheatsSnapshot& s = scratch;
    std::memset(&s, 0, sizeof s);
    s.generation = generation; s.supported = initialized; s.verified = initialized && profile.value("verified",false); s.ready = ready;
    std::snprintf(s.version, sizeof s.version, "%s", initialized ? profile["version"].get<std::string>().c_str() : "");
    std::snprintf(s.status, sizeof s.status, "%s", status.c_str());
    s.hp_lock = hp_lock; s.sp_lock = sp_lock; s.one_hit = one_hit; s.free_shop = free_shop; s.exp_multiplier = exp_multiplier;
    s.unit = -1;
    bool items = now_ms() - items_viewed_ms.load() < 2000;
    if (root) {
        const auto& general = catalog().raw[D2_CHEATS_GENERAL];
        for (size_t i = 0; i < general.size(); ++i) s.general[i] = read(root + general[i]["offset"].get<uint32_t>(), general[i]["size"]);
        s.party_count = std::min(party_count, unsigned(D2_CHEATS_MAX_PARTY));
        for (unsigned i = 0; i < s.party_count; ++i) {
            std::snprintf(s.party[i].name, sizeof s.party[i].name, "%s", name(character(i) + 0x650).c_str());
            s.party[i].level = vm_read16(character(i) + 0x1154); s.party[i].class_id = vm_read16(character(i) + 0x1158);
        }
        int u = selected_unit.load();
        if (u >= 0 && unsigned(u) < s.party_count) {
            uint32_t c = character(u); s.unit = u;
            const auto& raw = catalog().raw[D2_CHEATS_CHARACTER];
            for (size_t i = 0; i < raw.size(); ++i) s.character[i] = read(c + raw[i]["offset"].get<uint32_t>(), raw[i]["size"]);
            s.skill_count = std::min(unsigned(vm_read8(c + 0x117B)), unsigned(D2_CHEATS_MAX_SKILLS));
            for (unsigned i = 0; i < s.skill_count; ++i)
                s.skills[i] = {vm_read16(c + 0xB6C + i * 2), vm_read8(c + 0xE6C + i), vm_read8(c + 0xD6C + i), vm_read32(c + 0x76C + i * 4)};
            for (unsigned i = 0; i < D2_CHEATS_EQUIP_SLOTS; ++i) read_item(c + 0x10 + i * 0x190, i, s.equipment[i]);
        }
        s.inventory_count = vm_read16(root + 0x13EE08);
    }
    if (items) {
        if (!scratch_items) scratch_items = std::make_unique<D2CheatsItems>();
        D2CheatsItems& it = *scratch_items;
        it.generation = generation; it.ready = ready; it.count = 0; it.inventory_count = s.inventory_count;
        for (unsigned i = 0; root && i < D2_CHEATS_MAX_ITEMS; ++i)
            if (vm_read16(inventory(i) + 0xB8)) read_item(inventory(i), i, it.items[it.count++]);
    }
    std::lock_guard<std::mutex> hold(bridge_lock);
    s.serial = ++serial;
    published = s;
    if (items) {
        if (!published_items) published_items = std::make_unique<D2CheatsItems>();
        scratch_items->serial = serial;
        std::memcpy(published_items.get(), scratch_items.get(), offsetof(D2CheatsItems, items) + scratch_items->count * sizeof(D2CheatsItem));
    }
}
// PPU thread: apply queued actions, then publish while a viewer is active.
void service(bool ready)
{
    std::vector<Action> work;
    { std::lock_guard<std::mutex> hold(bridge_lock); work.swap(queue); }
    for (const auto& a : work) perform(a, ready);
    static uint64_t last_publish;
    static int last_unit = -1;
    bool viewer = now_ms() - viewed_ms.load() < 2000 || now_ms() - items_viewed_ms.load() < 2000;
    // ~4 Hz while a window/menu reads snapshots, 1 Hz otherwise (menu checkmarks).
    if (!work.empty() || selected_unit.load() != last_unit || last_tick - last_publish >= (viewer ? 15u : 60u)) {
        publish(ready); last_publish = last_tick; last_unit = selected_unit.load();
    }
}
}
extern "C" unsigned d2_cheats_fields(int scope, const D2CheatsField** out)
{
    if (scope < 0 || scope > 2) { if (out) *out = nullptr; return 0; }
    const auto& f = catalog().fields[scope];
    if (out) *out = f.data();
    return unsigned(f.size());
}
extern "C" int d2_cheats_field_index(int scope, const char* key) { return field_index(scope, key); }
extern "C" int d2_cheats_snapshot(D2CheatsSnapshot* out)
{
    viewed_ms = now_ms();
    std::lock_guard<std::mutex> hold(bridge_lock);
    if (out) *out = published;
    return published.serial != 0;
}
extern "C" int d2_cheats_items_snapshot(D2CheatsItems* out)
{
    items_viewed_ms = now_ms();
    std::lock_guard<std::mutex> hold(bridge_lock);
    if (!published_items) { if (out) { out->serial = 0; out->count = 0; } return 0; }
    if (out) std::memcpy(out, published_items.get(), offsetof(D2CheatsItems, items) + published_items->count * sizeof(D2CheatsItem));
    return 1;
}
extern "C" void d2_cheats_select_unit(int unit) { selected_unit = unit >= 0 && unit < D2_CHEATS_MAX_PARTY ? unit : -1; }
extern "C" int d2_cheats_set_general(const char* key, uint64_t value, uint64_t gen)
{
    if (field_index(D2_CHEATS_GENERAL, key) < 0) return -1;
    return enqueue({SET_GENERAL, key, 0, 0, value, gen});
}
extern "C" int d2_cheats_set_character(unsigned unit, const char* key, uint64_t value, uint64_t gen)
{
    if (unit >= D2_CHEATS_MAX_PARTY || field_index(D2_CHEATS_CHARACTER, key) < 0) return -1;
    return enqueue({SET_CHARACTER, key, unit, 0, value, gen});
}
extern "C" int d2_cheats_set_skill(unsigned unit, unsigned skill, const char* key, uint64_t value, uint64_t gen)
{
    Field f;
    if (unit >= D2_CHEATS_MAX_PARTY || skill >= D2_CHEATS_MAX_SKILLS || !key || !skill_field(key, skill, f)) return -1;
    return enqueue({SET_SKILL, key, unit, skill, value, gen});
}
extern "C" int d2_cheats_set_item(unsigned slot, const char* key, uint64_t value, uint64_t gen)
{
    if (slot >= D2_CHEATS_MAX_ITEMS || field_index(D2_CHEATS_ITEM, key) < 0) return -1;
    return enqueue({SET_ITEM, key, slot, 0, value, gen});
}
extern "C" int d2_cheats_set_equipment(unsigned unit, unsigned slot, const char* key, uint64_t value, uint64_t gen)
{
    if (unit >= D2_CHEATS_MAX_PARTY || slot >= D2_CHEATS_EQUIP_SLOTS || field_index(D2_CHEATS_ITEM, key) < 0) return -1;
    return enqueue({SET_EQUIP, key, unit, slot, value, gen});
}
extern "C" int d2_cheats_add_item(unsigned id)
{
    if (!id || id > 32767) return -1;
    return enqueue({ADD_ITEM, "add_item", 0, 0, id, D2_CHEATS_ANY_GENERATION});
}
extern "C" int d2_cheats_remove_item(unsigned slot, uint64_t gen)
{
    if (slot >= D2_CHEATS_MAX_ITEMS) return -1;
    return enqueue({REMOVE_ITEM, "remove_item", slot, 0, 0, gen});
}
extern "C" int d2_cheats_set_toggle(const char* name, int on)
{
    if (!name) return -1;
    std::string key = name;
    if (key != "hp_lock" && key != "sp_lock" && key != "one_hit" && key != "free_shop") return -1;
    return enqueue({TOGGLE, key, 0, 0, uint64_t(on != 0), D2_CHEATS_ANY_GENERATION});
}
extern "C" int d2_cheats_set_exp_multiplier(unsigned m)
{
    if (!m || m > 1024 || (m & (m - 1))) return -1;
    return enqueue({EXP_MULTIPLIER, "exp_multiplier", 0, 0, m, D2_CHEATS_ANY_GENERATION});
}
extern "C" int d2_cheats_disable_all(void) { return enqueue({DISABLE_ALL, "", 0, 0, 0, D2_CHEATS_ANY_GENERATION}); }
extern "C" int d2_cheats_preset(int save, unsigned slot)
{
    if (slot >= D2_CHEATS_PRESET_SLOTS) return -1;
    return enqueue({PRESET, "preset", slot, 0, uint64_t(save != 0), D2_CHEATS_ANY_GENERATION});
}
extern "C" const char* d2_cheats_preset_path(unsigned slot)
{
    thread_local std::string path;
    try { path = slot < D2_CHEATS_PRESET_SLOTS ? preset_path(slot).string() : ""; } catch (...) { path.clear(); }
    return path.c_str();
}
extern "C" __attribute__((weak)) void d2_cheats_window_toggle(void);
extern "C" void d2_cheats_toggle_menu(void)
{
    if (d2_cheats_window_toggle) d2_cheats_window_toggle();
    else std::fprintf(stderr,"[D2 cheats] native cheats window unavailable in this build\n");
}
extern "C" int ps3_host_key_event(unsigned code, unsigned modifiers, int down, int repeat)
{
#ifdef __APPLE__
    if (d2_flags_key_event(code, down, repeat)) return 1;
#endif
    bool hotkey = code == 122 || (code == 8 && (modifiers & (1u << 20)) && (modifiers & (1u << 17)));
    if (!hotkey) return 0;
    if (down && !repeat) d2_cheats_toggle_menu();
    return 1;
}
extern "C" void d2_register_cheats(void)
{
    try {
        data = json::parse(d2_cheats_data);
        for (const auto& p : data["versions"]) {
            if (p["version"] != (D2_CHEATS_VERSION == 140 ? "1.40" : "1.00")) continue;
            uint32_t a = p["count_signature"];
            // The count helper loads a pointer via r2, then reads +0x1507EC.
            // Compiler scheduling differs in 1.40; the profile owns its signature.
            bool matches = true; unsigned index = 0;
            for (const auto& word : p["resolver_words"]) {
                uint32_t actual = vm_read32(a + index * 4);
                if (!index) actual &= 0xFFFF0000;
                matches &= actual == std::stoul(word.get<std::string>(),nullptr,16);
                ++index;
            }
            if (!matches) continue;
            toc = p["toc"]; pointer_slot = toc + int16_t(vm_read32(a)); profile = p;
            initialized = true;
            std::fprintf(stderr,"[D2 cheats] signature=%08x version=%s pointer_slot=%08x\n",a,
                p["version"].get<std::string>().c_str(),pointer_slot);
            break;
        }
        if (!initialized) {
            std::fprintf(stderr,"[D2 cheats] unsupported EBOOT; writes disabled\n");
            std::lock_guard<std::mutex> hold(bridge_lock);
            published.serial = ++serial; published.unit = -1; published.exp_multiplier = 1;
            std::snprintf(published.status,sizeof published.status,"Unsupported EBOOT; editing disabled.");
        }
    } catch (const std::exception& e) { std::fprintf(stderr,"[D2 cheats] table error: %s\n",e.what()); }
}
extern "C" __attribute__((weak)) void d2_items_frame(void*); // AT
extern "C" void ps3_guest_frame_hook(ppu_context* ctx)
{
    if (!initialized || in_hook || ctx->thread_id != 1) return;
    uint64_t tick = cellGcmGetVBlankCount();
    if (tick == last_tick) return;
    last_tick = tick;
    in_hook = true;
    if (d2_items_frame) d2_items_frame(ctx); // AT: Item Editor PPU tick (d2_items.cpp)
    bool resolved = resolve(ctx);
    static bool was_busy;
    bool busy = save_busy();
    if (busy && !was_busy) generation++; // invalidate edits across save/load
    was_busy = busy;
    bool ready = resolved && !busy;
    // Test automation only ever runs against an AF-/AS- copy of the HDD.
    const char* test_hdd = std::getenv("PS3_HDD0_ROOT");
    bool copied_hdd = test_hdd && (std::strstr(test_hdd,"AF-") || std::strstr(test_hdd,"AS-"));
    // Unknown or unvalidated profiles cannot mutate guest state.
    if (ready && !profile.value("verified",false)) { hp_lock = sp_lock = one_hit = free_shop = false; exp_multiplier = 1; }
    if (ready && profile.value("verified",false)) {
        for (unsigned i = 0; i < party_count; ++i) {
            uint32_t c = character(i);
            if (hp_lock) vm_write64(c + 0x1070,vm_read64(c + 0x1080));
            if (sp_lock) vm_write64(c + 0x1078,vm_read64(c + 0x1088));
        }
        static bool tested;
        const char* check = std::getenv("D2_CHEATS_TEST_HL");
        if (copied_hdd && check && !tested && tick - stable_tick >= 120 && party_count == 118 && vm_read16(character(0) + 0x1154) == 9999) {
            char* end; uint64_t value = std::strtoull(check,&end,10);
            if (*check && !*end) { Field f{"hl","HL",0x568,0,8,0,9999999999999ull,false}; apply(root + f.offset,f,value); }
            tested = true;
            if (std::getenv("D2_CHEATS_TEST_EDIT")) {
                for (const auto& f : data["fields"]) {
                    if (!((f["scope"] == "character" && (f["key"] == "mana" || f["key"] == "base_2")) ||
                          (f["scope"] == "item" && (f["key"] == "level" || f["key"] == "stat_0")))) continue;
                    Field field = make_field(f); field.mirror = 0;
                    uint32_t address = (f["scope"] == "item" ? inventory(0) : character(0)) + field.offset;
                    apply(address,field,read(address,field.size) + 1);
                }
                unsigned before = vm_read16(root + 0x13EE08), empty = 0;
                while (empty < 999 && vm_read16(inventory(empty) + 0xB8)) ++empty;
                Field add{"add_item","Add item ID",0,0,2,1,32767,false};
                if (apply(root,add,109) && empty < 999 && vm_read16(inventory(empty) + 0xB8) == 109) {
                    call("remove_item",0,empty);
                    std::fprintf(stderr,"[D2 cheats] test add/remove count=%u -> %u (%s)\n",before,
                        vm_read16(root + 0x13EE08),vm_read16(root + 0x13EE08) == before ? "PASS" : "FAIL");
                }
            }
            if (std::getenv("D2_CHEATS_TEST_SAVE")) test_save(ctx);
        }
    }
    static bool saved;
    const char* save_when = std::getenv("D2_CHEATS_TEST_SAVE_WHEN_HL");
    if (ready && copied_hdd && save_when && !saved && *save_when && party_count == 118 &&
        vm_read64(root + 0x568) == std::strtoull(save_when,nullptr,10)) { saved = true; test_save(ctx); }
    service(ready);
    in_hook = false;
}

void d2_cheat_original_exp(ppu_context*);
void d2_cheat_original_shop(ppu_context*);
void d2_cheat_original_sp(ppu_context*);
void D2_CHEAT_EXP_FUNCTION(ppu_context* ctx)
{
    if (initialized && root && validate(root) && !save_busy() && profile.value("verified",false) && exp_multiplier > 1) {
        uint64_t gain = ctx->gpr[4];
        ctx->gpr[4] = gain > 99999999999ull / exp_multiplier ? 99999999999ull : gain * exp_multiplier;
    }
    d2_cheat_original_exp(ctx);
}
void D2_CHEAT_SHOP_FUNCTION(ppu_context* ctx)
{
    // This callback checks affordability and applies the signed item-shop
    // transaction. Zero only purchases; selling keeps its normal proceeds.
    if (initialized && free_shop && root && validate(root) && !save_busy() && profile.value("verified",false) && (int32_t)ctx->gpr[5] < 0)
        ctx->gpr[5] = 0;
    d2_cheat_original_shop(ctx);
}
void D2_CHEAT_SP_FUNCTION(ppu_context* ctx)
{
    if (initialized && sp_lock && root && validate(root) && !save_busy() && profile.value("verified",false) && ram(ctx->gpr[3],0x1090)) {
        bool ally = ctx->gpr[3] >= character(0) && ctx->gpr[3] < character(party_count) &&
            (ctx->gpr[3] - character(0)) % 0x1A60 == 0;
        // Battle entities may point at a separate character record. Resolve
        // the caller's entity only at known version-specific call sites.
        for (const auto& caller : profile["sp_callers"]) if (ctx->lr == caller["return"].get<uint32_t>()) {
            uint64_t entity = ctx->gpr[caller["entity_register"].get<unsigned>()];
            ally |= ram(entity,0x6EC) && vm_read32(entity + 0x1BC) == ctx->gpr[3] && !vm_read8(entity + 0x6EB);
        }
        if (ally) { ctx->gpr[4] = 0; vm_write64(ctx->gpr[3] + 0x1078,vm_read64(ctx->gpr[3] + 0x1088)); }
    }
    d2_cheat_original_sp(ctx);
}
extern "C" unsigned long long d2_cheats_damage(unsigned long long entity,
    unsigned long long record, unsigned long long value)
{
    if (!initialized || !root || !validate(root) || save_busy() || !profile.value("verified",false) ||
        !ram(entity,0x6EC) || !ram(record,0x1088)) return value;
    unsigned team = vm_read8(entity + 0x6EB);
    if (!team && hp_lock) return vm_read64(record + 0x1080);
    if (team == 1 && one_hit && int64_t(value) < int64_t(vm_read64(record + 0x1070))) return 0;
    return value;
}
