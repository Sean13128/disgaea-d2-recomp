#pragma once
/* D2 Item Editor bridge (AT). Same threading contract as d2_cheats.h: host
 * threads only copy published snapshots and queue actions; d2_items_frame()
 * runs on the PPU main thread once per vblank (called from the cheats frame
 * hook), applies queued actions with the game's own helpers and publishes.
 *
 * Item record (0x190 bytes, big-endian, pool at root+0xDD518, 999 slots;
 * equipment at character+0x10, 4 slots), verified against the lifted item
 * constructor func_00062CD0 / recalc func_000619CC (1.40):
 *   +04+8k innocent k (k<6): u32 level, u16 type, u8 variant, u8 subdued
 *   +34 u32 derived (recalc)   +38 8 x s64 totals (recalc)  +78 8 x s64 base
 *   +B8 id  +BA level  +BC IW floor limit (29/59/99)  +C0 grade+1
 *   +CC counter  +D2 rarity  +D3 type  +D4 icon  +D5 innocent slots (grade+4)
 *   +D6 move  +D7 jump  +D8 rank  +D9 range  +DC critical  +DF grade
 *   +F1 name (48)
 * Stats order: HP, SP, ATK, DEF, INT, RES, HIT, SPD. */
#include <stddef.h>
#include <stdint.h>
#ifdef __cplusplus
extern "C" {
#endif

#define D2_ITEM_RECORD 0x190
#define D2_ITEMS_POOL 999
#define D2_ITEMS_EQUIP 512           /* 128 units x 4 slots */
#define D2_ITEMS_INNOCENTS 6
#define D2_ITEMS_STATS 8
#define D2_ITEMS_CATALOG 1024
#define D2_ITEMS_INNOCENT_TYPES 128
#define D2_ITEMS_ICON 32             /* item.txf cell size */

enum { D2_ITEM_GROUP_WEAPON, D2_ITEM_GROUP_ARMOR, D2_ITEM_GROUP_ACCESSORY,
       D2_ITEM_GROUP_CONSUMABLE, D2_ITEM_GROUP_OTHER };

typedef struct D2Innocent { uint32_t level; uint16_t type; uint8_t variant, subdued; } D2Innocent;

typedef struct D2Item {
    uint16_t id, level, floors;
    uint8_t rarity, grade, icon, type, rank, slots;
    uint8_t counter, move, jump, range, critical;
    int64_t base[D2_ITEMS_STATS], total[D2_ITEMS_STATS];
    D2Innocent innocents[D2_ITEMS_INNOCENTS];
    char name[49];
} D2Item;

typedef struct D2ItemsEntry {
    int16_t unit;     /* -1 = bag/warehouse pool, else party index (equipped) */
    uint16_t slot;    /* pool index, or equipment slot 0..3 */
    D2Item item;
} D2ItemsEntry;

typedef struct D2ItemsSnapshot {
    uint64_t serial, generation;
    int ready;             /* resolved, not saving/loading: edits accepted */
    char version[8];
    char status[192];
    unsigned pool_count;   /* game's own counter (root+0x13EE08) */
    unsigned count;
    int last_added;        /* pool slot of the last add/duplicate/replace, -1 */
    D2ItemsEntry entries[D2_ITEMS_POOL + D2_ITEMS_EQUIP]; /* ~1 MB: heap */
} D2ItemsSnapshot;

typedef struct D2CatalogItem {
    uint16_t id, icon, type;
    uint8_t rank, group;
    char name[49], category[48], description[160];
} D2CatalogItem;

typedef struct D2CatalogInnocent { uint16_t id; uint32_t max_level; char name[49]; } D2CatalogInnocent;

typedef struct D2ItemsCatalog {
    uint64_t serial;
    unsigned item_count, innocent_count;
    D2CatalogItem items[D2_ITEMS_CATALOG];
    D2CatalogInnocent innocents[D2_ITEMS_INNOCENT_TYPES];
    char party[128][49];   /* unit names for equipped entries */
} D2ItemsCatalog;

/* Pure helpers (no guest access; unit-tested). */
void d2_item_decode(const uint8_t* record, D2Item* out);
/* Writes only editable fields; untouched bytes of `record` are preserved. */
void d2_item_encode(const D2Item* item, uint8_t* record);
uint8_t d2_item_grade(uint8_t rarity);          /* game func_00054AF8 */
/* Normalizes derived fields (grade/slots from rarity when rarity changed
 * against `before`) and validates ranges. Returns 0, or -1 with `error`. */
int d2_item_validate(const D2Item* before, D2Item* item, const D2ItemsCatalog* catalog,
                     char* error, size_t error_size);
int d2_item_group(const char* description);    /* from the "Wpn-Fist：" prefix */

/* item.txf from a NISPACK (START.dat) -> RGBA8 (ARGB1555 BE source).
 * Returns 0 and fills *rgba (malloc, caller frees), or -1. */
int d2_items_nispack_find(const uint8_t* pack, size_t size, const char* name,
                          size_t* offset, size_t* length);
int d2_items_txf_rgba(const uint8_t* txf, size_t size, uint8_t** rgba, unsigned* w, unsigned* h);
/* Reads <PS3_VFS_ROOT>/PS3_GAME/USRDIR/Data/START.dat (the user's game). */
int d2_items_icon_sheet(uint8_t** rgba, unsigned* w, unsigned* h, char* error, size_t error_size);

/* Snapshots (copy; any thread). Calling either keeps publishing alive. */
int d2_items_snapshot(D2ItemsSnapshot* out);
uint64_t d2_items_catalog_serial(void);
int d2_items_catalog(D2ItemsCatalog* out);

/* Actions (queued; validated again on the PPU). expected_id guards slot reuse. */
int d2_items_apply(int unit, unsigned slot, unsigned expected_id, uint64_t generation, const D2Item* edited);
int d2_items_add(unsigned item_id);
int d2_items_duplicate(unsigned slot, unsigned expected_id, uint64_t generation);
int d2_items_remove(unsigned slot, unsigned expected_id, uint64_t generation);
int d2_items_replace(unsigned slot, unsigned expected_id, uint64_t generation, unsigned new_id);

/* PPU main thread, once per vblank (ctx = ppu_context*). */
void d2_items_frame(void* ctx);
/* Menu entry (d2_item_editor.m). */
void d2_item_editor_show(void);

#ifdef __cplusplus
}
#endif
