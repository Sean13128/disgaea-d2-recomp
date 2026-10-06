/* Native guest memset (src/d2_fill.cpp) against the lifted body it replaces:
 * identical guest bytes, canaries and full end-state ppu_context, including
 * the fallback ranges (null page, out of bounds) that must run the lift. */
#include "ppu_recomp.h"
#include <assert.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <time.h>
#include <initializer_list>
extern "C" {
uint8_t* vm_base;
extern uint32_t ppu_vm_size;
const func_entry function_table[] = {{0, nullptr}};
const uint64_t function_table_count = 0;
}
void d2_original_0033D91C(ppu_context*);   /* the lift, from fill_lift.cpp */
enum : uint32_t { VM = 0x400000 };

static ppu_context seed(uint64_t a, uint64_t v, uint64_t n, unsigned salt)
{
    ppu_context c;
    memset(&c, 0, sizeof c);
    srand(salt);
    for (auto& r : c.gpr) r = (uint64_t)rand() << 33 ^ (uint64_t)rand();
    c.cr = (uint32_t)rand(); c.ctr = (uint32_t)rand() | 1; c.lr = 0x1234;
    c.gpr[3] = a; c.gpr[4] = v; c.gpr[5] = n;
    return c;
}

static void same(uint64_t a, uint64_t v, uint64_t n, unsigned salt)
{
    static uint8_t want[VM];
    ppu_context ref = seed(a, v, n, salt), got = ref;
    memset(vm_base, 0x91, VM); d2_original_0033D91C(&ref); memcpy(want, vm_base, VM);
    memset(vm_base, 0x91, VM); func_0033D91C(&got);
    if (memcmp(want, vm_base, VM) || memcmp(&ref, &got, sizeof ref)) {
        fprintf(stderr, "FAIL a=0x%llx v=0x%llx n=0x%llx\n",
                (unsigned long long)a, (unsigned long long)v, (unsigned long long)n);
        for (int i = 0; i < 32; i++)
            if (ref.gpr[i] != got.gpr[i])
                fprintf(stderr, "  r%d lift=0x%llx native=0x%llx\n", i,
                        (unsigned long long)ref.gpr[i], (unsigned long long)got.gpr[i]);
        fprintf(stderr, "  cr 0x%x/0x%x ctr 0x%llx/0x%llx\n", ref.cr, got.cr,
                (unsigned long long)ref.ctr, (unsigned long long)got.ctr);
        exit(1);
    }
}

static double cpu_us()
{
    timespec t; clock_gettime(CLOCK_PROCESS_CPUTIME_ID, &t);
    return t.tv_sec * 1e6 + t.tv_nsec / 1e3;
}

int main()
{
    vm_base = (uint8_t*)calloc(1, VM); assert(vm_base);
    ppu_vm_size = VM;
    unsigned cases = 0, salt = 1;
    const uint64_t sizes[] = {0, 1, 2, 3, 6, 7, 8, 9, 15, 16, 63, 64, 65, 71, 72, 127,
                              128, 129, 135, 136, 4095, 4096, 65536, 0x1c2010};
    for (uint64_t n : sizes)
        for (uint64_t align = 0; align < 16; align++)
            for (uint64_t v : {0x00ull, 0x01ull, 0x7Full, 0xFFull, 0xFFFFFFFFFFFFFF5Aull}) {
                same(0x10000 + align, v, n, salt++); cases++;
            }
    /* Ranges vm_fill declines: the lift must run unchanged. */
    same(0x800, 0, 0x40, salt++);                 /* null page: stores dropped */
    same(VM - 0x20, 0xAB, 0x40, salt++);          /* runs off the mapped VM */
    same(0x10000, 0xCD, 1ull << 32 | 8, salt++);  /* size with high bits */
    cases += 3;
    printf("PASS: %u fills match the lift (bytes, canaries, GPR/CR/CTR)\n", cases);

    const unsigned reps = 200; ppu_context c;
    double t = cpu_us();
    for (unsigned i = 0; i < reps; i++) { c = seed(0x10000, i, 0x1c2010, 0); d2_original_0033D91C(&c); }
    double lift = (cpu_us() - t) / reps;
    t = cpu_us();
    for (unsigned i = 0; i < reps; i++) { c = seed(0x10000, i, 0x1c2010, 0); func_0033D91C(&c); }
    double native = (cpu_us() - t) / reps;
    printf("INFO: 1.76 MiB fill lift %.1f us, native %.1f us (%.0fx)\n", lift, native, lift / native);
    free(vm_base);
}
