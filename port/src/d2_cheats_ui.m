/* Native Cheats menu and window. AppKit main thread only; all game access goes
 * through the d2_cheats.h bridge (queued actions + published snapshots). */
#import <AppKit/AppKit.h>
#include <errno.h>
#include <stdlib.h>
#include "d2_cheats.h"

extern void d2_item_editor_show(void) __attribute__((weak_import));

static D2CheatsSnapshot s_snap;
static NSWindow* s_game;
static NSString* s_local_error;
static NSDate* s_local_error_time;
static const unsigned s_multipliers[] = {1, 2, 4, 8, 16, 32, 64, 128, 256, 512, 1024};

static BOOL editable(void) { return s_snap.ready && s_snap.verified; }
static void ui_error(NSString* text) { NSBeep(); s_local_error = text; s_local_error_time = NSDate.date; }
static NSString* grouped(uint64_t v)
{
    return [NSNumberFormatter localizedStringFromNumber:@(v) numberStyle:NSNumberFormatterDecimalStyle];
}
/* Whole numbers only, inside the field's range; commas/spaces are ignored. */
static BOOL parse_value(NSString* text, uint64_t minimum, uint64_t maximum, NSString* label, uint64_t* out)
{
    NSString* digits = [[text componentsSeparatedByCharactersInSet:
        [NSCharacterSet characterSetWithCharactersInString:@", _  "]] componentsJoinedByString:@""];
    NSCharacterSet* bad = NSCharacterSet.decimalDigitCharacterSet.invertedSet;
    NSString* range = [NSString stringWithFormat:@"%@ must be a whole number from %@ to %@.", label, grouped(minimum), grouped(maximum)];
    if (!digits.length || digits.length > 19 || [digits rangeOfCharacterFromSet:bad].location != NSNotFound) { ui_error(range); return NO; }
    errno = 0;
    unsigned long long v = strtoull(digits.UTF8String, NULL, 10);
    if (errno || v < minimum || v > maximum) { ui_error(range); return NO; }
    *out = v; return YES;
}

/* ---- A label / value / range grid for one field scope. ---- */
@interface D2FieldGrid : NSObject <NSTextFieldDelegate>
@property(nonatomic, strong) NSGridView* grid;
@property(nonatomic, copy) BOOL (^commit)(int index, uint64_t value);
- (instancetype)initWithScope:(int)scope columns:(unsigned)columns;
- (void)update:(const uint64_t*)values enabled:(BOOL)enabled;
- (NSTextField*)inputForKey:(const char*)key;
@end
@implementation D2FieldGrid {
    const D2CheatsField* _fields;
    unsigned _count;
    NSMutableArray<NSTextField*>* _inputs;
    uint64_t _shown[D2_CHEATS_MAX_FIELDS];
    BOOL _dirty[D2_CHEATS_MAX_FIELDS]; /* user typed since the last commit/refresh */
}
- (instancetype)initWithScope:(int)scope columns:(unsigned)columns
{
    if (!(self = [super init])) return nil;
    _count = d2_cheats_fields(scope, &_fields);
    _inputs = [NSMutableArray new];
    NSMutableArray* rows = [NSMutableArray new];
    unsigned per = (_count + columns - 1) / MAX(columns, 1u);
    for (unsigned r = 0; r < per; ++r) [rows addObject:[NSMutableArray new]];
    for (unsigned i = 0; i < _count; ++i) {
        NSTextField* label = [NSTextField labelWithString:[@(_fields[i].label) stringByAppendingString:@":"]];
        label.alignment = NSTextAlignmentRight;
        NSTextField* input = [NSTextField textFieldWithString:@""];
        input.tag = i; input.target = self; input.action = @selector(commitField:); input.delegate = self;
        input.cell.sendsActionOnEndEditing = YES; input.cell.scrollable = YES;
        input.font = [NSFont monospacedDigitSystemFontOfSize:NSFont.systemFontSize weight:NSFontWeightRegular];
        input.placeholderString = @"—";
        input.toolTip = [NSString stringWithFormat:@"%s: %@ – %@. Press Return or Tab to apply.",
            _fields[i].label, grouped(_fields[i].minimum), grouped(_fields[i].maximum)];
        [input.widthAnchor constraintEqualToConstant:150].active = YES;
        NSTextField* range = [NSTextField labelWithString:_fields[i].readonly ? @"view only" :
            [NSString stringWithFormat:@"%@ – %@", grouped(_fields[i].minimum), grouped(_fields[i].maximum)]];
        range.textColor = NSColor.secondaryLabelColor; range.font = [NSFont systemFontOfSize:NSFont.smallSystemFontSize];
        [_inputs addObject:input];
        [rows[i % per] addObjectsFromArray:@[label, input, range]];
    }
    for (NSMutableArray* row in rows) while (row.count < columns * 3) [row addObject:NSGridCell.emptyContentView];
    _grid = [NSGridView gridViewWithViews:rows];
    _grid.rowSpacing = 6; _grid.columnSpacing = 8;
    for (unsigned c = 0; c < columns; ++c) {
        [_grid columnAtIndex:c * 3].xPlacement = NSGridCellPlacementTrailing;
        if (c) [_grid columnAtIndex:c * 3].leadingPadding = 16;
    }
    for (NSInteger r = 0; r < _grid.numberOfRows; ++r) [_grid rowAtIndex:r].yPlacement = NSGridCellPlacementCenter;
    return self;
}
- (NSTextField*)inputForKey:(const char*)key
{
    for (unsigned i = 0; i < _count; ++i) if (!strcmp(_fields[i].key, key)) return _inputs[i];
    return nil;
}
- (void)update:(const uint64_t*)values enabled:(BOOL)enabled
{
    for (unsigned i = 0; i < _count; ++i) {
        NSTextField* t = _inputs[i];
        BOOL can = enabled && values && !_fields[i].readonly;
        if (t.editable != can) { t.editable = can; t.selectable = YES; }
        if (_dirty[i] && t.currentEditor) continue; /* never overwrite what the user is typing */
        _dirty[i] = NO;
        NSString* text = values ? [@(values[i]) stringValue] : @"";
        NSText* editor = t.currentEditor; /* focused but untouched: refresh in place, keep focus */
        if (editor) { if (![editor.string isEqual:text]) editor.string = text; }
        else if (![t.stringValue isEqual:text]) t.stringValue = text;
        _shown[i] = values ? values[i] : 0;
    }
}
- (void)controlTextDidChange:(NSNotification*)note
{
    NSInteger i = [note.object tag];
    if (i >= 0 && (unsigned)i < _count) _dirty[i] = YES;
}
- (void)commitField:(NSTextField*)sender
{
    unsigned i = (unsigned)sender.tag;
    if (i >= _count || !sender.editable) return;
    _dirty[i] = NO;
    uint64_t v;
    if (!parse_value(sender.stringValue, _fields[i].minimum, _fields[i].maximum, @(_fields[i].label), &v)) {
        sender.stringValue = [@(_shown[i]) stringValue]; return;
    }
    if (v == _shown[i]) return; /* Tab through unchanged fields: no write */
    if (self.commit && !self.commit((int)i, v)) ui_error(@"Edit could not be queued.");
    else _shown[i] = v;
}
@end

/* ---- Window ---- */
@interface D2CheatsWindow : NSWindow
@end
@implementation D2CheatsWindow
- (BOOL)performKeyEquivalent:(NSEvent*)event
{
    if (event.type == NSEventTypeKeyDown && event.keyCode == 122) { [self performClose:nil]; return YES; } /* F1 */
    return [super performKeyEquivalent:event];
}
- (void)cancelOperation:(id)sender { (void)sender; [self performClose:nil]; } /* Esc outside text fields */
@end

@interface D2CheatsUI : NSObject <NSWindowDelegate, NSTableViewDataSource, NSTableViewDelegate, NSMenuDelegate, NSMenuItemValidation>
@property(nonatomic, strong) D2CheatsWindow* window;
@property(nonatomic, strong) NSTabView* tabs;
@property(nonatomic, strong) NSTabView* unitTabs;
@property(nonatomic, strong) D2FieldGrid* general;
@property(nonatomic, strong) D2FieldGrid* character;
@property(nonatomic, strong) D2FieldGrid* equipment;
@property(nonatomic, strong) NSTableView* roster;
@property(nonatomic, strong) NSTableView* skills;
@property(nonatomic, strong) NSPopUpButton* equipSlot;
@property(nonatomic, strong) NSPopUpButton* multiplier;
@property(nonatomic, strong) NSMutableDictionary<NSString*, NSButton*>* toggles;
@property(nonatomic, strong) NSTextField* unitTitle;
@property(nonatomic, strong) NSTextField* status;
@property(nonatomic, strong) NSTextField* readiness;
@property(nonatomic, strong) NSMutableArray<NSTextField*>* presetInfo;
@property(nonatomic, strong) NSMutableArray<NSButton*>* presetButtons;
@property(nonatomic, strong) NSTimer* timer;
@property(nonatomic, strong) NSMenu* menu;
@end
static D2CheatsUI* s_ui;

static NSTextField* heading(NSString* text)
{
    NSTextField* t = [NSTextField labelWithString:text];
    t.font = [NSFont boldSystemFontOfSize:NSFont.systemFontSize + 1];
    return t;
}
static NSScrollView* scroller(NSView* content, NSRect frame)
{
    NSScrollView* scroll = [[NSScrollView alloc] initWithFrame:frame];
    scroll.hasVerticalScroller = YES; scroll.autohidesScrollers = YES; scroll.drawsBackground = NO;
    scroll.autoresizingMask = NSViewWidthSizable | NSViewHeightSizable;
    scroll.documentView = content;
    return scroll;
}
@interface D2Flipped : NSView
@end
@implementation D2Flipped
- (BOOL)isFlipped { return YES; }
@end
/* Grid inside a flipped document view, top-left aligned. */
static NSView* grid_document(NSArray<NSView*>* stack)
{
    D2Flipped* doc = [D2Flipped new];
    CGFloat y = 12, width = 0;
    for (NSView* v in stack) {
        NSSize size = v.fittingSize;
        v.translatesAutoresizingMaskIntoConstraints = YES;
        v.frame = NSMakeRect(16, y, size.width, size.height);
        [doc addSubview:v]; y += size.height + 12; width = MAX(width, size.width + 32);
    }
    doc.frame = NSMakeRect(0, 0, width, y);
    return doc;
}
static NSTableColumn* column(NSString* ident, NSString* title, CGFloat width, BOOL edit)
{
    NSTableColumn* c = [[NSTableColumn alloc] initWithIdentifier:ident];
    c.title = title; c.width = width; c.editable = edit;
    NSTextFieldCell* cell = [NSTextFieldCell new];
    cell.font = [NSFont monospacedDigitSystemFontOfSize:NSFont.systemFontSize weight:NSFontWeightRegular];
    cell.editable = edit; cell.lineBreakMode = NSLineBreakByTruncatingTail;
    c.dataCell = cell;
    return c;
}
static NSTableView* table(NSArray<NSTableColumn*>* columns, id owner)
{
    NSTableView* t = [NSTableView new];
    for (NSTableColumn* c in columns) [t addTableColumn:c];
    t.dataSource = owner; t.delegate = owner; t.usesAlternatingRowBackgroundColors = YES;
    t.allowsEmptySelection = YES; t.allowsMultipleSelection = NO;
    return t;
}

@implementation D2CheatsUI
- (NSView*)generalTab:(NSSize)size
{
    NSView* v = [[NSView alloc] initWithFrame:(NSRect){NSZeroPoint, size}];
    self.general = [[D2FieldGrid alloc] initWithScope:D2_CHEATS_GENERAL columns:1];
    self.general.commit = ^BOOL(int i, uint64_t value) {
        const D2CheatsField* f; d2_cheats_fields(D2_CHEATS_GENERAL, &f);
        return d2_cheats_set_general(f[i].key, value, s_snap.generation) == 0;
    };
    self.toggles = [NSMutableDictionary new];
    NSMutableArray* boxes = [NSMutableArray new];
    for (NSArray* t in @[@[@"hp_lock", @"Infinite HP (allies)"], @[@"sp_lock", @"Infinite SP (allies)"],
                         @[@"one_hit", @"One-hit kills (enemies)"], @[@"free_shop", @"Free item-shop purchases"]]) {
        NSButton* b = [NSButton checkboxWithTitle:t[1] target:self action:@selector(toggle:)];
        b.identifier = t[0]; self.toggles[t[0]] = b; [boxes addObject:@[b]];
    }
    self.multiplier = [NSPopUpButton new];
    for (unsigned i = 0; i < sizeof s_multipliers / sizeof *s_multipliers; ++i)
        [self.multiplier addItemWithTitle:[NSString stringWithFormat:@"%u×", s_multipliers[i]]];
    self.multiplier.target = self; self.multiplier.action = @selector(pickMultiplier:);
    NSButton* off = [NSButton buttonWithTitle:@"Disable All Cheats" target:self action:@selector(disableAll:)];
    NSGridView* toggles = [NSGridView gridViewWithViews:@[
        @[self.toggles[@"hp_lock"], self.toggles[@"one_hit"]],
        @[self.toggles[@"sp_lock"], self.toggles[@"free_shop"]],
        @[[NSTextField labelWithString:@"EXP gain multiplier:"], self.multiplier], @[off, NSGridCell.emptyContentView]]];
    toggles.rowSpacing = 8; toggles.columnSpacing = 24;
    NSTextField* note = [NSTextField wrappingLabelWithString:@"Values apply on Return or Tab and are written by the game thread on the next frame. Save in-game to keep them; presets store these values and toggles."];
    note.textColor = NSColor.secondaryLabelColor; note.preferredMaxLayoutWidth = 560;
    NSScrollView* s = scroller(grid_document(@[heading(@"Values"), self.general.grid, heading(@"Cheats"), toggles, note]), v.bounds);
    [v addSubview:s];
    return v;
}
- (NSView*)charactersTab:(NSSize)size
{
    NSView* v = [[NSView alloc] initWithFrame:(NSRect){NSZeroPoint, size}];
    self.roster = table(@[column(@"index", @"#", 34, NO), column(@"name", @"Name", 116, NO),
                          column(@"level", @"Lv", 46, NO), column(@"class", @"Class", 44, NO)], self);
    NSScrollView* left = scroller(self.roster, NSMakeRect(4, 4, 290, size.height - 8));
    left.hasVerticalScroller = YES; left.borderType = NSBezelBorder; left.autoresizingMask = NSViewHeightSizable;
    [v addSubview:left];
    self.unitTitle = heading(@"Select a unit");
    self.unitTitle.frame = NSMakeRect(304, size.height - 26, size.width - 310, 22);
    [v addSubview:self.unitTitle];
    self.unitTabs = [[NSTabView alloc] initWithFrame:NSMakeRect(298, 0, size.width - 298, size.height - 28)];
    NSSize inner = self.unitTabs.contentRect.size;
    __weak D2CheatsUI* weak = self;
    self.character = [[D2FieldGrid alloc] initWithScope:D2_CHEATS_CHARACTER columns:1];
    self.character.commit = ^BOOL(int i, uint64_t value) {
        const D2CheatsField* f; d2_cheats_fields(D2_CHEATS_CHARACTER, &f);
        return s_snap.unit >= 0 && d2_cheats_set_character((unsigned)s_snap.unit, f[i].key, value, s_snap.generation) == 0;
    };
    NSTextField* note = [NSTextField wrappingLabelWithString:@"Level edits also set EXP from the class table. Class/base-stat changes refresh after re-entering a map; save in-game to keep edits."];
    note.textColor = NSColor.secondaryLabelColor; note.preferredMaxLayoutWidth = 480;
    NSTabViewItem* stats = [NSTabViewItem new];
    stats.label = @"Stats"; stats.view = [[NSView alloc] initWithFrame:(NSRect){NSZeroPoint, inner}];
    [stats.view addSubview:scroller(grid_document(@[self.character.grid, note]), stats.view.bounds)];
    [self.unitTabs addTabViewItem:stats];
    self.skills = table(@[column(@"slot", @"#", 34, NO), column(@"skill_id", @"Skill ID", 100, YES),
        column(@"skill_level", @"Level", 80, YES), column(@"skill_exp", @"EXP", 140, YES), column(@"skill_boost", @"Boost", 80, YES)], self);
    NSTabViewItem* skills = [NSTabViewItem new];
    skills.label = @"Skills"; skills.view = [[NSView alloc] initWithFrame:(NSRect){NSZeroPoint, inner}];
    NSScrollView* ss = scroller(self.skills, NSMakeRect(6, 40, inner.width - 12, inner.height - 46)); ss.borderType = NSBezelBorder;
    [skills.view addSubview:ss];
    NSTextField* sn = [NSTextField wrappingLabelWithString:@"Double-click a cell to edit. Skill IDs must already exist in the loaded roster; duplicates are rejected."];
    sn.textColor = NSColor.secondaryLabelColor; sn.frame = NSMakeRect(6, 2, inner.width - 12, 34);
    [skills.view addSubview:sn];
    [self.unitTabs addTabViewItem:skills];
    self.equipment = [[D2FieldGrid alloc] initWithScope:D2_CHEATS_ITEM columns:1];
    self.equipment.commit = ^BOOL(int i, uint64_t value) {
        const D2CheatsField* f; d2_cheats_fields(D2_CHEATS_ITEM, &f);
        D2CheatsUI* ui = weak;
        return s_snap.unit >= 0 && d2_cheats_set_equipment((unsigned)s_snap.unit, (unsigned)ui.equipSlot.indexOfSelectedItem,
            f[i].key, value, s_snap.generation) == 0;
    };
    self.equipSlot = [NSPopUpButton new];
    for (int i = 1; i <= D2_CHEATS_EQUIP_SLOTS; ++i) [self.equipSlot addItemWithTitle:[NSString stringWithFormat:@"Slot %d", i]];
    self.equipSlot.target = self; self.equipSlot.action = @selector(refresh);
    [self.equipSlot.widthAnchor constraintEqualToConstant:250].active = YES;
    NSButton* items = [NSButton buttonWithTitle:@"Open Item Editor…" target:self action:@selector(itemEditor:)];
    items.enabled = d2_item_editor_show != NULL;
    NSGridView* bar = [NSGridView gridViewWithViews:@[@[[NSTextField labelWithString:@"Equipped item:"], self.equipSlot, items]]];
    NSTabViewItem* equip = [NSTabViewItem new];
    equip.label = @"Equipment"; equip.view = [[NSView alloc] initWithFrame:(NSRect){NSZeroPoint, inner}];
    [equip.view addSubview:scroller(grid_document(@[bar, self.equipment.grid]), equip.view.bounds)];
    [self.unitTabs addTabViewItem:equip];
    [v addSubview:self.unitTabs];
    return v;
}
- (NSView*)presetsTab:(NSSize)size
{
    NSView* v = [[NSView alloc] initWithFrame:(NSRect){NSZeroPoint, size}];
    self.presetInfo = [NSMutableArray new]; self.presetButtons = [NSMutableArray new];
    NSMutableArray* rows = [NSMutableArray new];
    for (unsigned i = 0; i < D2_CHEATS_PRESET_SLOTS; ++i) {
        NSTextField* name = [NSTextField labelWithString:i ? [NSString stringWithFormat:@"Preset %u", i] : @"Default"];
        name.font = [NSFont boldSystemFontOfSize:NSFont.systemFontSize];
        NSTextField* info = [NSTextField labelWithString:@""]; info.textColor = NSColor.secondaryLabelColor;
        [info.widthAnchor constraintEqualToConstant:360].active = YES;
        NSButton* save = [NSButton buttonWithTitle:@"Save" target:self action:@selector(preset:)];
        NSButton* load = [NSButton buttonWithTitle:@"Load" target:self action:@selector(preset:)];
        save.tag = (NSInteger)i * 2 + 1; load.tag = (NSInteger)i * 2;
        [self.presetInfo addObject:info]; [self.presetButtons addObjectsFromArray:@[save, load]];
        [rows addObject:@[name, info, save, load]];
    }
    NSGridView* grid = [NSGridView gridViewWithViews:rows];
    grid.rowSpacing = 10; grid.columnSpacing = 12;
    NSTextField* note = [NSTextField wrappingLabelWithString:@"Presets store the General values, the first unit's Mana and the cheat toggles. Loading validates the whole file before writing anything. Character and item edits persist through the game's own save."];
    note.textColor = NSColor.secondaryLabelColor; note.preferredMaxLayoutWidth = 620;
    [v addSubview:scroller(grid_document(@[heading(@"Presets"), grid, note]), v.bounds)];
    return v;
}
- (void)build
{
    self.window = [[D2CheatsWindow alloc] initWithContentRect:NSMakeRect(0, 0, 900, 600)
        styleMask:NSWindowStyleMaskTitled | NSWindowStyleMaskClosable | NSWindowStyleMaskMiniaturizable
        backing:NSBackingStoreBuffered defer:NO];
    self.window.title = @"Disgaea D2 Cheats"; self.window.releasedWhenClosed = NO; self.window.delegate = self;
    self.window.collectionBehavior = NSWindowCollectionBehaviorFullScreenAuxiliary | NSWindowCollectionBehaviorMoveToActiveSpace;
    self.window.frameAutosaveName = @"D2CheatsWindow";
    NSView* content = self.window.contentView;
    self.tabs = [[NSTabView alloc] initWithFrame:NSMakeRect(6, 34, 888, 560)];
    NSArray* names = @[@"General", @"Characters", @"Presets"];
    NSSize size = self.tabs.contentRect.size;
    NSArray* views = @[[self generalTab:size], [self charactersTab:size], [self presetsTab:size]];
    for (NSUInteger i = 0; i < names.count; ++i) {
        NSTabViewItem* item = [[NSTabViewItem alloc] initWithIdentifier:[names[i] lowercaseString]];
        item.label = names[i]; item.view = views[i]; [self.tabs addTabViewItem:item];
    }
    [content addSubview:self.tabs];
    self.readiness = [NSTextField labelWithString:@""]; self.readiness.frame = NSMakeRect(14, 9, 260, 18);
    self.readiness.font = [NSFont systemFontOfSize:NSFont.smallSystemFontSize weight:NSFontWeightSemibold];
    self.status = [NSTextField labelWithString:@""]; self.status.frame = NSMakeRect(270, 9, 616, 18);
    self.status.font = [NSFont systemFontOfSize:NSFont.smallSystemFontSize]; self.status.lineBreakMode = NSLineBreakByTruncatingTail;
    [content addSubview:self.readiness]; [content addSubview:self.status];
    self.window.autorecalculatesKeyViewLoop = YES;
    [self.window center];
}
- (void)show:(NSString*)tab
{
    if (!self.window) [self build];
    if (tab) [self.tabs selectTabViewItemWithIdentifier:tab];
    if (s_game) self.window.level = MAX(s_game.level, NSNormalWindowLevel);
    if (!self.timer) {
        self.timer = [NSTimer timerWithTimeInterval:0.25 target:self selector:@selector(refresh) userInfo:nil repeats:YES];
        [NSRunLoop.mainRunLoop addTimer:self.timer forMode:NSRunLoopCommonModes];
    }
    [self refresh];
    [NSApp activateIgnoringOtherApps:YES];
    [self.window makeKeyAndOrderFront:nil];
}
- (void)windowWillClose:(NSNotification*)note
{
    (void)note;
    [self.timer invalidate]; self.timer = nil;
    [self.window makeFirstResponder:nil];
    if (s_game) [s_game makeKeyAndOrderFront:nil]; /* keyboard returns to the game */
}
- (void)refresh
{
    static BOOL busy; /* table selection callbacks re-enter */
    d2_cheats_snapshot(&s_snap);
    if (!self.window.visible || busy) return;
    busy = YES;
    BOOL can = editable();
    [self.general update:s_snap.serial && s_snap.party_count ? s_snap.general : NULL enabled:can];
    for (NSString* key in self.toggles) {
        int on = [key isEqual:@"hp_lock"] ? s_snap.hp_lock : [key isEqual:@"sp_lock"] ? s_snap.sp_lock :
                 [key isEqual:@"one_hit"] ? s_snap.one_hit : s_snap.free_shop;
        self.toggles[key].state = on ? NSControlStateValueOn : NSControlStateValueOff;
        self.toggles[key].enabled = s_snap.supported && s_snap.verified;
    }
    for (NSInteger i = 0; i < self.multiplier.numberOfItems; ++i)
        if (s_multipliers[i] == s_snap.exp_multiplier) [self.multiplier selectItemAtIndex:i];
    self.multiplier.enabled = s_snap.supported && s_snap.verified;
    /* Roster: reload only when it changed, keeping selection/scroll. */
    static unsigned shown_count; static char shown_hash[64];
    char hash[64]; snprintf(hash, sizeof hash, "%u:%llu", s_snap.party_count, (unsigned long long)s_snap.generation);
    unsigned long long sum = 0;
    for (unsigned i = 0; i < s_snap.party_count; ++i) sum = sum * 31 + s_snap.party[i].level * 7 + s_snap.party[i].class_id + (unsigned char)s_snap.party[i].name[0];
    snprintf(hash + strlen(hash), sizeof hash - strlen(hash), ":%llx", sum);
    if (shown_count != s_snap.party_count || strcmp(hash, shown_hash)) {
        NSInteger row = self.roster.selectedRow;
        shown_count = s_snap.party_count; snprintf(shown_hash, sizeof shown_hash, "%s", hash);
        [self.roster reloadData];
        if (row >= 0 && row < (NSInteger)s_snap.party_count) [self.roster selectRowIndexes:[NSIndexSet indexSetWithIndex:row] byExtendingSelection:NO];
        else if (s_snap.party_count) [self.roster selectRowIndexes:[NSIndexSet indexSetWithIndex:0] byExtendingSelection:NO];
    }
    NSInteger unit = self.roster.selectedRow;
    BOOL detail = unit >= 0 && s_snap.unit == unit;
    if (unit >= 0 && s_snap.unit != unit) d2_cheats_select_unit((int)unit);
    self.unitTitle.stringValue = detail ? [NSString stringWithFormat:@"%s — Lv %u, class %u", s_snap.party[unit].name,
        s_snap.party[unit].level, s_snap.party[unit].class_id] : s_snap.party_count ? @"Loading unit…" : @"No party loaded";
    [self.character update:detail ? s_snap.character : NULL enabled:can];
    if (self.skills.editedRow < 0) [self.skills reloadData];
    NSInteger slot = self.equipSlot.indexOfSelectedItem;
    for (int i = 0; i < D2_CHEATS_EQUIP_SLOTS; ++i) {
        const D2CheatsItem* item = &s_snap.equipment[i];
        NSString* title = [NSString stringWithFormat:@"Slot %d: %@", i + 1, detail && item->id ? @(item->name) : @"(empty)"];
        if (![[self.equipSlot itemAtIndex:i].title isEqual:title]) [self.equipSlot itemAtIndex:i].title = title;
    }
    BOOL equipped = detail && slot >= 0 && s_snap.equipment[slot].id;
    [self.equipment update:equipped ? s_snap.equipment[slot].values : NULL enabled:can];
    for (unsigned i = 0; i < D2_CHEATS_PRESET_SLOTS; ++i) {
        NSString* path = @(d2_cheats_preset_path(i));
        NSDictionary* attrs = path.length ? [NSFileManager.defaultManager attributesOfItemAtPath:path error:nil] : nil;
        NSString* text = attrs ? [NSString stringWithFormat:@"Saved %@", [NSDateFormatter localizedStringFromDate:attrs.fileModificationDate
            dateStyle:NSDateFormatterMediumStyle timeStyle:NSDateFormatterShortStyle]] : @"Empty";
        if (![self.presetInfo[i].stringValue isEqual:text]) { self.presetInfo[i].stringValue = text; self.presetInfo[i].toolTip = path; }
        self.presetButtons[i * 2].enabled = can;
        self.presetButtons[i * 2 + 1].enabled = can && attrs;
    }
    NSString* ready = !s_snap.serial ? @"Waiting for the game…" : !s_snap.supported ? @"Unsupported EBOOT" :
        !s_snap.verified ? [NSString stringWithFormat:@"%s: not validated (read only)", s_snap.version] :
        s_snap.ready ? [NSString stringWithFormat:@"● %s · editing live save", s_snap.version] :
        s_snap.party_count ? @"Saving/loading… edits paused" : @"Load a save to edit";
    self.readiness.stringValue = ready;
    self.readiness.textColor = s_snap.ready && s_snap.verified ? NSColor.systemGreenColor : NSColor.secondaryLabelColor;
    BOOL local = s_local_error && -s_local_error_time.timeIntervalSinceNow < 4;
    self.status.stringValue = local ? s_local_error : @(s_snap.status);
    self.status.textColor = local ? NSColor.systemRedColor : NSColor.labelColor;
    busy = NO;
}
/* Table data: roster and selected unit's skills. */
- (NSInteger)numberOfRowsInTableView:(NSTableView*)t
{
    if (t == self.roster) return s_snap.party_count;
    return s_snap.unit >= 0 && s_snap.unit == self.roster.selectedRow ? s_snap.skill_count : 0;
}
- (id)tableView:(NSTableView*)t objectValueForTableColumn:(NSTableColumn*)c row:(NSInteger)row
{
    NSString* k = c.identifier;
    if (t == self.roster) {
        if (row >= (NSInteger)s_snap.party_count) return nil;
        if ([k isEqual:@"index"]) return @(row + 1);
        if ([k isEqual:@"name"]) return @(s_snap.party[row].name);
        return @([k isEqual:@"level"] ? s_snap.party[row].level : s_snap.party[row].class_id);
    }
    if (row >= (NSInteger)s_snap.skill_count) return nil;
    const D2CheatsSkill* s = &s_snap.skills[row];
    if ([k isEqual:@"slot"]) return @(row + 1);
    if ([k isEqual:@"skill_id"]) return @(s->id);
    if ([k isEqual:@"skill_level"]) return @(s->level);
    if ([k isEqual:@"skill_exp"]) return @(s->exp);
    return @(s->boost);
}
- (BOOL)tableView:(NSTableView*)t shouldEditTableColumn:(NSTableColumn*)c row:(NSInteger)row
{
    (void)row; return t == self.skills && c.editable && editable();
}
- (void)tableView:(NSTableView*)t setObjectValue:(id)value forTableColumn:(NSTableColumn*)c row:(NSInteger)row
{
    if (t != self.skills || s_snap.unit < 0 || row >= (NSInteger)s_snap.skill_count) return;
    NSString* k = c.identifier;
    uint64_t maximum = [k isEqual:@"skill_id"] ? 32767 : [k isEqual:@"skill_level"] ? 99 : [k isEqual:@"skill_exp"] ? 999999999 : 9;
    uint64_t v;
    if (!parse_value([value description], [k isEqual:@"skill_id"] ? 1 : 0, maximum, c.title, &v)) return;
    if (d2_cheats_set_skill((unsigned)s_snap.unit, (unsigned)row, k.UTF8String, v, s_snap.generation)) ui_error(@"Edit could not be queued.");
}
- (void)tableViewSelectionDidChange:(NSNotification*)note
{
    if (note.object == self.roster) { d2_cheats_select_unit((int)self.roster.selectedRow); [self.skills reloadData]; [self refresh]; }
}
/* Actions shared by the window and the menu bar. */
- (void)toggle:(id)sender
{
    NSString* key = [sender isKindOfClass:NSMenuItem.class] ? [sender representedObject] : [sender identifier];
    int on = [key isEqual:@"hp_lock"] ? s_snap.hp_lock : [key isEqual:@"sp_lock"] ? s_snap.sp_lock :
             [key isEqual:@"one_hit"] ? s_snap.one_hit : s_snap.free_shop;
    if (d2_cheats_set_toggle(key.UTF8String, !on)) { ui_error(@"Toggle could not be queued."); return; }
    /* Optimistic until the next snapshot confirms. */
    if ([key isEqual:@"hp_lock"]) s_snap.hp_lock = !on; else if ([key isEqual:@"sp_lock"]) s_snap.sp_lock = !on;
    else if ([key isEqual:@"one_hit"]) s_snap.one_hit = !on; else s_snap.free_shop = !on;
}
- (void)pickMultiplier:(id)sender
{
    unsigned m = [sender isKindOfClass:NSMenuItem.class] ? (unsigned)[sender tag] : s_multipliers[[sender indexOfSelectedItem]];
    if (!d2_cheats_set_exp_multiplier(m)) s_snap.exp_multiplier = m;
}
- (void)disableAll:(id)sender
{
    (void)sender;
    if (!d2_cheats_disable_all()) { s_snap.hp_lock = s_snap.sp_lock = s_snap.one_hit = s_snap.free_shop = 0; s_snap.exp_multiplier = 1; }
}
- (void)preset:(id)sender
{
    NSInteger tag = [sender tag];
    unsigned slot = (unsigned)tag / 2; BOOL save = tag & 1;
    if (!save) {
        NSAlert* a = [NSAlert new];
        a.messageText = [NSString stringWithFormat:@"Load %@?", slot ? [NSString stringWithFormat:@"Preset %u", slot] : @"the default preset"];
        a.informativeText = @"This overwrites HL, Bonus Gauge, Cheat Shop values, the first unit's Mana and the cheat toggles.";
        [a addButtonWithTitle:@"Load"]; [a addButtonWithTitle:@"Cancel"];
        if ([a runModal] != NSAlertFirstButtonReturn) return;
    }
    if (d2_cheats_preset(save, slot)) ui_error(@"Preset action could not be queued.");
}
- (void)itemEditor:(id)sender { (void)sender; if (d2_item_editor_show) d2_item_editor_show(); }
- (void)openTab:(NSMenuItem*)sender { [self show:sender.representedObject]; }
- (void)toggleWindow:(id)sender
{
    (void)sender;
    if (self.window.visible && self.window.isKeyWindow) [self.window performClose:nil];
    else [self show:nil];
}
- (void)menuNeedsUpdate:(NSMenu*)menu { (void)menu; d2_cheats_snapshot(&s_snap); }
- (BOOL)validateMenuItem:(NSMenuItem*)item
{
    SEL a = item.action;
    if (a == @selector(toggle:)) {
        NSString* key = item.representedObject;
        int on = [key isEqual:@"hp_lock"] ? s_snap.hp_lock : [key isEqual:@"sp_lock"] ? s_snap.sp_lock :
                 [key isEqual:@"one_hit"] ? s_snap.one_hit : s_snap.free_shop;
        item.state = on ? NSControlStateValueOn : NSControlStateValueOff;
        return s_snap.supported && s_snap.verified;
    }
    if (a == @selector(pickMultiplier:)) {
        item.state = (unsigned)item.tag == s_snap.exp_multiplier ? NSControlStateValueOn : NSControlStateValueOff;
        return s_snap.supported && s_snap.verified;
    }
    if (a == @selector(disableAll:)) return s_snap.supported;
    if (a == @selector(preset:)) {
        if (!(item.tag & 1)) {
            NSString* path = @(d2_cheats_preset_path((unsigned)item.tag / 2));
            if (!path.length || ![NSFileManager.defaultManager fileExistsAtPath:path]) return NO;
        }
        return editable();
    }
    if (a == @selector(itemEditor:)) return d2_item_editor_show != NULL;
    if (a == @selector(closeWindow:)) return self.window.isKeyWindow;
    if (a == @selector(noop:)) {
        item.title = !s_snap.serial ? @"Waiting for the game…" : !s_snap.supported ? @"Unsupported EBOOT" :
            !s_snap.verified ? @"Version not validated: read only" :
            s_snap.ready ? [NSString stringWithFormat:@"Game %s · save loaded, %u units", s_snap.version, s_snap.party_count] :
            @"No save loaded";
        return NO;
    }
    return YES;
}
- (void)closeWindow:(id)sender { (void)sender; [self.window performClose:nil]; }
- (void)noop:(id)sender { (void)sender; }
@end

static NSMenuItem* add(NSMenu* menu, NSString* title, SEL action, NSString* key)
{
    NSMenuItem* item = [menu addItemWithTitle:title action:action keyEquivalent:key ?: @""];
    item.target = s_ui; return item;
}

/* Called by d2_settings.m whenever it (re)builds the menu bar. */
void d2_cheats_menu_install(NSMenu* main, NSWindow* game)
{
    if (!s_ui) s_ui = [D2CheatsUI new];
    s_game = game;
    NSMenu* m = [[NSMenu alloc] initWithTitle:@"Cheats"];
    m.delegate = s_ui;
    NSMenuItem* open = add(m, @"Cheats Window…", @selector(toggleWindow:), @"c");
    open.keyEquivalentModifierMask = NSEventModifierFlagCommand | NSEventModifierFlagShift;
    open.toolTip = @"Also F1 in the game window.";
    add(m, @"Close Cheats Window", @selector(closeWindow:), @"w");
    [m addItem:NSMenuItem.separatorItem];
    for (NSArray* t in @[@[@"hp_lock", @"Infinite HP"], @[@"sp_lock", @"Infinite SP"],
                         @[@"one_hit", @"One-Hit Kills"], @[@"free_shop", @"Free Item Shop"]])
        add(m, t[1], @selector(toggle:), nil).representedObject = t[0];
    NSMenuItem* expItem = [m addItemWithTitle:@"EXP Multiplier" action:nil keyEquivalent:@""];
    expItem.submenu = [[NSMenu alloc] initWithTitle:@"EXP Multiplier"];
    for (unsigned i = 0; i < sizeof s_multipliers / sizeof *s_multipliers; ++i)
        add(expItem.submenu, [NSString stringWithFormat:@"%u×", s_multipliers[i]], @selector(pickMultiplier:), nil).tag = s_multipliers[i];
    add(m, @"Disable All Cheats", @selector(disableAll:), nil);
    [m addItem:NSMenuItem.separatorItem];
    add(m, @"HL, Mana & Cheat Shop…", @selector(openTab:), nil).representedObject = @"general";
    add(m, @"Characters…", @selector(openTab:), nil).representedObject = @"characters";
    add(m, @"Item Editor…", @selector(itemEditor:), nil);
    NSMenuItem* presets = [m addItemWithTitle:@"Presets" action:nil keyEquivalent:@""];
    presets.submenu = [[NSMenu alloc] initWithTitle:@"Presets"];
    for (unsigned i = 0; i < D2_CHEATS_PRESET_SLOTS; ++i) {
        NSString* name = i ? [NSString stringWithFormat:@"Preset %u", i] : @"Default Preset";
        add(presets.submenu, [@"Save " stringByAppendingString:name], @selector(preset:), nil).tag = i * 2 + 1;
        add(presets.submenu, [@"Load " stringByAppendingString:name], @selector(preset:), nil).tag = i * 2;
        if (!i) [presets.submenu addItem:NSMenuItem.separatorItem];
    }
    [presets.submenu addItem:NSMenuItem.separatorItem];
    add(presets.submenu, @"Manage Presets…", @selector(openTab:), nil).representedObject = @"presets";
    [m addItem:NSMenuItem.separatorItem];
    add(m, @"", @selector(noop:), nil);
    NSMenuItem* top = [[NSMenuItem alloc] initWithTitle:@"Cheats" action:nil keyEquivalent:@""];
    top.submenu = m;
    NSInteger game_index = [main indexOfItemWithTitle:@"Game"];
    [main insertItem:top atIndex:game_index >= 0 ? game_index + 1 : main.numberOfItems];
    s_ui.menu = m;
}

void d2_cheats_window_toggle(void)
{
    dispatch_block_t run = ^{ if (!s_ui) s_ui = [D2CheatsUI new]; [s_ui toggleWindow:nil]; };
    if (NSThread.isMainThread) run(); else dispatch_async(dispatch_get_main_queue(), run);
}

/* ---- Test automation (opt-in env, AppKit main thread) ----
 * D2_CHEATS_UI_OPEN=general|characters|presets opens the window once a save is loaded.
 * D2_CHEATS_UI_TEST_HL=<n> types n into the HL field and commits it like Return.
 * D2_CHEATS_UI_TEST_MENU=1 toggles Infinite HP through the Cheats menu item.
 * D2_CHEATS_UI_SHOT_DIR=<dir> writes PNGs of every tab and logs the window id.
 * D2_CHEATS_UI_WAIT_UNITS=<n> waits for a party of at least n (the loaded save). */
static void shot(NSString* dir, NSString* name)
{
    NSView* v = s_ui.window.contentView.superview; /* frame view: title bar + window background */
    NSBitmapImageRep* rep = [v bitmapImageRepForCachingDisplayInRect:v.bounds];
    [v cacheDisplayInRect:v.bounds toBitmapImageRep:rep];
    NSString* path = [dir stringByAppendingPathComponent:[name stringByAppendingString:@".png"]];
    [[rep representationUsingType:NSBitmapImageFileTypePNG properties:@{}] writeToFile:path atomically:YES];
    fprintf(stderr, "[D2 cheats UI] shot %s window=%ld\n", path.UTF8String, (long)s_ui.window.windowNumber);
}
__attribute__((constructor)) static void d2_cheats_ui_automation(void)
{
    const char* open = getenv("D2_CHEATS_UI_OPEN");
    if (!open || !*open) return;
    NSString* tab = @(open);
    const char* hl = getenv("D2_CHEATS_UI_TEST_HL");
    const char* menu = getenv("D2_CHEATS_UI_TEST_MENU");
    const char* dir = getenv("D2_CHEATS_UI_SHOT_DIR");
    const char* units = getenv("D2_CHEATS_UI_WAIT_UNITS"); /* skip the pre-load default party */
    unsigned wait_units = units ? (unsigned)strtoul(units, NULL, 10) : 1;
    __block int phase = 0; __block NSDate* since = nil;
    dispatch_async(dispatch_get_main_queue(), ^{
        NSTimer* t = [NSTimer timerWithTimeInterval:0.5 repeats:YES block:^(NSTimer* timer) {
            D2CheatsSnapshot snap; d2_cheats_snapshot(&snap);
            if (!snap.ready || snap.party_count < wait_units) { since = nil; return; }
            if (!since) { since = NSDate.date; return; }
            if (-since.timeIntervalSinceNow < 3) return; /* let the loaded save settle */
            switch (phase++) {
            case 0: if (!s_ui) s_ui = [D2CheatsUI new];
                [s_ui show:tab];
                fprintf(stderr, "[D2 cheats UI] opened tab=%s units=%u HL=%llu\n", open, snap.party_count, (unsigned long long)snap.general[0]); break;
            case 1:
                if (hl) {
                    NSTextField* f = [s_ui.general inputForKey:"hl"];
                    f.stringValue = @(hl); [f sendAction:f.action to:f.target];
                    fprintf(stderr, "[D2 cheats UI] test: HL field committed '%s'\n", hl);
                }
                if (menu) {
                    NSInteger i = [s_ui.menu indexOfItemWithTitle:@"Infinite HP"];
                    [s_ui.menu update]; [s_ui.menu performActionForItemAtIndex:i];
                    fprintf(stderr, "[D2 cheats UI] test: menu Infinite HP activated\n");
                }
                break;
            case 2: case 3: break; /* PPU applies and republishes */
            case 4:
                fprintf(stderr, "[D2 cheats UI] test: snapshot HL=%llu hp_lock=%d status='%s'\n",
                    (unsigned long long)s_snap.general[0], s_snap.hp_lock, s_snap.status);
                if (dir) shot(@(dir), @"general");
                break;
            case 5: [s_ui.tabs selectTabViewItemWithIdentifier:@"characters"]; break;
            case 6: if (dir) shot(@(dir), @"characters-stats"); [s_ui.unitTabs selectTabViewItemAtIndex:1]; break;
            case 7: if (dir) shot(@(dir), @"characters-skills"); [s_ui.unitTabs selectTabViewItemAtIndex:2]; break;
            case 8: if (dir) shot(@(dir), @"characters-equipment"); [s_ui.tabs selectTabViewItemWithIdentifier:@"presets"]; break;
            case 9: if (dir) shot(@(dir), @"presets"); [s_ui.tabs selectTabViewItemWithIdentifier:tab]; [s_ui.unitTabs selectTabViewItemAtIndex:0]; break;
            case 10: /* the menu bar Cheats menu as AppKit validates it right now */
                [s_ui menuNeedsUpdate:s_ui.menu]; [s_ui.menu update];
                for (NSMenuItem* item in s_ui.menu.itemArray) if (!item.isSeparatorItem)
                    fprintf(stderr, "[D2 cheats UI] menu '%s'%s%s%s\n", item.title.UTF8String,
                        item.state == NSControlStateValueOn ? " [checked]" : "", item.enabled ? "" : " [disabled]",
                        item.submenu ? " >" : "");
                break;
            default: [timer invalidate]; fprintf(stderr, "[D2 cheats UI] automation done\n"); break;
            }
        }];
        [NSRunLoop.mainRunLoop addTimer:t forMode:NSRunLoopCommonModes];
    });
}
