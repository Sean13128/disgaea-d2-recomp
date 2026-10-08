#pragma once
/* D2 cheat/editor bridge between native host UI and the PPU main thread.
 *
 * Threading contract: every function below may be called from any host thread
 * (normally the AppKit main thread). Setters only QUEUE an action. Once per
 * observed vblank the PPU main thread resolves the save root, applies queued
 * actions (validated and clamped against d2_cheats.v1.json) and publishes a
 * snapshot. Getters copy the latest published snapshot under a lock; they never
 * touch guest memory. Results of an action appear in the next snapshot
 * (`status`, values, `serial`).
 *
 * Stale-edit protection: snapshots carry `generation`. Targeted edits (field,
 * skill, item, equipment, remove) pass the generation they were based on; the
 * PPU rejects them if the save, party or inventory changed since (load/save,
 * add/remove item, root move). Pass D2_CHEATS_ANY_GENERATION only for untargeted
 * values where that cannot matter.
 *
 * Field keys come from d2_cheats.v1.json ("fields" with scope general /
 * character / item). d2_cheats_fields() lists them with labels and ranges, and
 * is valid at any time (it does not need a running game). Snapshot value arrays
 * are indexed in that same order.
 *
 * Item API (stable, for the separate Item Editor window):
 *   d2_cheats_fields(D2_CHEATS_ITEM, ...)   item field descriptors
 *   d2_cheats_items_snapshot(out)            inventory pool (bag + warehouse)
 *   d2_cheats_set_item(slot, key, v, gen)    edit inventory pool slot
 *   d2_cheats_set_equipment(u, s, key, v, gen)  edit a unit's equipped item
 *   d2_cheats_add_item(id)                   native add (validated item ID)
 *   d2_cheats_remove_item(slot, gen)         native remove of a pool slot
 * Equipment records are in D2CheatsSnapshot.equipment for the selected unit
 * (d2_cheats_select_unit). The Item Editor window itself is provided by
 * d2_item_editor_show() (weak; the Cheats menu disables it when absent).
 */
#include <stdint.h>
#ifdef __cplusplus
extern "C" {
#endif

#define D2_CHEATS_MAX_FIELDS 48
#define D2_CHEATS_MAX_PARTY 128
#define D2_CHEATS_MAX_ITEMS 999
#define D2_CHEATS_MAX_SKILLS 255
#define D2_CHEATS_EQUIP_SLOTS 4
#define D2_CHEATS_PRESET_SLOTS 4 /* 0 = default, 1..3 = numbered presets */
#define D2_CHEATS_ANY_GENERATION UINT64_MAX

enum { D2_CHEATS_GENERAL = 0, D2_CHEATS_CHARACTER = 1, D2_CHEATS_ITEM = 2 };

typedef struct D2CheatsField {
    char key[32], label[64];
    uint64_t minimum, maximum;
    unsigned size;  /* bytes in guest memory */
    int readonly;   /* view only (e.g. item identity) */
} D2CheatsField;

typedef struct D2CheatsItem {
    unsigned slot;     /* inventory pool index or equipment slot */
    unsigned id;       /* 0 = empty */
    char name[49];
    uint64_t values[D2_CHEATS_MAX_FIELDS]; /* item field order */
} D2CheatsItem;

typedef struct D2CheatsSkill {
    unsigned id, level, boost;
    uint64_t exp;
    char name[97]; /* UTF-8, copied on PPU; empty means unknown/unloaded. */
} D2CheatsSkill;

typedef struct D2CheatsSnapshot {
    uint64_t serial;      /* increments on every publish; 0 = nothing published yet */
    uint64_t generation;  /* pass back with targeted edits */
    int supported;        /* EBOOT matched a profile */
    int verified;         /* profile validated for writes */
    int ready;            /* save state resolved, not saving/loading: edits accepted */
    char version[8];      /* "1.00" / "1.40" */
    char status[192];     /* last action result or waiting reason */
    int hp_lock, sp_lock, one_hit, free_shop;
    unsigned exp_multiplier; /* power of two, 1..1024 */
    uint64_t general[D2_CHEATS_MAX_FIELDS];
    unsigned party_count;
    struct { char name[49]; unsigned level, class_id; } party[D2_CHEATS_MAX_PARTY];
    int unit;             /* selected unit for the detail below, -1 = none */
    uint64_t character[D2_CHEATS_MAX_FIELDS];
    unsigned skill_count;
    D2CheatsSkill skills[D2_CHEATS_MAX_SKILLS];
    D2CheatsItem equipment[D2_CHEATS_EQUIP_SLOTS];
    unsigned inventory_count; /* game's own counter */
} D2CheatsSnapshot;

typedef struct D2CheatsItems {
    uint64_t serial, generation;
    int ready;
    unsigned inventory_count; /* game's own counter */
    unsigned count;           /* occupied entries in items[] */
    D2CheatsItem items[D2_CHEATS_MAX_ITEMS]; /* ~450 KB: allocate on the heap */
} D2CheatsItems;

/* Descriptors: returns the count and sets *out (static storage). */
unsigned d2_cheats_fields(int scope, const D2CheatsField** out);
int d2_cheats_field_index(int scope, const char* key); /* -1 if absent */

/* Copy the latest snapshot. Returns 0 until the PPU published once. Calling it
 * keeps snapshots flowing (~4 Hz); without viewers the PPU stops publishing. */
int d2_cheats_snapshot(D2CheatsSnapshot* out);
int d2_cheats_items_snapshot(D2CheatsItems* out);
void d2_cheats_select_unit(int unit);

/* Queue actions. Return 0 when queued, -1 for invalid arguments (unknown key,
 * index out of range). Validation against game state happens on the PPU. */
int d2_cheats_set_general(const char* key, uint64_t value, uint64_t generation);
int d2_cheats_set_character(unsigned unit, const char* key, uint64_t value, uint64_t generation);
/* key: skill_id, skill_level, skill_exp, skill_boost */
int d2_cheats_set_skill(unsigned unit, unsigned skill, const char* key, uint64_t value, uint64_t generation);
int d2_cheats_set_item(unsigned slot, const char* key, uint64_t value, uint64_t generation);
int d2_cheats_set_equipment(unsigned unit, unsigned slot, const char* key, uint64_t value, uint64_t generation);
int d2_cheats_add_item(unsigned item_id);
int d2_cheats_remove_item(unsigned slot, uint64_t generation);
/* name: hp_lock, sp_lock, one_hit, free_shop */
int d2_cheats_set_toggle(const char* name, int on);
int d2_cheats_set_exp_multiplier(unsigned multiplier);
int d2_cheats_disable_all(void);
int d2_cheats_preset(int save, unsigned slot);
/* Preset file for a slot (default.json / preset-N.json); "" when unavailable. */
const char* d2_cheats_preset_path(unsigned slot);

/* F1 / Cmd+Shift+C and menu: show/hide the native cheats window. */
void d2_cheats_toggle_menu(void);
void d2_register_cheats(void);

/* Native UI (d2_cheats_ui.m). d2_item_editor_show is provided by the Item
 * Editor (weak); absent, its menu item is disabled. */
void d2_cheats_window_toggle(void);
void d2_item_editor_show(void);

#ifdef __cplusplus
}
#endif
