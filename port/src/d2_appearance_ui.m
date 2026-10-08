#import <Cocoa/Cocoa.h>
#include "d2_appearance.h"
#include <stdio.h>
#include <math.h>
#include <string.h>
@interface D2AppearanceMenu : NSObject <NSMenuDelegate> {
    struct D2AppearanceSnapshot _snapshot;
}
@property(nonatomic,strong) NSMenu* menu;
@property(nonatomic,strong) NSTimer* timer;
@property(nonatomic,strong) NSArray* testSequence;
@property(nonatomic) NSUInteger testIndex;
@property(nonatomic) double testStart;
@property(nonatomic) int lastQueued;
@end
@implementation D2AppearanceMenu
- (void)menuNeedsUpdate:(NSMenu*)menu {
    d2_appearance_snapshot(&_snapshot);
    [menu removeAllItems];
    NSString* title=_snapshot.character[0]?[NSString stringWithFormat:@"%s",_snapshot.character]:@"Appearance";
    NSMenuItem* heading=[[NSMenuItem alloc] initWithTitle:title action:nil keyEquivalent:@""];
    heading.enabled=NO;[menu addItem:heading];
    for(unsigned i=0;i<_snapshot.count;++i) {
        NSMenuItem* item=[[NSMenuItem alloc] initWithTitle:[NSString stringWithUTF8String:_snapshot.choices[i].label]
                                                  action:@selector(select:) keyEquivalent:@""];
        item.target=self;item.tag=i;item.enabled=_snapshot.ready;
        item.state=i==_snapshot.active?NSControlStateValueOn:NSControlStateValueOff;
        [menu addItem:item];
    }
    [menu addItem:NSMenuItem.separatorItem];
    NSString* status=_snapshot.status[0]?[NSString stringWithUTF8String:_snapshot.status]:@"Load the private save to choose an appearance.";
    NSMenuItem* note=[[NSMenuItem alloc] initWithTitle:status action:nil keyEquivalent:@""];
    note.enabled=NO;[menu addItem:note];
}
- (void)select:(NSMenuItem*)item {
    if(item.tag<0 || item.tag>=_snapshot.count) return;
    int queued=d2_appearance_request(_snapshot.class_id,_snapshot.choices[item.tag].token,_snapshot.generation);
    self.lastQueued=queued;
    fprintf(stderr,"[D2 appearance menu] request class=%u costume=%s queued=%d\n",_snapshot.class_id,
            _snapshot.choices[item.tag].token[0]?_snapshot.choices[item.tag].token:"original",queued);
}
- (void)testTick:(NSTimer*)timer {
    if(self.testIndex>=self.testSequence.count){[timer invalidate];self.timer=nil;return;}
    NSDictionary* event=self.testSequence[self.testIndex];
    if(NSProcessInfo.processInfo.systemUptime-self.testStart<[event[@"second"] doubleValue]) return;
    ++self.testIndex;
    [self menuNeedsUpdate:self.menu];
    const char* token=[event[@"token"] UTF8String];
    self.lastQueued=0;
    for(NSMenuItem* item in self.menu.itemArray) {
        if(item.target==self && item.tag>=0 && item.tag<_snapshot.count &&
           strcmp(token,_snapshot.choices[item.tag].token)==0) {[self select:item];break;}
    }
    fprintf(stderr,"[D2 appearance menu test] second=%.1f class=%u ready=%d costume=%s queued=%d\n",
            [event[@"second"] doubleValue],_snapshot.class_id,_snapshot.ready,*token?token:"original",self.lastQueued);
}
@end
static D2AppearanceMenu* s_appearance_menu;
void d2_appearance_menu_install(NSMenu* game) {
    if(!getenv("D2_APPEARANCE_MANIFEST")) return;
    s_appearance_menu=[D2AppearanceMenu new];
    NSMenuItem* item=[[NSMenuItem alloc] initWithTitle:@"Appearance" action:nil keyEquivalent:@""];
    s_appearance_menu.menu=[[NSMenu alloc] initWithTitle:@"Appearance"];
    s_appearance_menu.menu.autoenablesItems=NO;s_appearance_menu.menu.delegate=s_appearance_menu;
    item.submenu=s_appearance_menu.menu;[game addItem:item];
    const char* raw=getenv("D2_APPEARANCE_TEST_SEQUENCE");
    if(raw && strlen(raw)<8192) {
        NSData* data=[[NSString stringWithUTF8String:raw] dataUsingEncoding:NSUTF8StringEncoding];
        id sequence=[NSJSONSerialization JSONObjectWithData:data options:0 error:nil];
        BOOL valid=[sequence isKindOfClass:NSArray.class] && [sequence count]>0 && [sequence count]<=16;
        double prior=-1;
        if(valid) for(id event in sequence) {
            if(![event isKindOfClass:NSDictionary.class] || ![event[@"second"] isKindOfClass:NSNumber.class] ||
               ![event[@"token"] isKindOfClass:NSString.class]) {valid=NO;break;}
            double second=[event[@"second"] doubleValue];
            if(!isfinite(second) || second<0 || second>600 || second<=prior || [event[@"token"] length]>64){valid=NO;break;}
            prior=second;
        }
        if(valid) {
            s_appearance_menu.testSequence=sequence;s_appearance_menu.testStart=NSProcessInfo.processInfo.systemUptime;
            s_appearance_menu.timer=[NSTimer scheduledTimerWithTimeInterval:0.2 target:s_appearance_menu
                selector:@selector(testTick:) userInfo:nil repeats:YES];
        } else fprintf(stderr,"[D2 appearance menu test] invalid test sequence rejected\n");
    }
    fprintf(stderr,"[D2 appearance menu] installed; session choices in private profile\n");
}
