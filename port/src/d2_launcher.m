/* Finder entry point: locate user-owned data and report runner failures. */
#import <AppKit/AppKit.h>
#include <fcntl.h>
#include <stdio.h>
#include <stdlib.h>
#include <unistd.h>
#include "d2_launcher_paths.h"
#include "d2_launcher_elf.h"

static void failure(NSString* detail)
{
    fprintf(stderr, "[D2 launcher] %s\n", detail.UTF8String);
    [NSApplication sharedApplication];
    [NSApp setActivationPolicy:NSApplicationActivationPolicyRegular];
    [NSApp activateIgnoringOtherApps:YES];
    NSAlert* alert = [NSAlert new];
    alert.messageText = @"Disgaea D2 could not start";
    alert.informativeText = detail;
    [alert runModal];
}

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
    return d2_elf_matches(path.fileSystemRepresentation, D2_EXPECTED_ENTRY_OPD, D2_EXPECTED_TOC);
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
        if (!make_directory(support) || !make_directory(logs)) {
            failure(@"Cannot create the Application Support or log directory."); return 1;
        }
        NSString* log = [logs stringByAppendingPathComponent:@"latest.log"];
        int fd = open(log.fileSystemRepresentation, O_WRONLY | O_CREAT | O_TRUNC, 0600);
        if (fd < 0 || dup2(fd, STDOUT_FILENO) < 0 || dup2(fd, STDERR_FILENO) < 0) {
            failure([@"Cannot open the game log: " stringByAppendingString:log]); return 1;
        }
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
        if (elf && !valid_elf(elf))
            fprintf(stderr, "[D2 launcher] rejecting eboot=%s; requires version %s entry/TOC\n",
                elf.fileSystemRepresentation, D2_GAME_VERSION_TEXT);
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
            candidate = [root stringByAppendingPathComponent:@D2_DEFAULT_EBOOT];
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
                elf = choose_path(@"Choose the decrypted BLUS31313 EBOOT.elf for version " D2_GAME_VERSION_TEXT ".", NO);
                if (!elf) return 0;
                if (!valid_elf(elf)) failure(@"The selected file is not a decrypted Disgaea D2 version "
                    D2_GAME_VERSION_TEXT @" executable. Choose the matching EBOOT.elf.");
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
        if (fd < 0) { failure(@"Cannot write the launcher configuration."); return 1; }
        BOOL written = write(fd, data.bytes, data.length) == (ssize_t)data.length;
        if (close(fd) != 0) written = NO;
        if (!written || rename(temporary.fileSystemRepresentation, config.fileSystemRepresentation) != 0) {
            perror("[D2 launcher] config write");
            unlink(temporary.fileSystemRepresentation);
            failure(@"Cannot save the launcher configuration.");
            return 1;
        }
        NSString* hdd0 = [support stringByAppendingPathComponent:@"hdd0"];
        NSString* hdd1 = [support stringByAppendingPathComponent:@"hdd1"];
        if (!make_directory(hdd0) || !make_directory(hdd1)) {
            failure(@"Cannot create the game save/cache directories."); return 1;
        }
        setenv("PS3_TITLE", "Disgaea D2", 1);
        setenv("PS3_VFS_ROOT", game.fileSystemRepresentation, 1);
        setenv("PS3_HDD0_ROOT", hdd0.fileSystemRepresentation, 1);
        setenv("PS3_HDD1_ROOT", hdd1.fileSystemRepresentation, 1);
        fprintf(stderr, "[D2 launcher] game_root=%s\neboot=%s\nhdd0=%s\nhdd1=%s\n",
            game.fileSystemRepresentation, elf.fileSystemRepresentation,
            hdd0.fileSystemRepresentation, hdd1.fileSystemRepresentation);
        // Relative SDK diagnostics belong in Application Support, never the dump.
        if (chdir(support.fileSystemRepresentation) != 0) {
            failure(@"Cannot access the Application Support directory."); return 1;
        }
        NSString* runner = [[NSBundle mainBundle].executablePath.stringByDeletingLastPathComponent
            stringByAppendingPathComponent:@"DisgaeaD2Recomp"];
        [NSApplication sharedApplication];
        [NSApp setActivationPolicy:NSApplicationActivationPolicyAccessory];
        NSTask* task = [NSTask new];
        task.executableURL = [NSURL fileURLWithPath:runner];
        task.arguments = @[elf];
        task.standardOutput = NSFileHandle.fileHandleWithStandardOutput;
        task.standardError = NSFileHandle.fileHandleWithStandardError;
        task.terminationHandler = ^(NSTask* finished) {
            dispatch_async(dispatch_get_main_queue(), ^{
                if (finished.terminationStatus != 0) {
                    NSFileHandle* file = [NSFileHandle fileHandleForReadingAtPath:log];
                    unsigned long long size = [file seekToEndOfFile];
                    [file seekToFileOffset:size > 8192 ? size - 8192 : 0];
                    NSString* tail = [[NSString alloc] initWithData:[file readDataToEndOfFile]
                        encoding:NSUTF8StringEncoding];
                    [file closeFile];
                    if (tail.length > 1200) tail = [tail substringFromIndex:tail.length - 1200];
                    failure([NSString stringWithFormat:@"Runner %@ %d.\nLog: %@\n\n%@",
                        finished.terminationReason == NSTaskTerminationReasonUncaughtSignal ? @"signal" : @"exit",
                        finished.terminationStatus, log, tail ?: @""]);
                }
                [NSApp terminate:nil];
            });
        };
        NSError* error = nil;
        if (![task launchAndReturnError:&error]) {
            failure([NSString stringWithFormat:@"Cannot launch %@: %@\nLog: %@",
                runner, error.localizedDescription, log]); return 1;
        }
        [NSApp run];
        return 0;
    }
}
