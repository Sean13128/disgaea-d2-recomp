/* Shared update overlay, hdd0 translation, parent-traversal rejection and the
 * read-only disc mount, without any game assets. */
#include "runtime/syscalls/sys_fs.c"
#undef st_atime
#undef st_mtime
#undef st_ctime
#pragma clang diagnostic ignored "-Wmacro-redefined"
#include "libs/filesystem/cellFs.c"
#include <assert.h>
uint8_t* vm_base;
uint32_t ppu_vm_size;
static void write_file(const char* path)
{
    ps3_vfs_ensure_parent_dirs(path);
    FILE* f = fopen(path, "wb"); assert(f); fputs("test", f); fclose(f);
}
int main(int argc, char** argv)
{
    assert(argc == 2);
    char disc[1024], hdd[1024], path[1024], update[1024], expected[1024];
    snprintf(disc, sizeof disc, "%s/disc", argv[1]);
    snprintf(hdd, sizeof hdd, "%s/hdd0", argv[1]);
    setenv("PS3_VFS_ROOT", disc, 1); setenv("PS3_HDD0_ROOT", hdd, 1);
    setenv("PS3_GAME_UPDATE_ID", "TEST00000", 1);
    snprintf(path, sizeof path, "%s/PS3_GAME/USRDIR/Data/START_7.dat", disc);
    write_file(path);
    snprintf(update, sizeof update, "%s/game/TEST00000/USRDIR/Data/START_7.dat", hdd);
    write_file(update);
    ps3_vfs_ps3game_fallback(path, sizeof path); assert(!strcmp(path, update));
    snprintf(path, sizeof path, "%s/USRDIR/Data/START_7.dat", disc);
    ps3_vfs_ps3game_fallback(path, sizeof path); assert(!strcmp(path, update));
    snprintf(path, sizeof path, "%s/PS3_GAME/USRDIR/Data/disc-only.dat", disc);
    write_file(path); snprintf(expected, sizeof expected, "%s", path);
    ps3_vfs_ps3game_fallback(path, sizeof path); assert(!strcmp(path, expected));
    unsetenv("PS3_GAME_UPDATE_ID");
    snprintf(path, sizeof path, "%s/PS3_GAME/USRDIR/Data/START_7.dat", disc);
    snprintf(expected, sizeof expected, "%s", path);
    ps3_vfs_ps3game_fallback(path, sizeof path); assert(!strcmp(path, expected));
    assert(cellfs_translate_path("/dev_hdd0/game/NPUB31321/USRDIR/Data/flag/test.edat", path, sizeof path) == 0);
    snprintf(expected, sizeof expected, "%s/game/NPUB31321/USRDIR/Data/flag/test.edat", hdd);
    assert(!strcmp(path, expected));
    assert(cellfs_translate_path("/dev_hdd0", path, sizeof path) == 0);
    snprintf(expected, sizeof expected, "%s/", hdd); assert(!strcmp(path, expected));

    /* ".." components never resolve, whichever translator sees them. */
    assert(!ps3_vfs_guest_path_safe("/dev_hdd0/game/../../etc/passwd"));
    assert(!ps3_vfs_guest_path_safe(".."));
    assert(!ps3_vfs_guest_path_safe("/app_home/USRDIR/.."));
    assert(!ps3_vfs_guest_path_safe("/dev_bdvd\\..\\x"));
    assert(ps3_vfs_guest_path_safe("/dev_hdd0/game/a..b/..c/d.."));
    assert(cellfs_translate_path("/dev_hdd0/game/../../etc/passwd", path, sizeof path) == -1);
    assert(cellfs_translate_path("/dev_bdvd/../outside", path, sizeof path) == -1);
    path[0] = 'x';
    sys_fs_translate_path("/app_home/../../outside", path, (int)sizeof path);
    assert(path[0] == '\0');

    /* The disc mount is read-only by guest prefix and by host location; hdd0
     * stays writable and a sibling of the dump root is not mistaken for it. */
    assert(ps3_vfs_write_denied("/dev_bdvd/PS3_GAME/USRDIR/x", "", NULL));
    assert(ps3_vfs_write_denied("/dev_bdvd", NULL, NULL));
    assert(!ps3_vfs_write_denied("/dev_bdvdx/y", "", NULL));
    snprintf(path, sizeof path, "%s/USRDIR/Data/new.dat", disc);
    assert(ps3_vfs_write_denied("/app_home/USRDIR/Data/new.dat", path, "."));
    snprintf(path, sizeof path, "%s/game/TEST00000/USRDIR/save.dat", hdd);
    assert(!ps3_vfs_write_denied("/dev_hdd0/game/TEST00000/USRDIR/save.dat", path, "."));
    snprintf(path, sizeof path, "%s2/x", disc);
    assert(!ps3_vfs_write_denied("/host_root/x", path, "."));
    snprintf(path, sizeof path, "%s/x", argv[1]);
    assert(ps3_vfs_write_denied("/host_root/x", path, argv[1]));
    puts("PASS: shared overlay precedence, disc fallback, version-100 isolation, DLC/bare hdd0 paths");
    puts("PASS: parent traversal rejected, disc mount read-only, hdd0 writable");
}
