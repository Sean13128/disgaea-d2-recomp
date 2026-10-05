#define main aa_existing_draw_tests
#include "../ps3recomp/libs/video/tests/test_rsx_draw_engine.c"
#undef main
#include "../ps3recomp/libs/video/rsx_draw_engine.c"
#include <assert.h>
static void put_bef(u32 off, float f)
{
    u32 raw; memcpy(&raw, &f, 4); raw = __builtin_bswap32(raw);
    memcpy(vm_base + off, &raw, 4);
}
static void many(u32 count)
{
    m(M_BEGIN_END, RSX_PRIMITIVE_TRIANGLES);
    m(M_DRAW_ARRAYS, ((count > 256 ? 256 : count) - 1) << 24);
    if (count > 256) { /* packet count is eight bits; append further batches */
        for (u32 first = 256; first < count; first += 256)
            m(M_DRAW_ARRAYS, ((count - first > 256 ? 256 : count - first) - 1) << 24 | first);
    }
    m(M_BEGIN_END, 0);
}
int main(void)
{
    vm_base = calloc(1, GUEST_BYTES); assert(vm_base); ppu_vm_size = GUEST_BYTES;
    engine_up();
    for (u32 i = 0; i < 512; i++) put_bef(VTX_OFFSET + i * 16, (float)i + 1);
    many(32); u64 miss = s_vertex_cache_misses, hit = s_vertex_cache_hits;
    many(32); assert(s_vertex_cache_hits == hit + 1 && s_vertex_cache_misses == miss);
    rsx_draw_engine_present(); many(32); assert(s_vertex_cache_hits == hit + 2);
    put_bef(VTX_OFFSET, 123); many(32);
    assert(stub.draw_first_vertex[0] == 123 && s_vertex_cache_misses == miss + 1);
    /* Defaults and formats are part of identity, even if the source is unchanged. */
    m(0x194c, 0x11223344); many(32); assert(s_vertex_cache_misses == miss + 2);
    m(M_VTXFMT, 2 | 3 << 4 | 16 << 8); many(32); assert(s_vertex_cache_misses == miss + 3);
    printf("PASS same-draw/across-frame reuse, source mutations, defaults and format changes\n");
    for (u32 draw = 0; draw < 512; draw++) {
        u32 off = 0x100000 + draw * 8192;
        for (u32 i = 0; i < 512; i++) put_bef(off + i * 16, (float)draw);
        m(M_VTXBUF_OFFSET, 0x80000000u | off);
        many(512);
        assert(s_vertex_cache_bytes <= ENG_VERTEX_CACHE_BYTES);
        assert(stub.draw_first_vertex[0] == (float)draw);
    }
    puts("PASS bounded eviction under changing guest addresses; no stale converted vertices");
    engine_down(); free(vm_base); vm_base = NULL;
    return 0;
}
