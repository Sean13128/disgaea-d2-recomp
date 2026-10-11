/* ThreadSanitizer target: ppu_fs descriptor tables under concurrent open,
 * read, fstat, close and directory traffic, including closes that race with
 * another thread's use of the same descriptor. No game assets. */
#include "runtime/ppu/ppu_fs.cpp"
#include <cassert>
#include <thread>
#include <vector>

extern "C" {
uint8_t* vm_base;
uint32_t ppu_vm_size;
void ppu_guest_caller(char* out, size_t n) { snprintf(out, n, "test"); }
void ps3_hle_register_ctx(uint32_t, const char*, void (*)(ppu_context*)) {}
void vm_write32(uint64_t a, uint32_t v)
{
    for (int i = 0; i < 4; i++) vm_base[a + i] = (uint8_t)(v >> (24 - 8 * i));
}
void vm_write64(uint64_t a, uint64_t v) { vm_write32(a, (uint32_t)(v >> 32)); vm_write32(a + 4, (uint32_t)v); }
void ydkj_host_bt(const char*) {}
const char* edat_resolve(const char* path, char*, size_t) { return path; }
}

static uint32_t be32(uint32_t a)
{
    return (uint32_t)vm_base[a] << 24 | (uint32_t)vm_base[a + 1] << 16 |
           (uint32_t)vm_base[a + 2] << 8 | vm_base[a + 3];
}

static int64_t call(void (*fn)(ppu_context*), uint64_t a, uint64_t b = 0, uint64_t c = 0, uint64_t d = 0)
{
    ppu_context ctx;
    memset(&ctx, 0, sizeof ctx);
    ctx.gpr[3] = a; ctx.gpr[4] = b; ctx.gpr[5] = c; ctx.gpr[6] = d;
    fn(&ctx);
    return (int64_t)(int32_t)ctx.gpr[3];
}

static std::atomic<int> g_opened{0}, g_reads{0};

static void worker(uint32_t base)
{
    const uint32_t path = base, fdp = base + 0x100, buf = base + 0x1000, sb = base + 0x200;
    strcpy((char*)vm_base + path, "/app_home/data.bin");
    for (int i = 0; i < 300; i++) {
        if (call(cellFsOpen, path, 0, fdp) != 0) continue;
        const int fd = (int)be32(fdp);
        g_opened++;
        if (call(cellFsRead, fd, buf, 4096, sb) == 0) g_reads++;
        call(cellFsFstat, fd, sb);
        call(cellFsClose, fd);
    }
}

static void chaos(uint32_t base)
{
    for (int i = 0; i < 3000; i++) {
        const int fd = 3 + i % 12;
        call(cellFsRead, fd, base + 0x1000, 512, base);
        call(cellFsFstat, fd, base + 0x200);
        if (i % 7 == 0) call(cellFsClose, fd);
    }
}

static void dirs(uint32_t base)
{
    strcpy((char*)vm_base + base, "/app_home");
    for (int i = 0; i < 200; i++) {
        if (call(cellFsOpendir, base, base + 0x100) != 0) continue;
        const int fd = (int)be32(base + 0x100);
        call(cellFsReaddir, fd, base + 0x200, base + 0x400);
        call(cellFsClosedir, fd);
    }
}

int main(int argc, char** argv)
{
    assert(argc == 2);
    ppu_vm_size = 16u << 20;
    vm_base = (uint8_t*)calloc(1, ppu_vm_size);
    ppu_vfs_root = argv[1];
    char host[1024];
    snprintf(host, sizeof host, "%s/data.bin", argv[1]);
    FILE* f = fopen(host, "wb");
    assert(f);
    for (int i = 0; i < 65536; i++) fputc(i & 0xFF, f);
    fclose(f);

    std::vector<std::thread> threads;
    for (uint32_t i = 0; i < 4; i++) threads.emplace_back(worker, 0x100000u * (i + 1));
    for (uint32_t i = 0; i < 2; i++) threads.emplace_back(chaos, 0x800000u + 0x100000u * i);
    threads.emplace_back(dirs, 0xC00000u);
    for (auto& t : threads) t.join();
    assert(g_opened > 0 && g_reads > 0);
    printf("PASS: %d opens, %d reads raced against foreign closes\n", g_opened.load(), g_reads.load());
}
