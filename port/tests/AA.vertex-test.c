/* Differential conversion/bounds tests plus an isolated stream benchmark. */
#include "libs/video/rsx_vertex_compact.h"
#include <assert.h>
#include <math.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <time.h>
#include <sys/mman.h>
#include <unistd.h>
#ifdef __APPLE__
#include <pthread/qos.h>
#endif
static const u8* source;
static u32 source_bytes;
static const u8* read_stream(void* user, u32 loc, u32 off, u32 n)
{
    (void)user; (void)loc;
    return (u64)off + n <= source_bytes ? source + off : NULL;
}
static double ms(void)
{
    struct timespec t; clock_gettime(CLOCK_MONOTONIC, &t);
    return t.tv_sec * 1000.0 + t.tv_nsec / 1e6;
}
int main(void)
{
#ifdef __APPLE__
    pthread_set_qos_class_self_np(QOS_CLASS_USER_INTERACTIVE, 0);
#endif
    rsx_dispatch* rsx = calloc(1, sizeof(*rsx));
    rsx_vertex_ref refs[4096];
    u8* scalar = malloc(4096 * 64), *bulk = malloc(4096 * 64);
    const size_t page = (size_t)sysconf(_SC_PAGESIZE);
    u8* pages = mmap(NULL, page * 2, PROT_READ | PROT_WRITE, MAP_PRIVATE | MAP_ANON, -1, 0);
    assert(pages != MAP_FAILED && !mprotect(pages + page, page, PROT_NONE));
    u32 checks = 0;
    for (u32 type = 1; type <= 7; type++) {
        for (u32 size = 1; size <= 4; size++) {
            u32 elem = type == 6 ? 4 : size * ((type == 2) ? 4 : (type == 4 || type == 7) ? 1 : 2);
            source_bytes = 19 * elem;
            source = pages + page - source_bytes;
            for (u32 i = 0; i < source_bytes; i++) ((u8*)source)[i] = (u8)(i * 131u + type * 17u);
            for (u32 freq = 0; freq <= 3; freq++) for (u32 modulo = 0; modulo < 2; modulo++) {
                rsx_dispatch_init(rsx, NULL);
                rsx_dispatch_method(rsx, 0x1740, type | size << 4 | elem << 8 | freq << 16);
                rsx_dispatch_method(rsx, 0x1fc0, modulo);
                rsx_vertex_layout_plan layout;
                rsx_vertex_layout_plan_init(&layout, 1);
                rsx_vertex_fetch_plan plan;
                rsx_vertex_fetch_plan_init(&plan, rsx, &layout, read_stream, NULL);
                for (u32 i = 0; i < 19; i++) refs[i] = (rsx_vertex_ref){18 - i, 0};
                rsx_vertex_fetch_plan_prepare(&plan, refs, 19);
                for (u32 i = 0; i < 19; i++) assert(rsx_vertex_fetch_one(&plan, &refs[i], scalar + i * 16));
                assert(rsx_vertex_fetch_many(&plan, refs, 19, bulk));
                for (u32 i = 0; i < 19 * 4; i++) {
                    float a, b; memcpy(&a, scalar + i * 4, 4); memcpy(&b, bulk + i * 4, 4);
                    assert((isnan(a) && isnan(b)) || a == b || fabsf(a - b) <= fabsf(a) * 1e-6f + 1e-7f);
                    checks++;
                }
            }
        }
    }
    /* Invalid position and disabled/invalid non-position fallback. */
    rsx_dispatch_init(rsx, NULL);
    rsx_dispatch_method(rsx, 0x1740, 2 | 4 << 4 | 16 << 8);
    rsx_vertex_layout_plan layout;
    rsx_vertex_layout_plan_init(&layout, 9);
    rsx_vertex_fetch_plan plan;
    rsx_vertex_fetch_plan_init(&plan, rsx, &layout, read_stream, NULL);
    refs[0] = (rsx_vertex_ref){0xfffff, 0};
    rsx_vertex_fetch_plan_prepare(&plan, refs, 1);
    assert(!rsx_vertex_fetch_many(&plan, refs, 1, bulk));
    rsx_dispatch_method(rsx, 0x1740, 0);
    rsx_vertex_fetch_plan_init(&plan, rsx, &layout, read_stream, NULL);
    assert(rsx_vertex_fetch_many(&plan, refs, 1, bulk));
    assert(((float*)bulk)[7] == 1.0f && ((float*)bulk)[4] == 1.0f);
    printf("PASS %u component comparisons; all 7 formats, sizes, frequencies, guard-page tails and invalid/default attributes\n", checks);
    munmap(pages, page * 2);
    u8* mesh = malloc(4096 * 32);
    source = mesh; source_bytes = 4096 * 32;
    for (u32 i = 0; i < source_bytes; i++) mesh[i] = (u8)(i * 131);
    rsx_dispatch_init(rsx, NULL);
    rsx_dispatch_method(rsx, 0x1740, 2 | 3 << 4 | 32 << 8);
    rsx_dispatch_method(rsx, 0x174c, 4 | 4 << 4 | 32 << 8);
    rsx_dispatch_method(rsx, 0x168c, 12);
    rsx_dispatch_method(rsx, 0x1760, 3 | 2 << 4 | 32 << 8);
    rsx_dispatch_method(rsx, 0x16a0, 16);
    rsx_vertex_layout_plan_init(&layout, 1 | 8 | 256);
    rsx_vertex_fetch_plan_init(&plan, rsx, &layout, read_stream, NULL);
    for (u32 i = 0; i < 4096; i++) refs[i] = (rsx_vertex_ref){i, 0};
    rsx_vertex_fetch_plan_prepare(&plan, refs, 4096);
    double t = ms();
    for (u32 run = 0; run < 300; run++) for (u32 i = 0; i < 4096; i++)
        assert(rsx_vertex_fetch_one(&plan, &refs[i], scalar + i * layout.stride));
    double old = ms() - t; t = ms();
    for (u32 run = 0; run < 300; run++) assert(rsx_vertex_fetch_many(&plan, refs, 4096, bulk));
    double now = ms() - t;
    printf("Synthetic 1,228,800 vertices (float3/u8n4/half2): scalar %.3f ms, bulk %.3f ms, %.2fx; checksum %u\n", old, now, old / now, bulk[0]);
    free(mesh); free(scalar); free(bulk); free(rsx);
    return 0;
}
