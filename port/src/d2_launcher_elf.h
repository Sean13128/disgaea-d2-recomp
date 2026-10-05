/* Match the runner's entry OPD/TOC before accepting a decrypted executable. */
#ifndef D2_LAUNCHER_ELF_H
#define D2_LAUNCHER_ELF_H
#include <stdint.h>
#include <stdio.h>
#include <string.h>

static uint64_t d2_elf_be(const unsigned char* p, unsigned n)
{
    uint64_t value = 0;
    for (unsigned i = 0; i < n; i++) value = (value << 8) | p[i];
    return value;
}

static int d2_elf_matches(const char* path, uint64_t entry, uint64_t toc)
{
    FILE* file = path ? fopen(path, "rb") : NULL;
    if (!file) return 0;
    unsigned char header[64], ph[56], opd[8];
    int match = 0;
    if (fread(header, 1, sizeof header, file) != sizeof header ||
        memcmp(header, "\177ELF\2\2\1", 7) || d2_elf_be(header + 18, 2) != 21 ||
        d2_elf_be(header + 24, 8) != entry || d2_elf_be(header + 54, 2) < sizeof ph)
        goto done;
    if (fseeko(file, 0, SEEK_END)) goto done;
    off_t length = ftello(file);
    if (length < 0) goto done;
    uint64_t phoff = d2_elf_be(header + 32, 8);
    uint64_t stride = d2_elf_be(header + 54, 2);
    unsigned count = (unsigned)d2_elf_be(header + 56, 2);
    if (phoff > (uint64_t)length || count > ((uint64_t)length - phoff) / stride) goto done;
    for (unsigned i = 0; i < count; i++) {
        if (fseeko(file, (off_t)(phoff + i * stride), SEEK_SET) ||
            fread(ph, 1, sizeof ph, file) != sizeof ph) break;
        if (d2_elf_be(ph, 4) != 1) continue; /* PT_LOAD */
        uint64_t offset = d2_elf_be(ph + 8, 8), address = d2_elf_be(ph + 16, 8);
        uint64_t size = d2_elf_be(ph + 32, 8);
        if (entry < address || size < sizeof opd || entry - address > size - sizeof opd ||
            offset > (uint64_t)length || size > (uint64_t)length - offset) continue;
        if (!fseeko(file, (off_t)(offset + entry - address), SEEK_SET) &&
            fread(opd, 1, sizeof opd, file) == sizeof opd)
            match = d2_elf_be(opd + 4, 4) == toc;
        break;
    }
done:
    fclose(file);
    return match;
}
#endif
