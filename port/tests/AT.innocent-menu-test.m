// Exercise the actual native picker without guest memory or game assets.
#include "../src/d2_item_editor.m"
#include <assert.h>

// The menu does not call the guest bridge; fail if that contract changes.
int d2_items_icon_sheet(uint8_t** p, unsigned* w, unsigned* h, char* e, size_t n) { abort(); }
int d2_items_snapshot(D2ItemsSnapshot* p) { abort(); }
uint64_t d2_items_catalog_serial(void) { abort(); }
int d2_items_catalog(D2ItemsCatalog* p) { abort(); }
int d2_item_validate(const D2Item* b, D2Item* p, const D2ItemsCatalog* c, char* e, size_t n) { abort(); }
int d2_items_apply(int u, unsigned s, unsigned i, uint64_t g, const D2Item* p) { abort(); }
int d2_items_add(unsigned i) { abort(); }
int d2_items_duplicate(unsigned s, unsigned i, uint64_t g) { abort(); }
int d2_items_remove(unsigned s, unsigned i, uint64_t g) { abort(); }
int d2_items_replace(unsigned s, unsigned i, uint64_t g, unsigned n) { abort(); }
int d2_cheats_set_general(const char* k, uint64_t v, uint64_t g) { abort(); }

int main(void)
{
    @autoreleasepool {
        [NSApplication sharedApplication];
        s_cat = calloc(1, sizeof *s_cat);
        // First/last IDs of each contiguous effect category, including gaps.
        const unsigned ids[] = {1, 8, 11, 17, 21, 25, 26, 41, 45, 46, 48,
                                60, 65, 131, 134, 201, 227, 250, 256, 999};
        const unsigned boundaries[] = {11, 21, 26, 41, 46, 60, 131, 201, 250, 999};
        s_cat->innocent_count = sizeof ids / sizeof *ids;
        for (unsigned i = 0; i < s_cat->innocent_count; ++i) {
            s_cat->innocents[i].id = ids[i];
            snprintf(s_cat->innocents[i].name, 49, "Innocent %u", ids[i]);
        }
        D2ItemEditor* editor = [D2ItemEditor new];
        NSPopUpButton* picker = [[NSPopUpButton alloc] initWithFrame:NSZeroRect pullsDown:NO];
        [editor fillInnocents:picker];
        assert([picker selectItemWithTag:0] && !picker.selectedItem.separatorItem);
        unsigned seen = 0, separators = 0;
        for (NSInteger i = 1; i < picker.numberOfItems; ++i) {
            NSMenuItem* item = [picker itemAtIndex:i];
            if (item.separatorItem) {
                assert(i > 1 && i + 1 < picker.numberOfItems);
                assert(![picker itemAtIndex:i - 1].separatorItem);
                assert([picker itemAtIndex:i + 1].tag == boundaries[separators]);
                ++separators;
            } else {
                assert(item.tag == ids[seen++]);
            }
        }
        assert(separators == sizeof boundaries / sizeof *boundaries);
        assert(seen == s_cat->innocent_count);
        for (unsigned i = 0; i < seen; ++i) {
            assert([picker selectItemWithTag:ids[i]]);
            assert(!picker.selectedItem.separatorItem);
        }
        // Rebuilding must not duplicate dividers; empty/single groups have none.
        [editor fillInnocents:picker];
        assert(picker.numberOfItems == 1 + seen + separators);
        s_cat->innocent_count = 2;
        [editor fillInnocents:picker];
        assert(picker.numberOfItems == 3);
        s_cat->innocent_count = 0;
        [editor fillInnocents:picker];
        assert(picker.numberOfItems == 1 && picker.selectedItem.tag == 0);
        // HABIT caps are stored levels, not the doubled subdued effect.
        const unsigned caps[] = {9999, 50, 150, 250, 950, 1};
        const unsigned effective[] = {19998, 100, 300, 500, 1900, 1};
        s_cat->innocent_count = sizeof caps / sizeof *caps;
        for (unsigned i = 0; i < s_cat->innocent_count; ++i) {
            s_cat->innocents[i].id = i + 1;
            s_cat->innocents[i].max_level = caps[i];
        }
        [editor fillInnocents:picker];
        NSButton* subdued = [NSButton checkboxWithTitle:@"Subdued" target:nil action:nil];
        NSTextField* max = [NSTextField labelWithString:@"stale"];
        editor.innocentTypes = [NSMutableArray arrayWithObject:picker];
        editor.innocentSubdued = [NSMutableArray arrayWithObject:subdued];
        editor.innocentMax = [NSMutableArray arrayWithObject:max];
        for (unsigned i = 0; i < s_cat->innocent_count; ++i) {
            [picker selectItemWithTag:i + 1];
            subdued.state = NSControlStateValueOff;
            [editor changed:picker];
            assert(([max.stringValue isEqualToString:[NSString stringWithFormat:@"%@ / %@", grouped(caps[i]), grouped(caps[i])]]));
            subdued.state = NSControlStateValueOn;
            [editor changed:subdued];
            assert(([max.stringValue isEqualToString:[NSString stringWithFormat:@"%@ / %@", grouped(caps[i]), grouped(effective[i])]]));
            assert(editor.dirty && [max.toolTip containsString:@"stored"]);
        }
        [picker selectItemWithTag:0]; [editor changed:picker];
        assert(!max.stringValue.length && !max.toolTip.length);
        [picker addItemWithTitle:@"Unknown"]; picker.lastItem.tag = 999;
        [picker selectItem:picker.lastItem]; [editor changed:picker];
        assert([max.stringValue isEqualToString:@"Unknown"]);
        free(s_cat); s_cat = NULL;
        puts("[AT-menu-test] separators, selections, stored/effective caps, subdued exception and immediate refresh: PASS");
    }
    return 0;
}
