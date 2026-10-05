/* Test actual Finder content admission/install without UI or a real dump. */
#import <AppKit/AppKit.h>
#include <assert.h>
static NSString* test_root(void) { return @(getenv("AL_TEST_ROOT")); }
@interface ALBundle : NSObject
+ (instancetype)mainBundle;
@property(readonly) NSString* resourcePath;
@property(readonly) NSString* bundlePath;
@property(readonly) NSString* executablePath;
@end
@implementation ALBundle
+ (instancetype)mainBundle { static ALBundle* b; if (!b) b=[self new]; return b; }
- (NSString*)bundlePath { return [test_root() stringByAppendingPathComponent:@"relocated/Disgaea D2.app"]; }
- (NSString*)executablePath { return [self.bundlePath stringByAppendingPathComponent:@"Contents/MacOS/Disgaea D2"]; }
- (NSString*)resourcePath { return [self.bundlePath stringByAppendingPathComponent:@"Contents/Resources"]; }
@end
@interface ALAlert : NSAlert
@end
@implementation ALAlert
- (NSModalResponse)runModal {
    assert([self.messageText isEqual:@"Install Disgaea D2 1.40 content"]);
    assert([self.informativeText containsString:@"hdd0"]);
    puts("[AL-launcher] empty Application Support requires explicit content installation: PASS");
    return NSAlertFirstButtonReturn;
}
@end
@interface ALPanel : NSObject
+ (instancetype)openPanel;
@property NSString* message;
@property BOOL canChooseDirectories, canChooseFiles, allowsMultipleSelection;
@property(readonly) NSURL* URL;
- (NSModalResponse)runModal;
@end
@implementation ALPanel
+ (instancetype)openPanel { return [self new]; }
- (NSModalResponse)runModal { return NSModalResponseOK; }
- (NSURL*)URL { return [NSURL fileURLWithPath:[test_root() stringByAppendingPathComponent:@"packages"]]; }
@end
#define NSBundle ALBundle
#define NSAlert ALAlert
#define NSOpenPanel ALPanel
#define main unused_launcher_main
#include "../src/d2_launcher.m"
#undef main
int main(void)
{
    @autoreleasepool {
        const char* real_hdd = getenv("AL_REAL_HDD0");
        if (real_hdd) {
            assert(d2_content_ready(@(real_hdd), YES));
            puts("[AL-launcher] actual installed 1.40 update + all required DLC accepted: PASS");
        }
        NSString* dump = [test_root() stringByAppendingPathComponent:@"dump"];
        assert(valid_game(dump)); assert(!valid_game([test_root() stringByAppendingPathComponent:@"wrong-dump"]));
        NSString* hdd = [test_root() stringByAppendingPathComponent:@"Application Support/hdd0"];
        assert(!d2_content_ready(hdd, YES));
        assert(ensure_content(hdd, @[]));
        assert(d2_content_ready(hdd, YES));
        assert(ensure_content(hdd, @[])); // no second install prompt
        NSString* flags = [hdd stringByAppendingPathComponent:@"game/NPUB31321/USRDIR/Data/flag"];
        NSString* flag = [NSFileManager.defaultManager contentsOfDirectoryAtPath:flags error:nil].firstObject;
        assert([NSFileManager.defaultManager removeItemAtPath:[flags stringByAppendingPathComponent:flag] error:nil]);
        assert(!d2_content_ready(hdd, YES)); assert(d2_content_ready(hdd, NO));
        puts("[AL-launcher] BLUS title validation, relocated resource install, complete content, missing DLC rejection, v100 admission: PASS");
    }
    return 0;
}
