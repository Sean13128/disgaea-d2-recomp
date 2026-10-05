/* Optional GPU-free validation of the guest programs submitted at draw time. */
#include <cstdio>
#include <cstdlib>
#include <cstring>

#include "rsx_commands.h"
#include "rsx_vp_decompiler.h"
#include "rsx_fp_decompiler.h"
#include "rsx_shader_msl.h"

extern "C" unsigned char* vm_base;
extern "C" u32 cellGcmResolveLocated(u32 location, u32 offset);

static rsx_backend s_backend;
static void (*s_set_shader)(void*, const rsx_state*);
static char s_hlsl[262144], s_msl[262144], s_log[4096];
static u64 s_seen[64];
static unsigned s_seen_count;

static void translate(const char* stage, int kind, int instructions)
{
    if (instructions <= 0) return;
    u64 hash = 1469598103934665603ull;
    for (const unsigned char* p = (const unsigned char*)s_hlsl; *p; ++p)
        hash = (hash ^ *p) * 1099511628211ull;
    for (unsigned i = 0; i < s_seen_count; ++i)
        if (s_seen[i] == hash) return;
    if (s_seen_count == 64) return;
    s_seen[s_seen_count++] = hash;
    int rc = rsx_hlsl_to_msl(s_hlsl, kind, s_msl, sizeof s_msl, s_log, sizeof s_log);
    std::fprintf(stderr, "[d2-shader] %s %016llX: %d instructions -> %s (%zu MSL bytes)%s%s\n",
        stage, (unsigned long long)hash, instructions, rc ? "FAILED" : "translated",
        rc ? 0 : std::strlen(s_msl), rc ? ": " : "", rc ? s_log : "");
    const char* dir = std::getenv("PS3RECOMP_METAL_SHADER_DUMP");
    if (!dir || !*dir) return;
    char path[1024];
    std::snprintf(path, sizeof path, "%s/%s_%016llx.hlsl", dir, stage, (unsigned long long)hash);
    if (FILE* f = std::fopen(path, "w")) { std::fputs(s_hlsl, f); std::fclose(f); }
    if (rc) return;
    std::snprintf(path, sizeof path, "%s/%s_%016llx.msl", dir, stage, (unsigned long long)hash);
    if (FILE* f = std::fopen(path, "w")) { std::fputs(s_msl, f); std::fclose(f); }
}

static void trace_shader(void* userdata, const rsx_state* st)
{
    if (s_set_shader) s_set_shader(userdata, st);
    u32 vtex_mask = 0, cube_mask = 0;
    for (u32 i = 0; i < RSX_MAX_VERTEX_TEXTURES; ++i)
        if (st->vertex_textures[i].control0 & 0x80000000u) vtex_mask |= 1u << i;
    for (u32 i = 0; i < RSX_MAX_TEXTURES; ++i)
        if (st->textures[i].format & 4u) cube_mask |= 1u << i;
    if (st->vp_ucode_bytes >= 16) {
        u32 start = st->transform_program_start * 16u;
        if (start >= st->vp_ucode_bytes) start = 0;
        rsx_vp_set_branch_base(start / 16u);
        int n = rsx_vp_decompile_ex(st->vp_ucode + start, st->vp_ucode_bytes - start,
                                   vtex_mask, s_hlsl, sizeof s_hlsl);
        translate("vp", RSX_SHADER_STAGE_VERTEX, n);
    }
    if (vm_base && st->shader_program) {
        u32 ea = cellGcmResolveLocated((st->shader_program & 3u) == 1u, st->shader_program & ~3u);
        if (ea != 0xFFFFFFFFu) {
            u32 constants = 0;
            int n = rsx_fp_decompile_buffered_ex(vm_base + ea, 8192, st->shader_control,
                                                 cube_mask, s_hlsl, sizeof s_hlsl, &constants);
            if (n > 0 && st->alpha_test_enable && st->alpha_func != 0x0207u &&
                rsx_fp_apply_alpha_test_buffered(s_hlsl, sizeof s_hlsl, st->alpha_func) < 0)
                n = -1;
            translate("fp", RSX_SHADER_STAGE_FRAGMENT, n);
        }
    }
}

extern "C" void d2_install_shader_trace(void)
{
    if (!std::getenv("PS3RECOMP_SHADER_TRACE") || !rsx_hlsl_to_msl_available()) return;
    rsx_backend* backend = rsx_get_backend();
    if (!backend) return;
    s_backend = *backend;
    s_set_shader = backend->set_shader;
    s_backend.set_shader = trace_shader;
    rsx_set_backend(&s_backend);
    std::fprintf(stderr, "[d2-shader] GPU-free guest HLSL -> MSL trace enabled\n");
}
