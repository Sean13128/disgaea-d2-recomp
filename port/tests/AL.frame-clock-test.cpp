/* Exercise the actual clock with submitted-without-display / failed outcomes. */
#define main unused_runner_main
#include "../main.cpp"
#undef main
#include <assert.h>
static int outcome, submissions, retirements, pending;
extern "C" {
void ps3_poll_thread_start(const char*, int) {}
void cellGcm_fifo_enable_snapshot(void) {}
int rsx_metal_backend_init(uint32_t,uint32_t,const char*) { return 0; }
void rsx_metal_backend_present(void) { submissions++; }
int rsx_metal_backend_submission_ok(void) { return outcome; }
int rsx_metal_backend_pump_messages(void) { s_frame_stopping = true; return 0; }
void rsx_metal_backend_set_flip_buffer(uint32_t) {}
void rsx_metal_backend_set_vsync(int) {}
int rsx_null_backend_init(uint32_t,uint32_t,const char*) { return -1; }
void rsx_null_backend_present(void) {}
int rsx_null_backend_pump_messages(void) { return 0; }
void d2_install_shader_trace(void) {}
int d2_install_draw_trace(void) { return 0; }
void rsx_draw_engine_present(void) {}
void ppu_report_guest_lrs(void) {}
uint64_t cellGcmGetVBlankCount(void) { return 0; }
unsigned cellGcm_vblank_wait_ms(void) { return 0; }
void cellGcm_fifo_kick_wait(unsigned) {}
void cellGcmTickVBlank(void) {}
int cellGcm_take_flip_pending(void) { return pending--; }
unsigned cellGcm_flip_request_count(void) { return 1; }
uint32_t cellGcmGetCurrentDisplayBufferId(void) { return 0; }
uint32_t cellGcm_flip_mode(void) { return 2; }
void cellGcmTickFlip(void) { retirements++; }
void cellGcm_rsx_process_fifo(void) {}
}
int main(void)
{
    pending=1; outcome=1;
    frame_clock(nullptr);
    assert(submissions == 1 && retirements == 1 && ppu_boot_frames_presented() == 1);
    puts("[AL-frame-clock] guest submission without drawable retires exactly once: PASS");
    pending=1; outcome=0; submissions=retirements=0;
    s_frame_stopping=false; s_stop_requested=false;
    frame_clock(nullptr);
    assert(submissions == 1 && retirements == 0 && s_stop_requested && s_stop_failure == 1);
    puts("[AL-frame-clock] failed submission does not retire and requests error shutdown: PASS");
}
