/* Finder entry point: locate user-owned data, then replace ourselves with the runner. */
#import <AppKit/AppKit.h>
#include <fcntl.h>
#include <stdio.h>
#include <stdlib.h>
#include <unistd.h>
#include "d2_launcher_paths.h"

static BOOL make_directory(NSString* path)
{
    NSError* error = nil;
    BOOL ok = [[NSFileManager defaultManager] createDirectoryAtPath:path
        withIntermediateDirectories:YES attributes:nil error:&error];
    if (!ok) fprintf(stderr, "[D2 launcher] mkdir: %s\n", error.localizedDescription.UTF8String);
    return ok;
}

static BOOL valid_game(NSString* path)
{
    return path && [[NSFileManager defaultManager] fileExistsAtPath:
        [path stringByAppendingPathComponent:@"PS3_GAME/PARAM.SFO"]];
}

static BOOL valid_elf(NSString* path)
{
    if (!path) return NO;
    FILE* file = fopen(path.fileSystemRepresentation, "rb");
    if (!file) return NO;
    unsigned char header[6] = {0};
    size_t count = fread(header, 1, sizeof header, file);
    fclose(file);
    return count == sizeof header && header[0] == 0x7f && header[1] == 'E' &&
        header[2] == 'L' && header[3] == 'F' && header[4] == 2 && header[5] == 2;
}

static NSString* choose_path(NSString* prompt, BOOL directory)
{
    NSOpenPanel* panel = [NSOpenPanel openPanel];
    panel.message = prompt;
    panel.canChooseDirectories = directory;
    panel.canChooseFiles = !directory;
    panel.allowsMultipleSelection = NO;
    return [panel runModal] == NSModalResponseOK ? panel.URL.path : nil;
}

int main(void)
{
    @autoreleasepool {
        NSString* home = NSHomeDirectory();
        NSString* support = [home stringByAppendingPathComponent:
            @"Library/Application Support/DisgaeaD2Recomp"];
        NSString* logs = [home stringByAppendingPathComponent:@"Library/Logs/DisgaeaD2Recomp"];
        if (!make_directory(support) || !make_directory(logs)) return 1;
        NSString* log = [logs stringByAppendingPathComponent:@"latest.log"];
        int fd = open(log.fileSystemRepresentation, O_WRONLY | O_CREAT | O_TRUNC, 0600);
        if (fd < 0) return 1;
        if (dup2(fd, STDOUT_FILENO) < 0 || dup2(fd, STDERR_FILENO) < 0) return 1;
        close(fd);
        setvbuf(stdout, NULL, _IOLBF, 0);

        NSString* config = [support stringByAppendingPathComponent:@"config"];
        NSString* game = nil;
        NSString* elf = nil;
        NSString* text = [NSString stringWithContentsOfFile:config
            encoding:NSUTF8StringEncoding error:nil];
        for (NSString* line in [text componentsSeparatedByCharactersInSet:
                [NSCharacterSet newlineCharacterSet]]) {
            if ([line hasPrefix:@"game_root="]) game = [[line substringFromIndex:10] stringByExpandingTildeInPath];
            if ([line hasPrefix:@"eboot="]) elf = [[line substringFromIndex:6] stringByExpandingTildeInPath];
        }
        NSString* app = [NSBundle mainBundle].bundlePath;
        NSString* parent = [app stringByDeletingLastPathComponent];
        NSArray<NSString*>* roots = @[
            @D2_PROJECT_ROOT,
            [[parent stringByDeletingLastPathComponent] stringByDeletingLastPathComponent],
            parent, [parent stringByAppendingPathComponent:@"Disgaea D2-RE"]
        ];
        for (NSString* root in roots) {
            NSString* candidate = [root stringByAppendingPathComponent:
                @"Disgaea D2 A Brighter Darkness - [BLUS31313]"];
            if (!valid_game(game) && valid_game(candidate)) game = candidate;
            candidate = [root stringByAppendingPathComponent:@"work/EBOOT.elf"];
            if (!valid_elf(elf) && valid_elf(candidate)) elf = candidate;
        }
        if (!valid_game(game) || !valid_elf(elf)) {
            [NSApplication sharedApplication];
            [NSApp setActivationPolicy:NSApplicationActivationPolicyRegular];
            [NSApp activateIgnoringOtherApps:YES];
            while (!valid_game(game)) {
                game = choose_path(@"Choose the BLUS31313 game dump folder containing PS3_GAME.", YES);
                if (!game) return 0;
            }
            while (!valid_elf(elf)) {
                elf = choose_path(@"Choose the decrypted BLUS31313 EBOOT.elf (not EBOOT.BIN).", NO);
                if (!elf) return 0;
            }
        }
        game = game.stringByStandardizingPath;
        elf = elf.stringByStandardizingPath;
        text = [NSString stringWithFormat:@"game_root=%@\neboot=%@\n", game, elf];
        // Keep the atomic replacement in this directory (Foundation may use
        // a separate replacement-directory service that a sandbox denies).
        NSString* temporary = [config stringByAppendingFormat:@".%d", getpid()];
        NSData* data = [text dataUsingEncoding:NSUTF8StringEncoding];
        fd = open(temporary.fileSystemRepresentation, O_WRONLY | O_CREAT | O_EXCL, 0600);
        if (fd < 0) { perror("[D2 launcher] config open"); return 1; }
        BOOL written = write(fd, data.bytes, data.length) == (ssize_t)data.length;
        if (close(fd) != 0) written = NO;
        if (!written || rename(temporary.fileSystemRepresentation, config.fileSystemRepresentation) != 0) {
            perror("[D2 launcher] config write");
            unlink(temporary.fileSystemRepresentation);
            return 1;
        }
        NSString* hdd0 = [support stringByAppendingPathComponent:@"hdd0"];
        NSString* hdd1 = [support stringByAppendingPathComponent:@"hdd1"];
        if (!make_directory(hdd0) || !make_directory(hdd1)) return 1;
        setenv("PS3_TITLE", "Disgaea D2", 1);
        setenv("PS3_VFS_ROOT", game.fileSystemRepresentation, 1);
        setenv("PS3_HDD0_ROOT", hdd0.fileSystemRepresentation, 1);
        setenv("PS3_HDD1_ROOT", hdd1.fileSystemRepresentation, 1);
        fprintf(stderr, "[D2 launcher] game_root=%s\neboot=%s\nhdd0=%s\nhdd1=%s\n",
            game.fileSystemRepresentation, elf.fileSystemRepresentation,
            hdd0.fileSystemRepresentation, hdd1.fileSystemRepresentation);
        // Relative SDK diagnostics belong in Application Support, never the dump.
        if (chdir(support.fileSystemRepresentation) != 0) return 1;
        NSString* runner = [[NSBundle mainBundle].executablePath.stringByDeletingLastPathComponent
            stringByAppendingPathComponent:@"DisgaeaD2Recomp"];
        execl(runner.fileSystemRepresentation, runner.fileSystemRepresentation,
            elf.fileSystemRepresentation, (char*)NULL);
        perror("[D2 launcher] exec runner");
        return 1;
    }
}
