#include "../src/d2_flags.cpp"
#include <cassert>
#include <cstdlib>
#include <cstring>
#include <cstdio>
extern "C" { uint8_t* vm_base; }
extern "C" uint32_t vm_read32(uint64_t address)
{ uint32_t n; std::memcpy(&n, vm_base + address, 4); return __builtin_bswap32(n); }
extern "C" uint16_t vm_read16(uint64_t address)
{ uint16_t n; std::memcpy(&n, vm_base + address, 2); return __builtin_bswap16(n); }
static void put32(uint32_t a, uint32_t n) { n = __builtin_bswap32(n); std::memcpy(vm_base+a, &n, 4); }
static void put16(uint32_t a, uint16_t n) { n = __builtin_bswap16(n); std::memcpy(vm_base+a, &n, 2); }
int main()
{
    unsigned map = 0, stage = 0;
    assert(!d2_flags_guest_location(&map, &stage));
    vm_base = (uint8_t*)calloc(1, 0x800000); assert(vm_base);
#if D2_GAME_VERSION == 140
    const uint32_t toc = 0x47DF98, slot = toc - 0x2DC0, entry = 0x461000;
#else
    const uint32_t toc = 0x3FDE60, slot = toc - 0x31D8, entry = 0x3E0EE8;
#endif
    assert(!d2_flags_guest_location(&map, &stage));
    put32(entry+4, toc); assert(!d2_flags_guest_location(&map, &stage));
    put32(slot, 0xFFFFFFFE); assert(!d2_flags_guest_location(&map, &stage));
    put32(slot, 0x500000); put16(0x500000+0xD3BBA, 30101); put16(0x500000+0xD3BBE, 7);
    assert(d2_flags_guest_location(&map, &stage)); assert(map == 30101 && stage == 7);
    free(vm_base); vm_base = nullptr;
    printf("[AN location] version=%d TOC, big-endian map/stage, null/wrong-version/OOB guards: PASS\n", D2_GAME_VERSION);
}
