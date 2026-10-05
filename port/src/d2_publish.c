/* Atomic publication on macOS; never remove the previous app before success. */
#include <stdio.h>
#include <fcntl.h>
#include <unistd.h>
#include <sys/file.h>
#include <sys/stat.h>
#include <errno.h>
#include <stdlib.h>
int main(int argc, char** argv)
{
    if (argc != 3) return 2;
    char* lock = NULL;
    if (asprintf(&lock, "%s.lock", argv[2]) < 0) return 1;
    int fd = open(lock, O_CREAT | O_RDWR, 0600);
    free(lock);
    if (fd < 0 || flock(fd, LOCK_EX)) { perror("package lock"); return 1; }
    struct stat st;
    int rc = lstat(argv[2], &st);
    if (rc == 0) rc = renamex_np(argv[1], argv[2], RENAME_SWAP);
    else if (errno == ENOENT) rc = rename(argv[1], argv[2]);
    if (rc) perror("package publish");
    close(fd);
    return rc ? 1 : 0;
}
