/* Native Item Editor window (AT). AppKit main thread only. All game access
 * goes through d2_items.h: published snapshots in, queued actions out. Icons
 * and names come from the user's own game at runtime (START.dat item.txf and
 * the in-memory item/innocent tables); decoded icons are cached under
 * ~/Library/Application Support/DisgaeaD2Recomp/cache/. */
#import <AppKit/AppKit.h>
#include <errno.h>
#include <stdlib.h>
#include <sys/stat.h>
#include "d2_items.h"
#include "d2_cheats.h"

static const char* kStat[] = {"HP", "SP", "ATK", "DEF", "INT", "RES", "HIT", "SPD"};
static NSString* grade_name(unsigned g) { return g == 2 ? @"Legendary" : g == 1 ? @"Rare" : @"Common"; }
static NSString* str(const char* s) { NSString* v = s ? [NSString stringWithUTF8String:s] : nil; return v ?: @""; }
/* Effect families in HABIT.dat; keep the catalog's order and real type IDs.
 * Unrecognized types stay visible in their own group. */
static unsigned innocent_group(unsigned id)
{
    if (id >= 1 && id <= 8) return 1;       // single-stat bonuses
    if (id >= 11 && id <= 17) return 2;     // dual-stat bonuses
    if (id >= 21 && id <= 25) return 3;     // status-inflicting attacks
    if (id == 26) return 4;                // critical hits (Professional)
    if (id >= 41 && id <= 45) return 5;     // status resistance
    if (id >= 46 && id <= 48) return 6;     // elemental resistance
    if (id >= 60 && id <= 65) return 7;     // rewards and growth
    if (id >= 131 && id <= 134) return 8;   // Item World bosses
    if (id >= 201 && id <= 227) return 9;   // unique special effects
    if (id >= 250 && id <= 256) return 10;  // special shop / DLC effects
    return 0;
}
static NSString* grouped(long long v)
{
    return [NSNumberFormatter localizedStringFromNumber:@(v) numberStyle:NSNumberFormatterDecimalStyle];
}
static BOOL parse(NSString* text, long long lo, long long hi, NSString* label, long long* out, NSString** error)
{
    NSString* digits = [[text componentsSeparatedByCharactersInSet:
        [NSCharacterSet characterSetWithCharactersInString:@", _"]] componentsJoinedByString:@""];
    char* end = NULL; errno = 0;
    long long v = strtoll(digits.UTF8String, &end, 10);
    if (!digits.length || errno || *end || v < lo || v > hi) {
        *error = [NSString stringWithFormat:@"%@ must be a whole number from %@ to %@.", label, grouped(lo), grouped(hi)];
        return NO;
    }
    *out = v; return YES;
}

@interface D2ItemFlipped : NSView
@end
@implementation D2ItemFlipped
- (BOOL)isFlipped { return YES; }
@end

@interface D2ItemEditor : NSObject <NSWindowDelegate, NSTableViewDataSource, NSTableViewDelegate, NSTextFieldDelegate, NSSearchFieldDelegate>
@property(nonatomic, strong) NSWindow* window;
@property(nonatomic, strong) NSTableView* table;
@property(nonatomic, strong) NSSearchField* search;
@property(nonatomic, strong) NSPopUpButton* filter;
@property(nonatomic, strong) NSButton *addButton, *duplicateButton, *deleteButton, *applyButton, *revertButton, *baseButton;
@property(nonatomic, strong) NSImageView* bigIcon;
@property(nonatomic, strong) NSTextField *title, *subtitle, *details, *status, *countLabel, *gradeLabel;
@property(nonatomic, strong) NSMutableDictionary<NSString*, NSTextField*>* inputs;
@property(nonatomic, strong) NSMutableArray<NSTextField*>* totals;
@property(nonatomic, strong) NSMutableArray<NSPopUpButton*>* innocentTypes;
@property(nonatomic, strong) NSMutableArray<NSTextField*>* innocentLevels;
@property(nonatomic, strong) NSMutableArray<NSButton*>* innocentSubdued;
@property(nonatomic, strong) NSMutableArray<NSTextField*>* innocentMax;
@property(nonatomic, strong) NSView* detail;
@property(nonatomic, strong) NSTimer* timer;
@property(nonatomic, strong) NSMutableArray<NSNumber*>* rows;
@property(nonatomic, strong) NSMutableDictionary<NSNumber*, NSImage*>* icons;
@property(nonatomic, strong) NSString* iconError;
@property(nonatomic, strong) NSString* localStatus;
/* picker */
@property(nonatomic, strong) NSPanel* picker;
@property(nonatomic, strong) NSTableView* pickerTable;
@property(nonatomic, strong) NSSearchField* pickerSearch;
@property(nonatomic, strong) NSMutableArray<NSNumber*>* pickerRows;
@property(nonatomic) BOOL pickerReplace;
@property(nonatomic) BOOL dirty;
@property(nonatomic) int selUnit;
@property(nonatomic) unsigned selSlot, selId;
@property(nonatomic) uint64_t shownSerial, catalogSerial;
@property(nonatomic) int lastAdded;
@end

static D2ItemEditor* s_editor;
static D2ItemsSnapshot* s_snap;
static D2ItemsCatalog* s_cat;
static CGImageRef s_sheet;

@implementation D2ItemEditor

/* ---------------------------------------------------------------- icons */
- (void)loadIcons
{
    if (s_sheet) return;
    const char* vfs = getenv("PS3_VFS_ROOT");
    NSString* start = [str(vfs && *vfs ? vfs : ".") stringByAppendingPathComponent:@"PS3_GAME/USRDIR/Data/START.dat"];
    struct stat st = {0};
    stat(start.fileSystemRepresentation, &st);
    NSString* cache = [NSString stringWithFormat:@"%@/Library/Application Support/DisgaeaD2Recomp/cache/item-icons-%lld-%ld.png",
        NSHomeDirectory(), (long long)st.st_size, (long)st.st_mtime];
    NSData* png = [NSData dataWithContentsOfFile:cache];
    if (png) {
        NSBitmapImageRep* rep = [NSBitmapImageRep imageRepWithData:png];
        if (rep.CGImage) { s_sheet = CGImageRetain(rep.CGImage); return; }
    }
    uint8_t* rgba = NULL; unsigned w = 0, h = 0; char error[512] = "";
    if (d2_items_icon_sheet(&rgba, &w, &h, error, sizeof error)) { self.iconError = str(error); return; }
    NSBitmapImageRep* rep = [[NSBitmapImageRep alloc] initWithBitmapDataPlanes:NULL pixelsWide:w pixelsHigh:h
        bitsPerSample:8 samplesPerPixel:4 hasAlpha:YES isPlanar:NO colorSpaceName:NSDeviceRGBColorSpace
        bitmapFormat:NSBitmapFormatAlphaNonpremultiplied bytesPerRow:w * 4 bitsPerPixel:32];
    memcpy(rep.bitmapData, rgba, (size_t)w * h * 4);
    free(rgba);
    s_sheet = CGImageRetain(rep.CGImage);
    [NSFileManager.defaultManager createDirectoryAtPath:cache.stringByDeletingLastPathComponent
        withIntermediateDirectories:YES attributes:nil error:nil];
    [[rep representationUsingType:NSBitmapImageFileTypePNG properties:@{}] writeToFile:cache atomically:YES];
    fprintf(stderr, "[D2 item editor] decoded %ux%u icon sheet from START.dat -> %s\n", w, h, cache.UTF8String);
}
- (NSImage*)icon:(unsigned)index
{
    NSImage* cached = self.icons[@(index)];
    if (cached) return cached;
    if (!s_sheet) return nil;
    size_t columns = CGImageGetWidth(s_sheet) / D2_ITEMS_ICON, rows = CGImageGetHeight(s_sheet) / D2_ITEMS_ICON;
    if (index >= columns * rows) return nil;
    CGImageRef cell = CGImageCreateWithImageInRect(s_sheet,
        CGRectMake((index % columns) * D2_ITEMS_ICON, (index / columns) * D2_ITEMS_ICON, D2_ITEMS_ICON, D2_ITEMS_ICON));
    NSImage* image = [[NSImage alloc] initWithCGImage:cell size:NSMakeSize(D2_ITEMS_ICON, D2_ITEMS_ICON)];
    CGImageRelease(cell);
    self.icons[@(index)] = image;
    return image;
}

/* ------------------------------------------------------------- catalog */
- (const D2CatalogItem*)catalogItem:(unsigned)id
{
    for (unsigned i = 0; i < s_cat->item_count; ++i) if (s_cat->items[i].id == id) return &s_cat->items[i];
    return NULL;
}
- (const D2CatalogInnocent*)innocent:(unsigned)id
{
    for (unsigned i = 0; i < s_cat->innocent_count; ++i) if (s_cat->innocents[i].id == id) return &s_cat->innocents[i];
    return NULL;
}
- (const D2ItemsEntry*)selected
{
    for (unsigned i = 0; i < s_snap->count; ++i) {
        const D2ItemsEntry* e = &s_snap->entries[i];
        if (e->unit == self.selUnit && e->slot == self.selSlot && e->item.id == self.selId) return e;
    }
    return NULL;
}

/* ------------------------------------------------------------------ UI */
static NSTextField* label(NSString* text, CGFloat size, BOOL bold)
{
    NSTextField* f = [NSTextField labelWithString:text];
    f.font = bold ? [NSFont boldSystemFontOfSize:size] : [NSFont systemFontOfSize:size];
    return f;
}
- (NSTextField*)input:(NSString*)key width:(CGFloat)width
{
    NSTextField* f = [NSTextField textFieldWithString:@""];
    f.alignment = NSTextAlignmentRight; f.delegate = self;
    [f.widthAnchor constraintEqualToConstant:width].active = YES;
    if (key) self.inputs[key] = f;
    return f;
}
- (void)build
{
    self.inputs = [NSMutableDictionary new]; self.totals = [NSMutableArray new]; self.icons = [NSMutableDictionary new];
    self.innocentTypes = [NSMutableArray new]; self.innocentLevels = [NSMutableArray new];
    self.innocentSubdued = [NSMutableArray new]; self.innocentMax = [NSMutableArray new];
    self.rows = [NSMutableArray new]; self.pickerRows = [NSMutableArray new]; self.selUnit = -2; self.lastAdded = -1;

    self.window = [[NSWindow alloc] initWithContentRect:NSMakeRect(0, 0, 1320, 860)
        styleMask:NSWindowStyleMaskTitled | NSWindowStyleMaskClosable | NSWindowStyleMaskResizable | NSWindowStyleMaskMiniaturizable
        backing:NSBackingStoreBuffered defer:NO];
    self.window.title = @"Item Editor"; self.window.delegate = self; self.window.releasedWhenClosed = NO;
    self.window.minSize = NSMakeSize(900, 600);
    self.window.frameAutosaveName = @"D2ItemEditor";

    NSSplitView* split = [NSSplitView new]; split.vertical = YES; split.dividerStyle = NSSplitViewDividerStyleThin;
    self.window.contentView = split;

    /* left: search, filter, list, buttons */
    NSView* left = [NSView new];
    self.search = [NSSearchField new]; self.search.placeholderString = @"Search name, category or ID"; self.search.delegate = self;
    self.filter = [NSPopUpButton new];
    [self.filter addItemsWithTitles:@[@"All items", @"Weapons", @"Armor", @"Accessories", @"Consumables", @"Other", @"Equipped"]];
    self.filter.target = self; self.filter.action = @selector(filterChanged:);
    self.table = [NSTableView new];
    self.table.rowHeight = 36; self.table.usesAlternatingRowBackgroundColors = YES;
    self.table.style = NSTableViewStyleFullWidth;
    NSArray* cols = @[@[@"item", @"Item", @220], @[@"rarity", @"Rarity", @110], @[@"level", @"Lv", @46], @[@"where", @"Location", @120]];
    for (NSArray* c in cols) {
        NSTableColumn* col = [[NSTableColumn alloc] initWithIdentifier:c[0]];
        col.title = c[1]; col.width = [c[2] doubleValue];
        [self.table addTableColumn:col];
    }
    self.table.dataSource = self; self.table.delegate = self;
    NSScrollView* scroll = [NSScrollView new]; scroll.documentView = self.table; scroll.hasVerticalScroller = YES;
    self.addButton = [NSButton buttonWithTitle:@"Add Item…" target:self action:@selector(addItem:)];
    self.duplicateButton = [NSButton buttonWithTitle:@"Duplicate" target:self action:@selector(duplicateItem:)];
    self.deleteButton = [NSButton buttonWithTitle:@"Delete…" target:self action:@selector(deleteItem:)];
    self.countLabel = label(@"", 11, NO); self.countLabel.textColor = NSColor.secondaryLabelColor;
    NSStackView* buttons = [NSStackView stackViewWithViews:@[self.addButton, self.duplicateButton, self.deleteButton, self.countLabel]];
    NSStackView* top = [NSStackView stackViewWithViews:@[self.search, self.filter]];
    for (NSView* v in @[top, scroll, buttons]) { v.translatesAutoresizingMaskIntoConstraints = NO; [left addSubview:v]; }
    [NSLayoutConstraint activateConstraints:@[
        [top.topAnchor constraintEqualToAnchor:left.topAnchor constant:10],
        [top.leadingAnchor constraintEqualToAnchor:left.leadingAnchor constant:10],
        [top.trailingAnchor constraintEqualToAnchor:left.trailingAnchor constant:-10],
        [scroll.topAnchor constraintEqualToAnchor:top.bottomAnchor constant:8],
        [scroll.leadingAnchor constraintEqualToAnchor:left.leadingAnchor],
        [scroll.trailingAnchor constraintEqualToAnchor:left.trailingAnchor],
        [buttons.topAnchor constraintEqualToAnchor:scroll.bottomAnchor constant:8],
        [buttons.leadingAnchor constraintEqualToAnchor:left.leadingAnchor constant:10],
        [buttons.bottomAnchor constraintEqualToAnchor:left.bottomAnchor constant:-10],
        [left.widthAnchor constraintGreaterThanOrEqualToConstant:530],
    ]];

    /* right: detail editor */
    NSScrollView* rightScroll = [NSScrollView new]; rightScroll.hasVerticalScroller = YES; rightScroll.drawsBackground = NO;
    D2ItemFlipped* doc = [D2ItemFlipped new]; doc.translatesAutoresizingMaskIntoConstraints = NO;
    rightScroll.documentView = doc;
    self.detail = doc;
    self.bigIcon = [NSImageView new]; self.bigIcon.imageScaling = NSImageScaleProportionallyUpOrDown;
    [self.bigIcon.widthAnchor constraintEqualToConstant:64].active = YES; [self.bigIcon.heightAnchor constraintEqualToConstant:64].active = YES;
    self.title = label(@"No item selected", 20, YES);
    self.subtitle = label(@"", 12, NO); self.subtitle.textColor = NSColor.secondaryLabelColor;
    self.details = [NSTextField wrappingLabelWithString:@""]; self.details.font = [NSFont systemFontOfSize:12];
    [self.details.widthAnchor constraintLessThanOrEqualToConstant:520].active = YES;
    self.baseButton = [NSButton buttonWithTitle:@"Change Base Item…" target:self action:@selector(changeBase:)];
    NSStackView* names = [NSStackView stackViewWithViews:@[self.title, self.subtitle, self.details, self.baseButton]];
    names.orientation = NSUserInterfaceLayoutOrientationVertical; names.alignment = NSLayoutAttributeLeading; names.spacing = 4;
    NSStackView* header = [NSStackView stackViewWithViews:@[self.bigIcon, names]]; header.alignment = NSLayoutAttributeTop; header.spacing = 14;

    self.gradeLabel = label(@"", 12, NO); self.gradeLabel.textColor = NSColor.secondaryLabelColor;
    NSArray* props = @[@[@"level", @"Level", @"0 – 9,999"], @[@"rarity", @"Rarity", @""],
        @[@"floors", @"Item World floor limit", @"0 – 99 (game: 29 / 59 / 99)"], @[@"slots", @"Innocent slots", @"1 – 6 (game: grade + 4)"],
        @[@"counter", @"Counter", @"0 – 9"], @[@"move", @"Move", @"0 – 99"], @[@"jump", @"Jump", @"0 – 99"],
        @[@"range", @"Range", @"0 – 10"], @[@"critical", @"Critical %", @"0 – 100"]];
    NSMutableArray* propRows = [NSMutableArray new];
    for (NSArray* p in props) {
        NSTextField* hint = label(p[2], 11, NO); hint.textColor = NSColor.tertiaryLabelColor;
        [propRows addObject:@[label(p[1], 12, NO), [self input:p[0] width:70], [p[0] isEqual:@"rarity"] ? self.gradeLabel : hint]];
    }
    NSGridView* propGrid = [NSGridView gridViewWithViews:propRows];
    propGrid.rowSpacing = 6; propGrid.columnSpacing = 10;

    NSMutableArray* statRows = [NSMutableArray arrayWithObject:@[label(@"Stat", 12, YES), label(@"Base (editable)", 12, YES), label(@"Total", 12, YES)]];
    for (unsigned i = 0; i < D2_ITEMS_STATS; ++i) {
        NSTextField* total = label(@"", 12, NO); total.alignment = NSTextAlignmentRight; total.textColor = NSColor.secondaryLabelColor;
        [self.totals addObject:total];
        [statRows addObject:@[label(@(kStat[i]), 12, NO), [self input:[NSString stringWithFormat:@"base%u", i] width:120], total]];
    }
    NSGridView* statGrid = [NSGridView gridViewWithViews:statRows];
    statGrid.rowSpacing = 6; statGrid.columnSpacing = 14;

    NSMutableArray* innRows = [NSMutableArray arrayWithObject:@[label(@"Slot", 12, YES), label(@"Innocent (specialist)", 12, YES), label(@"Level (stored)", 12, YES), label(@"", 12, YES), label(@"Max: stored / effective", 12, YES)]];
    for (unsigned k = 0; k < D2_ITEMS_INNOCENTS; ++k) {
        NSPopUpButton* type = [NSPopUpButton new]; type.target = self; type.action = @selector(changed:);
        [type.widthAnchor constraintEqualToConstant:230].active = YES;
        NSButton* subdued = [NSButton checkboxWithTitle:@"Subdued" target:self action:@selector(changed:)];
        NSTextField* max = label(@"", 11, NO); max.textColor = NSColor.tertiaryLabelColor;
        [self.innocentTypes addObject:type]; [self.innocentLevels addObject:[self input:nil width:80]];
        [self.innocentSubdued addObject:subdued]; [self.innocentMax addObject:max];
        [innRows addObject:@[label([NSString stringWithFormat:@"%u", k + 1], 12, NO), type, self.innocentLevels[k], subdued, max]];
    }
    NSGridView* innGrid = [NSGridView gridViewWithViews:innRows];
    innGrid.rowSpacing = 6; innGrid.columnSpacing = 10;

    self.revertButton = [NSButton buttonWithTitle:@"Revert" target:self action:@selector(revert:)];
    self.applyButton = [NSButton buttonWithTitle:@"Apply" target:self action:@selector(apply:)];
    self.applyButton.keyEquivalent = @"\r";
    self.status = [NSTextField wrappingLabelWithString:@""]; self.status.textColor = NSColor.secondaryLabelColor;
    [self.status.widthAnchor constraintLessThanOrEqualToConstant:560].active = YES;
    NSStackView* actions = [NSStackView stackViewWithViews:@[self.revertButton, self.applyButton]];

    NSStackView* propBox = [NSStackView stackViewWithViews:@[label(@"Properties", 14, YES), propGrid]];
    NSStackView* statBox = [NSStackView stackViewWithViews:@[label(@"Stats", 14, YES), statGrid]];
    for (NSStackView* b in @[propBox, statBox]) { b.orientation = NSUserInterfaceLayoutOrientationVertical; b.alignment = NSLayoutAttributeLeading; }
    NSStackView* columns = [NSStackView stackViewWithViews:@[propBox, statBox]];
    columns.alignment = NSLayoutAttributeTop; columns.spacing = 28;
    NSStackView* body = [NSStackView stackViewWithViews:@[header, columns, label(@"Innocents", 14, YES), innGrid, actions, self.status]];
    body.orientation = NSUserInterfaceLayoutOrientationVertical; body.alignment = NSLayoutAttributeLeading; body.spacing = 12;
    body.edgeInsets = NSEdgeInsetsMake(14, 18, 18, 18);
    body.translatesAutoresizingMaskIntoConstraints = NO;
    [doc addSubview:body];
    [NSLayoutConstraint activateConstraints:@[
        [body.topAnchor constraintEqualToAnchor:doc.topAnchor], [body.leadingAnchor constraintEqualToAnchor:doc.leadingAnchor],
        [body.trailingAnchor constraintEqualToAnchor:doc.trailingAnchor], [body.bottomAnchor constraintEqualToAnchor:doc.bottomAnchor],
        [doc.widthAnchor constraintEqualToAnchor:rightScroll.contentView.widthAnchor],
    ]];
    [split addArrangedSubview:left]; [split addArrangedSubview:rightScroll];
    [split setHoldingPriority:NSLayoutPriorityDefaultLow + 10 forSubviewAtIndex:0];
    [self.window center];
    [self showDetail:NULL];
}

/* --------------------------------------------------------------- data */
- (BOOL)entry:(const D2ItemsEntry*)e matchesFilter:(NSInteger)filter text:(NSString*)q
{
    const D2CatalogItem* c = [self catalogItem:e->item.id];
    if (filter == 6 && e->unit < 0) return NO;
    if (filter >= 1 && filter <= 5 && (!c || c->group != filter - 1)) return NO;
    if (!q.length) return YES;
    NSString* hay = [NSString stringWithFormat:@"%@ %@ %u", str(e->item.name), c ? str(c->category) : @"", e->item.id];
    return [hay rangeOfString:q options:NSCaseInsensitiveSearch | NSDiacriticInsensitiveSearch].location != NSNotFound;
}
- (void)rebuildRows
{
    [self.rows removeAllObjects];
    NSString* q = self.search.stringValue; NSInteger filter = self.filter.indexOfSelectedItem;
    for (unsigned i = 0; i < s_snap->count; ++i) if ([self entry:&s_snap->entries[i] matchesFilter:filter text:q]) [self.rows addObject:@(i)];
    [self.table reloadData];
    NSInteger keep = -1;
    for (NSUInteger r = 0; r < self.rows.count; ++r) {
        const D2ItemsEntry* e = &s_snap->entries[self.rows[r].unsignedIntValue];
        if (e->unit == self.selUnit && e->slot == self.selSlot && e->item.id == self.selId) keep = (NSInteger)r;
    }
    if (keep >= 0) [self.table selectRowIndexes:[NSIndexSet indexSetWithIndex:(NSUInteger)keep] byExtendingSelection:NO];
    else [self.table deselectAll:nil];
    self.countLabel.stringValue = [NSString stringWithFormat:@"%lu shown · %u / 999 in inventory", (unsigned long)self.rows.count, s_snap->pool_count];
}
- (void)selectPoolSlot:(unsigned)slot
{
    for (unsigned i = 0; i < s_snap->count; ++i) {
        const D2ItemsEntry* e = &s_snap->entries[i];
        if (e->unit < 0 && e->slot == slot) { self.selUnit = -1; self.selSlot = slot; self.selId = e->item.id; self.dirty = NO; }
    }
}
- (void)refresh
{
    if (d2_items_catalog_serial() != self.catalogSerial && d2_items_catalog(s_cat)) {
        self.catalogSerial = s_cat->serial;
        for (NSPopUpButton* p in self.innocentTypes) [self fillInnocents:p];
        self.shownSerial = 0;
    }
    if (!d2_items_snapshot(s_snap)) { self.status.stringValue = @"Waiting for the game to load a save…"; return; }
    if (s_snap->serial == self.shownSerial) return;
    self.shownSerial = s_snap->serial;
    if (s_snap->last_added >= 0 && s_snap->last_added != self.lastAdded) [self selectPoolSlot:(unsigned)s_snap->last_added];
    self.lastAdded = s_snap->last_added;
    [self rebuildRows];
    const D2ItemsEntry* e = [self selected];
    if (!self.dirty) [self showDetail:e];
    else if (!e) { self.dirty = NO; [self showDetail:NULL]; }
    BOOL ready = s_snap->ready;
    self.addButton.enabled = ready;
    self.duplicateButton.enabled = self.deleteButton.enabled = self.baseButton.enabled = ready && e && e->unit < 0;
    self.applyButton.enabled = ready && e;
    NSString* text = self.localStatus ?: str(s_snap->status);
    if (self.iconError) text = [text stringByAppendingFormat:@"\nIcons unavailable: %@", self.iconError];
    self.status.stringValue = [NSString stringWithFormat:@"%@%@", text, ready ? @"" : @"  (editing paused)"];
    self.localStatus = nil;
}
- (void)fillInnocents:(NSPopUpButton*)p
{
    [p removeAllItems];
    [p addItemWithTitle:@"— empty —"]; p.lastItem.tag = 0;
    for (unsigned i = 0; i < s_cat->innocent_count; ++i) {
        if (i && innocent_group(s_cat->innocents[i].id) != innocent_group(s_cat->innocents[i - 1].id))
            [p.menu addItem:[NSMenuItem separatorItem]];
        [p addItemWithTitle:[NSString stringWithFormat:@"%@  (%u)", str(s_cat->innocents[i].name), s_cat->innocents[i].id]];
        p.lastItem.tag = s_cat->innocents[i].id;
    }
}
- (void)updateInnocentLimits
{
    for (NSUInteger k = 0; k < self.innocentTypes.count; ++k) {
        unsigned type = (unsigned)self.innocentTypes[k].selectedItem.tag;
        const D2CatalogInnocent* info = [self innocent:type];
        NSTextField* hint = self.innocentMax[k];
        if (!type || !info) {
            hint.stringValue = type ? @"Unknown" : @"";
            hint.toolTip = type ? @"This type has no verified game-table limit." : nil;
            continue;
        }
        unsigned stored = info->max_level ? info->max_level : 1;
        // Game func_00032648: clamp stored level to HABIT cap, then double
        // its effective value when subdued, except fixed-level (cap == 1) types.
        unsigned effective = stored;
        if (self.innocentSubdued[k].state == NSControlStateValueOn && stored != 1) effective *= 2;
        hint.stringValue = [NSString stringWithFormat:@"%@ / %@", grouped(stored), grouped(effective)];
        hint.toolTip = @"Left: maximum stored level entered here (from the game's table). Right: maximum effective level used by the game. Subdued doubles the effect, not the stored limit; fixed-level 1 Innocents stay at 1.";
    }
}
- (void)showDetail:(const D2ItemsEntry*)e
{
    for (NSTextField* f in self.inputs.allValues) f.enabled = e != NULL;
    for (NSUInteger k = 0; k < D2_ITEMS_INNOCENTS; ++k) {
        self.innocentTypes[k].enabled = self.innocentLevels[k].enabled = self.innocentSubdued[k].enabled = e != NULL;
    }
    if (!e) {
        for (NSTextField* hint in self.innocentMax) { hint.stringValue = @""; hint.toolTip = nil; }
        self.title.stringValue = s_snap && s_snap->count ? @"Select an item" : @"No item selected";
        self.subtitle.stringValue = self.details.stringValue = @""; self.bigIcon.image = nil; return;
    }
    const D2Item* it = &e->item;
    const D2CatalogItem* c = [self catalogItem:it->id];
    self.bigIcon.image = [self icon:it->icon];
    self.title.stringValue = str(it->name);
    NSString* where = e->unit < 0 ? [NSString stringWithFormat:@"Inventory slot %u", e->slot]
        : [NSString stringWithFormat:@"Equipped by %@ (slot %u)", str(s_cat->party[e->unit]), e->slot + 1];
    self.subtitle.stringValue = [NSString stringWithFormat:@"%@ · ID %u · Rank %u · %@", c ? str(c->category) : @"Item", it->id, it->rank, where];
    self.details.stringValue = c ? str(c->description) : @"";
    NSDictionary* values = @{@"level": @(it->level), @"rarity": @(it->rarity), @"floors": @(it->floors), @"slots": @(it->slots),
        @"counter": @(it->counter), @"move": @(it->move), @"jump": @(it->jump), @"range": @(it->range), @"critical": @(it->critical)};
    for (NSString* k in values) self.inputs[k].stringValue = [values[k] stringValue];
    self.gradeLabel.stringValue = [NSString stringWithFormat:@"%@ · 0–7 Leg. · 8–31 Rare · 32+ Common", grade_name(it->grade)];
    for (unsigned i = 0; i < D2_ITEMS_STATS; ++i) {
        self.inputs[[NSString stringWithFormat:@"base%u", i]].stringValue = [@(it->base[i]) stringValue];
        self.totals[i].stringValue = grouped(it->total[i]);
    }
    for (unsigned k = 0; k < D2_ITEMS_INNOCENTS; ++k) {
        const D2Innocent* n = &it->innocents[k];
        NSPopUpButton* p = self.innocentTypes[k];
        if (n->type && ![p selectItemWithTag:n->type]) {
            [p addItemWithTitle:[NSString stringWithFormat:@"Unknown (%u)", n->type]]; p.lastItem.tag = n->type; [p selectItem:p.lastItem];
        } else if (!n->type) [p selectItemWithTag:0];
        self.innocentLevels[k].stringValue = n->type ? [@(n->level) stringValue] : @"";
        self.innocentSubdued[k].state = n->subdued ? NSControlStateValueOn : NSControlStateValueOff;
        BOOL inSlots = k < it->slots;
        p.enabled = self.innocentLevels[k].enabled = self.innocentSubdued[k].enabled = inSlots || n->type;
    }
    [self updateInnocentLimits];
}

/* ------------------------------------------------------------ actions */
- (void)controlTextDidChange:(NSNotification*)n
{
    if (n.object == self.search) { [self rebuildRows]; return; }
    if (n.object == self.pickerSearch) { [self rebuildPicker]; return; }
    self.dirty = YES;
}
- (void)changed:(id)sender { (void)sender; self.dirty = YES; [self updateInnocentLimits]; }
- (void)filterChanged:(id)sender { (void)sender; [self rebuildRows]; }
- (void)revert:(id)sender { (void)sender; self.dirty = NO; [self showDetail:[self selected]]; }
- (void)fail:(NSString*)text { NSBeep(); self.status.stringValue = text; }
- (void)apply:(id)sender
{
    (void)sender;
    const D2ItemsEntry* e = [self selected];
    if (!e || !s_snap->ready) { [self fail:@"No editable item selected."]; return; }
    D2Item item = e->item; NSString* error = nil; long long v = 0;
    struct { NSString *key, *name; long long hi; void* field; int size; } spec[] = {
        {@"level", @"Level", 9999, &item.level, 2}, {@"rarity", @"Rarity", 255, &item.rarity, 1},
        {@"floors", @"Item World floor limit", 99, &item.floors, 2}, {@"slots", @"Innocent slots", 6, &item.slots, 1},
        {@"counter", @"Counter", 9, &item.counter, 1}, {@"move", @"Move", 99, &item.move, 1},
        {@"jump", @"Jump", 99, &item.jump, 1}, {@"range", @"Range", 10, &item.range, 1}, {@"critical", @"Critical", 100, &item.critical, 1}};
    for (size_t i = 0; i < sizeof spec / sizeof *spec; ++i) {
        if (!parse(self.inputs[spec[i].key].stringValue, 0, spec[i].hi, spec[i].name, &v, &error)) { [self fail:error]; return; }
        if (spec[i].size == 2) *(uint16_t*)spec[i].field = (uint16_t)v; else *(uint8_t*)spec[i].field = (uint8_t)v;
    }
    for (unsigned i = 0; i < D2_ITEMS_STATS; ++i) {
        if (!parse(self.inputs[[NSString stringWithFormat:@"base%u", i]].stringValue, 0, 99999999, [NSString stringWithFormat:@"Base %s", kStat[i]], &v, &error)) { [self fail:error]; return; }
        item.base[i] = v;
    }
    for (unsigned k = 0; k < D2_ITEMS_INNOCENTS; ++k) {
        D2Innocent* n = &item.innocents[k];
        unsigned type = (unsigned)self.innocentTypes[k].selectedItem.tag;
        if (!type) { *n = (D2Innocent){0}; continue; }
        const D2CatalogInnocent* info = [self innocent:type];
        long long hi = info ? info->max_level : 9999;
        if (!parse(self.innocentLevels[k].stringValue, 1, hi, [NSString stringWithFormat:@"Innocent %u level", k + 1], &v, &error)) { [self fail:error]; return; }
        if (n->type != type) n->variant = (uint8_t)(arc4random() & 0xFF);   // the game picks a random name variant
        n->type = (uint16_t)type; n->level = (uint32_t)v;
        n->subdued = self.innocentSubdued[k].state == NSControlStateValueOn;
    }
    char text[160];
    D2Item check = item;
    if (d2_item_validate(&e->item, &check, s_cat, text, sizeof text)) { [self fail:str(text)]; return; }
    if (d2_items_apply(e->unit, e->slot, e->item.id, s_snap->generation, &item)) { [self fail:@"Action queue is full; try again."]; return; }
    self.dirty = NO; self.localStatus = @"Applying…"; self.status.stringValue = self.localStatus;
}
- (void)duplicateItem:(id)sender
{
    (void)sender; const D2ItemsEntry* e = [self selected];
    if (e && e->unit < 0) d2_items_duplicate(e->slot, e->item.id, s_snap->generation);
}
- (void)deleteItem:(id)sender
{
    (void)sender; const D2ItemsEntry* e = [self selected];
    if (!e || e->unit >= 0) return;
    unsigned slot = e->slot, id = e->item.id; uint64_t gen = s_snap->generation;
    NSAlert* alert = [NSAlert new];
    alert.messageText = [NSString stringWithFormat:@"Delete %@?", str(e->item.name)];
    alert.informativeText = @"The item is removed from the inventory with the game's own helper. Save in-game to make it permanent.";
    [alert addButtonWithTitle:@"Delete"]; [alert addButtonWithTitle:@"Cancel"];
    alert.buttons[0].hasDestructiveAction = YES;
    [alert beginSheetModalForWindow:self.window completionHandler:^(NSModalResponse r) {
        if (r == NSAlertFirstButtonReturn) d2_items_remove(slot, id, gen);
    }];
}

/* ------------------------------------------------------------- picker */
- (void)buildPicker
{
    self.picker = [[NSPanel alloc] initWithContentRect:NSMakeRect(0, 0, 560, 560)
        styleMask:NSWindowStyleMaskTitled | NSWindowStyleMaskResizable backing:NSBackingStoreBuffered defer:NO];
    self.pickerSearch = [NSSearchField new]; self.pickerSearch.placeholderString = @"Search all items"; self.pickerSearch.delegate = self;
    self.pickerTable = [NSTableView new]; self.pickerTable.rowHeight = 36;
    for (NSArray* c in @[@[@"pname", @"Item", @260], @[@"pcategory", @"Category", @150], @[@"pid", @"ID", @60]]) {
        NSTableColumn* col = [[NSTableColumn alloc] initWithIdentifier:c[0]]; col.title = c[1]; col.width = [c[2] doubleValue];
        [self.pickerTable addTableColumn:col];
    }
    self.pickerTable.dataSource = self; self.pickerTable.delegate = self;
    self.pickerTable.doubleAction = @selector(pickerChoose:); self.pickerTable.target = self;
    NSScrollView* scroll = [NSScrollView new]; scroll.documentView = self.pickerTable; scroll.hasVerticalScroller = YES;
    NSButton* cancel = [NSButton buttonWithTitle:@"Cancel" target:self action:@selector(pickerCancel:)];
    cancel.keyEquivalent = @"\e";
    NSButton* choose = [NSButton buttonWithTitle:@"Choose" target:self action:@selector(pickerChoose:)];
    choose.keyEquivalent = @"\r";
    NSStackView* buttons = [NSStackView stackViewWithViews:@[cancel, choose]];
    NSView* content = self.picker.contentView;
    for (NSView* v in @[self.pickerSearch, scroll, buttons]) { v.translatesAutoresizingMaskIntoConstraints = NO; [content addSubview:v]; }
    [NSLayoutConstraint activateConstraints:@[
        [self.pickerSearch.topAnchor constraintEqualToAnchor:content.topAnchor constant:12],
        [self.pickerSearch.leadingAnchor constraintEqualToAnchor:content.leadingAnchor constant:12],
        [self.pickerSearch.trailingAnchor constraintEqualToAnchor:content.trailingAnchor constant:-12],
        [scroll.topAnchor constraintEqualToAnchor:self.pickerSearch.bottomAnchor constant:8],
        [scroll.leadingAnchor constraintEqualToAnchor:content.leadingAnchor],
        [scroll.trailingAnchor constraintEqualToAnchor:content.trailingAnchor],
        [buttons.topAnchor constraintEqualToAnchor:scroll.bottomAnchor constant:10],
        [buttons.trailingAnchor constraintEqualToAnchor:content.trailingAnchor constant:-12],
        [buttons.bottomAnchor constraintEqualToAnchor:content.bottomAnchor constant:-12],
    ]];
}
- (void)rebuildPicker
{
    [self.pickerRows removeAllObjects];
    NSString* q = self.pickerSearch.stringValue;
    for (unsigned i = 0; i < s_cat->item_count; ++i) {
        const D2CatalogItem* c = &s_cat->items[i];
        NSString* hay = [NSString stringWithFormat:@"%@ %@ %u", str(c->name), str(c->category), c->id];
        if (!q.length || [hay rangeOfString:q options:NSCaseInsensitiveSearch].location != NSNotFound) [self.pickerRows addObject:@(i)];
    }
    [self.pickerTable reloadData];
    if (self.pickerRows.count) [self.pickerTable selectRowIndexes:[NSIndexSet indexSetWithIndex:0] byExtendingSelection:NO];
}
- (void)openPicker:(BOOL)replace
{
    if (!s_cat->item_count) { [self fail:@"The game's item table is not loaded yet."]; return; }
    if (!self.picker) [self buildPicker];
    self.pickerReplace = replace;
    self.picker.title = replace ? @"Change Base Item" : @"Add Item";
    self.pickerSearch.stringValue = @"";
    [self rebuildPicker];
    [self.window beginSheet:self.picker completionHandler:nil];
    [self.picker makeFirstResponder:self.pickerSearch];
}
- (void)addItem:(id)sender { (void)sender; [self openPicker:NO]; }
- (void)changeBase:(id)sender { (void)sender; [self openPicker:YES]; }
- (void)pickerCancel:(id)sender { (void)sender; [self.window endSheet:self.picker]; }
- (void)pickerChoose:(id)sender
{
    (void)sender;
    NSInteger r = self.pickerTable.selectedRow;
    if (r < 0 || r >= (NSInteger)self.pickerRows.count) { NSBeep(); return; }
    unsigned id = s_cat->items[self.pickerRows[(NSUInteger)r].unsignedIntValue].id;
    [self.window endSheet:self.picker];
    const D2ItemsEntry* e = [self selected];
    if (self.pickerReplace) { if (e && e->unit < 0) d2_items_replace(e->slot, e->item.id, s_snap->generation, id); }
    else d2_items_add(id);
    self.localStatus = @"Working…";
}

/* --------------------------------------------------------------- table */
- (NSInteger)numberOfRowsInTableView:(NSTableView*)t { return (NSInteger)(t == self.table ? self.rows.count : self.pickerRows.count); }
- (NSView*)tableView:(NSTableView*)t viewForTableColumn:(NSTableColumn*)col row:(NSInteger)row
{
    NSString* ident = col.identifier;
    NSTableCellView* cell = [t makeViewWithIdentifier:ident owner:self];
    if (!cell) {
        cell = [NSTableCellView new]; cell.identifier = ident;
        NSTextField* f = label(@"", 12, NO); f.lineBreakMode = NSLineBreakByTruncatingTail;
        f.translatesAutoresizingMaskIntoConstraints = NO; [cell addSubview:f]; cell.textField = f;
        BOOL withIcon = [ident isEqual:@"item"] || [ident isEqual:@"pname"];
        if (withIcon) {
            NSImageView* image = [NSImageView new]; image.translatesAutoresizingMaskIntoConstraints = NO;
            [cell addSubview:image]; cell.imageView = image;
            [NSLayoutConstraint activateConstraints:@[
                [image.leadingAnchor constraintEqualToAnchor:cell.leadingAnchor constant:2],
                [image.centerYAnchor constraintEqualToAnchor:cell.centerYAnchor],
                [image.widthAnchor constraintEqualToConstant:32], [image.heightAnchor constraintEqualToConstant:32]]];
        }
        [NSLayoutConstraint activateConstraints:@[
            [f.leadingAnchor constraintEqualToAnchor:withIcon ? cell.imageView.trailingAnchor : cell.leadingAnchor constant:6],
            [f.trailingAnchor constraintEqualToAnchor:cell.trailingAnchor constant:-2],
            [f.centerYAnchor constraintEqualToAnchor:cell.centerYAnchor]]];
    }
    if (t == self.pickerTable) {
        const D2CatalogItem* c = &s_cat->items[self.pickerRows[(NSUInteger)row].unsignedIntValue];
        if ([ident isEqual:@"pname"]) { cell.textField.stringValue = str(c->name); cell.imageView.image = [self icon:c->icon]; }
        else if ([ident isEqual:@"pcategory"]) cell.textField.stringValue = str(c->category);
        else cell.textField.stringValue = [@(c->id) stringValue];
        return cell;
    }
    const D2ItemsEntry* e = &s_snap->entries[self.rows[(NSUInteger)row].unsignedIntValue];
    if ([ident isEqual:@"item"]) { cell.textField.stringValue = str(e->item.name); cell.imageView.image = [self icon:e->item.icon]; }
    else if ([ident isEqual:@"rarity"]) cell.textField.stringValue = [NSString stringWithFormat:@"%@ %u", grade_name(e->item.grade), e->item.rarity];
    else if ([ident isEqual:@"level"]) cell.textField.stringValue = [@(e->item.level) stringValue];
    else cell.textField.stringValue = e->unit < 0 ? [NSString stringWithFormat:@"Inventory #%u", e->slot] : str(s_cat->party[e->unit]);
    cell.textField.textColor = [ident isEqual:@"rarity"] && e->item.grade == 2 ? NSColor.systemOrangeColor
        : [ident isEqual:@"rarity"] && e->item.grade == 1 ? NSColor.systemBlueColor : NSColor.labelColor;
    return cell;
}
- (void)tableViewSelectionDidChange:(NSNotification*)n
{
    if (n.object != self.table) return;
    NSInteger r = self.table.selectedRow;
    if (r < 0 || r >= (NSInteger)self.rows.count) return;
    const D2ItemsEntry* e = &s_snap->entries[self.rows[(NSUInteger)r].unsignedIntValue];
    if (e->unit == self.selUnit && e->slot == self.selSlot && e->item.id == self.selId) return;
    self.selUnit = e->unit; self.selSlot = e->slot; self.selId = e->item.id; self.dirty = NO;
    [self showDetail:e];
    self.duplicateButton.enabled = self.deleteButton.enabled = self.baseButton.enabled = s_snap->ready && e->unit < 0;
    self.applyButton.enabled = s_snap->ready;
}

/* ------------------------------------------------------------ window */
- (void)show
{
    if (!self.window) {
        s_snap = calloc(1, sizeof *s_snap); s_cat = calloc(1, sizeof *s_cat);
        [self build];
        [self loadIcons];
    }
    if (!self.timer) {
        self.timer = [NSTimer timerWithTimeInterval:0.25 target:self selector:@selector(refresh) userInfo:nil repeats:YES];
        [NSRunLoop.mainRunLoop addTimer:self.timer forMode:NSRunLoopCommonModes];
    }
    [self refresh];
    [self.window makeKeyAndOrderFront:nil];
}
- (void)windowWillClose:(NSNotification*)n { (void)n; [self.timer invalidate]; self.timer = nil; }
@end

void d2_item_editor_show(void)
{
    void (^run)(void) = ^{ if (!s_editor) s_editor = [D2ItemEditor new]; [s_editor show]; };
    if (NSThread.isMainThread) run(); else dispatch_async(dispatch_get_main_queue(), run);
}

/* ---- Test automation (only with env vars; never during normal play) ----
 * D2_ITEM_EDITOR=1 opens the window once a save is loaded.
 * D2_ITEM_EDITOR_SHOT_DIR=<dir> writes PNGs of the window and the picker.
 * D2_ITEM_EDITOR_TEST=1 edits inventory slot 0 through the UI (level +1, base
 *   ATK +1, innocent 1 level +1 or a new Statistician), adds "Yoshitsuna",
 *   duplicates it and deletes the duplicate, logging each snapshot.
 * D2_ITEM_EDITOR_SAVE_HL=<n> then sets HL to n through the cheats bridge; with
 *   D2_CHEATS_TEST_SAVE_WHEN_HL=<n> on an AS-/AF- HDD copy that triggers D2's
 *   real save callbacks. */
static void shot(NSWindow* w, NSString* name)
{
    const char* dir = getenv("D2_ITEM_EDITOR_SHOT_DIR");
    if (!dir || !*dir) return;
    NSView* v = w.contentView.superview ?: w.contentView;
    NSBitmapImageRep* rep = [v bitmapImageRepForCachingDisplayInRect:v.bounds];
    [v cacheDisplayInRect:v.bounds toBitmapImageRep:rep];
    NSString* path = [[str(dir) stringByAppendingPathComponent:name] stringByAppendingPathExtension:@"png"];
    [[rep representationUsingType:NSBitmapImageFileTypePNG properties:@{}] writeToFile:path atomically:YES];
    fprintf(stderr, "[D2 item editor] shot %s window=%ld\n", path.UTF8String, (long)w.windowNumber);
}
static void log_slot0(const char* when)
{
    for (unsigned i = 0; i < s_snap->count; ++i) {
        const D2ItemsEntry* e = &s_snap->entries[i];
        if (e->unit >= 0 || e->slot) continue;
        const D2Item* it = &e->item;
        fprintf(stderr, "[D2 item editor] %s slot0 id=%u '%s' lv=%u rarity=%u grade=%u ATK=%lld totalATK=%lld inn=[", when,
            it->id, it->name, it->level, it->rarity, it->grade, (long long)it->base[2], (long long)it->total[2]);
        for (unsigned k = 0; k < D2_ITEMS_INNOCENTS; ++k) if (it->innocents[k].type)
            fprintf(stderr, "%u:%u%s ", it->innocents[k].type, it->innocents[k].level, it->innocents[k].subdued ? "s" : "");
        fprintf(stderr, "] pool=%u\n", s_snap->pool_count);
    }
}
__attribute__((constructor)) static void d2_item_editor_automation(void)
{
    const char* open = getenv("D2_ITEM_EDITOR");
    if (!open || !*open) return;
    BOOL test = getenv("D2_ITEM_EDITOR_TEST") != NULL;
    __block int phase = 0; __block NSDate* since = nil; __block unsigned pool0 = 0, settle = ~0u;
    dispatch_async(dispatch_get_main_queue(), ^{
        NSTimer* t = [NSTimer timerWithTimeInterval:0.75 repeats:YES block:^(NSTimer* timer) {
            if (!s_editor) {
                D2ItemsSnapshot* probe = calloc(1, sizeof *probe);
                int ok = d2_items_snapshot(probe) && probe->ready && probe->count && d2_items_catalog_serial();
                unsigned pool = probe->pool_count;
                free(probe);
                /* Wait until the loaded save's inventory has been stable for 5 s. */
                const char* min = getenv("D2_ITEM_EDITOR_MIN_POOL"); /* e.g. 900: skip the pre-load default state */
                if (!ok || pool != settle || (min && pool < strtoul(min, NULL, 10))) { since = nil; settle = pool; return; }
                if (!since) { since = NSDate.date; return; }
                if (-since.timeIntervalSinceNow < 5) return;
                d2_item_editor_show(); return;
            }
            D2ItemEditor* ed = s_editor;
            switch (phase++) {
            case 0: [ed selectPoolSlot:0]; ed.shownSerial = 0; [ed refresh]; log_slot0("opened"); pool0 = s_snap->pool_count; break;
            case 1: shot(ed.window, @"item-editor"); if (!test) phase = 100; break;
            case 2: {
                const D2ItemsEntry* e = [ed selected];
                if (!e) { fprintf(stderr, "[D2 item editor] test: slot 0 missing\n"); phase = 100; break; }
                ed.inputs[@"level"].stringValue = [@(e->item.level + 1) stringValue];
                ed.inputs[@"base2"].stringValue = [@(e->item.base[2] + 1) stringValue];
                unsigned k = 0;
                while (k < e->item.slots && e->item.innocents[k].type) ++k;
                if (k < e->item.slots) { [ed.innocentTypes[k] selectItemWithTag:62]; ed.innocentLevels[k].stringValue = @"100"; }
                else ed.innocentLevels[0].stringValue = [@(e->item.innocents[0].level + 1) stringValue];
                ed.dirty = YES;
                fprintf(stderr, "[D2 item editor] test: UI fields set (innocent slot %u), pressing Apply\n", k + 1);
                [ed.applyButton performClick:nil];
                break;
            }
            case 4: log_slot0("applied"); fprintf(stderr, "[D2 item editor] test: status '%s'\n", s_snap->status); shot(ed.window, @"item-editor-edited"); break;
            case 5: [ed openPicker:NO]; ed.pickerSearch.stringValue = @"Yoshitsuna"; [ed rebuildPicker]; break;
            case 6: shot(ed.picker, @"item-picker"); [ed pickerChoose:nil]; break;
            case 8: fprintf(stderr, "[D2 item editor] test: add -> pool %u (was %u) status '%s' selected=%u/%u\n",
                        s_snap->pool_count, pool0, s_snap->status, ed.selSlot, ed.selId);
                    [ed duplicateItem:nil]; break;
            case 10: fprintf(stderr, "[D2 item editor] test: duplicate -> pool %u status '%s' selected=%u\n", s_snap->pool_count, s_snap->status, ed.selSlot);
                     { const D2ItemsEntry* e = [ed selected]; if (e) d2_items_remove(e->slot, e->item.id, s_snap->generation); } break;
            case 12: fprintf(stderr, "[D2 item editor] test: delete -> pool %u status '%s'\n", s_snap->pool_count, s_snap->status);
                     [ed.filter selectItemAtIndex:1]; [ed rebuildRows]; shot(ed.window, @"item-editor-weapons");
                     [ed.filter selectItemAtIndex:0]; [ed rebuildRows]; break;
            case 13: {
                const char* hl = getenv("D2_ITEM_EDITOR_SAVE_HL");
                if (hl && *hl) {
                    int q = d2_cheats_set_general("hl", strtoull(hl, NULL, 10), D2_CHEATS_ANY_GENERATION);
                    fprintf(stderr, "[D2 item editor] test: HL -> %s queued=%d (save trigger)\n", hl, q);
                }
                break;
            }
            case 100: [timer invalidate]; fprintf(stderr, "[D2 item editor] automation done\n"); break;
            default: if (phase > 20) phase = 100; break;
            }
        }];
        [NSRunLoop.mainRunLoop addTimer:t forMode:NSRunLoopCommonModes];
    });
}
