#ifndef D2_FLAGS_H
#define D2_FLAGS_H
#ifdef __cplusplus
extern "C" {
#endif
void d2_flags_init(void);
void d2_flags_configure(double scale, unsigned cap);
void d2_flags_attach_window(void* window);
void d2_flags_request(void);
int d2_flags_key_event(unsigned code, int down, int repeat);
int d2_flags_guest_location(unsigned* map, unsigned* stage);
#ifdef __cplusplus
}
#endif
#endif
