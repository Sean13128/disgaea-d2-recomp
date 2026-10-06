/* AT Item Editor logic: record decode/encode, validation, icon decode and the
 * PPU action queue against a mock guest (asset-free). */
#include "../src/d2_items.h"
#include <cassert>
#include <cstdio>
#include <cstdlib>
#include <cstring>
#include <vector>

static std::vector<uint8_t> mem(64u << 20);
extern "C" {
uint8_t  vm_read8 (uint64_t a) { return a < mem.size() ? mem[a] : 0; }
uint16_t vm_read16(uint64_t a) { return uint16_t(vm_read8(a) << 8 | vm_read8(a + 1)); }
uint32_t vm_read32(uint64_t a) { return uint32_t(vm_read16(a)) << 16 | vm_read16(a + 2); }
uint64_t vm_read64(uint64_t a) { return uint64_t(vm_read32(a)) << 32 | vm_read32(a + 4); }
void vm_write8 (uint64_t a, uint8_t v)  { if (a < mem.size()) mem[a] = v; }
void vm_write16(uint64_t a, uint16_t v) { vm_write8(a, uint8_t(v >> 8)); vm_write8(a + 1, uint8_t(v)); }
void vm_write32(uint64_t a, uint32_t v) { vm_write16(a, uint16_t(v >> 16)); vm_write16(a + 2, uint16_t(v)); }
void vm_write64(uint64_t a, uint64_t v) { vm_write32(a, uint32_t(v >> 32)); vm_write32(a + 4, uint32_t(v)); }
}

/* Mock 1.40 layout. */
const uint32_t TOC = 0x47DF98, ROOT = 0x800000, POOL = ROOT + 0xDD518, COUNT = ROOT + 0x13EE08;
const uint32_t ITEMS = 0x400000, INNS = 0x410000, INVTABLE = 0x420000, MANAGER = 0x430000;
static uint32_t rec(unsigned i) { return POOL + i * D2_ITEM_RECORD; }
static unsigned calls_recalc;
static void make_item(uint32_t a, unsigned id, uint8_t rarity)
{
    for (unsigned i = 0; i < D2_ITEM_RECORD; ++i) vm_write8(a + i, 0);
    vm_write16(a + 0xB8, uint16_t(id)); vm_write8(a + 0xD2, rarity);
    uint8_t g = d2_item_grade(rarity);
    vm_write8(a + 0xDF, g); vm_write8(a + 0xD5, g + 4); vm_write16(a + 0xBC, g == 2 ? 99 : g ? 59 : 29);
    vm_write64(a + 0x78 + 16, 40);                         // base ATK
    char name[16]; std::snprintf(name, sizeof name, "Item %u", id);
    for (unsigned i = 0; name[i]; ++i) vm_write8(a + 0xF1 + i, uint8_t(name[i]));
}
extern "C" uint64_t ppu_guest_call_ct(uint32_t code, uint32_t toc, uint64_t a, uint64_t b, uint64_t c,
    uint64_t, uint64_t, uint64_t, uint64_t, uint64_t)
{
    assert(toc == TOC); (void)a;
    unsigned n = vm_read16(COUNT);
    if (code == 0xD4C60) {                                 // add(0, 0, id, -1)
        for (unsigned i = 0; i < D2_ITEMS_POOL; ++i) if (!vm_read16(rec(i) + 0xB8)) {
            make_item(rec(i), unsigned(c), 50); vm_write16(COUNT, uint16_t(n + 1)); break;
        }
    } else if (code == 0x5DF58) {                          // remove(0, slot): compacts
        for (unsigned i = unsigned(b); i + 1 < D2_ITEMS_POOL; ++i)
            for (unsigned j = 0; j < D2_ITEM_RECORD; ++j) vm_write8(rec(i) + j, vm_read8(rec(i + 1) + j));
        vm_write16(COUNT, uint16_t(n - 1));
    } else if (code == 0x619CC) {                          // recalc(item): total = base + innocent levels
        ++calls_recalc;
        uint64_t extra = 0;
        for (unsigned k = 0; k < 6; ++k) extra += vm_read32(uint32_t(a) + 4 + 8 * k);
        for (unsigned i = 0; i < 8; ++i) vm_write64(uint32_t(a) + 0x38 + 8 * i, vm_read64(uint32_t(a) + 0x78 + 8 * i) + extra);
    } else assert(!"unexpected guest call");
    return 0;
}
static void sig(uint32_t a, uint32_t w0, uint32_t w1, uint32_t w2) { vm_write32(a, w0); vm_write32(a + 4, w1); vm_write32(a + 8, w2); }
static void setup()
{
    std::fill(mem.begin(), mem.end(), 0);
    vm_write32(0x19678, 0x81220000u | uint16_t(-0x7E34));  // lwz r9,-0x7E34(r2)
    vm_write32(TOC - 0x7E34, ROOT);
    sig(0xD4C60, 0xf821fde1, 0x7c0802a6, 0xfba10208);
    sig(0x5DF58, 0xf821ff91, 0x7c0802a6, 0xf8010080);
    sig(0x619CC, 0xf821ff21, 0x7c0802a6, 0xfa610078);
    vm_write32(TOC - 0x75EC, ITEMS); vm_write32(TOC - 0x744C, INNS);
    vm_write32(TOC - 30260, INVTABLE); vm_write32(INVTABLE, POOL);
    vm_write32(TOC - 17424, MANAGER);
    vm_write16(ITEMS, 3); vm_write32(ITEMS + 4, ITEMS + 0x100);
    const unsigned ids[] = {101, 102, 239};
    const char* desc[] = {"Wpn-Fist\xEF\xBC\x9A A fist.", "Etc-Armor\xEF\xBC\x9A Armor.", "Item\xEF\xBC\x9A Heals."};
    for (unsigned i = 0; i < 3; ++i) {
        uint32_t r = ITEMS + 0x100 + i * 0xF0;
        vm_write16(r + 0x14, uint16_t(ids[i])); vm_write16(r + 0x16, uint16_t(i));
        for (unsigned j = 0; desc[i][j]; ++j) vm_write8(r + 0x52 + j, uint8_t(desc[i][j]));
        vm_write8(r + 0x22, 'A' + i);
    }
    vm_write16(INNS, 3); vm_write32(INNS + 4, INNS + 0x100);
    const unsigned inn[][2] = {{1, 9999}, {62, 150}, {21, 50}};
    for (unsigned i = 0; i < 3; ++i) { vm_write32(INNS + 0x100 + i * 0x1A0, inn[i][1]); vm_write16(INNS + 0x104 + i * 0x1A0, uint16_t(inn[i][0])); }
    vm_write16(ROOT + 0x1507EC, 1);                        // party of one, named
    vm_write8(ROOT + 0x598 + 0x650, 'L');
    make_item(rec(0), 101, 50); vm_write16(COUNT, 1);
}
static uint32_t toc_ctx = TOC;
static D2ItemsSnapshot* snap = static_cast<D2ItemsSnapshot*>(std::calloc(1, sizeof(D2ItemsSnapshot)));
static void tick(unsigned n = 16) { for (unsigned i = 0; i < n; ++i) { d2_items_snapshot(snap); d2_items_frame(&toc_ctx); } d2_items_snapshot(snap); }

static void test_record()
{
    uint8_t r[D2_ITEM_RECORD], copy[D2_ITEM_RECORD];
    srand(7);
    for (auto& b : r) b = uint8_t(rand());
    r[0xDF] = d2_item_grade(r[0xD2]);
    D2Item it; d2_item_decode(r, &it);
    std::memcpy(copy, r, sizeof r); d2_item_encode(&it, copy);
    assert(!std::memcmp(r, copy, sizeof r));               // lossless for every encoded field
    it.level = 1234; it.innocents[2] = {77, 62, 9, 1}; it.base[7] = 555;
    d2_item_encode(&it, copy);
    assert(copy[0xBA] == 0x04 && copy[0xBB] == 0xD2);
    assert(copy[0x14 + 3] == 77 && copy[0x14 + 5] == 62 && copy[0x14 + 6] == 9 && copy[0x14 + 7] == 1);
    assert(copy[0x78 + 56 + 7] == uint8_t(555) && copy[0x78 + 56 + 6] == 2);
    for (unsigned i = 0xF1; i < D2_ITEM_RECORD; ++i) assert(copy[i] == r[i]);   // name and tail untouched
    for (unsigned i = 0x38; i < 0x78; ++i) assert(copy[i] == r[i]);             // totals left to recalc
    assert(d2_item_grade(7) == 2 && d2_item_grade(8) == 1 && d2_item_grade(31) == 1 && d2_item_grade(32) == 0);
}
static void test_validate()
{
    D2ItemsCatalog* cat = static_cast<D2ItemsCatalog*>(std::calloc(1, sizeof *cat));
    cat->innocent_count = 2; cat->innocents[0] = {1, 9999, "Dietician"}; cat->innocents[1] = {21, 50, "Alchemist"};
    D2Item before = {}; before.rarity = 50; before.grade = 0; before.slots = 4; before.floors = 29;
    D2Item it = before; char e[160];
    it.rarity = 3;                                          // to legendary: derived fields follow
    assert(!d2_item_validate(&before, &it, cat, e, sizeof e) && it.grade == 2 && it.slots == 6 && it.floors == 99);
    it = before; it.rarity = 3; it.floors = 10;            // explicit floor edit is kept
    assert(!d2_item_validate(&before, &it, cat, e, sizeof e) && it.floors == 10 && it.slots == 6);
    it = before; it.level = 10000; assert(d2_item_validate(&before, &it, cat, e, sizeof e));
    it = before; it.base[0] = -1; assert(d2_item_validate(&before, &it, cat, e, sizeof e));
    it = before; it.range = 11; assert(d2_item_validate(&before, &it, cat, e, sizeof e));
    it = before; it.innocents[4] = {5, 1, 0, 0}; assert(d2_item_validate(&before, &it, cat, e, sizeof e)); // beyond 4 slots
    it = before; it.innocents[0] = {5, 99, 0, 0}; assert(d2_item_validate(&before, &it, cat, e, sizeof e)); // unknown type
    it = before; it.innocents[0] = {51, 21, 0, 0}; assert(d2_item_validate(&before, &it, cat, e, sizeof e)); // > table max 50
    it = before; it.innocents[0] = {50, 21, 0, 1}; it.innocents[1] = {0, 0, 3, 1};
    assert(!d2_item_validate(&before, &it, cat, e, sizeof e) && !it.innocents[1].variant && !it.innocents[1].subdued);
    assert(d2_item_group("Wpn-Fist\xEF\xBC\x9A x") == D2_ITEM_GROUP_WEAPON && d2_item_group("Etc-Armor") == D2_ITEM_GROUP_ARMOR &&
           d2_item_group("Etc-Orb") == D2_ITEM_GROUP_ACCESSORY && d2_item_group("Item\xEF\xBC\x9A") == D2_ITEM_GROUP_CONSUMABLE);
    std::free(cat);
}
static void test_icons()
{
    uint8_t txf[16 + 4] = {0x0B, 1, 1, 1, 0, 2, 0, 1, 0, 1, 0, 0, 0, 0, 0, 4, 0xFC, 0x00, 0x00, 0x1F}; // red, transparent blue
    uint8_t* rgba = nullptr; unsigned w, h;
    assert(!d2_items_txf_rgba(txf, sizeof txf, &rgba, &w, &h) && w == 2 && h == 1);
    assert(rgba[0] == 255 && rgba[1] == 0 && rgba[2] == 0 && rgba[3] == 255);
    assert(rgba[4] == 0 && rgba[6] == 255 && rgba[7] == 0);
    std::free(rgba);
    txf[15] = 5; assert(d2_items_txf_rgba(txf, sizeof txf, &rgba, &w, &h));    // size mismatch rejected
    uint8_t pack[16 + 44 * 2] = {'N','I','S','P','A','C','K'}; pack[15] = 2;
    std::memcpy(pack + 16, "a.dat", 5); std::memcpy(pack + 60, "item.txf", 8);
    pack[60 + 34] = 0x12; pack[60 + 39] = 0x34;
    size_t off, len;
    assert(!d2_items_nispack_find(pack, sizeof pack, "item.txf", &off, &len) && off == 0x1200 && len == 0x34);
    assert(d2_items_nispack_find(pack, sizeof pack, "nope", &off, &len));
}
static const D2ItemsEntry* find(unsigned slot)
{
    for (unsigned i = 0; i < snap->count; ++i) if (snap->entries[i].unit < 0 && snap->entries[i].slot == slot) return &snap->entries[i];
    return nullptr;
}
static void test_queue()
{
    setup(); tick();
    assert(snap->ready && snap->count == 1 && snap->pool_count == 1 && !std::strcmp(snap->version, "1.40"));
    D2ItemsCatalog* cat = static_cast<D2ItemsCatalog*>(std::calloc(1, sizeof *cat));
    assert(d2_items_catalog(cat) && cat->item_count == 3 && cat->innocent_count == 3 && cat->items[1].group == D2_ITEM_GROUP_ARMOR);
    assert(!std::strcmp(cat->items[0].category, "Wpn-Fist") && !std::strcmp(cat->party[0], "L"));

    D2Item it = find(0)->item; uint64_t gen = snap->generation;
    it.level = 7; it.base[2] = 99; it.innocents[0] = {150, 62, 4, 0};
    assert(!d2_items_apply(-1, 0, 101, gen, &it)); tick(1);
    const D2ItemsEntry* e = find(0);
    assert(e->item.level == 7 && e->item.base[2] == 99 && e->item.innocents[0].type == 62 && e->item.total[2] == 249 && calls_recalc == 1);

    it.level = 8; assert(!d2_items_apply(-1, 0, 101, gen - 1, &it)); tick(1);    // stale generation
    assert(find(0)->item.level == 7 && std::strstr(snap->status, "rejected"));
    assert(!d2_items_apply(-1, 0, 999, snap->generation, &it)); tick(1);        // slot holds another item
    assert(find(0)->item.level == 7);
    it.innocents[0].level = 151; assert(!d2_items_apply(-1, 0, 101, snap->generation, &it)); tick(1);  // > Statistician max
    assert(find(0)->item.innocents[0].level == 150 && std::strstr(snap->status, "1 to 150"));

    assert(!d2_items_add(239)); tick(1);
    assert(snap->pool_count == 2 && snap->last_added == 1 && find(1)->item.id == 239);
    assert(!d2_items_add(4242)); tick(1);                                       // not in the item table
    assert(snap->pool_count == 2 && std::strstr(snap->status, "not in the game's item table"));
    assert(!d2_items_duplicate(0, 101, snap->generation)); tick(1);
    assert(snap->pool_count == 3 && snap->last_added == 2 && find(2)->item.level == 7 && find(2)->item.innocents[0].type == 62);
    assert(!d2_items_replace(0, 101, snap->generation, 102)); tick(1);          // new base, keeps level + innocents
    assert(snap->pool_count == 3 && find(0)->item.id == 239 && snap->last_added == 2);
    assert(find(2)->item.id == 102 && find(2)->item.level == 7 && find(2)->item.innocents[0].level == 150);
    assert(!d2_items_remove(1, 101, snap->generation)); tick(1);
    assert(snap->pool_count == 2 && find(0)->item.id == 239 && find(1)->item.id == 102);

    vm_write8(MANAGER + 0x14, 1);                                               // saving: discard, not ready
    assert(!d2_items_add(101)); tick(1);
    assert(!snap->ready && snap->pool_count == 2);
    vm_write8(MANAGER + 0x14, 0); tick();
    assert(snap->ready);
    assert(d2_items_apply(-1, 999, 1, 0, &it) == -1 && d2_items_add(0) == -1);  // argument checks
    std::free(cat);
}
int main()
{
    test_record(); test_validate(); test_icons(); test_queue();
    std::puts("AT items: PASS");
    return 0;
}
