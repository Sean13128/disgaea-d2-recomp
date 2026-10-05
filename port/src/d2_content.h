/* Small host-side PARAM.SFO reader; never writes game content. */
#import <Foundation/Foundation.h>
static NSString* d2_sfo_string(NSString* path, const char* key)
{
    NSData* data = [NSData dataWithContentsOfFile:path];
    const unsigned char* b = data.bytes;
    size_t n = data.length;
    if (n < 20 || memcmp(b, "\0PSF", 4)) return nil;
    #define LE32(p) ((uint32_t)(p)[0] | (uint32_t)(p)[1]<<8 | (uint32_t)(p)[2]<<16 | (uint32_t)(p)[3]<<24)
    if (LE32(b+4) != 0x101) return nil;
    size_t keys = LE32(b+8), values = LE32(b+12), count = LE32(b+16);
    if (count > (n-20)/16 || keys < 20+count*16 || keys >= values || values > n) return nil;
    for (size_t i = 0; i < count; i++) {
        const unsigned char* e = b+20+i*16;
        size_t k = e[0] | (size_t)e[1]<<8, v = LE32(e+12), len = LE32(e+4);
        if (k >= values-keys || v > n-values || len > LE32(e+8) || LE32(e+8) > n-values-v || !len) return nil;
        const char* name = (const char*)b+keys+k;
        if (!memchr(name, 0, values-keys-k)) return nil;
        if (!strcmp(name, key)) {
            if (e[2] != 4 || e[3] != 2) return nil;
            const char* value = (const char*)b+values+v;
            const char* end = memchr(value, 0, len);
            return end ? [[NSString alloc] initWithBytes:value length:end-value encoding:NSUTF8StringEncoding] : nil;
        }
    }
    #undef LE32
    return nil;
}
static BOOL d2_content_ready(NSString* hdd, BOOL update)
{
    if (!update) return YES;
    NSString* game = [hdd stringByAppendingPathComponent:@"game"];
    NSString* sfo = [game stringByAppendingPathComponent:@"BLUS31313/PARAM.SFO"];
    if (![d2_sfo_string(sfo, "TITLE_ID") isEqual:@"BLUS31313"] ||
        ![d2_sfo_string(sfo, "APP_VER") isEqual:@"01.40"]) return NO;
    NSDictionary* attrs = [NSFileManager.defaultManager attributesOfItemAtPath:
        [game stringByAppendingPathComponent:@"BLUS31313/USRDIR/Data/START_7.dat"] error:nil];
    if (![attrs[NSFileType] isEqual:NSFileTypeRegular] || ![attrs[NSFileSize] unsignedLongLongValue]) return NO;
    NSString* dlc = [game stringByAppendingPathComponent:@"NPUB31321"];
    if (![d2_sfo_string([dlc stringByAppendingPathComponent:@"PARAM.SFO"], "TITLE_ID") isEqual:@"NPUB31321"]) return NO;
    NSString* flags = [dlc stringByAppendingPathComponent:@"USRDIR/Data/flag"];
    /* The supplied 45 unlocks occupy these three contiguous ID ranges. */
    static const unsigned ranges[][2] = {{10001, 18}, {40001, 22}, {50001, 5}};
    for (unsigned group = 0; group < 3; group++) {
        for (unsigned i = 0; i < ranges[group][1]; i++) {
            NSString* name = [NSString stringWithFormat:@"flag%08u.edat", ranges[group][0] + i];
            NSDictionary* a = [NSFileManager.defaultManager attributesOfItemAtPath:
                [flags stringByAppendingPathComponent:name] error:nil];
            if (![a[NSFileType] isEqual:NSFileTypeRegular] || [a[NSFileSize] unsignedLongLongValue] < 256) return NO;
        }
    }
    return YES;
}
