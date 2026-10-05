#include "../ps3recomp/libs/system/sys_overlay.h"
#include <assert.h>
#include <stdint.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <unistd.h>
static int captured;
uint16_t ps3_pad_host_buttons(void) { return 0; }
void ps3_pad_overlay_capture(int active) { captured = active; }
static void pulse(uint16_t buttons) { ps3_overlay_input(0); ps3_overlay_input(buttons); }
int main(void)
{
    setenv("PS3RECOMP_METAL_HEADLESS","1",1);
    ps3_overlay_set_renderer(0);
    static SysOverlaySnapshot ui, snapshot;
    ui.kind = SYS_OVERLAY_EDITOR; ui.count = 118; ui.buttons = 1;
    strcpy(ui.title,"D2 cheats / Characters");
    uint64_t token = ps3_overlay_open(&ui,SYS_OVERLAY_BACK);
    assert(token && captured);
    ps3_overlay_poll(); usleep(10000); ps3_overlay_poll();
    assert(!ps3_overlay_take_result(token,NULL,NULL));
    pulse(0x40); pulse(0x4000); pulse(0x40);
    int selected = -1;
    assert(ps3_overlay_editor_action(token,&selected) == 0x4000 && selected == 1);
    assert(!ps3_overlay_editor_action(token,&selected) && selected == 2);
    ui.selected = -1;
    assert(ps3_overlay_editor_update(token,&ui));
    ps3_overlay_snapshot(&snapshot); assert(snapshot.selected == 2 && snapshot.active);
    pulse(0x40); usleep(450000); ps3_overlay_input(0x40);
    ps3_overlay_snapshot(&snapshot); assert(snapshot.selected == 4);
    pulse(0x4000);
    strcpy(ui.title,"D2 cheats / Edit value"); ui.count = 6; ui.selected = 0;
    assert(ps3_overlay_editor_update(token,&ui));
    assert(!ps3_overlay_editor_action(token,NULL)); /* discard old-page actions */
    pulse(0x20);
    assert(ps3_overlay_editor_action(token,&selected) == 0x20 && selected == 0);
    assert(!ps3_overlay_editor_update(token + 1,&ui));
    ps3_overlay_finish(token,SYS_OVERLAY_BACK);
    assert(!captured && ps3_overlay_take_result(token,NULL,NULL));
    puts("[AF-test] persistent/headless editor, captured input, queued selection, repeat, page invalidation: PASS");
}
