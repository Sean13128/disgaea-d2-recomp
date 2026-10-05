/* D2 state editor. Host input only queues actions; the PPU main thread owns
 * resolution, snapshots and writes, once per observed vblank. */
#include "ppu_recomp.h"
#include "d2_cheats.h"
#ifdef __APPLE__
extern "C" __attribute__((weak)) int d2_flags_key_event(unsigned, int, int) { return 0; }
#endif
#include "d2_cheats_data.h"
#include "sys_overlay.h"
#include "cellSaveData.h"
#include <nlohmann/json.hpp>
#include <algorithm>
#include <atomic>
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
uint64_t last_tick, token;
std::atomic<unsigned> requests;
bool initialized, in_hook, hp_lock, sp_lock, one_hit, free_shop;
unsigned exp_multiplier = 1;
uint64_t generation, edit_generation, stable_tick;
unsigned page, subpage, unit, item, skill, selected, return_selected;
std::string status;
struct Field { std::string key, label; uint32_t offset, mirror; unsigned size;
    uint64_t minimum, maximum; bool readonly; };
std::vector<Field> fields;
struct Row { std::string label; int action; uint32_t address; Field field; };
std::vector<Row> rows;
Field edit_field;
uint32_t edit_address, edit_root;
uint64_t draft, step = 1;
bool editing;
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
bool apply(uint32_t address, const Field& field, uint64_t value)
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
void field_rows(const char* scope, uint32_t base)
{
    for (const auto& f : data["fields"]) if (f["scope"] == scope) {
        Field field{f["key"], f["label"], f["offset"], f.value("mirror", 0u),
            f["size"], f["min"], f["max"], f.value("readonly", false)};
        if (field.key == "hp") field.maximum = std::min(field.maximum,vm_read64(base + 0x1080));
        if (field.key == "sp") field.maximum = std::min(field.maximum,vm_read64(base + 0x1088));
        uint32_t a = base + field.offset;
        rows.push_back({field.label + ": " + std::to_string(read(a, field.size)) +
            (field.readonly ? " [view]" : ""), 1, a, field});
    }
}
void row(std::string label, int action) { rows.push_back({std::move(label), action, 0, {}}); }
std::filesystem::path preset_path()
{
    const char* home = std::getenv("HOME");
    if (!home || !*home) throw std::runtime_error("HOME unavailable");
    return std::filesystem::path(home) / "Library/Application Support/DisgaeaD2Recomp/cheats/default.json";
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
                Field field{key,f["label"],f["offset"],0,f["size"],f["min"],f["max"],false};
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
    if (!hdd || std::string(hdd).find("AF-") == std::string::npos) {
        std::fprintf(stderr,"[D2 cheats] test save rejected: use an AF- HDD copy\n"); return;
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

void build_rows()
{
    rows.clear();
    if (!root) { row("Load a save or start a game to edit state.",0); return; }
    if (editing) {
        row(edit_field.label + ": " + std::to_string(draft), 0);
        row("Step: " + std::to_string(step) + " (Square cycles)",0);
        row("Set minimum: " + std::to_string(edit_field.minimum),20);
        row("Set maximum: " + std::to_string(edit_field.maximum),21);
        row("Apply",22); row("Cancel",23); return;
    }
    if (page == 0) {
        field_rows("general",root);
        Field mana{"mana","Mana",0x1150,0,4,0,9999999,false};
        uint32_t c = character(0);
        rows.push_back({name(c + 0x650) + " Mana: " + std::to_string(vm_read32(c + 0x1150)),1,c + mana.offset,mana});
        row(std::string("Infinite HP: ") + (hp_lock ? "ON" : "OFF"),2);
        row(std::string("Infinite SP: ") + (sp_lock ? "ON" : "OFF"),3);
        row(std::string("1-hit kills: ") + (one_hit ? "ON" : "OFF"),8);
        row("EXP gain multiplier: " + std::to_string(exp_multiplier) + "x",9);
        row(std::string("Free item shop: ") + (free_shop ? "ON" : "OFF"),10);
        
    } else if (page == 1 && subpage == 0) {
        for (unsigned i = 0; i < party_count; ++i)
            row(name(character(i) + 0x650) + "  Lv " + std::to_string(vm_read16(character(i) + 0x1154)),100 + i);
    } else if (page == 1 && subpage == 1) {
        if (unit >= party_count) { subpage = 0; return; }
        field_rows("character",character(unit));
        row("Equipment (4 slots)",4);
        row("Skills (existing skill IDs / levels / EXP)",11);
    } else if (page == 1 && subpage == 2) {
        for (unsigned i = 0; i < 4; ++i) {
            uint32_t a = character(unit) + 0x10 + i * 0x190;
            row("Slot " + std::to_string(i + 1) + ": " + name(a + 0xF1),4000 + i);
        }
    } else if (page == 2 && subpage == 0) {
        for (unsigned i = 0; i < 999; ++i) {
            uint32_t a = inventory(i);
            if (vm_read16(a + 0xB8)) row("#" + std::to_string(i) + " " + name(a + 0xF1) +
                "  Lv " + std::to_string(vm_read16(a + 0xBA)),1000 + i);
        }
        row("Add item by ID",12);
    } else if ((page == 2 && subpage == 1) || (page == 1 && subpage == 3)) {
        uint32_t a = page == 2 ? inventory(item) : character(unit) + 0x10 + item * 0x190;
        field_rows("item",a);
        if (page == 2) row("Remove this item",13);
        row("Item World: level / level limit; advanced fields pending",0);
    } else if (page == 1 && subpage == 4) {
        uint32_t c = character(unit);
        unsigned count = vm_read8(c + 0x117B);
        for (unsigned i = 0; i < count; ++i)
            row("Skill ID " + std::to_string(vm_read16(c + 0xB6C + i * 2)) +
                "  Lv " + std::to_string(vm_read8(c + 0xE6C + i)),3000 + i);
    } else if (page == 1 && subpage == 5) {
        uint32_t c = character(unit);
        auto add = [&](const char* key,const char* label,uint32_t off,unsigned size,uint64_t cap,uint64_t min=0) {
            Field f{key,label,off,0,size,min,cap,false};
            rows.push_back({std::string(label) + ": " + std::to_string(read(c + off,size)),1,c + off,f});
        };
        add("skill_id","Skill ID (from loaded roster)",0xB6C + skill * 2,2,32767,1);
        add("skill_level","Skill level",0xE6C + skill,1,99);
        add("skill_exp","Skill EXP",0x76C + skill * 4,4,999999999);
        add("skill_boost","Skill boost",0xD6C + skill,1,9);
    } else if (subpage == 6) {
        row("Remove item permanently from this inventory?",0);
        row("Remove",14); row("Cancel",15);
    } else {
        row("Save default preset",5); row("Load default preset",6);
        for (unsigned i = 1; i <= 3; ++i) {
            row("Save preset " + std::to_string(i),30 + (i - 1) * 2);
            row("Load preset " + std::to_string(i),31 + (i - 1) * 2);
        }
        row("Disable continuous cheats",7);
        row("Presets store General values + toggles. Save edits in-game.",0);
    }
}
void display(bool opening, bool preserve_selection = false)
{
    build_rows();
    static SysOverlaySnapshot ui;
    ui = {};
    ui.kind = SYS_OVERLAY_EDITOR; ui.buttons = 1;
    const char* titles[] = {"General","Characters","Items: bag / warehouse pool","Presets"};
    std::snprintf(ui.title,sizeof ui.title,"D2 cheats / %s",editing ? "Edit value" : titles[page]);
    if (!editing && subpage && root) {
        std::string context = page == 1 ? name(character(unit) + 0x650) : name(inventory(item) + 0xF1);
        std::snprintf(ui.title,sizeof ui.title,"D2 cheats / %s / %u",context.c_str(),subpage);
    }
    std::snprintf(ui.message,sizeof ui.message,"%s%s%s",root ? "" : "Waiting for game state. ",
        status.c_str(), profile.value("verified",false) ? "" : "  Version requires validation.");
    std::snprintf(ui.footer,sizeof ui.footer,"%s", editing ?
        "←/→ Adjust   Square Step   ✕ Choose   ○ Cancel" : "L1/R1 Page   ✕ Edit   ○ Back   F1 Close");
    ui.count = std::min(rows.size(),size_t(SYS_OVERLAY_MAX_ITEMS));
    ui.selected = preserve_selection ? -1 : selected < unsigned(ui.count) ? int(selected) : 0;
    for (int i = 0; i < ui.count; ++i) std::snprintf(ui.items[i].label,sizeof ui.items[i].label,"%s",rows[i].label.c_str());
    if (opening) token = ps3_overlay_open(&ui,SYS_OVERLAY_BACK);
    else if (!ps3_overlay_editor_update(token,&ui)) token = 0;
}
void close()
{
    if (token) { ps3_overlay_finish(token,SYS_OVERLAY_BACK); ps3_overlay_take_result(token,nullptr,nullptr); }
    token = 0; editing = false; subpage = selected = 0;
}
void action(uint16_t buttons, unsigned pick)
{
    if (!root) {
        if (buttons & 0x2000) close();
        else { editing = false; subpage = selected = 0; if (token) display(false); }
        return;
    }
    selected = pick;
    if (buttons & 0x2000) {
        if (editing) { editing = false; selected = return_selected; }
        else if (subpage) { subpage = 0; selected = 0; }
        else { close(); return; }
    } else if (editing) {
        if (buttons & 0x80) draft = draft > edit_field.minimum + step ? draft - step : edit_field.minimum;
        if (buttons & 0x20) draft = std::min(edit_field.maximum,draft + step);
        if (buttons & 0x8000) step = step >= 1000000000000ull ? 1 : step * 10;
        if ((buttons & 0x4000) && pick < rows.size()) {
            switch (rows[pick].action) {
            case 20: draft = edit_field.minimum; break;
            case 21: draft = edit_field.maximum; break;
            case 22:
                if (root == edit_root && generation == edit_generation) apply(edit_address,edit_field,draft);
                else status = "Save changed; edit rejected.";
                [[fallthrough]];
            case 23: editing = false; selected = return_selected; break;
            }
        }
    } else if (buttons & 0xC) {
        page = (page + (buttons & 8 ? 1 : 3)) % 4; subpage = selected = 0;
    } else if ((buttons & 0x4000) && pick < rows.size()) {
        Row r = rows[pick];
        if ((r.action == 1 || (r.action >= 2 && r.action <= 10) || (r.action >= 12 && r.action <= 14) || (r.action >= 30 && r.action <= 35)) &&
            (!profile.value("verified",false) || save_busy())) {
            status = "Editing disabled during save/load or on an unverified version.";
            display(false); return;
        }
        if (r.action == 1) {
            if (r.field.readonly) status = "View only until this mutation is validated.";
            else {
                edit_field = r.field; edit_address = r.address; edit_root = root; edit_generation = generation;
                draft = std::clamp(read(r.address,r.field.size),r.field.minimum,r.field.maximum);
                step = 1; editing = true; return_selected = selected; selected = 0;
            }
        } else if (r.action == 2) hp_lock = !hp_lock;
        else if (r.action == 3) sp_lock = !sp_lock;
        else if (r.action == 4) { subpage = 2; selected = 0; }
        else if (r.action == 5 || r.action == 6) preset(r.action == 5);
        else if (r.action == 7) { hp_lock = sp_lock = one_hit = free_shop = false; exp_multiplier = 1; }
        else if (r.action == 8) one_hit = !one_hit;
        else if (r.action == 9) exp_multiplier = exp_multiplier == 1024 ? 1 : exp_multiplier * 2;
        else if (r.action == 10) free_shop = !free_shop;
        else if (r.action == 11) { subpage = 4; selected = 0; }
        else if (r.action == 12) {
            edit_field = {"add_item","Add item ID",0,0,2,1,32767,false};
            edit_address = edit_root = root; edit_generation = generation;
            draft = 109; step = 1; editing = true; return_selected = selected; selected = 0;
        } else if (r.action == 13) { subpage = 6; selected = 1; }
        else if (r.action == 14) {
            unsigned before = vm_read16(root + 0x13EE08);
            if (!before || item >= 999 || !inventory_ready() || !vm_read16(inventory(item) + 0xB8)) {
                status = "Inventory changed; removal rejected."; display(false); return;
            }
            call("remove_item",0,item);
            unsigned after = vm_read16(root + 0x13EE08);
            std::fprintf(stderr,"[D2 cheats] remove slot=%u count=%u -> %u\n",item,before,after);
            if (after + 1 == before) generation++;
            status = after + 1 == before ? "Item removed." : "Game rejected removal.";
            subpage = selected = 0;
        } else if (r.action == 15) { subpage = 1; selected = 0; }
        else if (r.action >= 30 && r.action <= 35) {
            unsigned index = (r.action - 30) / 2 + 1;
            preset(!(r.action & 1),preset_path().parent_path() / ("preset-" + std::to_string(index) + ".json"));
        }
        else if (r.action >= 4000) { item = r.action - 4000; subpage = 3; selected = 0; }
        else if (r.action >= 3000) { skill = r.action - 3000; subpage = 5; selected = 0; }
        else if (r.action >= 1000) { item = r.action - 1000; subpage = 1; selected = 0; }
        else if (r.action >= 100) { unit = r.action - 100; subpage = 1; selected = 0; }
    }
    if (token) display(false);
}
}
extern "C" void d2_cheats_toggle_menu(void) { requests.fetch_add(1,std::memory_order_relaxed); }
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
        if (!initialized) std::fprintf(stderr,"[D2 cheats] unsupported EBOOT; writes disabled\n");
    } catch (const std::exception& e) { std::fprintf(stderr,"[D2 cheats] table error: %s\n",e.what()); }
}
extern "C" void ps3_guest_frame_hook(ppu_context* ctx)
{
    if (!initialized || in_hook || ctx->thread_id != 1) return;
    uint64_t tick = cellGcmGetVBlankCount();
    if (tick == last_tick) return;
    last_tick = tick;
    in_hook = true;
    bool resolved = resolve(ctx);
    static bool was_busy;
    bool busy = save_busy();
    if (busy && !was_busy) generation++; // invalidate edits across save/load
    was_busy = busy;
    bool ready = resolved && !busy;
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
        const char* test_hdd = std::getenv("PS3_HDD0_ROOT");
        bool copied_hdd = test_hdd && std::string(test_hdd).find("AF-") != std::string::npos;
        if (copied_hdd && check && !tested && tick - stable_tick >= 120 && party_count == 118 && vm_read16(character(0) + 0x1154) == 9999) {
            char* end; uint64_t value = std::strtoull(check,&end,10);
            if (*check && !*end) { Field f{"hl","HL",0x568,0,8,0,9999999999999ull,false}; apply(root + f.offset,f,value); }
            tested = true;
            if (std::getenv("D2_CHEATS_TEST_EDIT")) {
                for (const auto& f : data["fields"]) {
                    if (!((f["scope"] == "character" && (f["key"] == "mana" || f["key"] == "base_2")) ||
                          (f["scope"] == "item" && (f["key"] == "level" || f["key"] == "stat_0")))) continue;
                    Field field{f["key"],f["label"],f["offset"],0,f["size"],f["min"],f["max"],false};
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
    static bool opened;
    const char* auto_page = std::getenv("D2_CHEATS_OPEN_PAGE");
    if (auto_page && ready && tick - stable_tick >= 120 && party_count == 118 && !opened) {
        page = std::min(3u,(unsigned)std::strtoul(auto_page,nullptr,10));
        selected = subpage = 0; display(true); opened = true;
    }
    unsigned pending = requests.exchange(0,std::memory_order_relaxed);
    if (pending & 1) {
        if (token) close();
        else { page = selected = subpage = 0; display(true); }
    }
    if (token) {
        ps3_overlay_poll();
        int pick = selected;
        uint16_t buttons = ps3_overlay_editor_action(token,&pick);
        if (buttons) action(buttons,pick);
        static uint64_t refresh;
        if (tick - refresh >= 30) { display(false,true); refresh = tick; }
    }
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
