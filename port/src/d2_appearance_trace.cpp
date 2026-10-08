/* Opt-in staged alternate-body binding and read-only 1.40 observations.
 * Definitions in the build copy call through these wrappers; shipped lifts
 * and runtime selection behavior remain unchanged. */
#include "ppu_recomp.h"
#include "d2_appearance.h"
#include <cstring>
#include <algorithm>
#include <array>
#include <map>
extern "C" uint64_t ppu_guest_call_ct(uint32_t,uint32_t,uint64_t,uint64_t,uint64_t,uint64_t,uint64_t,uint64_t,uint64_t,uint64_t);
#include <cstdio>
#include <cstdlib>
#include <mutex>
#include <set>
#include <tuple>
#include <string_view>
#if D2_APPEARANCE_IMPORTER
#include <filesystem>
#include <fstream>
#include <map>
#include <optional>
#include <vector>
#include <cerrno>
#include <fcntl.h>
#include <sys/file.h>
#include <sys/stat.h>
#include <unistd.h>
#include <nlohmann/json.hpp>
#endif

void d2_appearance_original_illustration(ppu_context*);
void d2_appearance_original_select(ppu_context*);
void d2_appearance_original_update(ppu_context*);
void d2_appearance_original_write_body(ppu_context*);
void d2_appearance_original_read_body(ppu_context*);
void d2_appearance_original_record(ppu_context*);
void d2_appearance_original_visual(ppu_context*);
void d2_appearance_original_request(ppu_context*);
void d2_appearance_original_category(ppu_context*);
void d2_appearance_original_body_kind(ppu_context*);
void d2_appearance_original_motion(ppu_context*);
void d2_appearance_original_file_size(ppu_context*);
void d2_appearance_original_allocate(ppu_context*);
void d2_appearance_original_file_read(ppu_context*);
void d2_appearance_original_load_update(ppu_context*);
void d2_appearance_original_model_select(ppu_context*);
void d2_appearance_original_texture_bind(ppu_context*);
void d2_appearance_original_unit_face(ppu_context*);
void d2_appearance_original_unit_face_large(ppu_context*);
void d2_appearance_original_unit_panel_face(ppu_context*);
void d2_appearance_original_class_queued_face(ppu_context*);
void d2_appearance_original_class_queued_face_alt(ppu_context*);
void d2_appearance_original_ui_face_record(ppu_context*);
void d2_appearance_original_ui_face_draw(ppu_context*);
void d2_appearance_original_unit_list_face(ppu_context*);
void d2_appearance_original_unit_list_face_alt(ppu_context*);
void d2_appearance_original_unit_small_face(ppu_context*);
void d2_appearance_original_unit_small_face_alt(ppu_context*);
void d2_appearance_original_face_coordinates(ppu_context*);

namespace {
struct VisualScope { unsigned resource=0,donor=0; };
thread_local VisualScope active_visual;
thread_local uint64_t face_unit=0;
thread_local unsigned face_class=0;
struct FaceClassScope {
    unsigned previous;
    explicit FaceClassScope(unsigned cls):previous(face_class) { face_class=cls; }
    ~FaceClassScope() { face_class=previous; }
};
struct FaceScope {
    uint64_t previous;
    explicit FaceScope(uint64_t unit):previous(face_unit) { face_unit=unit; }
    ~FaceScope() { face_unit=previous; }
};
unsigned resource_filter()
{
    static unsigned filter = [] {
        const char* value = std::getenv("D2_APPEARANCE_TRACE");
        if (!value || !*value) return 0u;
        char* end = nullptr;
        unsigned long id = std::strtoul(value, &end, 10);
        return *end || !id || id >= 100000 ? 0u : unsigned(id);
    }();
    return filter;
}
bool readable(uint64_t address, uint32_t size)
{
    return address >= 0x10000 && address <= 0xffffffffull && address + size <= 0x100000000ull;
}
#if D2_APPEARANCE_IMPORTER
struct Binding {
    unsigned selector,resource,visual_class;
    bool renderer_only,enabled;
    unsigned illustration_resource=0,illustration_donor=0;
    std::array<unsigned,5> face{}; // x,y,width,height,original face identity
};
struct BindingState {
    nlohmann::json manifest;
    std::map<unsigned,Binding> active;
    std::map<std::pair<unsigned,std::string>,Binding> costumes;
    std::map<std::pair<unsigned,std::string>,std::string> labels;
};
int checked_binding_integer(const nlohmann::json& entry,const char* key,int minimum,int maximum,int fallback=-1)
{
    if(!entry.contains(key)) {
        if(fallback>=minimum && fallback<=maximum) return fallback;
        throw std::runtime_error("Missing binding integer");
    }
    const auto& item=entry.at(key);
    if(!item.is_number_integer()) throw std::runtime_error("Binding integer has wrong type");
    int64_t value=item.get<int64_t>();
    if(value<minimum || value>maximum) throw std::runtime_error("Binding integer out of range");
    return int(value);
}
Binding parse_binding(const nlohmann::json& entry,unsigned& cls)
{
    int identity=checked_binding_integer(entry,"class_id",1,32767),selector=checked_binding_integer(entry,"selector",1,1),
        resource=checked_binding_integer(entry,"new_resource",1,32767);
    int visual=checked_binding_integer(entry,"visual_class_id",0,32767,0);
    std::string mode=entry.value("selection_mode",std::string("selector"));
    bool renderer_only=mode=="renderer-only";
    if (identity<1 || identity>=32768 || selector!=1 || resource<1 || resource>=32768 ||
        visual<0 || visual>=32768 || (mode!="selector" && !renderer_only) || (renderer_only && !visual))
        throw std::runtime_error("Invalid appearance binding");
    int picture=0,picture_donor=0;
    if(entry.contains("illustration_resource") || entry.contains("illustration_donor")) {
        picture=checked_binding_integer(entry,"illustration_resource",10000,19999);
        picture_donor=checked_binding_integer(entry,"illustration_donor",10000,19999);
        if(!renderer_only || picture==picture_donor) throw std::runtime_error("Invalid independent illustration binding");
    }
    std::array<unsigned,5> face{};
    if(entry.contains("face_cell")) {
        const auto& c=entry.at("face_cell");
        if(!renderer_only || !c.is_object() || c.size()!=5) throw std::runtime_error("Invalid face-cell binding");
        face={unsigned(checked_binding_integer(c,"x",384,4000)),unsigned(checked_binding_integer(c,"y",0,4000)),
              unsigned(checked_binding_integer(c,"width",480,4096)),unsigned(checked_binding_integer(c,"height",96,4096)),
              unsigned(checked_binding_integer(c,"donor",0,499))};
        if(face[0]%96 || face[1]%96 || face[2]%96 || face[3]%96 || face[0]+96>face[2] || face[1]+96>face[3])
            throw std::runtime_error("Face-cell coordinates outside appended columns");
    }
    cls=unsigned(identity);
    return {unsigned(selector),unsigned(resource),unsigned(visual),renderer_only,entry.value("enabled",true),unsigned(picture),unsigned(picture_donor),face};
}
BindingState load_bindings()
{
        BindingState result;
        const char* path=std::getenv("D2_APPEARANCE_MANIFEST");
        if (!path || !*path) return result;
        try {
            if (std::filesystem::file_size(path)>1024*1024) throw std::runtime_error("Manifest too large");
            std::ifstream stream(path);
            auto data=nlohmann::json::parse(stream);
            if (data.at("mode")!="isolated-runtime-experiment") throw std::runtime_error("Unsupported manifest mode");
            // Experimental bindings require the explicitly staged environment,
            // including private save/cache roots. Nothing is enabled implicitly.
            for (const char* key:{"PS3_VFS_ROOT","PS3_HDD0_ROOT","PS3_HDD1_ROOT"}) {
                const char* actual=std::getenv(key);
                std::string expected=data.at("runtime_environment").at(key);
                if (!actual || std::filesystem::weakly_canonical(actual)!=std::filesystem::weakly_canonical(expected))
                    throw std::runtime_error(std::string("Staged root mismatch: ")+key);
            }
            auto entries=data.contains("appearances")?data.at("appearances"):nlohmann::json::array({data});
            if (!entries.is_array() || entries.empty() || entries.size()>128) throw std::runtime_error("Invalid appearance list");
            for (const auto& entry:entries) {
                unsigned cls;
                auto binding=parse_binding(entry,cls);
                if (!result.active.emplace(cls,binding).second)
                    throw std::runtime_error("Duplicate appearance binding");
            }
            // Only explicitly catalogued renderer-only costumes are candidates
            // for a future PPU-thread live request. Legacy selectors remain static.
            if (data.contains("costumes")) {
                const auto& catalog=data.at("costumes");
                if (!catalog.is_array() || catalog.empty() || catalog.size()>128)
                    throw std::runtime_error("Invalid costume catalog");
                std::set<unsigned> resources,visuals,pictures;
                std::set<std::pair<unsigned,unsigned>> face_locations,face_dimensions;
                for (const auto& entry:catalog) {
                    unsigned cls;
                    auto binding=parse_binding(entry,cls);
                    if(binding.face[2]) {
                        if(!face_locations.emplace(binding.face[0],binding.face[1]).second) throw std::runtime_error("Duplicate face cell");
                        face_dimensions.emplace(binding.face[2],binding.face[3]);
                    }
                    std::string token=entry.at("costume_id");
                    std::string label=entry.value("display_name",std::string(""));
                    if(label.size()>127 || std::any_of(label.begin(),label.end(),[](unsigned char c){return c<32 || c==127;}))
                        throw std::runtime_error("Invalid costume display name");
                    result.labels[{cls,token}]=label;
                    if (token.empty() || token.size()>64 ||
                        token.find_first_not_of("abcdefghijklmnopqrstuvwxyz0123456789-")!=std::string::npos ||
                        token.front()=='-' ||
                        !binding.renderer_only || !result.active.contains(cls) ||
                        !resources.emplace(binding.resource).second || !visuals.emplace(binding.visual_class).second ||
                        (binding.illustration_resource && !pictures.emplace(binding.illustration_resource).second) ||
                        !result.costumes.emplace(std::make_pair(cls,token),binding).second)
                        throw std::runtime_error("Invalid or duplicate catalog costume");
                }
                if(face_dimensions.size()>1) throw std::runtime_error("Face atlas dimensions disagree");
                for(unsigned picture:pictures) if(resources.contains(picture))
                    throw std::runtime_error("Illustration/body resource collision");
                for (const auto& [cls,binding]:result.active) {
                    bool matched=false;
                    for (const auto& [key,costume]:result.costumes)
                        if (key.first==cls && binding.renderer_only && binding.selector==costume.selector &&
                            binding.resource==costume.resource && binding.visual_class==costume.visual_class &&
                            binding.illustration_resource==costume.illustration_resource && binding.illustration_donor==costume.illustration_donor && binding.face==costume.face) matched=true;
                    if (!matched) throw std::runtime_error("Active appearance absent from catalog");
                }
            }
            result.manifest=data;
            std::fprintf(stderr,"[D2 appearance] loaded %zu staged binding(s) from %s\n",result.active.size(),path);
        } catch (const std::exception& error) {
            result={};
            std::fprintf(stderr,"[D2 appearance] bindings rejected: %s\n",error.what());
        }
        return result;
}
struct BindingRegistry {
    std::mutex lock;
    BindingState state=load_bindings();
    uint64_t generation=1;
};
BindingRegistry& registry() { static BindingRegistry value; return value; }
std::optional<Binding> binding_for(unsigned cls)
{
    auto& value=registry();
    std::lock_guard<std::mutex> hold(value.lock);
    auto found=value.state.active.find(cls);
    if (found==value.state.active.end()) return std::nullopt;
    return found->second;
}
[[maybe_unused]] uint64_t binding_generation()
{
    auto& value=registry();
    std::lock_guard<std::mutex> hold(value.lock);
    return value.generation;
}
// Session state only. The future live bridge must validate scene/actor readiness
// on the PPU thread before calling this; changing a binding does not refresh an
// existing actor. No guest/save/manifest writes occur here.
[[maybe_unused]] bool select_session_costume(unsigned cls,std::string_view token,uint64_t expected_generation)
{
    auto& value=registry();
    std::lock_guard<std::mutex> hold(value.lock);
    auto active=value.state.active.find(cls);
    if (expected_generation!=value.generation || active==value.state.active.end() || !active->second.renderer_only)
        return false;
    if (token.empty()) active->second.enabled=false;
    else {
        auto found=value.state.costumes.find({cls,std::string(token)});
        if (found==value.state.costumes.end()) return false;
        active->second=found->second;
        active->second.enabled=true;
    }
    ++value.generation;
    return true;
}
unsigned alternate_body(uint64_t unit,unsigned index,bool renderer=false)
{
    if (index || !readable(unit,0x11FE)) return 0;
    const unsigned cls=vm_read16(unit+0x1158);
    auto found=binding_for(cls);
    if (!found || !found->enabled) return 0;
    if (found->renderer_only) {
        if (!renderer) return 0;
    } else if (vm_read8(unit+0x117A)!=found->selector) return 0;
    // Follow the exact class getter, checking its cached index first. Legacy
    // personality selection requires its authored second slot. Renderer-only
    // costumes instead validate the independent visual definition below.
    uint32_t manager=vm_read32(0x47DF98-0x7E68);
    if (!readable(manager,8)) return 0;
    unsigned row=vm_read16(unit+0x115C),count=vm_read16(manager);
    uint32_t first=vm_read32(manager+4);
    if (row>=count || !readable(first,uint32_t(count)*676)) return 0;
    uint32_t record=first+row*676;
    if (vm_read16(record+0x194)!=cls ||
        (!found->renderer_only && vm_read16(record+0x1BE)!=found->resource)) return 0;
    return found->resource;
}
unsigned validated_visual(uint64_t unit,unsigned requested,const Binding& binding,unsigned& resource)
{
    if (!readable(unit,0x11FE) || vm_read16(unit+0x1158)!=requested) return 0;
    const Binding* entry=&binding;
    if (!entry || !entry->enabled || !entry->visual_class ||
        (!entry->renderer_only && vm_read8(unit+0x117A)!=entry->selector)) return 0;
    unsigned visual=entry->visual_class;
    uint32_t manager=vm_read32(0x47DF98-0x7E68);
    if (!readable(manager,8)) return 0;
    uint32_t first=vm_read32(manager+4);
    unsigned count=vm_read16(manager),index=vm_read16(unit+0x115C);
    if (index>=count || !readable(first,count*676)) return 0;
    uint32_t donor=first+index*676;
    if (vm_read16(donor+0x194)!=requested ||
        (!entry->renderer_only && vm_read16(donor+0x1BE)!=entry->resource)) return 0;
    for (unsigned i=0;i<count;++i) {
        uint32_t row=first+i*676;
        if (vm_read16(row+0x194)==visual && vm_read16(row+0x196)==entry->resource &&
            vm_read16(row+0x1BC)==entry->resource) {
            resource=entry->resource;
            return visual;
        }
    }
    return 0;
}
unsigned visual_class(uint64_t unit,unsigned requested,unsigned& resource)
{
    auto entry=binding_for(requested);
    return entry?validated_visual(unit,requested,*entry,resource):0;
}
unsigned illustration_for(uint64_t unit,unsigned original)
{
    if(!readable(unit,0x11FE)) return original;
    unsigned cls=vm_read16(unit+0x1158);auto entry=binding_for(cls);
    if(!entry || !entry->enabled || !entry->renderer_only || !entry->illustration_resource ||
       entry->illustration_donor!=original) return original;
    unsigned body=0;
    return validated_visual(unit,cls,*entry,body)?entry->illustration_resource:original;
}
uint32_t hub_source_unit(uint64_t descriptor,uint64_t stack,unsigned requested,unsigned caller)
{
    auto entry=binding_for(requested);
    if (!entry || !entry->enabled || !entry->renderer_only ||
        caller!=0x000E836C || !readable(stack+0xA0,8) ||
        vm_read32(stack+0xA0)!=0 || vm_read32(stack+0xA4)!=0x000E83F8 ||
        !readable(descriptor,0x3DC) || vm_read32(descriptor+0x3D8)!=2 ||
        vm_read16(descriptor+0x21C)!=requested) return 0;
    // E83BC gets the controlled character's class through 2EB70. The actor
    // has no unit link; recover the same party identity read by 2E9B8/1074C8.
    uint32_t control=vm_read32(0x47DF98-0x7CA4),party=vm_read32(0x47DF98-0x4F48);
    if (!readable(control,0x150AA8) || !readable(party,0x1507EE)) return 0;
    unsigned count=vm_read16(party+0x1507EC),identity=vm_read16(control+0x150AA6);
    if (!identity || identity>=32768 || count<1 || count>128 || !readable(party+0x598,count*0x1A60)) return 0;
    uint32_t source=0;
    for (unsigned i=0;i<count;++i) {
        uint32_t unit=party+0x598+i*0x1A60;
        if (vm_read16(unit+0x1202)!=identity) continue;
        if (source || vm_read16(unit+0x1158)!=requested) return 0;
        source=unit;
    }
    return source;
}
std::array<unsigned,6> face_for(uint64_t unit,unsigned group,unsigned original)
{
    if(group || !readable(unit,0x11FE)) return {};
    unsigned cls=vm_read16(unit+0x1158);auto entry=binding_for(cls);
    if(!entry || !entry->renderer_only || !entry->face[2] || entry->face[4]!=original) return {};
    unsigned body=0;
    if(!validated_visual(unit,cls,*entry,body)) return {};
    uint32_t manager=vm_read32(0x47DF98-0x7E68),first=vm_read32(manager+4);
    unsigned index=vm_read16(unit+0x115C);
    if(vm_read16(first+index*676+0x19E)!=original) return {};
    uint32_t bank=vm_read32(0x47DF98-0x47F0);
    if(!readable(bank,4)) return {};
    uint32_t texture=vm_read32(bank);
    if(!readable(texture,0x30) || vm_read16(texture+0x2C)!=entry->face[2] || vm_read16(texture+0x2E)!=entry->face[3]) return {};
    return {entry->face[0],entry->face[1],entry->face[2],entry->face[3],entry->face[4],entry->resource};
}
std::array<unsigned,6> face_for_class(unsigned cls,unsigned group,unsigned original)
{
    if(!cls || cls>=32768 || group) return {};
    auto entry=binding_for(cls);
    if(!entry || !entry->enabled || !entry->renderer_only || !entry->face[2] || entry->face[4]!=original) return {};
    uint32_t manager=vm_read32(0x47DF98-0x7E68);
    if(!readable(manager,8)) return {};
    uint32_t first=vm_read32(manager+4);unsigned count=vm_read16(manager),donors=0,visuals=0;
    if(!count || count>4096 || !readable(first,count*676)) return {};
    for(unsigned i=0;i<count;++i) {
        uint32_t row=first+i*676;unsigned id=vm_read16(row+0x194);
        if(id==cls) { if(vm_read16(row+0x19E)!=original) return {}; ++donors; }
        if(id==entry->visual_class) {
            if(vm_read16(row+0x196)!=entry->resource || vm_read16(row+0x1BC)!=entry->resource) return {};
            ++visuals;
        }
    }
    if(donors!=1 || visuals!=1) return {};
    uint32_t bank=vm_read32(0x47DF98-0x47F0);
    if(!readable(bank,4)) return {};
    uint32_t texture=vm_read32(bank);
    if(!readable(texture,0x30) || vm_read16(texture+0x2C)!=entry->face[2] || vm_read16(texture+0x2E)!=entry->face[3]) return {};
    return {entry->face[0],entry->face[1],entry->face[2],entry->face[3],entry->face[4],entry->resource};
}

#else
std::array<unsigned,6> face_for(uint64_t,unsigned,unsigned) { return {}; }
std::array<unsigned,6> face_for_class(unsigned,unsigned,unsigned) { return {}; }
unsigned illustration_for(uint64_t,unsigned original) { return original; }
unsigned alternate_body(uint64_t,unsigned,bool=false) { return 0; }
unsigned visual_class(uint64_t,unsigned,unsigned&) { return 0; }
uint32_t hub_source_unit(uint64_t,uint64_t,unsigned,unsigned) { return 0; }
#endif
std::mutex trace_lock;
std::set<std::tuple<uint32_t,unsigned,unsigned,unsigned,unsigned,unsigned>> face_routes;
std::set<std::tuple<uint32_t,unsigned,unsigned,unsigned>> face_lookups;
std::set<std::tuple<uint32_t,unsigned,unsigned>> selections;
std::set<std::tuple<uint32_t,unsigned,unsigned>> states;
std::set<uint32_t> managers;
std::set<std::tuple<uint32_t,unsigned,unsigned,unsigned>> body_accesses;
std::set<std::tuple<uint32_t,unsigned,unsigned>> records;
std::set<std::tuple<uint32_t,unsigned,unsigned>> visual_calls;
std::set<std::tuple<uint32_t,unsigned,unsigned>> requests;
std::set<std::tuple<uint32_t,unsigned,unsigned>> file_sizes;
std::set<std::tuple<unsigned,uint32_t>> allocations;
std::set<std::tuple<uint32_t,unsigned,unsigned>> file_reads;
std::set<uint32_t> appearance_models;
std::set<std::tuple<uint32_t,unsigned,unsigned,unsigned>> model_selections;
std::set<std::tuple<uint32_t,unsigned,unsigned,unsigned>> texture_bindings;
void trace_manager(uint64_t manager);

void trace_body(uint64_t unit, unsigned index, unsigned body, unsigned caller, bool write)
{
    if (!resource_filter() || !readable(unit,0x11FE)) return;
    unsigned identity=vm_read16(unit+0x1158);
    if (body!=resource_filter() && identity!=30 && body!=30) return;
    std::lock_guard<std::mutex> lock(trace_lock);
    if (body_accesses.emplace(uint32_t(unit),index,body,write).second)
        std::fprintf(stderr,"[D2 appearance] %s unit=%08x class=%u selector=%u family=%u index=%u body=%u caller=%08x\n",
                     write?"write_body":"read_body",uint32_t(unit),identity,
                     unsigned(vm_read8(unit+0x117A)),unsigned(vm_read16(unit+0x11FC)),index,body,caller);
}
}

void func_00109350(ppu_context* ctx)
{
    uint64_t unit=ctx->gpr[3];unsigned caller=unsigned(ctx->lr);
    d2_appearance_original_illustration(ctx);
    unsigned original=unsigned(ctx->gpr[3]),selected=illustration_for(unit,original);
    if(selected!=original) {
        ctx->gpr[3]=selected;
        if(resource_filter()) {
            std::lock_guard<std::mutex> lock(trace_lock);
            if(requests.emplace(uint32_t(unit),selected,caller).second)
                std::fprintf(stderr,"[D2 appearance] illustration unit=%08x donor=%u resource=%u caller=%08x\n",uint32_t(unit),original,selected,caller);
        }
    }
}

void func_00029804(ppu_context* ctx)
{
    uint64_t descriptor=ctx->gpr[3];
    unsigned requested=unsigned(ctx->gpr[4]),caller=unsigned(ctx->lr);
    uint32_t unit=readable(descriptor,0x1c0)?vm_read32(descriptor+0x1bc):0;
    // 1.40 func_000A8F00 builds a temporary skill actor before copying the
    // source descriptor. At this exact callsite its saved r29 holds the
    // source unit; the new descriptor's unit link is still zero.
    if (!unit && caller==0x000A8FE0 && readable(ctx->gpr[29],0x11FE) &&
        vm_read16(ctx->gpr[29]+0x1158)==requested)
        unit=uint32_t(ctx->gpr[29]);
    if (!unit) unit=hub_source_unit(descriptor,ctx->gpr[1],requested,caller);
    if (resource_filter() && requested==30 && caller==0x000E836C) {
        uint64_t stack=ctx->gpr[1];uint32_t control=vm_read32(0x47DF98-0x7CA4),party=vm_read32(0x47DF98-0x4F48);
        std::fprintf(stderr,"[D2 appearance] hub_source stack=%08x parent=%08x/%08x tag=%u descriptor_class=%u control=%08x party=%08x count=%u identity=%u recovered=%08x\n",
            uint32_t(stack),readable(stack+0xA0,8)?vm_read32(stack+0xA0):0,
            readable(stack+0xA0,8)?vm_read32(stack+0xA4):0,
            readable(descriptor,0x3DC)?vm_read32(descriptor+0x3D8):0,
            readable(descriptor,0x21E)?vm_read16(descriptor+0x21C):0,control,party,
            readable(party,0x1507EE)?unsigned(vm_read16(party+0x1507EC)):0,
            readable(control,0x150AA8)?unsigned(vm_read16(control+0x150AA6)):0,unit);
    }
    unsigned resource=0,alias=visual_class(unit,requested,resource);
    if (resource_filter() && (requested==30 || alias)) {
        std::lock_guard<std::mutex> lock(trace_lock);
        if (visual_calls.emplace(uint32_t(descriptor),requested,alias).second)
            std::fprintf(stderr,"[D2 appearance] visual descriptor=%08x unit=%08x class=%u alias=%u arg5=%llu arg6=%llu arg7=%llu arg8=%llu caller=%08x\n",
                         uint32_t(descriptor),unit,requested,alias,
                         (unsigned long long)ctx->gpr[5],(unsigned long long)ctx->gpr[6],
                         (unsigned long long)ctx->gpr[7],(unsigned long long)ctx->gpr[8],caller);
    }
    if (alias) ctx->gpr[4]=alias;
    const VisualScope previous=active_visual;
    if (alias) {
        uint32_t manager=vm_read32(0x47DF98-0x7E68),first=vm_read32(manager+4);
        uint32_t row=first+vm_read16(unit+0x115C)*676;
        active_visual={resource,unsigned(vm_read16(row+0x196))};
    }
    d2_appearance_original_visual(ctx);
    active_visual=previous;
    if (alias && resource_filter() && readable(descriptor,0x254)) {
        std::lock_guard<std::mutex> lock(trace_lock);
        uint32_t model=vm_read32(descriptor+0x1a4);
        if (model) appearance_models.emplace(model);
        std::fprintf(stderr,"[D2 appearance] visual_result descriptor=%08x model=%08x body_handle=%d class_row=%u kind=%u\n",
                     uint32_t(descriptor),model,int32_t(vm_read32(descriptor+0x1ac)),
                     unsigned(vm_read16(descriptor+0x250)),unsigned(vm_read16(descriptor+0x252)));
    }
}

void func_002E89D8(ppu_context* ctx)
{
    uint32_t model=uint32_t(ctx->gpr[3]);
    unsigned library=unsigned(ctx->gpr[4]),variant=unsigned(ctx->gpr[5]),caller=unsigned(ctx->lr);
    // Cached models may bind their body inside the constructor, before its
    // result hook sees the model pointer. Observe that same scoped model now.
    if(resource_filter() && active_visual.resource) {
        std::lock_guard<std::mutex> lock(trace_lock);appearance_models.emplace(model);
    }
    d2_appearance_original_model_select(ctx);
    if (!resource_filter()) return;
    std::lock_guard<std::mutex> lock(trace_lock);
    if (library==resource_filter()) appearance_models.emplace(model);
    if (appearance_models.contains(model) && model_selections.emplace(model,library,variant,caller).second)
        std::fprintf(stderr,"[D2 appearance] model_select model=%08x library=%u variant=%u caller=%08x\n",
                     model,library,variant,caller);
}

namespace {
struct QueuedFace { uint32_t owner,slot,callback;unsigned cls; };
std::mutex queued_face_lock;
std::map<uint32_t,QueuedFace> queued_faces;
unsigned queued_face_class(uint64_t parameter)
{
    if(!readable(parameter,0x44)) return 0;
    std::lock_guard<std::mutex> lock(queued_face_lock);
    auto found=queued_faces.find(uint32_t(parameter));if(found==queued_faces.end()) return 0;
    const auto& link=found->second;
    if(!readable(link.owner,0x804) || !readable(link.slot,16) || !readable(link.callback,8)) return 0;
    unsigned count=vm_read16(link.owner+0x800);
    if(count>128 || link.slot<link.owner || link.slot>=link.owner+count*16 || (link.slot-link.owner)%16 ||
       vm_read32(parameter)!=link.owner || vm_read32(link.slot+8)!=parameter ||
       vm_read32(link.slot+4)!=link.callback || vm_read32(link.callback)!=0x001964C0 ||
       vm_read32(parameter+0x3C)>255 || !face_for_class(link.cls,0,vm_read32(parameter+0x38))[2]) return 0;
    return link.cls;
}
}
void func_0019E544(ppu_context* ctx)
{
    // The UI constructor receives a class ID in r9, then queues its original face ID.
    FaceClassScope scope(unsigned(ctx->gpr[9]));
    d2_appearance_original_class_queued_face(ctx);
}
void func_0019E6A8(ppu_context* ctx)
{
    FaceClassScope scope(unsigned(ctx->gpr[9]));
    d2_appearance_original_class_queued_face_alt(ctx);
}
void func_00193AC0(ppu_context* ctx)
{
    uint64_t owner=ctx->gpr[3],parameter=ctx->gpr[6],callback=ctx->gpr[5];unsigned cls=face_class;
    d2_appearance_original_ui_face_record(ctx);
    uint64_t slot=ctx->gpr[3];
    std::lock_guard<std::mutex> lock(queued_face_lock);
    // Every configuration invalidates an earlier association for the reused slot or data.
    for(auto i=queued_faces.begin();i!=queued_faces.end();) {
        if(i->first==parameter || i->second.slot==slot) i=queued_faces.erase(i);else ++i;
    }
    if(!D2_APPEARANCE_IMPORTER || !cls || cls>=32768 || !readable(owner,0x804) || !readable(parameter,0x44) ||
       !readable(slot,16) || !readable(callback,8)) return;
    unsigned count=vm_read16(owner+0x800);
    if(count>128 || slot<owner || slot>=owner+count*16 || (slot-owner)%16 ||
       vm_read32(slot+8)!=parameter || vm_read32(slot+4)!=callback || vm_read32(callback)!=0x001964C0) return;
    if(queued_faces.size()>=512) queued_faces.clear();
    queued_faces[uint32_t(parameter)]={uint32_t(owner),uint32_t(slot),uint32_t(callback),cls};
}
void func_001964C0(ppu_context* ctx)
{
    FaceScope unit_scope(0);
    FaceClassScope scope(queued_face_class(ctx->gpr[3]));
    d2_appearance_original_ui_face_draw(ctx);
}

void func_0015ACDC(ppu_context* ctx)
{
    FaceScope scope(ctx->gpr[9]);
    d2_appearance_original_unit_face(ctx);
}
void func_0015BBEC(ppu_context* ctx)
{
    FaceScope scope(ctx->gpr[9]);
    d2_appearance_original_unit_face_large(ctx);
}
void func_0015CCAC(ppu_context* ctx)
{
    // The panel receives the unit in r6; its nested glyph call receives only class ID.
    FaceScope scope(ctx->gpr[6]);
    d2_appearance_original_unit_panel_face(ctx);
}
void func_0007C11C(ppu_context* ctx)
{
    FaceScope scope(ctx->gpr[8]);
    d2_appearance_original_unit_list_face(ctx);
}
void func_0007C2E8(ppu_context* ctx)
{
    FaceScope scope(ctx->gpr[7]);
    d2_appearance_original_unit_list_face_alt(ctx);
}
void func_0007C550(ppu_context* ctx)
{
    FaceScope scope(ctx->gpr[7]);
    d2_appearance_original_unit_small_face(ctx);
}
void func_0007C680(ppu_context* ctx)
{
    FaceScope scope(ctx->gpr[7]);
    d2_appearance_original_unit_small_face_alt(ctx);
}
void func_00149E80(ppu_context* ctx)
{
    unsigned group=unsigned(ctx->gpr[3]),original=unsigned(ctx->gpr[4]),color=unsigned(ctx->gpr[5]),caller=unsigned(ctx->lr);
    uint64_t x=ctx->gpr[6],y=ctx->gpr[7];
    d2_appearance_original_face_coordinates(ctx);
    if(resource_filter() && readable(x,4) && readable(y,4)) {
        std::lock_guard<std::mutex> lock(trace_lock);
        if(face_lookups.emplace(uint32_t(face_unit),group,original,caller).second) {
            uint32_t bank=vm_read32(0x47DF98-0x47F0),texture=0;
            if(group<5 && readable(bank,20)) texture=vm_read32(bank+group*4);
            unsigned width=readable(texture,0x30)?vm_read16(texture+0x2C):0,height=readable(texture,0x30)?vm_read16(texture+0x2E):0;
            std::array<unsigned,4> parents{};uint64_t stack=ctx->gpr[1];
            for(unsigned i=0;i<parents.size();++i) {
                if(!readable(stack,8) || vm_read32(stack)) break;
                stack=vm_read32(stack+4);
                if(!readable(stack,24) || vm_read32(stack+16)) break;
                parents[i]=vm_read32(stack+20);
            }
            std::fprintf(stderr,"[D2 appearance] face_lookup unit=%08x face=%u group=%u texture=%08x size=%ux%u x=%u y=%u caller=%08x parents=%08x/%08x/%08x/%08x\n",
                uint32_t(face_unit),original,group,texture,width,height,vm_read32(x),vm_read32(y),caller,parents[0],parents[1],parents[2],parents[3]);
        }
    }
    auto cell=face_unit?face_for(face_unit,group,original):face_for_class(face_class,group,original);
    if(!cell[2] || !readable(x,4) || !readable(y,4) ||
       (x<face_unit+0x1A60 && x+4>face_unit) || (y<face_unit+0x1A60 && y+4>face_unit)) return;
    vm_write32(x,cell[0]);vm_write32(y,cell[1]);
    if(resource_filter()) {
        std::lock_guard<std::mutex> lock(trace_lock);
        if(face_routes.emplace(uint32_t(face_unit),original,color,cell[0],cell[1],caller).second)
            std::fprintf(stderr,"[D2 appearance] face_cell unit=%08x class=%u donor=%u resource=%u color=%u x=%u y=%u atlas=%ux%u caller=%08x\n",
                uint32_t(face_unit),face_class,original,cell[5],color,cell[0],cell[1],cell[2],cell[3],caller);
    }
}

void func_002E8D78(ppu_context* ctx)
{
    uint32_t model=uint32_t(ctx->gpr[3]);
    unsigned group=unsigned(ctx->gpr[4]),flags=unsigned(ctx->gpr[5]),resource=unsigned(ctx->gpr[6]),caller=unsigned(ctx->lr);
    if(resource_filter() && active_visual.resource) {
        std::lock_guard<std::mutex> lock(trace_lock);appearance_models.emplace(model);
    }
    d2_appearance_original_texture_bind(ctx);
    if (!resource_filter()) return;
    std::lock_guard<std::mutex> lock(trace_lock);
    // Separately loaded portrait/secondary resources need not pass through
    // the alternate-body constructor. Observe an explicitly filtered bind
    // without changing its model, resource, or original call arguments.
    if (resource==resource_filter()) appearance_models.emplace(model);
    if (appearance_models.contains(model) && texture_bindings.emplace(model,group,resource,caller).second)
        std::fprintf(stderr,"[D2 appearance] texture_bind model=%08x group=%u flags=%u resource=%u caller=%08x\n",
                     model,group,flags,resource,caller);
}

// Numeric body categories are hard-coded in the guest. During an authored
// visual constructor, inherit the donor category and shared motion library.
// The separate body resource still reaches the normal loader unchanged.
void func_00106E34(ppu_context* ctx)
{
    if (active_visual.resource && ctx->gpr[3]==active_visual.resource && ctx->lr==0x299D4)
        ctx->gpr[3]=active_visual.donor;
    d2_appearance_original_category(ctx);
}
void func_00106E84(ppu_context* ctx)
{
    if (active_visual.resource && ctx->gpr[3]==active_visual.resource && ctx->lr==0x299F0)
        ctx->gpr[3]=active_visual.donor;
    d2_appearance_original_body_kind(ctx);
}
void func_00016548(ppu_context* ctx)
{
    d2_appearance_original_motion(ctx);
    if (active_visual.resource && ctx->gpr[3]==active_visual.resource+4)
        ctx->gpr[3]=active_visual.donor+4;
}

void func_00181438(ppu_context* ctx)
{
    unsigned resource=unsigned(ctx->gpr[4]),caller=unsigned(ctx->lr);
    uint32_t manager=uint32_t(ctx->gpr[3]);
    if (resource_filter() && (resource==30 || resource==resource_filter())) {
        std::lock_guard<std::mutex> lock(trace_lock);
        if (requests.emplace(manager,resource,caller).second)
            std::fprintf(stderr,"[D2 appearance] request manager=%08x resource=%u caller=%08x\n",manager,resource,caller);
    }
    d2_appearance_original_request(ctx);
}

void func_00182F1C(ppu_context* ctx)
{
    unsigned filter=resource_filter(),caller=unsigned(ctx->lr);
    uint32_t manager=uint32_t(ctx->gpr[3]);
    uint64_t pointer=ctx->gpr[4];
    char name[64]={};
    if (filter && readable(pointer,sizeof(name))) {
        for (unsigned i=0;i<sizeof(name)-1;++i) {
            name[i]=char(vm_read8(pointer+i));
            if (!name[i]) break;
        }
    }
    d2_appearance_original_file_size(ctx);
    char expected[32];std::snprintf(expected,sizeof(expected),"anm%05u.lzs",filter);
    if (filter && std::string_view(name)==expected) {
        std::lock_guard<std::mutex> lock(trace_lock);
        if (file_sizes.emplace(manager,unsigned(ctx->gpr[3]),caller).second)
            std::fprintf(stderr,"[D2 appearance] file_size manager=%08x name=%s bytes=%d caller=%08x\n",
                         manager,name,int32_t(ctx->gpr[3]),caller);
    }
}

void func_00166CB4(ppu_context* ctx)
{
    unsigned caller=unsigned(ctx->lr),size=unsigned(ctx->gpr[3]);
    uint64_t descriptor=ctx->gpr[29];
    bool target=resource_filter() && caller==0x181CC4 && readable(descriptor,36) &&
                vm_read16(descriptor)==resource_filter();
    d2_appearance_original_allocate(ctx);
    if (target) {
        std::lock_guard<std::mutex> lock(trace_lock);
        if (allocations.emplace(size,uint32_t(ctx->gpr[3])).second)
            std::fprintf(stderr,"[D2 appearance] allocate bytes=%u result=%08x caller=%08x\n",
                         size,uint32_t(ctx->gpr[3]),caller);
    }
}

void func_00183084(ppu_context* ctx)
{
    unsigned filter=resource_filter(),caller=unsigned(ctx->lr),bytes=unsigned(ctx->gpr[6]);
    uint32_t destination=uint32_t(ctx->gpr[5]);
    uint64_t pointer=ctx->gpr[4];char name[64]={};
    if (filter && readable(pointer,sizeof(name))) {
        for (unsigned i=0;i<sizeof(name)-1;++i) {
            name[i]=char(vm_read8(pointer+i));if (!name[i]) break;
        }
    }
    d2_appearance_original_file_read(ctx);
    char expected[32];std::snprintf(expected,sizeof(expected),"anm%05u.lzs",filter);
    if (filter && std::string_view(name)==expected) {
        std::lock_guard<std::mutex> lock(trace_lock);
        if (file_reads.emplace(destination,unsigned(ctx->gpr[3]),caller).second)
            std::fprintf(stderr,"[D2 appearance] file_read name=%s bytes=%u destination=%08x result=%d caller=%08x\n",
                         name,bytes,destination,int32_t(ctx->gpr[3]),caller);
    }
}

void func_00015E18(ppu_context* ctx)
{
    const uint64_t unit=ctx->gpr[3];
    const unsigned caller=unsigned(ctx->lr);
    d2_appearance_original_record(ctx);
    const uint64_t record=ctx->gpr[3];
    if (!resource_filter() || !readable(record,676)) return;
    const unsigned identity=vm_read16(record+0x194);
    if (identity!=30) return;
    const unsigned primary=vm_read16(record+0x1BC),alternate=vm_read16(record+0x1BE);
    std::lock_guard<std::mutex> lock(trace_lock);
    if (records.emplace(uint32_t(record),primary,alternate).second)
        std::fprintf(stderr,"[D2 appearance] record=%08x unit=%08x class=%u primary=%u alternate=%u caller=%08x\n",
                     uint32_t(record),uint32_t(unit),identity,primary,alternate,caller);
}

void func_00015A98(ppu_context* ctx)
{
    uint64_t unit=ctx->gpr[3];
    unsigned index=unsigned(ctx->gpr[4]),body=unsigned(ctx->gpr[5]),caller=unsigned(ctx->lr);
    unsigned alternate=alternate_body(unit,index);
    if (alternate) ctx->gpr[5]=body=alternate;
    d2_appearance_original_write_body(ctx);
    trace_body(unit,index,body,caller,true);
}

void func_00015AB0(ppu_context* ctx)
{
    uint64_t unit=ctx->gpr[3];
    unsigned index=unsigned(ctx->gpr[4]),caller=unsigned(ctx->lr);
    d2_appearance_original_read_body(ctx);
    unsigned alternate=alternate_body(unit,index);
    if (alternate) ctx->gpr[3]=alternate;
    trace_body(unit,index,unsigned(ctx->gpr[3]),caller,false);
}

void func_00109E44(ppu_context* ctx)
{
    const uint64_t unit = ctx->gpr[3], output = ctx->gpr[4];
    d2_appearance_original_select(ctx);
    if (!resource_filter() || !readable(unit,0x11FE) || !readable(output,4)) return;
    const unsigned body = vm_read16(output), identity = vm_read16(unit+0x1158);
    const unsigned selector = vm_read8(unit+0x117A);
    if (body != resource_filter() && identity != 30) return;
    std::lock_guard<std::mutex> lock(trace_lock);
    if (selections.emplace(uint32_t(unit),selector,body).second)
        std::fprintf(stderr,"[D2 appearance] select unit=%08x class=%u selector=%u family=%u stored_body=%u body=%u secondary=%u\n",
                     uint32_t(unit),identity,selector,unsigned(vm_read16(unit+0x11FC)),
                     unsigned(vm_read16(unit+0x11D8)),body,unsigned(vm_read16(output+2)));
}

void func_00181728(ppu_context* ctx)
{
    const uint64_t manager = ctx->gpr[3];
    d2_appearance_original_update(ctx);
    trace_manager(manager);
}

void func_00181B78(ppu_context* ctx)
{
    const uint64_t manager=ctx->gpr[3];
    d2_appearance_original_load_update(ctx);
    trace_manager(manager);
}

namespace {
void trace_manager(uint64_t manager)
{
    if (!resource_filter() || !readable(manager,24)) return;
    const uint32_t bank = vm_read32(manager), count = vm_read32(manager+0x10);
    {
        std::lock_guard<std::mutex> lock(trace_lock);
        if (managers.emplace(uint32_t(manager)).second)
            std::fprintf(stderr,"[D2 appearance] bank manager=%08x descriptors=%08x capacity=%u enabled=%u mode=%u\n",
                         uint32_t(manager),bank,count,unsigned(vm_read8(manager+4)),unsigned(vm_read8(manager+5)));
    }
    if (!count || count > 1047 || !readable(bank,count*36)) return;
    for (unsigned i=0;i<count;++i) {
        const uint32_t descriptor = bank+i*36;
        const unsigned id = vm_read16(descriptor), state = vm_read8(descriptor+0x10);
        if (!state || (id != resource_filter() && id != 30)) continue;
        std::lock_guard<std::mutex> lock(trace_lock);
        if (states.emplace(uint32_t(manager),id,state).second)
            std::fprintf(stderr,"[D2 appearance] manager=%08x slot=%u resource=%u state=%u refs=%u ptr8=%08x ptr14=%08x file_size=%d\n",
                         uint32_t(manager),i,id,state,unsigned(vm_read16(descriptor+2)),
                         vm_read32(descriptor+8),vm_read32(descriptor+0x14),int32_t(vm_read32(descriptor+0xc)));
    }
}
}

#if D2_APPEARANCE_IMPORTER
#include "d2_appearance_persist.inc"
#include "d2_appearance_live.inc"
#endif
