/* Full-span mutation coverage and indicative renderer-hotspot benchmark. */
#include "../ps3recomp/libs/video/rsx_draw_engine.c"
#include <assert.h>
#include <time.h>
u8* vm_base;
u32 ppu_vm_size;
u32 cellGcmResolveLocated(int local, u32 offset) { (void)local; return offset; }
u32 cellGcmResolveIO(u32 offset) { return offset; }

static u64 ns(void)
{
    struct timespec t;
    clock_gettime(CLOCK_MONOTONIC, &t);
    return (u64)t.tv_sec * 1000000000ull + t.tv_nsec;
}
static const u8* reader(void* user, u32 location, u32 offset, u32 span)
{
    (void)user; (void)location;
    return (u64)offset + span <= ppu_vm_size ? vm_base + offset : NULL;
}
__attribute__((noinline)) static u64 previous_hash(const u8* src, u32 span)
{
    u64 hash = 1469598103934665603ull;
    u32 i = 0;
    for (; i + 8 <= span; i += 8) {
        u64 word;
        memcpy(&word, src + i, sizeof(word));
        hash = (hash ^ word) * 1099511628211ull;
    }
    for (; i < span; i++) hash = (hash ^ src[i]) * 1099511628211ull;
    return hash;
}
__attribute__((noinline)) static u64 current_hash(u32 offset, u32 span)
{
    int readable = 0;
    u64 hash = eng_texture_content_hash(1, offset, span, &readable);
    assert(readable);
    return hash;
}
int main(void)
{
    ppu_vm_size = (8u << 20) + 32;
    vm_base = malloc(ppu_vm_size);
    assert(vm_base);
    for (u32 i = 0; i < ppu_vm_size; i++) vm_base[i] = (u8)(i * 131 + i / 31);
    rsx_draw_engine_set_guest_memory(reader, NULL);
    unsigned checked = 0;
    for (u32 offset = 0; offset < 8; offset++) {
        for (u32 span = 1; span <= 129; span++) {
            u64 hash = current_hash(offset, span);
            assert(hash == current_hash(offset, span));
            for (u32 byte = 0; byte < span; byte++) {
                vm_base[offset + byte] ^= (u8)(1u << (byte % 8));
                assert(hash != current_hash(offset, span));
                vm_base[offset + byte] ^= (u8)(1u << (byte % 8));
                checked++;
            }
        }
    }
    int readable = 1;
    assert(!eng_texture_content_hash(1, 0, 0, &readable) && !readable);
    assert(!eng_texture_content_hash(1, ppu_vm_size - 1, 2, &readable) && !readable);
    printf("PASS %u individual byte mutations, all alignments/tails, stable and unreadable inputs\n", checked);
    volatile u64 sink = 0;
    const u32 span = 8u << 20;
    u64 start = ns();
    for (unsigned i = 0; i < 64; i++) sink ^= previous_hash(vm_base + i % 8, span);
    u64 before = ns() - start;
    start = ns();
    for (unsigned i = 0; i < 64; i++) sink ^= current_hash(i % 8, span);
    u64 after = ns() - start;
    printf("512 MiB: previous=%.3f ms current=%.3f ms speedup=%.2fx sink=%llu\n",
           before / 1e6, after / 1e6, (double)before / after, (unsigned long long)sink);
    free(vm_base);
}
