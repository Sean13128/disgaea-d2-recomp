/* Stop completes an active system dialog and releases its guest waiter. */
#include "libs/system/sys_overlay.h"
#include <pthread.h>
#include <stdatomic.h>
#include <assert.h>
#include <stdio.h>
#include <unistd.h>
void ps3_pad_overlay_capture(int active) { (void)active; }
uint16_t ps3_pad_host_buttons(void) { return 0; }
static uint64_t token;
static atomic_int waiting;
static int result;
static void* guest(void* arg)
{
    (void)arg; waiting = 1; result = ps3_overlay_wait(token, NULL); return NULL;
}
int main(void)
{
    ps3_overlay_set_renderer(1);
    SysOverlaySnapshot request = {0}; request.kind = SYS_OVERLAY_YESNO;
    token = ps3_overlay_open(&request, SYS_OVERLAY_OK); assert(token);
    pthread_t thread; assert(!pthread_create(&thread, NULL, guest, NULL));
    while (!waiting) usleep(1000);
    SysOverlaySnapshot snapshot; ps3_overlay_snapshot(&snapshot); assert(snapshot.active);
    ps3_overlay_finish(snapshot.token, SYS_OVERLAY_BACK);
    assert(!pthread_join(thread, NULL)); assert(result == SYS_OVERLAY_BACK);
    puts("[AL-dialog-stop] active dialog closes with Back and releases the guest waiter: PASS");
    return 0;
}
