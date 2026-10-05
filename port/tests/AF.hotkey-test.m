#define main af_pad_base_main
#include "libs/input/tests/test_pad_macos.m"
#undef main
static unsigned toggles;
int ps3_host_key_event(unsigned code,unsigned modifiers,int down,int repeat)
{
    int hotkey=code==122 || (code==8 && (modifiers & NSEventModifierFlagCommand) && (modifiers & NSEventModifierFlagShift));
    if (hotkey && down && !repeat) toggles++;
    return hotkey;
}
@interface AFKeyEvent : ITestKeyEvent
@property BOOL repeating;
@end
@implementation AFKeyEvent
- (BOOL)isARepeat { return self.repeating; }
@end
int main(void)
{
    @autoreleasepool {
        setenv("PAD_NO_KEYBOARD","1",1);
        [NSApplication sharedApplication];
        ITestWindow* window=[[ITestWindow alloc] initWithContentRect:NSMakeRect(0,0,240,120)
            styleMask:NSWindowStyleMaskTitled backing:NSBackingStoreBuffered defer:NO];
        window.testFocus=YES;pad_macos_attach_window((__bridge void*)window);
        AFKeyEvent* event=[[AFKeyEvent alloc] init];event.target=window;event.kind=NSEventTypeKeyDown;event.code=122;
        assert(pad_macos_process_event((__bridge void*)event) && toggles==1);
        event.repeating=YES;assert(pad_macos_process_event((__bridge void*)event) && toggles==1);
        event.repeating=NO;event.code=8;event.flags=NSEventModifierFlagCommand|NSEventModifierFlagShift;
        assert(pad_macos_process_event((__bridge void*)event) && toggles==2);
        window.testFocus=NO;assert(!pad_macos_process_event((__bridge void*)event) && toggles==2);
        window.testFocus=YES;event.code=6;event.flags=0;
        assert(!pad_macos_process_event((__bridge void*)event));assert(!pad_macos_keyboard_enabled());
        puts("[AF-test] AppKit dispatch: F1/Cmd+Shift+C, repeat/focus gating, hotkeys with keyboard disabled: PASS");
    }
}
