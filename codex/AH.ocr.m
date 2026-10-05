/* Vision reads captured frames, without screen recording or accessibility. */
#import <Vision/Vision.h>
#include <stdio.h>
#include <stdlib.h>
int main(int argc, char** argv)
{
    @autoreleasepool {
        if (argc != 2) return 2;
        FILE* file = fopen(argv[1], "rb"); if (!file) return 2;
        unsigned w, h, max;
        if (fscanf(file, "P6\n%u %u\n%u", &w, &h, &max) != 3 || max != 255 ||
            !w || !h || w > 8192 || h > 8192) { fclose(file); return 2; }
        fgetc(file);
        size_t size = (size_t)w * h * 3;
        unsigned char* pixels = malloc(size);
        if (!pixels || fread(pixels, 1, size, file) != size) { free(pixels); fclose(file); return 2; }
        fclose(file);
        CGDataProviderRef provider = CGDataProviderCreateWithData(NULL, pixels, size, NULL);
        CGColorSpaceRef space = CGColorSpaceCreateDeviceRGB();
        CGImageRef image = CGImageCreate(w, h, 8, 24, w*3, space, kCGImageAlphaNone,
            provider, NULL, false, kCGRenderingIntentDefault);
        VNRecognizeTextRequest* request = [VNRecognizeTextRequest new];
        request.recognitionLevel = VNRequestTextRecognitionLevelAccurate;
        request.usesLanguageCorrection = NO;
        request.customWords = @[@"ATTACK ENTRY", @"Base Panel", @"Laharl", @"Execute"];
        VNImageRequestHandler* handler = [[VNImageRequestHandler alloc] initWithCGImage:image options:@{}];
        NSError* error = nil;
        BOOL ok = [handler performRequests:@[request] error:&error];
        NSMutableArray* lines = [NSMutableArray new];
        for (VNRecognizedTextObservation* observation in request.results) {
            VNRecognizedText* candidate = [observation topCandidates:1].firstObject;
            CGRect box = observation.boundingBox;
            [lines addObject:@{@"text": candidate.string, @"confidence": @(candidate.confidence),
                @"x": @(box.origin.x * 1280), @"y": @((1-CGRectGetMaxY(box))*720),
                @"w": @(box.size.width*1280), @"h": @(box.size.height*720)}];
        }
        if (ok) {
            NSData* json = [NSJSONSerialization dataWithJSONObject:lines options:0 error:nil];
            fwrite(json.bytes, 1, json.length, stdout); puts("");
        } else fprintf(stderr, "%s\n", error.localizedDescription.UTF8String);
        CGImageRelease(image); CGColorSpaceRelease(space); CGDataProviderRelease(provider); free(pixels);
        return ok ? 0 : 1;
    }
}
