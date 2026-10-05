/* Exercise the actual launcher with an isolated home/bundle and a fake runner.
 * NSAlert is intercepted, so failure paths need no window or user response. */
#import <AppKit/AppKit.h>
#include <assert.h>
#include <stdlib.h>
#include <string.h>
static NSString* test_home(void) { return @(getenv("AH_LAUNCHER_TEST_ROOT")); }
@interface AHTestBundle : NSObject
+ (instancetype)mainBundle;
@property(readonly) NSString* bundlePath;
@property(readonly) NSString* executablePath;
@end
@implementation AHTestBundle
+ (instancetype)mainBundle { static AHTestBundle* bundle; if (!bundle) bundle = [self new]; return bundle; }
- (NSString*)bundlePath { return [test_home() stringByAppendingPathComponent:@"Test.app"]; }
- (NSString*)executablePath { return [test_home() stringByAppendingPathComponent:@"launcher"]; }
@end
@interface AHTestAlert : NSAlert
@end
@implementation AHTestAlert
- (NSModalResponse)runModal
{
    assert([self.messageText isEqual:@"Disgaea D2 could not start"]);
    const char* mode = getenv("AH_LAUNCHER_TEST_MODE");
    if (!strcmp(mode, "exit")) {
        assert([self.informativeText containsString:@"Runner exit 73"]);
        assert([self.informativeText containsString:@"AH intentional runner start failure"]);
    } else {
        assert(!strcmp(mode, "missing"));
        assert([self.informativeText containsString:@"Cannot launch"]);
    }
    NSString* config = [NSString stringWithContentsOfFile:[test_home() stringByAppendingPathComponent:
        @"Library/Application Support/DisgaeaD2Recomp/config"] encoding:NSUTF8StringEncoding error:nil];
    assert([config containsString:@"work/v140/EBOOT.elf"]);
    fprintf(stderr, "[AH-test] mismatched configured ELF -> v140 fallback; %s NSAlert: PASS\n", mode);
    return NSModalResponseOK;
}
@end
#define NSHomeDirectory test_home
#define NSBundle AHTestBundle
#define NSAlert AHTestAlert
#define main launcher_main
#include "../port/src/d2_launcher.m"
#undef main
int main(void) { return launcher_main(); }
