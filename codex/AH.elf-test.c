#include "../port/src/d2_launcher_elf.h"
#include <assert.h>
int main(int argc, char** argv)
{
    assert(argc == 3);
    assert(d2_elf_matches("work/v140/EBOOT.elf", 0x461000, 0x47df98));
    assert(d2_elf_matches("work/EBOOT.elf", 0x3e0ee8, 0x3fde60));
    assert(!d2_elf_matches("work/EBOOT.elf", 0x461000, 0x47df98));
    assert(!d2_elf_matches("work/v140/EBOOT.elf", 0x3e0ee8, 0x3fde60));
    /* Entry patched to match 140, but the OPD still carries the 100 TOC. */
    assert(!d2_elf_matches(argv[1], 0x461000, 0x47df98));
    assert(!d2_elf_matches(argv[2], 0x461000, 0x47df98));
    assert(!d2_elf_matches(NULL, 0x461000, 0x47df98));
    puts("[AH-test] ELF 100/140 entry + segment-mapped TOC, spoofed entry, truncated ELF: PASS");
}
