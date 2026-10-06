/* D2 Item Editor PPU side (AT). Host threads never touch guest memory: they
 * copy snapshots and queue actions; d2_items_frame() (PPU main thread, once
 * per vblank, from the cheats frame hook) applies them with the game's own
 * add/remove/recalc helpers, each signature-checked per EBOOT version. */
#include "d2_items.h"
#include <algorithm>
#include <atomic>
#include <cstdio>
#include <cstdlib>
#include <cstring>
#include <mutex>
#include <string>
#include <vector>
#include <chrono>

extern "C" {
uint8_t  vm_read8 (uint64_t addr);
uint16_t vm_read16(uint64_t addr);
uint32_t vm_read32(uint64_t addr);
uint64_t vm_read64(uint64_t addr);
void     vm_write8 (uint64_t addr, uint8_t  val);
void     vm_write16(uint64_t addr, uint16_t val);
void     vm_write32(uint64_t addr, uint32_t val);
void     vm_write64(uint64_t addr, uint64_t val);
uint64_t ppu_guest_call_ct(uint32_t, uint32_t, uint64_t, uint64_t,
    uint64_t, uint64_t, uint64_t, uint64_t, uint64_t, uint64_t);
}
#ifndef D2_ITEMS_TEST
#include "ppu_recomp.h"
#endif

/* ---------------------------------------------------------------- record */
namespace {
uint64_t be(const uint8_t* p, unsigned n) { uint64_t v = 0; while (n--) v = v << 8 | *p++; return v; }
void put(uint8_t* p, unsigned n, uint64_t v) { while (n--) { p[n] = uint8_t(v); v >>= 8; } }
/* Copy a NUL-terminated guest string, cutting only at a UTF-8 boundary. */
void text(char* out, size_t cap, const uint8_t* in, size_t limit)
{
    size_t n = 0;
    while (n < limit && in[n] && n + 1 < cap) ++n;
    while (n && (in[n - 1] & 0xC0) == 0x80) --n;          // drop a partial sequence tail
    if (n && in[n - 1] >= 0xC0) --n;                      // ... and its lead byte
    std::memcpy(out, in, n); out[n] = 0;
}
}

extern "C" uint8_t d2_item_grade(uint8_t rarity) { return rarity <= 7 ? 2 : rarity <= 31 ? 1 : 0; }

extern "C" void d2_item_decode(const uint8_t* r, D2Item* o)
{
    std::memset(o, 0, sizeof *o);
    for (unsigned k = 0; k < D2_ITEMS_INNOCENTS; ++k) {
        const uint8_t* e = r + 4 + 8 * k;
        o->innocents[k] = {uint32_t(be(e, 4)), uint16_t(be(e + 4, 2)), e[6], e[7]};
    }
    for (unsigned i = 0; i < D2_ITEMS_STATS; ++i) {
        o->total[i] = int64_t(be(r + 0x38 + 8 * i, 8));
        o->base[i] = int64_t(be(r + 0x78 + 8 * i, 8));
    }
    o->id = be(r + 0xB8, 2); o->level = be(r + 0xBA, 2); o->floors = be(r + 0xBC, 2);
    o->counter = r[0xCC]; o->rarity = r[0xD2]; o->type = r[0xD3]; o->icon = r[0xD4]; o->slots = r[0xD5];
    o->move = r[0xD6]; o->jump = r[0xD7]; o->rank = r[0xD8]; o->range = r[0xD9]; o->critical = r[0xDC];
    o->grade = r[0xDF];
    text(o->name, sizeof o->name, r + 0xF1, 48);
}

extern "C" void d2_item_encode(const D2Item* o, uint8_t* r)
{
    for (unsigned k = 0; k < D2_ITEMS_INNOCENTS; ++k) {
        uint8_t* e = r + 4 + 8 * k; const D2Innocent& n = o->innocents[k];
        put(e, 4, n.level); put(e + 4, 2, n.type); e[6] = n.variant; e[7] = n.subdued;
    }
    for (unsigned i = 0; i < D2_ITEMS_STATS; ++i) put(r + 0x78 + 8 * i, 8, uint64_t(o->base[i]));
    put(r + 0xBA, 2, o->level); put(r + 0xBC, 2, o->floors);
    if (r[0xDF] != o->grade) r[0xC0] = o->grade + 1;      // the constructor's grade+1 marker
    r[0xCC] = o->counter; r[0xD2] = o->rarity; r[0xD5] = o->slots; r[0xD6] = o->move;
    r[0xD7] = o->jump; r[0xD9] = o->range; r[0xDC] = o->critical; r[0xDF] = o->grade;
}

extern "C" int d2_item_group(const char* d)
{
    if (!d) return D2_ITEM_GROUP_OTHER;
    if (!std::strncmp(d, "Wpn-", 4)) return D2_ITEM_GROUP_WEAPON;
    if (!std::strncmp(d, "Etc-Armor", 9)) return D2_ITEM_GROUP_ARMOR;
    if (!std::strncmp(d, "Etc-", 4) || !std::strncmp(d, "Other-", 6)) return D2_ITEM_GROUP_ACCESSORY;
    if (!std::strncmp(d, "Item", 4)) return D2_ITEM_GROUP_CONSUMABLE;
    return D2_ITEM_GROUP_OTHER;
}

extern "C" int d2_item_validate(const D2Item* before, D2Item* it, const D2ItemsCatalog* cat,
                                char* error, size_t cap)
{
#define fail(...) (std::snprintf(error, cap, __VA_ARGS__), -1)
    if (before && it->rarity != before->rarity) {
        // Same derivation as the item constructor (func_00062CD0).
        it->grade = d2_item_grade(it->rarity);
        if (it->slots == before->slots) it->slots = it->grade + 4;
        if (it->floors == before->floors) it->floors = it->grade == 2 ? 99 : it->grade ? 59 : 29;
    }
    if (it->grade != d2_item_grade(it->rarity)) it->grade = d2_item_grade(it->rarity);
    // ponytail: series caps (Apollo/CE codes + game clamps); per-item limits are not modeled.
    if (it->level > 9999) return fail("Level must be 0 to 9,999.");
    if (it->floors > 99) return fail("Item World floor limit must be 0 to 99.");
    if (it->slots < 1 || it->slots > D2_ITEMS_INNOCENTS) return fail("Innocent slots must be 1 to 6.");
    if (it->counter > 9) return fail("Counter must be 0 to 9.");
    if (it->move > 99 || it->jump > 99) return fail("Move and Jump must be 0 to 99.");
    if (it->range > 10) return fail("Range must be 0 to 10.");
    if (it->critical > 100) return fail("Critical must be 0 to 100.");
    static const char* stat[] = {"HP","SP","ATK","DEF","INT","RES","HIT","SPD"};
    for (unsigned i = 0; i < D2_ITEMS_STATS; ++i)
        if (it->base[i] < 0 || it->base[i] > 99999999) return fail("Base %s must be 0 to 99,999,999.", stat[i]);
    for (unsigned k = 0; k < D2_ITEMS_INNOCENTS; ++k) {
        D2Innocent& n = it->innocents[k];
        if (!n.type) { n = {}; continue; }
        if (k >= it->slots) return fail("Innocent %u is outside the item's %u slots.", k + 1, it->slots);
        uint32_t max = 9999;
        if (cat && cat->innocent_count) {
            const D2CatalogInnocent* found = nullptr;
            for (unsigned i = 0; i < cat->innocent_count; ++i) if (cat->innocents[i].id == n.type) found = &cat->innocents[i];
            if (!found) return fail("Innocent type %u is not in the game's innocent table.", n.type);
            max = found->max_level ? found->max_level : 1;
        }
        if (n.level < 1 || n.level > max) return fail("Innocent %u level must be 1 to %u.", k + 1, max);
        if (n.subdued > 1) return fail("Subdued must be 0 or 1.");
    }
    return 0;
#undef fail
}

/* ------------------------------------------------------------ icon sheet */
extern "C" int d2_items_nispack_find(const uint8_t* p, size_t size, const char* name, size_t* off, size_t* len)
{
    if (size < 16 || std::memcmp(p, "NISPACK", 7)) return -1;
    uint64_t n = be(p + 12, 4);
    if (n > (size - 16) / 44) return -1;
    for (uint64_t i = 0; i < n; ++i) {
        const uint8_t* e = p + 16 + i * 44;
        if (!std::strncmp(reinterpret_cast<const char*>(e), name, 32)) {
            *off = be(e + 32, 4); *len = be(e + 36, 4); return 0;
        }
    }
    return -1;
}

extern "C" int d2_items_txf_rgba(const uint8_t* t, size_t size, uint8_t** rgba, unsigned* w, unsigned* h)
{
    if (size < 16 || t[0] != 0x0B) return -1;              // 0x0B = ARGB1555, big-endian
    unsigned width = be(t + 4, 2), height = be(t + 6, 2);
    uint64_t bytes = be(t + 12, 4);
    if (!width || !height || width > 4096 || height > 4096 || bytes != uint64_t(width) * height * 2 || 16 + bytes > size)
        return -1;
    uint8_t* out = static_cast<uint8_t*>(std::malloc(size_t(width) * height * 4));
    if (!out) return -1;
    for (size_t i = 0; i < size_t(width) * height; ++i) {
        unsigned v = unsigned(be(t + 16 + 2 * i, 2));
        auto c5 = [](unsigned x) { return uint8_t(x * 255 / 31); };
        out[4 * i] = c5(v >> 10 & 31); out[4 * i + 1] = c5(v >> 5 & 31); out[4 * i + 2] = c5(v & 31);
        out[4 * i + 3] = v & 0x8000 ? 255 : 0;
    }
    *rgba = out; *w = width; *h = height; return 0;
}

extern "C" int d2_items_icon_sheet(uint8_t** rgba, unsigned* w, unsigned* h, char* error, size_t cap)
{
    const char* root = std::getenv("PS3_VFS_ROOT");
    std::string path = std::string(root && *root ? root : ".") + "/PS3_GAME/USRDIR/Data/START.dat";
    FILE* f = std::fopen(path.c_str(), "rb");
    if (!f) { std::snprintf(error, cap, "Cannot open %s", path.c_str()); return -1; }
    std::vector<uint8_t> head(16);
    int result = -1; size_t off = 0, len = 0;
    if (std::fread(head.data(), 1, 16, f) == 16 && !std::memcmp(head.data(), "NISPACK", 7)) {
        uint64_t n = be(head.data() + 12, 4);
        if (n < 100000) {
            head.resize(16 + n * 44);
            if (std::fread(head.data() + 16, 1, n * 44, f) == n * 44 &&
                !d2_items_nispack_find(head.data(), head.size(), "item.txf", &off, &len) && len < (64u << 20)) {
                std::vector<uint8_t> txf(len);
                if (!std::fseek(f, long(off), SEEK_SET) && std::fread(txf.data(), 1, len, f) == len)
                    result = d2_items_txf_rgba(txf.data(), len, rgba, w, h);
            }
        }
    }
    std::fclose(f);
    if (result) std::snprintf(error, cap, "item.txf not found/decodable in %s", path.c_str());
    return result;
}

/* ------------------------------------------------------------ PPU bridge */
namespace {
struct Call { uint32_t address, sig[3]; };
struct Profile {
    const char* version; uint32_t toc, count_helper;
    int item_table, innocent_table, inventory_table, save_manager;
    Call add, remove, recalc;
};
// Addresses/signatures from the lifted 1.00 and 1.40 EBOOTs (AT.report.md).
// ponytail: duplicated from d2_cheats.v1.json + three new entries; fold into the JSON if AS exposes it.
const Profile kProfiles[] = {
    {"1.00", 0x3FDE60, 0x1957C, -0x7664, -0x74DC, -30380, -18212,
     {0xCF178, {0xf821fde1, 0x7c0802a6, 0xfba10208}}, {0x5D3D8, {0x2f830000, 0x7c0802a6, 0xf821ff91}},
     {0x60DB0, {0x7d800026, 0xf821ff21, 0xfb0100a0}}},
    {"1.40", 0x47DF98, 0x19678, -0x75EC, -0x744C, -30260, -17424,
     {0xD4C60, {0xf821fde1, 0x7c0802a6, 0xfba10208}}, {0x5DF58, {0xf821ff91, 0x7c0802a6, 0xf8010080}},
     {0x619CC, {0xf821ff21, 0x7c0802a6, 0xfa610078}}},
};
constexpr uint32_t kSaveSize = 1498152, kPool = 0xDD518, kPoolCount = 0x13EE08, kParty = 0x598,
    kPartyStride = 0x1A60, kPartyCount = 0x1507EC, kEquip = 0x10;

enum Kind { APPLY, ADD, DUPLICATE, REMOVE, REPLACE };
struct Action { Kind kind; int unit; unsigned slot, expected, id; uint64_t generation; D2Item item; };

std::mutex lock;
std::vector<Action> queue;
D2ItemsSnapshot* published;       // guarded by lock
D2ItemsCatalog* catalog_pub;      // guarded by lock
std::atomic<uint64_t> catalog_serial{0}, viewer_ms{0};

// PPU-thread state.
const Profile* prof;
uint32_t toc, root;
uint64_t generation = 1, serial, last_publish, ticks;
unsigned last_pool, last_party;
bool was_busy;
int last_added = -1;
std::string status = "Waiting for game state.";
D2ItemsSnapshot* work;
D2ItemsCatalog* cat;              // PPU copy

uint64_t now_ms()
{
    return uint64_t(std::chrono::duration_cast<std::chrono::milliseconds>(
        std::chrono::steady_clock::now().time_since_epoch()).count());
}
// Game tables live in sys_memory blocks above 256 MB (e.g. 0x456xxxxx), so accept the
// whole 32-bit guest space; every pointer here is read from the game's own TOC slots.
bool ram(uint64_t a, uint64_t n) { return a >= 0x10000 && a < 0x100000000ull && n <= 0x100000000ull - a; }
uint32_t slot_ptr(int off) { return vm_read32(toc + uint32_t(off)); }
bool signed_ok(const Call& c) { for (unsigned i = 0; i < 3; ++i) if (vm_read32(c.address + 4 * i) != c.sig[i]) return false; return true; }
uint64_t call(const Call& c, uint64_t a = 0, uint64_t b = 0, uint64_t d = 0, uint64_t e = 0)
{
    if (!signed_ok(c)) return uint64_t(-1);
    return ppu_guest_call_ct(c.address, toc, a, b, d, e, 0, 0, 0, 0);
}
uint32_t pool(unsigned i) { return root + kPool + i * D2_ITEM_RECORD; }
uint32_t equip(unsigned u, unsigned s) { return root + kParty + u * kPartyStride + kEquip + s * D2_ITEM_RECORD; }
void read_record(uint32_t a, uint8_t* r) { for (unsigned i = 0; i < D2_ITEM_RECORD; i += 8) put(r + i, 8, vm_read64(a + i)); }
void write_changed(uint32_t a, const uint8_t* before, const uint8_t* after)
{
    for (unsigned i = 0; i < D2_ITEM_RECORD; ++i) if (before[i] != after[i]) vm_write8(a + i, after[i]);
}
void guest_text(char* out, size_t cap, uint32_t a, size_t limit)
{
    uint8_t buf[256] = {}; limit = std::min(limit, sizeof buf - 1);
    for (size_t i = 0; i < limit; ++i) if (!(buf[i] = vm_read8(a + i))) break;
    text(out, cap, buf, limit);
}
bool valid_root(uint32_t r)
{
    if (!ram(r, kSaveSize) || (r & 7)) return false;
    unsigned party = vm_read16(r + kPartyCount);
    return party && party <= 128 && vm_read16(r + kPoolCount) <= D2_ITEMS_POOL;
}
bool save_busy() { uint32_t m = slot_ptr(prof->save_manager); return ram(m, 0x700) && vm_read8(m + 0x14); }
bool pool_ready() { uint32_t t = slot_ptr(prof->inventory_table); return ram(t, 8) && vm_read32(t) == pool(0); }

void build_catalog()
{
    D2ItemsCatalog* c = cat; std::memset(c, 0, sizeof *c);
    uint32_t t = slot_ptr(prof->item_table);
    if (ram(t, 8)) {
        unsigned n = std::min<unsigned>(vm_read16(t), D2_ITEMS_CATALOG); uint32_t recs = vm_read32(t + 4);
        if (ram(recs, uint64_t(n) * 0xF0)) for (unsigned i = 0; i < n; ++i) {
            uint32_t r = recs + i * 0xF0; D2CatalogItem& e = c->items[c->item_count];
            e.id = vm_read16(r + 0x14); e.icon = vm_read16(r + 0x16); e.type = vm_read16(r + 0x18);
            e.rank = vm_read8(r + 0xDF);
            guest_text(e.name, sizeof e.name, r + 0x22, 48);
            guest_text(e.description, sizeof e.description, r + 0x52, 0xDF - 0x52);
            const char* colon = std::strstr(e.description, "\xEF\xBC\x9A");   // "：" ends the category
            size_t cl = colon ? size_t(colon - e.description) : 0;
            std::snprintf(e.category, sizeof e.category, "%.*s", int(std::min(cl, sizeof e.category - 1)), e.description);
            e.group = uint8_t(d2_item_group(e.description));
            if (e.id) ++c->item_count;
        }
    }
    t = slot_ptr(prof->innocent_table);
    if (ram(t, 8)) {
        unsigned n = std::min<unsigned>(vm_read16(t), D2_ITEMS_INNOCENT_TYPES); uint32_t recs = vm_read32(t + 4);
        if (ram(recs, uint64_t(n) * 0x1A0)) for (unsigned i = 0; i < n; ++i) {
            uint32_t r = recs + i * 0x1A0; D2CatalogInnocent& e = c->innocents[c->innocent_count];
            e.max_level = vm_read32(r); e.id = vm_read16(r + 4);
            guest_text(e.name, sizeof e.name, r + 8, 64);
            if (e.id) ++c->innocent_count;
        }
    }
    unsigned party = std::min(vm_read16(root + kPartyCount), uint16_t(128));
    for (unsigned u = 0; u < party; ++u) guest_text(c->party[u], 49, root + kParty + u * kPartyStride + 0x650, 48);
    c->serial = catalog_serial.load() + 1;
    { std::lock_guard<std::mutex> hold(lock); if (!catalog_pub) catalog_pub = new D2ItemsCatalog; *catalog_pub = *c; }
    catalog_serial = c->serial;
    static unsigned logged = ~0u;
    if (logged != c->item_count) std::fprintf(stderr, "[D2 items] catalog %s: %u items, %u innocent types (item table %08x: n=%u recs=%08x)\n",
        prof->version, c->item_count, c->innocent_count, slot_ptr(prof->item_table),
        vm_read16(slot_ptr(prof->item_table)), vm_read32(slot_ptr(prof->item_table) + 4));
    logged = c->item_count;
}

void publish(bool ready)
{
    D2ItemsSnapshot* s = work;
    s->serial = ++serial; s->generation = generation; s->ready = ready; s->last_added = last_added;
    std::snprintf(s->version, sizeof s->version, "%s", prof ? prof->version : "");
    std::snprintf(s->status, sizeof s->status, "%s", status.c_str());
    s->count = 0; s->pool_count = root ? vm_read16(root + kPoolCount) : 0;
    if (root) {
        uint8_t r[D2_ITEM_RECORD];
        for (unsigned i = 0; i < D2_ITEMS_POOL; ++i) {
            if (!vm_read16(pool(i) + 0xB8)) continue;
            read_record(pool(i), r);
            D2ItemsEntry& e = s->entries[s->count++]; e.unit = -1; e.slot = i; d2_item_decode(r, &e.item);
        }
        unsigned party = std::min(vm_read16(root + kPartyCount), uint16_t(128));
        for (unsigned u = 0; u < party; ++u) for (unsigned k = 0; k < 4; ++k) {
            if (!vm_read16(equip(u, k) + 0xB8)) continue;
            read_record(equip(u, k), r);
            D2ItemsEntry& e = s->entries[s->count++]; e.unit = int16_t(u); e.slot = k; d2_item_decode(r, &e.item);
        }
    }
    std::lock_guard<std::mutex> hold(lock);
    if (!published) published = new D2ItemsSnapshot;
    std::memcpy(published, s, offsetof(D2ItemsSnapshot, entries) + s->count * sizeof(D2ItemsEntry));
}

/* Inserts with the game's own helper; returns the new pool slot or -1. */
int native_add(unsigned id)
{
    unsigned before = vm_read16(root + kPoolCount);
    bool known = false;
    for (unsigned i = 0; i < cat->item_count; ++i) known |= cat->items[i].id == id;
    if (!known) { status = "Item ID " + std::to_string(id) + " is not in the game's item table."; return -1; }
    if (before >= D2_ITEMS_POOL || !pool_ready() || !signed_ok(prof->add)) { status = "Inventory full or add helper unavailable."; return -1; }
    std::vector<uint16_t> ids(D2_ITEMS_POOL);
    for (unsigned i = 0; i < D2_ITEMS_POOL; ++i) ids[i] = vm_read16(pool(i) + 0xB8);
    call(prof->add, 0, 0, id, uint64_t(-1));
    unsigned after = vm_read16(root + kPoolCount);
    std::fprintf(stderr, "[D2 items] add id=%u count=%u -> %u\n", id, before, after);
    if (after != before + 1) { status = "Game rejected item insertion."; return -1; }
    generation++;
    for (unsigned i = 0; i < D2_ITEMS_POOL; ++i) if (!ids[i] && vm_read16(pool(i) + 0xB8) == id) return int(i);
    status = "Item added, but its slot could not be identified."; return -1;
}
bool native_remove(unsigned slot)
{
    unsigned before = vm_read16(root + kPoolCount);
    if (!before || !pool_ready() || !signed_ok(prof->remove)) { status = "Remove helper unavailable."; return false; }
    call(prof->remove, 0, slot);
    unsigned after = vm_read16(root + kPoolCount);
    std::fprintf(stderr, "[D2 items] remove slot=%u count=%u -> %u\n", slot, before, after);
    if (after + 1 != before) { status = "Game rejected removal."; return false; }
    generation++; return true;
}
void recalc(uint32_t a) { if (signed_ok(prof->recalc)) call(prof->recalc, a); }

void run(const Action& a)
{
    if (a.kind == ADD) {
        int s = native_add(a.id);
        if (s >= 0) { last_added = s; status = "Added item to slot " + std::to_string(s) + "."; }
        return;
    }
    if (a.generation != generation) { status = "Inventory changed since you selected this item; edit rejected."; return; }
    bool equipped = a.unit >= 0;
    if ((equipped && (a.unit >= int(vm_read16(root + kPartyCount)) || a.slot >= 4)) || (!equipped && a.slot >= D2_ITEMS_POOL)) {
        status = "Invalid item slot."; return;
    }
    uint32_t addr = equipped ? equip(unsigned(a.unit), a.slot) : pool(a.slot);
    if (vm_read16(addr + 0xB8) != a.expected || !a.expected) { status = "Item slot changed; edit rejected."; return; }
    if (equipped && a.kind != APPLY) { status = "Equipped items can only be edited."; return; }
    uint8_t before[D2_ITEM_RECORD], after[D2_ITEM_RECORD];
    read_record(addr, before); std::memcpy(after, before, sizeof after);
    if (a.kind == APPLY) {
        D2Item old, edited = a.item; char error[160];
        d2_item_decode(before, &old);
        if (d2_item_validate(&old, &edited, cat, error, sizeof error)) { status = error; return; }
        d2_item_encode(&edited, after);
        write_changed(addr, before, after);
        recalc(addr);
        std::fprintf(stderr, "[D2 items] apply %s slot=%u id=%u lv=%u rarity=%u inn0=%u/%u ATK=%lld\n",
            equipped ? "equip" : "pool", a.slot, a.expected, edited.level, edited.rarity,
            edited.innocents[0].type, edited.innocents[0].level, (long long)edited.base[2]);
        status = equipped ? "Applied. Re-equip or re-enter the map to refresh unit totals; save in-game to keep."
                          : "Applied. Save in-game to keep this edit.";
    } else if (a.kind == REMOVE) {
        if (native_remove(a.slot)) status = "Item removed.";
    } else if (a.kind == DUPLICATE || a.kind == REPLACE) {
        int s = native_add(a.kind == DUPLICATE ? a.expected : a.id);
        if (s < 0) return;
        uint32_t na = pool(unsigned(s));
        uint8_t fresh[D2_ITEM_RECORD]; read_record(na, fresh);
        uint8_t merged[D2_ITEM_RECORD];
        if (a.kind == DUPLICATE) std::memcpy(merged, before, sizeof merged);
        else {
            // New base item keeps the old item's level and innocents that fit its slots.
            D2Item item, old; d2_item_decode(fresh, &item); d2_item_decode(before, &old);
            item.level = old.level; unsigned k = 0;
            for (const D2Innocent& n : old.innocents) if (n.type && k < item.slots) item.innocents[k++] = n;
            std::memcpy(merged, fresh, sizeof merged); d2_item_encode(&item, merged);
        }
        write_changed(na, fresh, merged);
        recalc(na);
        last_added = s;
        if (a.kind == REPLACE) {
            if (vm_read16(pool(a.slot) + 0xB8) != a.expected || !native_remove(a.slot)) { status = "New item added; old item kept."; return; }
            // Removal may compact the pool; follow the new item.
            if (unsigned(s) > a.slot && vm_read16(pool(unsigned(s)) + 0xB8) != a.id) last_added = s - 1;
            status = "Base item replaced.";
        } else status = "Duplicated to slot " + std::to_string(s) + ".";
    }
}

void frame(uint32_t current_toc)
{
    ++ticks;
    if (!prof || prof->toc != current_toc) {
        prof = nullptr;
        for (const Profile& p : kProfiles) if (p.toc == current_toc && (vm_read32(p.count_helper) & 0xFFFF0000u) == 0x81220000u) prof = &p;
        if (!prof) return;
        toc = current_toc;
        if (!work) { work = new D2ItemsSnapshot(); cat = new D2ItemsCatalog(); }
        std::fprintf(stderr, "[D2 items] profile %s add=%d remove=%d recalc=%d\n", prof->version,
            signed_ok(prof->add), signed_ok(prof->remove), signed_ok(prof->recalc));
    }
    uint32_t candidate = vm_read32(toc + uint32_t(int16_t(vm_read32(prof->count_helper))));
    bool resolved = valid_root(candidate);
    bool busy = resolved && save_busy();
    if (!resolved) { if (root) generation++; root = 0; }
    else {
        unsigned count = vm_read16(candidate + kPoolCount), party = vm_read16(candidate + kPartyCount);
        if (candidate != root || count != last_pool || party != last_party) {
            bool rebuild = candidate != root || party != last_party;
            generation++; root = candidate; last_pool = count; last_party = party;
            if (rebuild) build_catalog();
        }
    }
    if (busy != was_busy) generation++;
    was_busy = busy;
    bool ready = root && !busy;
    std::vector<Action> pending;
    { std::lock_guard<std::mutex> hold(lock); pending.swap(queue); }
    for (const Action& a : pending) {
        if (!ready) { status = "Game is saving/loading or no save is loaded; action discarded."; continue; }
        run(a);
        last_pool = vm_read16(root + kPoolCount);
    }
    if (ready && !cat->item_count && ticks % 60 == 0) build_catalog();   // tables load after the save
    if (root && !status.compare(0, 7, "Waiting")) status = "Ready.";
    bool viewer = now_ms() - viewer_ms.load() < 2000;
    if (!pending.empty() || (viewer && ticks - last_publish >= 15)) { publish(ready); last_publish = ticks; }
}
int enqueue(Action a) { std::lock_guard<std::mutex> hold(lock); if (queue.size() >= 64) return -1; queue.push_back(a); return 0; }
}

extern "C" int d2_items_snapshot(D2ItemsSnapshot* out)
{
    viewer_ms = now_ms();
    std::lock_guard<std::mutex> hold(lock);
    if (!published) return 0;
    std::memcpy(out, published, offsetof(D2ItemsSnapshot, entries) + published->count * sizeof(D2ItemsEntry));
    return 1;
}
extern "C" uint64_t d2_items_catalog_serial(void) { return catalog_serial.load(); }
extern "C" int d2_items_catalog(D2ItemsCatalog* out)
{
    std::lock_guard<std::mutex> hold(lock);
    if (!catalog_pub) return 0;
    *out = *catalog_pub; return 1;
}
extern "C" int d2_items_apply(int unit, unsigned slot, unsigned id, uint64_t gen, const D2Item* item)
{
    if (!item || unit >= 128 || (unit < 0 && slot >= D2_ITEMS_POOL) || (unit >= 0 && slot >= 4)) return -1;
    return enqueue({APPLY, unit < 0 ? -1 : unit, slot, id, 0, gen, *item});
}
extern "C" int d2_items_add(unsigned id) { return id && id < 65536 ? enqueue({ADD, -1, 0, 0, id, 0, {}}) : -1; }
extern "C" int d2_items_duplicate(unsigned slot, unsigned id, uint64_t gen)
{ return slot < D2_ITEMS_POOL ? enqueue({DUPLICATE, -1, slot, id, 0, gen, {}}) : -1; }
extern "C" int d2_items_remove(unsigned slot, unsigned id, uint64_t gen)
{ return slot < D2_ITEMS_POOL ? enqueue({REMOVE, -1, slot, id, 0, gen, {}}) : -1; }
extern "C" int d2_items_replace(unsigned slot, unsigned id, uint64_t gen, unsigned new_id)
{ return slot < D2_ITEMS_POOL && new_id && new_id < 65536 ? enqueue({REPLACE, -1, slot, id, new_id, gen, {}}) : -1; }

extern "C" void d2_items_frame(void* ctx)
{
#ifdef D2_ITEMS_TEST
    frame(*static_cast<uint32_t*>(ctx));
#else
    auto* c = static_cast<ppu_context*>(ctx);
    if (c->thread_id == 1) frame(uint32_t(c->gpr[2]));
#endif
}
