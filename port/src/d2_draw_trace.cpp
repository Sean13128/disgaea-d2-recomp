/* Opt-in register-engine capture; the offline backend records, never renders. */
#include <cstdio>
#include <cstdlib>
#include <cstring>
#include <map>
#include "rsx_draw_engine.h"
#include "rsx_shader_msl.h"

static rsx_draw_backend s_real, s_trace;
static const char* s_dir;
static bool s_offline;
static unsigned s_next, s_frame, s_draw, s_upload;
static u32 s_pipeline;
struct Pipeline { rsx_be_render_state state; rsx_vertex_layout_plan layout; };
static std::map<u32, Pipeline> s_pipelines;
static std::map<u32, bool> s_pipeline_captured;
static bool s_capture_new, s_new_pipeline;
static std::map<u32, rsx_be_format> s_formats;
static float s_xf[8], s_fp[4096];
static unsigned s_fp_count;
static u32 s_targets[4], s_depth, s_tex[16], s_mask, s_sc[4];
static u32 s_stencil_ref;
static rsx_be_sampler_desc s_smp[16];
static unsigned s_capture_limit = 600;
static unsigned s_texture_limit = 24;
static unsigned s_capture_min, s_capture_every = 60;
static bool capture() { return s_new_pipeline || (s_frame >= s_capture_min &&
    (s_frame < 3 || ((!s_capture_limit || s_frame <= s_capture_limit) && s_frame % s_capture_every == 0))); }
static void blob(const char* kind, const void* data, size_t size)
{
    char path[1024];
    std::snprintf(path, sizeof path, "%s/f%u-d%u.%s", s_dir, s_frame, s_draw, kind);
    if (FILE* f = std::fopen(path, "wb")) { std::fwrite(data, 1, size, f); std::fclose(f); }
}
static u32 texture_create(void* u, rsx_be_format fmt, u32 w, u32 h, u32 m,
                          u32 faces, u32 remap, u32 rf)
{
    u32 id = s_offline ? ++s_next : s_real.texture_create(u, fmt, w, h, m, faces, remap, rf);
    s_formats[id] = fmt;
    if (s_upload < s_texture_limit) {
        u8 sel[4]; rsx_texture_component_remap(remap, rf, sel);
        std::fprintf(stderr, "[F-texture] id=%u %ux%u fmt=%02X host=%u mips=%u faces=%u remap=%04X RGBA=%u,%u,%u,%u\n",
            id, w, h, rf, fmt, m, faces, remap, sel[1], sel[2], sel[3], sel[0]);
    }
    return id;
}
static void texture_upload(void* u, u32 id, u32 face, u32 mip, u32 w, u32 h,
                           const void* data, u32 row, u32 rows)
{
    if (!s_offline) s_real.texture_upload(u, id, face, mip, w, h, data, row, rows);
    if (face || mip || s_upload++ >= s_texture_limit) return;
    char path[1024];
    std::snprintf(path, sizeof path, "%s/tex%u-%ux%u.bin", s_dir, id, w, h);
    if (FILE* f = std::fopen(path, "wb")) { std::fwrite(data, row, rows, f); std::fclose(f); }
    const bool rgba = s_formats[id] == RSX_BE_FMT_R8G8B8A8;
    if (!rgba && s_formats[id] != RSX_BE_FMT_R8) return;
    std::snprintf(path, sizeof path, "%s/tex%u.ppm", s_dir, id);
    FILE* f = std::fopen(path, "wb");
    if (f) std::fprintf(f, "P6\n%u %u\n255\n", w, h);
    unsigned nonblack = 0, nonzero_alpha = 0;
    const u8* p = (const u8*)data;
    for (u32 y = 0; y < h; ++y) for (u32 x = 0; x < w; ++x) {
        const u8* px = p + y * row + x * (rgba ? 4 : 1);
        nonblack += rgba ? (px[0] || px[1] || px[2]) : px[0] != 0;
        nonzero_alpha += rgba ? px[3] != 0 : 1;
        const u8 rgb[3] = {px[0], rgba ? px[1] : px[0], rgba ? px[2] : px[0]};
        if (f) std::fwrite(rgb, 1, 3, f);
    }
    if (f) std::fclose(f);
    std::fprintf(stderr, "[F-texture] id=%u nonblack=%u/%u alpha_nonzero=%u first_RGBA=%u,%u,%u,%u\n",
        id, nonblack, w*h, nonzero_alpha, p[0], rgba ? p[1] : p[0],
        rgba ? p[2] : p[0], rgba ? p[3] : 255);
}
static u32 pipeline_create(void* u, const char* vs, const char* ps,
                           const rsx_be_render_state* rs, const rsx_vertex_layout_plan* layout,
                           u32 stride, rsx_be_format fmt, u32 count)
{
    u32 id = s_offline ? ++s_next : s_real.pipeline_create(u, vs, ps, rs, layout, stride, fmt, count);
    s_pipelines[id] = {*rs, *layout};
    std::fprintf(stderr,"[V-pipeline] id=%u mask=%08X blend=%u rgb=%04X/%04X/%04X a=%04X/%04X/%04X alpha=%u/%04X\n",
        id,rs->color_mask,rs->blend_enable,rs->sf_rgb,rs->df_rgb,rs->eq_rgb,rs->sf_a,rs->df_a,rs->eq_a,rs->alpha_test_enable,rs->alpha_func);
    const char* stages[2] = {"vp", "fp"}; const char* sources[2] = {vs, ps};
    static char msl[262144], log[4096];
    for (unsigned i = 0; i < 2; ++i) {
        char path[1024];
        std::snprintf(path, sizeof path, "%s/p%u.%s.hlsl", s_dir, id, stages[i]);
        if (FILE* f = std::fopen(path, "w")) { std::fputs(sources[i], f); std::fclose(f); }
        int rc = rsx_hlsl_to_msl(sources[i], i ? RSX_SHADER_STAGE_FRAGMENT : RSX_SHADER_STAGE_VERTEX,
                                msl, sizeof msl, log, sizeof log);
        std::fprintf(stderr, "[F-pipeline] id=%u %s mask=%04X stride=%u translation=%d %s\n", id, stages[i], layout->mask, stride, rc, log);
        if (!rc) {
            std::snprintf(path, sizeof path, "%s/p%u.%s.msl", s_dir, id, stages[i]);
            if (FILE* f = std::fopen(path, "w")) { std::fputs(msl, f); std::fclose(f); }
        }
    }
    return id;
}
static void bind_pipeline(void* u, u32 p)
{
    s_pipeline = p;
    s_new_pipeline = s_capture_new && !s_pipeline_captured[p];
    if (!s_offline) s_real.bind_pipeline(u, p);
}
static void bind_targets(void* u, const u32* t, u32 n, u32 z)
{
    std::memset(s_targets, 0, sizeof s_targets);
    std::memcpy(s_targets, t, n * 4);
    s_depth = z;
    if (!s_offline) s_real.bind_targets(u, t, n, z);
}
static void bind_vs(void* u, const void* d, u32 n)
{
    if (n >= 514*16) std::memcpy(s_xf, (const u8*)d+512*16, sizeof s_xf);
    if (capture()) blob("vs.bin",d,n);
    if (!s_offline) s_real.bind_vs_constants(u,d,n);
}
static void bind_ps(void* u, const void* d, u32 n)
{
    const u32 size = n < sizeof s_fp ? n : sizeof s_fp;
    s_fp_count = size / 16;
    std::memcpy(s_fp,d,size); if (capture()) blob("ps.bin",d,n);
    if (!s_offline) s_real.bind_ps_constants(u,d,n);
}
static void bind_textures(void* u, const u32* t, const rsx_be_sampler_desc* s, u32 m)
{
    std::memcpy(s_tex, t, sizeof s_tex);
    std::memcpy(s_smp, s, sizeof s_smp);
    s_mask = m;
    if (!s_offline) s_real.bind_textures(u, t, s, m);
}
static void scissor(void* u, u32 x, u32 y, u32 w, u32 h)
{
    s_sc[0] = x; s_sc[1] = y; s_sc[2] = w; s_sc[3] = h;
    if (!s_offline) s_real.set_scissor(u, x, y, w, h);
}
static void draw(void* u, rsx_topology topology, const void* vertices, u32 n, u32 stride,
                 const u32* indices,u32 ni)
{
    if (capture()) {
        blob("vertices.bin",vertices,n*stride); if (ni) blob("indices.bin",indices,ni*4);
        const auto& p = s_pipelines[s_pipeline];
        const auto& r = p.state;
        std::fprintf(stderr,"[V-alpha] frame=%u draw=%u ref=%08X format=%02X separate_blend=%04X/%04X/%04X\n",
            s_frame,s_draw,r.alpha_ref_raw,r.alpha_ref_format,r.sf_a,r.df_a,r.eq_a);
        std::fprintf(stderr,"[V-stencil] enabled=%u ref=%u func=%04X masks=%02X/%02X ops=%04X/%04X/%04X two_sided=%u\n",
            r.stencil_enable,s_stencil_ref,r.s_func,r.s_func_mask,r.s_write_mask,r.s_fail,r.s_zfail,r.s_zpass,r.stencil_two_sided);
        std::fprintf(stderr,"[F-draw] frame=%u draw=%u pipeline=%u target=%u depth=%u vertices=%u indices=%u stride=%u scissor=%u,%u,%u,%u mask=%08X depth=%u/%u/%04X cull=%u/%04X/%04X blend=%u/%04X/%04X/%04X alpha=%u/%04X xf=%g,%g,%g;%g,%g,%g\n",
            s_frame,s_draw,s_pipeline,s_targets[0],s_depth,n,ni,stride,s_sc[0],s_sc[1],s_sc[2],s_sc[3],r.color_mask,r.depth_test,r.depth_write,r.depth_func,r.cull_enable,r.cull_face,r.front_face,r.blend_enable,r.sf_rgb,r.df_rgb,r.eq_rgb,r.alpha_test_enable,r.alpha_func,s_xf[0],s_xf[1],s_xf[2],s_xf[4],s_xf[5],s_xf[6]);
        for (u32 v = 0; v < n && v < 4; ++v) for (u32 slot = 0; slot < p.layout.count; ++slot) {
            const float* a=(const float*)((const u8*)vertices+v*stride+slot*16);
            std::fprintf(stderr,"[F-vertex] v=%u a%u=%g,%g,%g,%g\n",v,p.layout.attrs[slot],a[0],a[1],a[2],a[3]);
        }
        for (u32 i = 0; i < s_fp_count && i < 32; ++i) std::fprintf(stderr,"[F-fp] c%u=%g,%g,%g,%g\n",i,s_fp[i*4],s_fp[i*4+1],s_fp[i*4+2],s_fp[i*4+3]);
        for (u32 i = 0; i < 16; ++i) if ((s_mask>>i)&1) std::fprintf(stderr,"[F-sampler] unit=%u texture=%u linear=%u/%u mip=%u/%u wrap=%u/%u lod=%g..%g\n",i,s_tex[i],s_smp[i].min_linear,s_smp[i].mag_linear,s_smp[i].mip_present,s_smp[i].mip_linear,s_smp[i].wrap_s,s_smp[i].wrap_t,s_smp[i].min_lod,s_smp[i].max_lod);
    }
    ++s_draw;
    s_pipeline_captured[s_pipeline] = true;
    s_new_pipeline = false;
    if (!s_offline) s_real.draw(u,topology,vertices,n,stride,indices,ni);
}
static void present(void* u, u32 target)
{
    if (capture()) std::fprintf(stderr,"[F-present] frame=%u target=%u draws=%u\n",s_frame,target,s_draw);
    ++s_frame;
    s_draw = 0;
    if (!s_offline) s_real.present(u, target);
}
static void clear_color(void* u, u32 t, const float* c)
{
    if (capture()) std::fprintf(stderr,"[F-clear] target=%u rgba=%g,%g,%g,%g\n",t,c[0],c[1],c[2],c[3]);
    if (!s_offline) s_real.clear_color(u, t, c);
}
static void clear_depth(void* u, u32 t, u32 flags, float z, u8 s)
{
    if (capture()) std::fprintf(stderr,"[F-clear-depth] target=%u flags=%u z=%g stencil=%u\n",t,flags,z,s);
    if (!s_offline) s_real.clear_depth_stencil(u, t, flags, z, s);
}
static u32 color_create(void* u,rsx_be_format fmt,u32 w,u32 h,const void* seed,u32 row)
{
    u32 id = s_offline ? ++s_next : s_real.color_target_create(u,fmt,w,h,seed,row);
    std::fprintf(stderr,"[V-surface] id=%u %ux%u host=%u seeded=%u\n",id,w,h,fmt,seed != nullptr);
    return id;
}
static u32 surface_view(void* u,u32 surface,u32 remap,u32 fmt)
{
    u32 id = s_offline ? surface : s_real.surface_view(u,surface,remap,fmt);
    if (capture()) std::fprintf(stderr,"[V-surface-view] id=%u surface=%u fmt=%02X remap=%04X\n",id,surface,fmt,remap);
    return id;
}
static u32 depth_create(void*,u32,u32) { return ++s_next; }
static void noop_handle(void*,u32) {}
static void stencil_ref(void* u,u32 ref)
{
    s_stencil_ref = ref;
    if (!s_offline) s_real.set_stencil_ref(u,ref);
}
static void noop_vtex(void*,const u32*,const rsx_be_sampler_desc*,u32) {}
static void noop_viewport(void*,float,float,float,float) {}

extern "C" int d2_install_draw_trace(void)
{
    s_dir = std::getenv("D2_DRAW_TRACE");
    if (!s_dir || !*s_dir) return 0;
    s_capture_new = std::getenv("D2_DRAW_TRACE_NEW_PIPELINES") != nullptr;
    if (const char* limit = std::getenv("D2_DRAW_TRACE_MAX_FRAME"))
        s_capture_limit = (unsigned)std::strtoul(limit, nullptr, 10);
    if (const char* limit = std::getenv("D2_DRAW_TRACE_TEXTURE_LIMIT"))
        s_texture_limit = (unsigned)std::strtoul(limit, nullptr, 10);
    if (const char* first = std::getenv("D2_DRAW_TRACE_MIN_FRAME"))
        s_capture_min = (unsigned)std::strtoul(first, nullptr, 10);
    if (const char* every = std::getenv("D2_DRAW_TRACE_EVERY")) {
        s_capture_every = (unsigned)std::strtoul(every, nullptr, 10);
        if (!s_capture_every) s_capture_every = 60;
    }
    const rsx_draw_backend* be = rsx_draw_engine_get_backend();
    s_offline = !rsx_draw_engine_enabled();
    if (!s_offline && be) s_real = *be;
    s_trace = s_real;
    if (s_offline) {
        rsx_set_backend(nullptr);
        s_trace.color_target_create = color_create;
        s_trace.depth_target_create = depth_create;
        s_trace.texture_release = noop_handle;
        s_trace.color_target_release = noop_handle;
        s_trace.depth_target_release = noop_handle;
        s_trace.pipeline_release = noop_handle;
        s_trace.bind_vertex_textures = noop_vtex;
        s_trace.set_viewport = noop_viewport;
        s_trace.set_stencil_ref = noop_handle;
    }
    s_trace.texture_create = texture_create;
    s_trace.color_target_create = color_create;
    if (s_offline || s_real.surface_view) s_trace.surface_view = surface_view;
    s_trace.texture_upload = texture_upload;
    s_trace.pipeline_create = pipeline_create;
    s_trace.bind_pipeline = bind_pipeline;
    s_trace.bind_targets = bind_targets;
    s_trace.bind_vs_constants = bind_vs;
    s_trace.bind_ps_constants = bind_ps;
    s_trace.bind_textures = bind_textures;
    s_trace.set_scissor = scissor;
    s_trace.draw = draw;
    s_trace.set_stencil_ref = stencil_ref;
    s_trace.present = present;
    s_trace.clear_color = clear_color;
    s_trace.clear_depth_stencil = clear_depth;
    rsx_draw_engine_set_backend(&s_trace);
    if (s_offline) {
        rsx_draw_engine_set_default(1);
        rsx_draw_engine_init(1280,720);
    }
    std::fprintf(stderr,"[F-trace] %s register-engine capture to %s (first=%u every=%u limit=%u, 0=unlimited; new_pipelines=%u)\n",
        s_offline ? "GPU-free" : "Metal",s_dir,s_capture_min,s_capture_every,s_capture_limit,s_capture_new);
    return s_offline;
}
