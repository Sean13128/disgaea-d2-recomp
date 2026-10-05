/* D2 host settings. All UI/model/persistence access stays on AppKit's main thread. */
#import <AppKit/AppKit.h>
#include <assert.h>
#include <fcntl.h>
#include <unistd.h>
#include "d2_launcher_paths.h"
#include "rsx_host_settings.h"
#include "cellAudio_host.h"

extern void d2_cheats_toggle_menu(void) __attribute__((weak_import));
static NSMutableDictionary* s_settings;
static NSWindow* s_window;
static NSTextField* s_fps;
static BOOL s_borderless;
static NSRect s_regular_frame;
static NSWindowStyleMask s_regular_style;
static NSArray* s_observers;
static NSTimer* s_geometry_timer;
static void message(NSString* title, NSString* detail);

static NSDictionary* defaults(void)
{
    return @{ @"scale": @1, @"filter": @"linear", @"aspect": @"letterbox", @"vsync": @YES,
        @"frame_cap": @60, @"show_fps": @NO, @"volume": @1, @"mute": @NO,
        @"mute_unfocused": @NO, @"always_on_top": @NO, @"remember_window": @YES,
        @"window_width": @1280, @"window_height": @720 };
}

static NSString* settings_path(void)
{
    const char* override = getenv("D2_SETTINGS_PATH");
    if (override && *override) return [NSString stringWithUTF8String:override];
    return [NSHomeDirectory() stringByAppendingPathComponent:
        @"Library/Application Support/DisgaeaD2Recomp/settings.json"];
}

/* Unknown fields and wrong types cannot change the model. Corrupt files use defaults. */
static void merge_settings(NSMutableDictionary* result, id input)
{
    if (![input isKindOfClass:NSDictionary.class]) return;
    for (NSString* key in defaults()) {
        id v = input[key];
        if (!v) continue;
        if ([key isEqual:@"filter"]) {
            if ([@[@"linear", @"nearest", @"integer"] containsObject:v]) result[key] = v;
        } else if ([key isEqual:@"aspect"]) {
            if ([@[@"letterbox", @"stretch"] containsObject:v]) result[key] = v;
        } else if ([v isKindOfClass:NSNumber.class] && isfinite([v doubleValue])) {
            double n = [v doubleValue];
            if ([key isEqual:@"scale"]) {
                if ([@[@1, @1.5, @2, @3] containsObject:v]) result[key] = v;
            } else if ([key isEqual:@"frame_cap"]) {
                if ([@[@0, @30, @60, @120] containsObject:v]) result[key] = v;
            } else if ([key isEqual:@"volume"]) result[key] = @(MAX(0, MIN(1, n)));
            else if ([key hasPrefix:@"window_"]) result[key] = @(MAX(180, MIN(8192, n)));
            else result[key] = @([v boolValue]);
        }
    }
    for (NSString* key in @[@"window_x", @"window_y"]) {
        id v = input[key];
        if ([v isKindOfClass:NSNumber.class] && isfinite([v doubleValue]) && fabs([v doubleValue]) < 100000)
            result[key] = v;
    }
}

static id json_data(NSData* data)
{
    return data ? [NSJSONSerialization JSONObjectWithData:data options:0 error:nil] : nil;
}

static BOOL save_settings(void)
{
    assert(NSThread.isMainThread);
    NSString* path = settings_path();
    NSError* error = nil;
    NSFileManager* fm = NSFileManager.defaultManager;
    if (![fm createDirectoryAtPath:path.stringByDeletingLastPathComponent
        withIntermediateDirectories:YES attributes:nil error:&error]) {
        fprintf(stderr, "[D2 settings] create directory: %s\n", error.localizedDescription.UTF8String);
        return NO;
    }
    NSData* data = [NSJSONSerialization dataWithJSONObject:s_settings options:NSJSONWritingPrettyPrinted error:&error];
    // Same-directory atomic rename avoids Foundation replacement services in a sandbox.
    NSString* stage = [path stringByAppendingFormat:@".%d.tmp", getpid()];
    int fd = open(stage.fileSystemRepresentation, O_WRONLY | O_CREAT | O_EXCL, 0600);
    if (fd < 0) { perror("[D2 settings] open"); return NO; }
    const uint8_t* bytes = data.bytes;
    size_t left = data.length;
    BOOL ok = data != nil;
    while (ok && left) {
        ssize_t written = write(fd, bytes, left);
        if (written <= 0) { ok = NO; break; }
        bytes += written; left -= written;
    }
    if (ok && fsync(fd)) ok = NO;
    if (close(fd)) ok = NO;
    if (ok && rename(stage.fileSystemRepresentation, path.fileSystemRepresentation)) ok = NO;
    if (!ok) { perror("[D2 settings] save"); unlink(stage.fileSystemRepresentation); }
    return ok;
}

static void persist_geometry(void)
{
    [s_geometry_timer invalidate]; s_geometry_timer = nil;
    if (!save_settings()) message(@"Settings could not be saved", @"Check write access to the settings folder. Changes apply for this session.");
}

static void schedule_geometry_save(void)
{
    [s_geometry_timer invalidate];
    s_geometry_timer = [NSTimer timerWithTimeInterval:0.35 repeats:NO block:^(NSTimer* timer) {
        (void)timer; persist_geometry();
    }];
    [NSRunLoop.mainRunLoop addTimer:s_geometry_timer forMode:NSRunLoopCommonModes];
}

void d2_settings_flush(void)
{
    assert(NSThread.isMainThread);
    if (s_geometry_timer) persist_geometry();
}

static void apply_settings(void)
{
    assert(NSThread.isMainThread);
    unsigned filter = [s_settings[@"filter"] isEqual:@"linear"] ? 0 :
                      [s_settings[@"filter"] isEqual:@"nearest"] ? 1 : 2;
    rsx_metal_backend_configure((unsigned)([s_settings[@"scale"] doubleValue] * 2), filter,
        [s_settings[@"aspect"] isEqual:@"stretch"], [s_settings[@"vsync"] boolValue],
        [s_settings[@"frame_cap"] unsignedIntValue]);
    BOOL muted = [s_settings[@"mute"] boolValue] ||
        ([s_settings[@"mute_unfocused"] boolValue] && s_window && !s_window.isKeyWindow);
    cellAudioHostSetGain([s_settings[@"volume"] floatValue], muted);
    if (s_window) {
        s_window.level = [s_settings[@"always_on_top"] boolValue] ? NSFloatingWindowLevel : NSNormalWindowLevel;
        [s_window.contentView setNeedsLayout:YES];
        s_fps.hidden = ![s_settings[@"show_fps"] boolValue];
    }
}

static NSString* save_folder(void)
{
    const char* root = getenv("PS3_HDD0_ROOT");
    NSString* hdd = root && *root ? [NSString stringWithUTF8String:root] :
        [@D2_PROJECT_ROOT stringByAppendingPathComponent:@"port/hdd0"];
    return [hdd stringByAppendingPathComponent:@"home/00000001/savedata"];
}

static void message(NSString* title, NSString* detail)
{
    NSAlert* alert = [NSAlert new];
    alert.messageText = title; alert.informativeText = detail ?: @"";
    [alert runModal];
}

static BOOL python_crypto_available(NSString* python)
{
    if (![NSFileManager.defaultManager isExecutableFileAtPath:python]) return NO;
    NSTask* probe = [NSTask new];
    probe.executableURL = [NSURL fileURLWithPath:python];
    probe.arguments = @[@"-c", @"from Crypto.Cipher import AES; from Crypto.Hash import CMAC, SHA1"];
    probe.standardOutput = NSFileHandle.fileHandleWithNullDevice;
    probe.standardError = NSFileHandle.fileHandleWithNullDevice;
    if (![probe launchAndReturnError:nil]) return NO;
    [probe waitUntilExit];
    return probe.terminationStatus == 0;
}

static void open_save_folder(void)
{
    NSString* folder = save_folder();
    [NSFileManager.defaultManager createDirectoryAtPath:folder withIntermediateDirectories:YES attributes:nil error:nil];
    [NSWorkspace.sharedWorkspace openURL:[NSURL fileURLWithPath:folder]];
}

@interface D2SettingsController : NSObject <NSMenuItemValidation>
- (void)change:(NSMenuItem*)item;
- (void)command:(NSMenuItem*)item;
@end
static D2SettingsController* s_controller;

static NSMenu* submenu(NSMenu* parent, NSString* name)
{
    NSMenuItem* item = [[NSMenuItem alloc] initWithTitle:name action:nil keyEquivalent:@""];
    item.submenu = [[NSMenu alloc] initWithTitle:name]; [parent addItem:item];
    return item.submenu;
}

static NSMenuItem* option(NSMenu* menu, NSString* title, NSString* key, id value)
{
    NSMenuItem* item = [[NSMenuItem alloc] initWithTitle:title action:@selector(change:) keyEquivalent:@""];
    item.target = s_controller;
    item.representedObject = @{ @"key": key, @"value": value ?: NSNull.null };
    [menu addItem:item]; return item;
}

static NSMenuItem* command(NSMenu* menu, NSString* title, NSString* name, NSString* shortcut)
{
    NSMenuItem* item = [[NSMenuItem alloc] initWithTitle:title action:@selector(command:) keyEquivalent:shortcut];
    item.target = s_controller; item.representedObject = name; [menu addItem:item]; return item;
}

static void install_menu(void)
{
    NSMenu* menu = [NSMenu new];
    NSMenu* app = submenu(menu, @"Disgaea D2");
    command(app, @"Reset Settings", @"reset", @"");
    [app addItem:NSMenuItem.separatorItem];
    [app addItemWithTitle:@"Quit Disgaea D2" action:@selector(terminate:) keyEquivalent:@"q"];
    NSMenu* graphics = submenu(menu, @"Graphics");
    NSMenu* scale = submenu(graphics, @"Internal Resolution");
    option(scale, @"1× — 1280 × 720", @"scale", @1);
    option(scale, @"1.5× — 1920 × 1080", @"scale", @1.5);
    option(scale, @"2× — 2560 × 1440", @"scale", @2);
    option(scale, @"3× — 3840 × 2160", @"scale", @3);
    NSMenu* filter = submenu(graphics, @"Output Filter");
    option(filter, @"Linear", @"filter", @"linear");
    option(filter, @"Nearest", @"filter", @"nearest");
    option(filter, @"Integer Scale", @"filter", @"integer");
    NSMenu* aspect = submenu(graphics, @"Aspect Ratio");
    option(aspect, @"16:9 Letterbox", @"aspect", @"letterbox");
    option(aspect, @"Stretch", @"aspect", @"stretch");
    option(graphics, @"VSync", @"vsync", nil);
    NSMenu* cap = submenu(graphics, @"Presentation Frame Cap");
    option(cap, @"30 FPS", @"frame_cap", @30); option(cap, @"60 FPS", @"frame_cap", @60);
    option(cap, @"120 FPS", @"frame_cap", @120); option(cap, @"Unlimited", @"frame_cap", @0);
    option(graphics, @"Show FPS", @"show_fps", nil);
    NSMenu* window = submenu(menu, @"Window");
    for (NSString* size in @[@"1280 × 720", @"1600 × 900", @"1920 × 1080", @"2560 × 1440"])
        command(window, size, [@"size:" stringByAppendingString:size], @"");
    NSMenuItem* fullscreen = command(window, @"Toggle Fullscreen", @"fullscreen", @"f");
    fullscreen.keyEquivalentModifierMask = NSEventModifierFlagCommand | NSEventModifierFlagControl;
    command(window, @"Borderless Fullscreen", @"borderless", @"");
    option(window, @"Always on Top", @"always_on_top", nil);
    option(window, @"Remember Size and Position", @"remember_window", nil);
    NSMenu* audio = submenu(menu, @"Audio");
    NSMenuItem* mute = option(audio, @"Mute", @"mute", nil); mute.keyEquivalent = @"m";
    NSMenu* volume = submenu(audio, @"Master Volume");
    for (int percent = 0; percent <= 100; percent += 10)
        option(volume, [NSString stringWithFormat:@"%d%%", percent], @"volume", @(percent / 100.0));
    option(audio, @"Mute When Unfocused", @"mute_unfocused", nil);
    NSMenu* game = submenu(menu, @"Game");
    command(game, @"Import PS3 Save…", @"import", @"");
    command(game, @"Export Save…", @"export", @"");
    command(game, @"Open Save Folder", @"saves", @"");
    command(game, @"Open Log", @"log", @"");
    command(game, @"Cheats…", @"cheats", @"");
    NSMenu* controls = submenu(menu, @"Controls");
    command(controls, @"Keyboard Mapping…", @"controls", @"");
    NSApp.mainMenu = menu;
    fprintf(stderr, "[D2 settings] native menus installed on main thread\n");
}

static void toggle_borderless(void)
{
    if (s_window.styleMask & NSWindowStyleMaskFullScreen) { [s_window toggleFullScreen:nil]; return; }
    if (!s_borderless) {
        s_regular_frame = s_window.frame; s_regular_style = s_window.styleMask;
        s_borderless = YES; s_window.styleMask = NSWindowStyleMaskBorderless;
        [s_window setFrame:s_window.screen.frame display:YES];
    } else {
        s_borderless = NO; s_window.styleMask = s_regular_style;
        [s_window setFrame:s_regular_frame display:YES];
    }
    [s_window makeKeyAndOrderFront:nil];
}

@implementation D2SettingsController
- (BOOL)validateMenuItem:(NSMenuItem*)item
{
    if ([item.representedObject isKindOfClass:NSDictionary.class]) {
        NSString* key = item.representedObject[@"key"];
        id value = item.representedObject[@"value"];
        BOOL checked = value == NSNull.null ? [s_settings[key] boolValue] : [s_settings[key] isEqual:value];
        item.state = checked ? NSControlStateValueOn : NSControlStateValueOff;
    } else if ([item.representedObject isEqual:@"cheats"]) return d2_cheats_toggle_menu != NULL;
    else if ([item.representedObject isEqual:@"borderless"]) item.state = s_borderless;
    return YES;
}
- (void)change:(NSMenuItem*)item
{
    NSString* key = item.representedObject[@"key"];
    id value = item.representedObject[@"value"];
    s_settings[key] = value == NSNull.null ? @(![s_settings[key] boolValue]) : value;
    apply_settings(); save_settings();
    fprintf(stderr, "[D2 settings] %s=%s\n", key.UTF8String, [s_settings[key] description].UTF8String);
}
- (void)command:(NSMenuItem*)item
{
    NSString* name = item.representedObject;
    if ([name isEqual:@"fullscreen"]) {
        if (s_borderless) toggle_borderless();
        [s_window toggleFullScreen:nil];
    } else if ([name isEqual:@"borderless"]) {
        toggle_borderless();
    } else if ([name hasPrefix:@"size:"]) {
        if (s_borderless || (s_window.styleMask & NSWindowStyleMaskFullScreen)) return;
        NSArray* wh = [[name substringFromIndex:5] componentsSeparatedByString:@" × "];
        [s_window setContentSize:NSMakeSize([wh[0] doubleValue], [wh[1] doubleValue])];
    } else if ([name isEqual:@"reset"]) {
        assert(!python_crypto_available(@"/nonexistent/python3"));
        assert(!python_crypto_available(@"/usr/bin/false"));
        const char* test_python = getenv("D2_SETTINGS_TEST_PYTHON");
        if (test_python) assert(python_crypto_available(@(test_python)));
        fprintf(stderr, "[D2 settings] save-import interpreter/module dependency probe: PASS\n");
        s_settings = [defaults() mutableCopy]; apply_settings(); save_settings();
        if (!s_borderless && !(s_window.styleMask & NSWindowStyleMaskFullScreen)) {
            [s_window setContentSize:NSMakeSize(1280, 720)]; [s_window center];
        }
    } else if ([name isEqual:@"controls"]) {
        message(@"Keyboard Mapping", @"Arrows: D-pad / left stick\nZ: Cross   X / Esc / Backspace: Circle\nA: Square   S: Triangle\nQ / W: L1 / R1   1 / 2: L2 / R2\nSpace: Start   Shift: Select\nReturn: Cross + Start\n\nClick the game window to focus. A connected gamepad takes precedence.");
    } else if ([name isEqual:@"cheats"]) { if (d2_cheats_toggle_menu) d2_cheats_toggle_menu(); }
    else if ([name isEqual:@"saves"]) open_save_folder();
    else if ([name isEqual:@"log"]) {
        char file[PATH_MAX] = {0}; const char* env = getenv("D2_LOG_PATH");
        NSString* log = env ? [NSString stringWithUTF8String:env] :
            fcntl(STDERR_FILENO, F_GETPATH, file) == 0 ? [NSString stringWithUTF8String:file] :
            [NSHomeDirectory() stringByAppendingPathComponent:@"Library/Logs/DisgaeaD2Recomp/latest.log"];
        if (![NSWorkspace.sharedWorkspace openURL:[NSURL fileURLWithPath:log]]) message(@"Open Log", log);
    } else if ([name isEqual:@"import"]) {
        NSOpenPanel* panel = [NSOpenPanel openPanel];
        panel.message = @"Choose a Disgaea D2 PS3 save folder containing PARAM.PFD.";
        panel.canChooseDirectories = YES; panel.canChooseFiles = NO; panel.allowsMultipleSelection = NO;
        if ([panel runModal] != NSModalResponseOK) return;
        NSString* script = [@D2_PROJECT_ROOT stringByAppendingPathComponent:@"tools/d2_save_import.py"];
        if (![NSFileManager.defaultManager fileExistsAtPath:script]) {
            NSString* runner = NSProcessInfo.processInfo.arguments[0];
            script = [[[runner stringByDeletingLastPathComponent] stringByDeletingLastPathComponent]
                stringByAppendingPathComponent:@"Resources/d2_save_import.py"];
        }
        NSString* python = nil;
        for (NSString* candidate in @[[ @D2_PROJECT_ROOT stringByAppendingPathComponent:@".venv/bin/python"],
                @"/opt/homebrew/bin/python3", @"/usr/local/bin/python3", @"/usr/bin/python3"])
            if (python_crypto_available(candidate)) { python = candidate; break; }
        if (!python || ![NSFileManager.defaultManager fileExistsAtPath:script]) {
            message(@"Save Import Unavailable", @"Import requires Python 3 with PyCryptodome (Crypto). Install Python 3 and run python3 -m pip install pycryptodome, or use the project’s .venv. The save folder will open.");
            open_save_folder(); return;
        }
        NSTask* task = [NSTask new]; task.executableURL = [NSURL fileURLWithPath:python];
        NSString* hdd = [[save_folder() stringByDeletingLastPathComponent] stringByDeletingLastPathComponent];
        hdd = [hdd stringByDeletingLastPathComponent];
        task.arguments = @[script, panel.URL.path, @"--into", hdd];
        NSPipe* pipe = [NSPipe pipe]; task.standardOutput = pipe; task.standardError = pipe;
        NSError* error = nil;
        if (![task launchAndReturnError:&error]) { message(@"Save Import Failed", error.localizedDescription); return; }
        dispatch_async(dispatch_get_global_queue(QOS_CLASS_UTILITY, 0), ^{
            NSData* output = [pipe.fileHandleForReading readDataToEndOfFile]; [task waitUntilExit];
            NSString* result = [[NSString alloc] initWithData:output encoding:NSUTF8StringEncoding];
            dispatch_async(dispatch_get_main_queue(), ^{
                message(task.terminationStatus == 0 ? @"Save Imported" : @"Save Import Failed",
                    [result stringByAppendingString:@"\nImport uses a free slot; existing saves are kept. Load it from the game's Continue menu."]);
            });
        });
    } else if ([name isEqual:@"export"]) {
        NSOpenPanel* panel = [NSOpenPanel openPanel]; panel.directoryURL = [NSURL fileURLWithPath:save_folder()];
        panel.message = @"Choose a save slot to export (plaintext port/RPCS3 format).";
        panel.canChooseDirectories = YES; panel.canChooseFiles = NO;
        if ([panel runModal] != NSModalResponseOK) return;
        if (![panel.URL.path.stringByDeletingLastPathComponent.stringByStandardizingPath
              isEqual:save_folder().stringByStandardizingPath]) {
            message(@"Export Save", @"Choose one slot inside the game's save folder."); return;
        }
        NSSavePanel* target = [NSSavePanel savePanel]; target.nameFieldStringValue = panel.URL.lastPathComponent;
        if ([target runModal] != NSModalResponseOK) return;
        NSError* error = nil;
        if (![NSFileManager.defaultManager copyItemAtURL:panel.URL toURL:target.URL error:&error])
            message(@"Save Export Failed", error.localizedDescription);
        else message(@"Save Exported", @"This is a plaintext port/RPCS3 save. It must be resigned before use on a PS3.");
    }
}
@end

void d2_settings_init(void)
{
    @autoreleasepool {
        assert(NSThread.isMainThread);
        assert(!python_crypto_available(@"/nonexistent/python3"));
        assert(!python_crypto_available(@"/usr/bin/false"));
        const char* test_python = getenv("D2_SETTINGS_TEST_PYTHON");
        if (test_python) assert(python_crypto_available(@(test_python)));
        fprintf(stderr, "[D2 settings] save-import interpreter/module dependency probe: PASS\n");
        s_settings = [defaults() mutableCopy];
        merge_settings(s_settings, json_data([NSData dataWithContentsOfFile:settings_path()]));
        const char* override = getenv("D2_SETTINGS_OVERRIDE");
        if (override) merge_settings(s_settings, json_data([[NSString stringWithUTF8String:override] dataUsingEncoding:NSUTF8StringEncoding]));
        s_controller = [D2SettingsController new]; apply_settings();
        fprintf(stderr, "[D2 settings] loaded scale=%s filter=%s volume=%.2f cap=%u from %s\n",
            [s_settings[@"scale"] description].UTF8String, [s_settings[@"filter"] UTF8String],
            [s_settings[@"volume"] doubleValue], [s_settings[@"frame_cap"] unsignedIntValue], settings_path().UTF8String);
        /* Test-only live update on the same main run loop as menu actions. */
        const char* live = getenv("D2_SETTINGS_LIVE_OVERRIDE");
        if (live) {
            NSString* text = [NSString stringWithUTF8String:live];
            [NSTimer scheduledTimerWithTimeInterval:25 repeats:NO block:^(NSTimer* timer) {
                (void)timer; merge_settings(s_settings, json_data([text dataUsingEncoding:NSUTF8StringEncoding]));
                apply_settings(); fprintf(stderr, "[D2 settings] live test override applied\n");
            }];
        }
    }
}

void ps3_host_window_created(void* window)
{
    assert(NSThread.isMainThread);
    if (s_observers) for (id observer in s_observers) [NSNotificationCenter.defaultCenter removeObserver:observer];
    s_window = (__bridge NSWindow*)window;
    if (!s_window) { d2_settings_flush(); s_fps = nil; s_observers = nil; return; }
    if ([s_settings[@"remember_window"] boolValue]) {
        NSRect frame = [s_window frameRectForContentRect:NSMakeRect(0, 0,
            [s_settings[@"window_width"] doubleValue], [s_settings[@"window_height"] doubleValue])];
        if (s_settings[@"window_x"] && s_settings[@"window_y"]) {
            frame.origin = NSMakePoint([s_settings[@"window_x"] doubleValue], [s_settings[@"window_y"] doubleValue]);
            BOOL visible = NO;
            for (NSScreen* screen in NSScreen.screens)
                if (NSIntersectsRect(frame, screen.visibleFrame)) visible = YES;
            if (visible) [s_window setFrame:frame display:NO];
            else {
                [s_window setContentSize:NSMakeSize([s_settings[@"window_width"] doubleValue], [s_settings[@"window_height"] doubleValue])];
                [s_window center];
            }
        } else [s_window setContentSize:NSMakeSize([s_settings[@"window_width"] doubleValue], [s_settings[@"window_height"] doubleValue])];
    }
    s_fps = [NSTextField labelWithString:@"Guest: — · Display: —"];
    s_fps.frame = NSMakeRect(12, 12, 330, 26);
    s_fps.textColor = NSColor.whiteColor; s_fps.backgroundColor = [NSColor.blackColor colorWithAlphaComponent:0.7];
    s_fps.drawsBackground = YES; s_fps.font = [NSFont monospacedDigitSystemFontOfSize:15 weight:NSFontWeightMedium];
    [s_window.contentView addSubview:s_fps];
    NSMutableArray* observers = [NSMutableArray new];
    for (NSString* name in @[NSWindowDidMoveNotification, NSWindowDidResizeNotification,
            NSWindowDidBecomeKeyNotification, NSWindowDidResignKeyNotification]) {
        id observer = [NSNotificationCenter.defaultCenter addObserverForName:name object:s_window queue:nil
            usingBlock:^(NSNotification* note) {
                apply_settings();
                if (([note.name isEqual:NSWindowDidMoveNotification] || [note.name isEqual:NSWindowDidResizeNotification]) &&
                    [s_settings[@"remember_window"] boolValue] && !s_borderless &&
                    !(s_window.styleMask & NSWindowStyleMaskFullScreen)) {
                    s_settings[@"window_width"] = @(s_window.contentView.bounds.size.width);
                    s_settings[@"window_height"] = @(s_window.contentView.bounds.size.height);
                    s_settings[@"window_x"] = @(s_window.frame.origin.x);
                    s_settings[@"window_y"] = @(s_window.frame.origin.y);
                    schedule_geometry_save();
                }
            }];
        [observers addObject:observer];
    }
    s_observers = observers; install_menu(); apply_settings();
}

void ps3_host_frame_rates(double guest, double display)
{
    dispatch_async(dispatch_get_main_queue(), ^{
        @autoreleasepool { s_fps.stringValue = [NSString stringWithFormat:@"Guest: %.1f FPS · Display: %.1f FPS", guest, display]; }
    });
}

int d2_settings_self_test(void)
{
    @autoreleasepool {
        assert(NSThread.isMainThread);
        assert(getenv("D2_SETTINGS_PATH")); /* tests never write personal settings */
        assert(!python_crypto_available(@"/nonexistent/python3"));
        assert(!python_crypto_available(@"/usr/bin/false"));
        const char* test_python = getenv("D2_SETTINGS_TEST_PYTHON");
        if (test_python) assert(python_crypto_available(@(test_python)));
        fprintf(stderr, "[D2 settings] save-import interpreter/module dependency probe: PASS\n");
        s_settings = [defaults() mutableCopy];
        merge_settings(s_settings, @{@"scale": @2, @"volume": @0.5, @"window_x": @-120, @"filter": @"nearest"});
        assert(save_settings());
        NSData* before_geometry = [NSData dataWithContentsOfFile:settings_path()];
        for (int i = 0; i < 20; i++) { s_settings[@"window_x"] = @(i); schedule_geometry_save(); }
        assert([[NSData dataWithContentsOfFile:settings_path()] isEqual:before_geometry]);
        [NSRunLoop.mainRunLoop runUntilDate:[NSDate dateWithTimeIntervalSinceNow:0.45]];
        assert(!s_geometry_timer);
        assert([json_data([NSData dataWithContentsOfFile:settings_path()]) isEqual:s_settings]);
        s_settings[@"window_y"] = @120; schedule_geometry_save(); d2_settings_flush();
        assert(!s_geometry_timer && [json_data([NSData dataWithContentsOfFile:settings_path()]) isEqual:s_settings]);
        fprintf(stderr, "[D2 settings] geometry coalesces until idle and flushes at shutdown: PASS\n");
        NSMutableDictionary* read = [defaults() mutableCopy];
        merge_settings(read, json_data([NSData dataWithContentsOfFile:settings_path()]));
        assert([read isEqual:s_settings]);
        merge_settings(read, @{@"scale": @7, @"frame_cap": @-1, @"filter": @"invalid", @"volume": @2});
        assert([read[@"scale"] intValue] == 2 && [read[@"frame_cap"] intValue] == 60);
        assert([read[@"volume"] intValue] == 1 && [read[@"filter"] isEqual:@"nearest"]);
        merge_settings(read, json_data([@"broken json" dataUsingEncoding:NSUTF8StringEncoding]));
        assert([read[@"scale"] intValue] == 2);
        for (unsigned scale = 2; scale <= 6; scale++) {
            assert(rsx_host_scale_edge(1280, scale) == 640 * scale);
            assert(rsx_host_scale_edge(720, scale) == 360 * scale);
            assert(rsx_host_scale_edge(7, scale) + rsx_host_scale_extent(7, 11, scale) == rsx_host_scale_edge(18, scale));
        }
        assert(rsx_host_scale_edge(3, 3) == 5);
        cellAudioHostSetGain(0.5f, 0); assert(cellAudioHostGetGain() == 0.5f);
        assert(cellAudioHostSample(0.8f, cellAudioHostGetGain()) == 0.4f);
        assert(cellAudioHostSample(2, 0.5f) == 0.5f && cellAudioHostSample(-2, 0.5f) == -0.5f);
        cellAudioHostSetGain(0.8f, 1); assert(cellAudioHostGetGain() == 0);
        cellAudioHostSetGain(NAN, 0); assert(cellAudioHostGetGain() == 0);
        assert(cellAudioHostSample(NAN, 1) == 0);
        if (getenv("D2_SETTINGS_TEST_UI")) {
            [NSApplication sharedApplication];
            s_controller = [D2SettingsController new];
            NSWindow* window = [[NSWindow alloc] initWithContentRect:NSMakeRect(0, 0, 640, 360)
                styleMask:NSWindowStyleMaskTitled | NSWindowStyleMaskResizable
                backing:NSBackingStoreBuffered defer:NO];
            assert(window); ps3_host_window_created((__bridge void*)window);
            assert(NSApp.mainMenu.numberOfItems == 6);
            NSMenu* menu = [NSMenu new];
            NSMenuItem* mute = option(menu, @"Mute", @"mute", nil);
            s_settings[@"mute"] = @NO; s_settings[@"volume"] = @0.5;
            [s_controller change:mute]; assert(cellAudioHostGetGain() == 0);
            [s_controller change:mute]; assert(cellAudioHostGetGain() == 0.5f);
            s_settings[@"mute_unfocused"] = @YES; apply_settings(); assert(cellAudioHostGetGain() == 0);
            s_settings[@"mute_unfocused"] = @NO;
            NSMenuItem* size = command(menu, @"size", @"size:1600 × 900", @"");
            [s_controller command:size]; assert(window.contentView.bounds.size.width == 1600);
            assert([s_settings[@"window_width"] intValue] == 1600);
            ps3_host_window_created(NULL); [window orderOut:nil];
            printf("[AG-test] main-thread menus, mute actions/focus, window geometry: PASS\n");
        }
        printf("[AG-test] settings round-trip, malformed input, scale edges/extents, output gain: PASS\n");
        return 0;
    }
}
