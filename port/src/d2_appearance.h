#pragma once
#include <stdint.h>
#ifdef __cplusplus
extern "C" {
#endif
/* Host APIs copy snapshots or queue one request. They never read/write guest VM.
 * Choices affect this session only. The PPU frame hook validates the castle,
 * controlled identity and save readiness again before rebuilding the actor. */
#define D2_APPEARANCE_MAX_CHOICES 129
struct D2AppearanceChoice { char token[65],label[128]; };
struct D2AppearanceSnapshot {
    uint64_t serial,generation;
    unsigned class_id,count,active;
    int ready;
    char character[49],status[192];
    struct D2AppearanceChoice choices[D2_APPEARANCE_MAX_CHOICES];
};
void d2_appearance_snapshot(struct D2AppearanceSnapshot* out);
int d2_appearance_request(unsigned class_id,const char* token,uint64_t generation);
void d2_appearance_frame(void* context,int save_ready);
#ifdef __cplusplus
}
#endif
