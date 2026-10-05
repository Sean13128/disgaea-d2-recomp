/* Exercise quit admission while the production savedata callback is active. */
#define main baseline_savedata_main
#define callback baseline_callback
#include "libs/system/tests/test_savedata_io.c"
#undef callback
#undef main
#include <pthread.h>
#include <stdatomic.h>
static atomic_int entered, release_callback;
static s32 save_result;
static void blocking_callback(u32 opd, u64 cb, u64 get, u64 set,
                              u64 a, u64 b, u64 c, u64 d, u64 e)
{
    if (opd == 0x900) {
        entered = 1;
        while (!release_callback) usleep(1000);
    }
    baseline_callback(opd, cb, get, set, a,b,c,d,e);
}
static void* saver(void* arg)
{
    (void)arg;
    save_result = cellSaveDataFixedSave2(0, (void*)0x100, (void*)0x200, (void*)0x800,
                                       (void*)0x900, (void*)0xA00, 0, (void*)7);
    return NULL;
}
int main(int argc, char** argv)
{
    assert(argc == 2);
    char root[1024]; snprintf(root, sizeof root, "%s/save-stop.XXXXXX", argv[1]);
    assert(mkdtemp(root)); strcpy(s_save_root, root);
    void* arena = NULL;
    assert(!posix_memalign(&arena, vm_host_page_size(), 0x200000));
    vm_base = arena; memset(vm_base, 0, 0x200000);
    assert(cellSaveData_set_scratch_region(0x100000, 0x20000) == CELL_OK);
    strcpy((char*)vm_base+0x300, "TEST00000"); strcpy((char*)vm_base+0x340, "DATA.BIN");
    memcpy(vm_base+0x400, payload, sizeof payload);
    vm_write32(0x108, 0x300); vm_write32(0x200, 4); vm_write32(0x204, 2);
    g_ps3_guest_caller = blocking_callback;
    pthread_t thread; assert(!pthread_create(&thread, NULL, saver, NULL));
    while (!entered) usleep(1000);
    assert(!cellSaveDataHostRequestStop());
    assert(cellSaveDataFixedSave2(0, NULL,NULL,NULL,NULL,NULL,0,NULL) == CELL_SAVEDATA_ERROR_BUSY);
    release_callback = 1; assert(!pthread_join(thread, NULL));
    assert(save_result == CELL_OK && cellSaveDataHostRequestStop());
    char path[1200], bytes[sizeof payload]; snprintf(path, sizeof path, "%s/TEST00000/DATA.BIN", root);
    FILE* f = fopen(path, "rb"); assert(f); assert(fread(bytes, 1, sizeof bytes, f) == sizeof bytes); fclose(f);
    assert(!memcmp(bytes, payload, sizeof bytes));
    snprintf(path, sizeof path, "%s/TEST00000", root); assert(delete_save_path(path) == CELL_OK);
    assert(!rmdir(root)); free(vm_base);
    puts("[AL-save-stop] active save finishes with intact payload; subsequent saves rejected: PASS");
    return 0;
}
