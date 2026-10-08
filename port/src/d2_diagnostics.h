#ifndef D2_DIAGNOSTICS_H
#define D2_DIAGNOSTICS_H
#ifdef __cplusplus
extern "C" {
#endif
/* AppKit main-thread only. This window never reads guest memory. */
void d2_diagnostics_toggle(void);
void d2_diagnostics_close(void);
int d2_diagnostics_visible(void);
#ifdef __cplusplus
}
#endif
#endif
