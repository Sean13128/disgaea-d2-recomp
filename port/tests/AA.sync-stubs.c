#include <stdint.h>
void rsx_draw_engine_record_begin(void) {}
void rsx_draw_engine_record_packet(uint32_t io, const void* p, uint32_t n)
{ (void)io; (void)p; (void)n; }
