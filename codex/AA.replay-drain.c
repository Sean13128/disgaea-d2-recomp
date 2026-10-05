/* Drive the actual live GCM walker over a flattened consumed-packet recording.
 * Guest scheduling/flip pacing is supplied by the recording's P boundaries. */
#ifndef AA_GCM_SOURCE
#define AA_GCM_SOURCE "../ps3recomp/libs/video/cellGcmSys.c"
#endif
#include AA_GCM_SOURCE
int g_resv_store_active;
u32 g_ww_lo, g_ww_hi;
int spu_coh_is_reserved(u32 ea) { (void)ea; return 0; }
void spu_lockline_lock(void) {}
void spu_lockline_unlock(void) {}
void spu_coh_notify_write(u32 ea) { (void)ea; }
void ppu_resv_break_store(u64 ea) { (void)ea; }
void ps3_ww_report_inline(u32 ea, u64 v, int n) { (void)ea; (void)v; (void)n; }
ps3_guest_caller_fn g_ps3_guest_caller;
PPU_THREAD_LOCAL ppu_context* g_active_ctx;
void ppu_dump_guest_stack(ppu_context* ctx, const char* tag) { (void)ctx; (void)tag; }
void ppu_dump_bctrl_ring(u32 id, const char* tag) { (void)id; (void)tag; }
#ifndef AA_WITH_METAL
int rsx_live_draw_enabled(void) { return 0; }
void rsx_live_draw_method(u32 m, u32 v) { (void)m; (void)v; }
void rsx_raise_user_cmd(u32 v) { (void)v; }
int rsx_live_draw_blit(u32 a, u32 b, u32 c, u32 d, u32 e, u32 f, u32 g, u32 h)
{ (void)a; (void)b; (void)c; (void)d; (void)e; (void)f; (void)g; (void)h; return 0; }
void rsx_live_draw_note_resolve(u32 a, u32 b, u32 c, u32 d) { (void)a; (void)b; (void)c; (void)d; }
int rsx_live_draw_resolve_blit(u32 a,u32 b,u32 c,u32 d,u32 e,u32 f,u32 g,u32 h,u32 i,u32 j,u32 k,u32 l)
{ (void)a;(void)b;(void)c;(void)d;(void)e;(void)f;(void)g;(void)h;(void)i;(void)j;(void)k;(void)l;return 0; }
#endif
void aa_live_drain(const u8* bytes, u32 n)
{
    const u32 begin = 0x70000000u, ctx = 0x60001000u;
    static int initialized;
    if (!initialized) {
        ppu_hle_inject_base = 0x60000000u;
        memset(s_io_address_table, 0xff, sizeof(s_io_address_table));
        memset(s_ea_address_table, 0xff, sizeof(s_ea_address_table));
        populate_offset_table(begin, 0, 0x100000);
        s_gcm_context_ea = ctx;
        s_gcm_ctx_out_ea = 0;
        vm_write32(ctx, begin); vm_write32(ctx + 4, begin + 0x100000);
        initialized = 1;
    }
    if (!n || n > 0x100000) abort();
    memcpy(vm_base + begin, bytes, n);
    vm_write32(ctx + 8, begin + n);
    vm_write32(GCM_CONTROL_GUEST_ADDR, n);
    s_fifo_getoff = 0;
    s_fifo_flip_reached = 0;
    while (s_fifo_getoff < n) {
        u32 before = s_fifo_getoff;
        cellGcm_rsx_process_fifo();
        if (before == s_fifo_getoff) { fprintf(stderr, "replay drain stalled\n"); abort(); }
    }
    /* There is no PPU equality waiter in throughput replay. Avoid creating an
     * artificial paced-reference backlog between repetitions. */
    s_ref_qhead = s_ref_qtail;
}
