// Native Cheats menu/window against a recording fake bridge (no game, no guest RAM).
#include "../src/d2_cheats_ui.m"
#include <assert.h>
#include <string.h>
#include <objc/runtime.h>

static D2CheatsSnapshot fake;
static char last_call[64], last_key[32];
static uint64_t last_value, last_gen;
static unsigned last_a, last_b, calls;
static void record(const char* name, const char* key, unsigned a, unsigned b, uint64_t v, uint64_t g)
{
    snprintf(last_call, sizeof last_call, "%s", name); snprintf(last_key, sizeof last_key, "%s", key ? key : "");
    last_a = a; last_b = b; last_value = v; last_gen = g; calls++;
}
static const D2CheatsField general_fields[] = {{"hl", "HL", 0, 9999999999999ull, 8, 0}, {"cp", "Cheat Shop CP", 0, 9999, 2, 0}};
static const D2CheatsField character_fields[] = {{"level", "Level", 1, 9999, 2, 0}, {"mana", "Mana", 0, 9999999, 4, 0}};
static const D2CheatsField item_fields[] = {{"id", "Item ID", 1, 32767, 2, 1}, {"level", "Item level", 0, 9999, 2, 0}};
unsigned d2_cheats_fields(int scope, const D2CheatsField** out)
{
    *out = scope == 0 ? general_fields : scope == 1 ? character_fields : item_fields; return 2;
}
int d2_cheats_field_index(int scope, const char* key) { (void)scope; (void)key; return -1; }
int d2_cheats_snapshot(D2CheatsSnapshot* out) { *out = fake; return fake.serial != 0; }
int d2_cheats_items_snapshot(D2CheatsItems* out) { (void)out; return 0; }
static int selected = -1;
void d2_cheats_select_unit(int unit) { selected = unit; fake.unit = unit; }
int d2_cheats_set_general(const char* k, uint64_t v, uint64_t g) { record("general", k, 0, 0, v, g); return 0; }
int d2_cheats_set_character(unsigned u, const char* k, uint64_t v, uint64_t g) { record("character", k, u, 0, v, g); return 0; }
int d2_cheats_set_skill(unsigned u, unsigned s, const char* k, uint64_t v, uint64_t g) { record("skill", k, u, s, v, g); return 0; }
int d2_cheats_set_item(unsigned s, const char* k, uint64_t v, uint64_t g) { record("item", k, s, 0, v, g); return 0; }
int d2_cheats_set_equipment(unsigned u, unsigned s, const char* k, uint64_t v, uint64_t g) { record("equipment", k, u, s, v, g); return 0; }
int d2_cheats_add_item(unsigned id) { record("add", "", id, 0, 0, 0); return 0; }
int d2_cheats_remove_item(unsigned s, uint64_t g) { record("remove", "", s, 0, 0, g); return 0; }
int d2_cheats_set_toggle(const char* n, int on) { record("toggle", n, 0, 0, (uint64_t)on, 0); return 0; }
int d2_cheats_set_exp_multiplier(unsigned m) { record("exp", "", m, 0, m, 0); return 0; }
int d2_cheats_disable_all(void) { record("disable", "", 0, 0, 0, 0); return 0; }
int d2_cheats_preset(int save, unsigned slot) { record("preset", "", slot, 0, (uint64_t)save, 0); return 0; }
const char* d2_cheats_preset_path(unsigned slot) { (void)slot; return "/nonexistent/d2-preset.json"; }

static NSMenuItem* find(NSMenu* m, NSString* title)
{
    NSMenuItem* i = [m itemWithTitle:title]; assert(i); return i;
}
static void activate(NSMenu* m, NSString* title)
{
    [m update]; [m performActionForItemAtIndex:[m indexOfItem:find(m, title)]];
}
static NSButton* find_button(NSView* view, NSString* title)
{
    if ([view isKindOfClass:NSButton.class] && [[(NSButton*)view title] isEqual:title]) return (NSButton*)view;
    for (NSView* child in view.subviews) { NSButton* found = find_button(child, title); if (found) return found; }
    return nil;
}
static NSModalResponse skill_id_modal(id alert, SEL selector)
{
    (void)selector;
    assert([[alert messageText] containsString:@"Triple Strike"]);
    NSTextField* input = [alert accessoryView];
    assert([input.stringValue isEqual:@"10"]);
    input.stringValue = @"1001";
    fake.generation = 42; // a refresh while the dialog is open cannot retarget the edit
    return NSAlertFirstButtonReturn;
}
static NSString* dialog_input;
static NSModalResponse dialog_response;
static NSModalResponse skill_id_choice(id alert, SEL selector)
{
    (void)selector;
    [(NSTextField*)[alert accessoryView] setStringValue:dialog_input];
    return dialog_response;
}
int main(void)
{
    @autoreleasepool {
        [NSApplication sharedApplication];
        fake.serial = 1; fake.generation = 41; fake.supported = fake.verified = fake.ready = 1;
        snprintf(fake.version, sizeof fake.version, "1.40"); fake.exp_multiplier = 4; fake.unit = -1;
        fake.general[0] = 100; fake.general[1] = 5; fake.party_count = 2;
        snprintf(fake.party[0].name, 49, "Laharl"); fake.party[0].level = 9999;
        snprintf(fake.party[1].name, 49, "Etna"); fake.party[1].level = 50;
        fake.skill_count = 1; fake.skills[0].id = 10; fake.skills[0].level = 3;
        fake.character[0] = 9999; fake.character[1] = 106348;
        fake.equipment[1].id = 109; snprintf(fake.equipment[1].name, 49, "Sword"); fake.equipment[1].values[1] = 7;
        NSMenu* main = [NSMenu new];
        for (NSString* t in @[@"Disgaea D2", @"Graphics", @"Window", @"Audio", @"Game", @"Controls"]) [main addItemWithTitle:t action:nil keyEquivalent:@""];
        NSWindow* game = [[NSWindow alloc] initWithContentRect:NSMakeRect(0, 0, 320, 180) styleMask:NSWindowStyleMaskTitled backing:NSBackingStoreBuffered defer:NO];
        d2_cheats_menu_install(main, game);
        assert([main indexOfItemWithTitle:@"Cheats"] == [main indexOfItemWithTitle:@"Game"] + 1);
        NSMenu* m = [main itemWithTitle:@"Cheats"].submenu;
        [s_ui menuNeedsUpdate:m];
        // Checkmarks and enablement mirror the snapshot.
        fake.hp_lock = 1; [s_ui menuNeedsUpdate:m];
        NSMenuItem* hp = find(m, @"Infinite HP");
        assert([s_ui validateMenuItem:hp] && hp.state == NSControlStateValueOn);
        assert([s_ui validateMenuItem:find(m, @"One-Hit Kills")] && find(m, @"One-Hit Kills").state == NSControlStateValueOff);
        NSMenu* exp = find(m, @"EXP Multiplier").submenu;
        assert([s_ui validateMenuItem:find(exp, @"4×")] && find(exp, @"4×").state == NSControlStateValueOn);
        assert(![s_ui validateMenuItem:find(m, @"Item Editor…")]); // weak d2_item_editor_show absent
        NSMenu* presets = find(m, @"Presets").submenu;
        assert(![s_ui validateMenuItem:find(presets, @"Load Preset 1")] && [s_ui validateMenuItem:find(presets, @"Save Preset 1")]);
        // Menu actions queue bridge actions.
        activate(m, @"Infinite HP"); assert(!strcmp(last_call, "toggle") && !strcmp(last_key, "hp_lock") && last_value == 0);
        activate(m, @"One-Hit Kills"); assert(!strcmp(last_key, "one_hit") && last_value == 1);
        activate(exp, @"64×"); assert(!strcmp(last_call, "exp") && last_value == 64);
        activate(m, @"Disable All Cheats"); assert(!strcmp(last_call, "disable"));
        activate(presets, @"Save Preset 2"); assert(!strcmp(last_call, "preset") && last_a == 2 && last_value == 1);
        fake.verified = 0; [s_ui menuNeedsUpdate:m]; assert(![s_ui validateMenuItem:hp]); fake.verified = 1;
        // F1 / Cmd+Shift+C path opens the window; General grid applies validated input once.
        d2_cheats_window_toggle(); assert(s_ui.window.visible);
        [s_ui refresh];
        NSTextField* hl = [s_ui.general inputForKey:"hl"];
        assert([hl.stringValue isEqual:@"100"] && hl.editable);
        unsigned before = calls;
        hl.stringValue = @"1,234,567"; [hl sendAction:hl.action to:hl.target];
        assert(calls == before + 1 && !strcmp(last_call, "general") && !strcmp(last_key, "hl") && last_value == 1234567 && last_gen == 41);
        hl.stringValue = @"12abc"; [hl sendAction:hl.action to:hl.target]; assert(calls == before + 1);
        hl.stringValue = @"99999999999999"; [hl sendAction:hl.action to:hl.target]; assert(calls == before + 1); // > max
        [s_ui refresh]; assert([s_ui.status.stringValue containsString:@"whole number"]);
        fake.general[0] = 1234567; [s_ui refresh]; assert([hl.stringValue isEqual:@"1234567"]);
        hl.stringValue = @"1234567"; [hl sendAction:hl.action to:hl.target]; assert(calls == before + 1); // unchanged: no write
        fake.general[0] = 5; [s_ui refresh]; assert([hl.stringValue isEqual:@"5"]); // live refresh
        // Characters: roster, selection drives the detail snapshot, field + skill edits target the unit.
        [s_ui.tabs selectTabViewItemWithIdentifier:@"characters"]; [s_ui refresh];
        assert(s_ui.roster.numberOfRows == 2 && s_ui.roster.selectedRow == 0 && selected == 0);
        [s_ui refresh];
        assert([[s_ui.character inputForKey:"mana"].stringValue isEqual:@"106348"]);
        NSTextField* mana = [s_ui.character inputForKey:"mana"];
        mana.stringValue = @"7"; [mana sendAction:mana.action to:mana.target];
        assert(!strcmp(last_call, "character") && last_a == 0 && last_value == 7);
        assert(s_ui.skills.numberOfRows == 1);
        // The primary skill column is a name, not an editable numeric ID.
        NSTableColumn* skill = [s_ui.skills tableColumnWithIdentifier:@"skill_name"];
        assert(skill && [skill.title isEqual:@"Skill"] && !skill.editable);
        snprintf(fake.skills[0].name, sizeof fake.skills[0].name, "Triple Strike");
        [s_ui refresh];
        assert(([[s_ui tableView:s_ui.skills objectValueForTableColumn:skill row:0] isEqual:@"Triple Strike"]));
        NSButton* editID = find_button([s_ui.unitTabs tabViewItemAtIndex:1].view, @"Edit Skill ID…");
        assert(editID && !editID.enabled);
        [s_ui.skills selectRowIndexes:[NSIndexSet indexSetWithIndex:0] byExtendingSelection:NO];
        [s_ui refresh]; assert(editID.enabled);
        Method modal = class_getInstanceMethod(NSAlert.class, @selector(runModal));
        IMP original = method_setImplementation(modal, (IMP)skill_id_modal);
        before = calls; [editID performClick:nil];
        method_setImplementation(modal, original);
        assert(calls == before + 1 && !strcmp(last_key, "skill_id") && last_a == 0 && last_b == 0 && last_value == 1001 && last_gen == 41);
        fake.generation = 41; [s_ui refresh];
        original = method_setImplementation(modal, (IMP)skill_id_choice);
        before = calls;
        dialog_input = @"1001"; dialog_response = NSAlertSecondButtonReturn; [editID performClick:nil];
        dialog_response = NSAlertFirstButtonReturn;
        for (NSString* value in @[@"0", @"32768", @"not an ID", @"10"]) { dialog_input = value; [editID performClick:nil]; }
        assert(calls == before); // cancellation, invalid and unchanged IDs do not queue
        fake.ready = 0; [s_ui refresh]; [editID performClick:nil]; assert(!editID.enabled && calls == before);
        fake.ready = 1; [s_ui refresh];
        method_setImplementation(modal, original);
        fake.skills[0].name[0] = 0; [s_ui refresh];
        assert(([[s_ui tableView:s_ui.skills objectValueForTableColumn:skill row:0] isEqual:@"Unknown skill (ID 10)"]));
        fake.skills[0].name[0] = (char)0xFF; fake.skills[0].name[1] = 0; [s_ui refresh];
        assert(([[s_ui tableView:s_ui.skills objectValueForTableColumn:skill row:0] isEqual:@"Unknown skill (ID 10)"]));
        snprintf(fake.skills[0].name, sizeof fake.skills[0].name, "Triple Strike"); [s_ui refresh];
        assert(![s_ui tableView:s_ui.skills shouldEditTableColumn:skill row:0]);
        [s_ui tableView:s_ui.skills setObjectValue:@"12" forTableColumn:[s_ui.skills tableColumnWithIdentifier:@"skill_level"] row:0];
        assert(!strcmp(last_call, "skill") && !strcmp(last_key, "skill_level") && last_b == 0 && last_value == 12);
        before = calls;
        [s_ui tableView:s_ui.skills setObjectValue:@"100" forTableColumn:[s_ui.skills tableColumnWithIdentifier:@"skill_level"] row:0];
        assert(calls == before); // level > 99 rejected in the UI
        [s_ui.equipSlot selectItemAtIndex:1]; [s_ui refresh];
        assert([[s_ui.equipSlot itemAtIndex:1].title isEqual:@"Slot 2: Sword"]);
        NSTextField* ilevel = [s_ui.equipment inputForKey:"level"], *iid = [s_ui.equipment inputForKey:"id"];
        assert([ilevel.stringValue isEqual:@"7"] && !iid.editable);
        ilevel.stringValue = @"8"; [ilevel sendAction:ilevel.action to:ilevel.target];
        assert(!strcmp(last_call, "equipment") && last_a == 0 && last_b == 1 && last_value == 8);
        [s_ui.roster selectRowIndexes:[NSIndexSet indexSetWithIndex:1] byExtendingSelection:NO];
        assert(selected == 1);
        // Not ready: fields become read only.
        fake.ready = 0; [s_ui refresh]; assert(!hl.editable && [s_ui.readiness.stringValue containsString:@"Saving"]);
        [s_ui.window performClose:nil]; assert(!s_ui.window.visible && !s_ui.timer);
        puts("[AS-test] native Cheats menu (checkmarks, enablement, actions), window fields/validation/live refresh, roster/skills/equipment, read-only gating: PASS");
    }
    return 0;
}
