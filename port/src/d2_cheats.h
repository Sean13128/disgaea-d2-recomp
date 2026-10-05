#pragma once
#ifdef __cplusplus
extern "C" {
#endif
/* Thread-safe request; UI and guest writes are serviced by the PPU frame hook. */
void d2_cheats_toggle_menu(void);
void d2_register_cheats(void);
#ifdef __cplusplus
}
#endif
