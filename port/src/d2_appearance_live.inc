/* Included by the importer implementation; registry helpers remain private. */
namespace {
std::mutex live_lock;
D2AppearanceSnapshot published_live={};
struct LiveRequest { unsigned cls;std::string token;uint64_t generation; };
std::optional<LiveRequest> pending_live;
using LiveKey=std::tuple<uint32_t,uint32_t,uint32_t,uint32_t,uint32_t,unsigned,unsigned,bool,uint64_t>;
LiveKey live_key={};
uint64_t live_generation=0,live_serial=0;
bool refresh_failed=false;
const char* live_status="Choose a costume in the castle. Changes last for this session.";
uint64_t native_call(unsigned address,uint64_t actor=0)
{
    return ppu_guest_call_ct(address,0x47DF98,actor,0,0,0,0,0,0,0);
}
uint32_t controlled_unit(uint32_t party,uint32_t control)
{
    if (!readable(party,0x1507EE) || !readable(control,0x150AA8)) return 0;
    unsigned count=vm_read16(party+0x1507EC),identity=vm_read16(control+0x150AA6);
    if (!identity || identity>=32768 || count<1 || count>128 || !readable(party+0x598,count*0x1A60)) return 0;
    uint32_t result=0;
    for(unsigned i=0;i<count;++i) {
        uint32_t unit=party+0x598+i*0x1A60;
        if(vm_read16(unit+0x1202)!=identity) continue;
        if(result) return 0;
        result=unit;
    }
    return result;
}
bool live_donor_valid(uint32_t unit,unsigned cls)
{
    if(!readable(unit,0x1A60)) return false;
    uint32_t manager=vm_read32(0x47DF98-0x7E68);
    if(!readable(manager,8)) return false;
    unsigned count=vm_read16(manager),row=vm_read16(unit+0x115C);
    uint32_t table=vm_read32(manager+4);
    return row<count && readable(table,count*676) && vm_read16(table+row*676+0x194)==cls;
}
bool live_visual_valid(const Binding& candidate)
{
    uint32_t manager=vm_read32(0x47DF98-0x7E68);
    if(!readable(manager,8)) return false;
    unsigned count=vm_read16(manager);uint32_t table=vm_read32(manager+4);
    if(!readable(table,count*676)) return false;
    for(unsigned i=0;i<count;++i) {
        uint32_t row=table+i*676;
        if(vm_read16(row+0x194)==candidate.visual_class &&
           vm_read16(row+0x196)==candidate.resource && vm_read16(row+0x1BC)==candidate.resource) return true;
    }
    return false;
}
void build_live_choices(D2AppearanceSnapshot& out,unsigned cls,const Binding& active)
{
    out.count=1;
    std::snprintf(out.choices[0].label,sizeof out.choices[0].label,"Original");
    auto& value=registry();std::lock_guard<std::mutex> hold(value.lock);
    for(const auto& [key,binding]:value.state.costumes) {
        if(key.first!=cls || out.count>=D2_APPEARANCE_MAX_CHOICES) continue;
        auto& choice=out.choices[out.count];
        std::snprintf(choice.token,sizeof choice.token,"%s",key.second.c_str());
        std::string label=value.state.labels.at(key);
        if(label.empty()) label="Costume "+std::to_string(out.count);
        std::snprintf(choice.label,sizeof choice.label,"%s",label.c_str());
        if(active.enabled && active.resource==binding.resource && active.visual_class==binding.visual_class) out.active=out.count;
        ++out.count;
    }
}
}
extern "C" void d2_appearance_snapshot(D2AppearanceSnapshot* out)
{
    if(!out) return;
    std::lock_guard<std::mutex> hold(live_lock);*out=published_live;
}
extern "C" int d2_appearance_request(unsigned cls,const char* token,uint64_t generation)
{
    if(!token || std::strlen(token)>64) return 0;
    std::lock_guard<std::mutex> hold(live_lock);
    if(pending_live || !published_live.ready || published_live.class_id!=cls || published_live.generation!=generation) return 0;
    bool found=false;
    for(unsigned i=0;i<published_live.count;++i) if(std::string_view(token)==published_live.choices[i].token) found=true;
    if(!found) return 0;
    pending_live=LiveRequest{cls,token,generation};return 1;
}
extern "C" void d2_appearance_frame(void* context,int save_ready)
{
    auto* ctx=static_cast<ppu_context*>(context);
    if(!ctx || ctx->thread_id!=1) return;
    if(live_serial==0 && persistent_choices()) live_status="Choose a costume in the castle. Your choice will be remembered.";
    uint32_t party=vm_read32(0x47DF98-0x4F48),control=vm_read32(0x47DF98-0x7CA4);
    uint32_t scene=vm_read32(0x47DF98-0x3FC4),event=vm_read32(0x47DF98-0x37C8);
    uint32_t actor=vm_read32(0x47DF98-0xFC0),unit=0,camera=vm_read32(0x47DF98-0x3794);
    unsigned cls=0,map=0;
    bool ready=save_ready && !refresh_failed && readable(party,0xD3BBC) && readable(scene,12) &&
        readable(event,0x13318) && readable(actor,0x3F0) && readable(camera,0x1F08);
    if(ready) {
        map=vm_read16(party+0xD3BBA);
        ready=map/100==300 && vm_read32(scene+8)==12 && vm_read32(event+0x13314)==0;
    }
    if(ready) {
        unit=controlled_unit(party,control);
        cls=unit?vm_read16(unit+0x1158):0;
        auto binding=binding_for(cls);
        unsigned actor_cls=vm_read16(actor+0x21C);
        ready=!uses_color_slots(cls) && binding && binding->renderer_only && live_donor_valid(unit,cls) && vm_read32(actor+0x3D8)==2 &&
            vm_read32(actor+0x1A4)!=0 && (actor_cls==cls || actor_cls==binding->visual_class);
        if(ready && native_call(0x00033C48)) ready=false;
    }
    auto key=LiveKey{party,control,actor,unit,camera,cls,map,ready,binding_generation()};
    if(key!=live_key) {live_key=key;++live_generation;}
    std::optional<LiveRequest> request;
    {std::lock_guard<std::mutex> hold(live_lock);request=std::move(pending_live);pending_live.reset();}
    if(request) {
        bool accepted=ready && request->generation==live_generation && request->cls==cls;
        Binding candidate={};uint64_t version=binding_generation();
        if(accepted) {
            auto& value=registry();std::lock_guard<std::mutex> hold(value.lock);
            candidate=value.state.active.at(cls);
            if(request->token.empty()) candidate.enabled=false;
            else {
                auto found=value.state.costumes.find({cls,request->token});
                accepted=found!=value.state.costumes.end();
                if(accepted) {candidate=found->second;candidate.enabled=true;}
            }
        }
        if(accepted && candidate.enabled) accepted=live_visual_valid(candidate);
        if(!accepted || !select_session_costume(cls,request->token,version)) live_status="Costume request expired or is unavailable. Open Appearance again.";
        else {
            uint32_t camera_x=vm_read32(camera+0x1F00),camera_z=vm_read32(camera+0x1F04);
            uint32_t position[4];for(unsigned i=0;i<4;++i) position[i]=vm_read32(actor+4+i*4);
            uint8_t saved_unit[0x1A60];for(unsigned i=0;i<sizeof saved_unit;++i) saved_unit[i]=vm_read8(unit+i);
            native_call(0x000E849C,actor);native_call(0x000E83BC,actor);
            bool position_same=true,unit_same=true;
            for(unsigned i=0;i<4;++i) position_same &= position[i]==vm_read32(actor+4+i*4);
            for(unsigned i=0;i<sizeof saved_unit;++i) unit_same &= saved_unit[i]==vm_read8(unit+i);
            bool camera_same=camera_x==vm_read32(camera+0x1F00) && camera_z==vm_read32(camera+0x1F04);
            refresh_failed=!position_same || !unit_same || !camera_same;
            live_status=refresh_failed?"Refresh changed protected state; further switching is disabled.":"Costume changed for this session.";
            std::fprintf(stderr,"[D2 appearance live] class=%u costume=%s actor=%08x unit=%08x position_same=%u unit_same=%u camera_same=%u model=%08x\n",
                cls,request->token.empty()?"original":request->token.c_str(),actor,unit,position_same,unit_same,camera_same,vm_read32(actor+0x1A4));
            if(!refresh_failed && persistent_choices())
                live_status=persist_choice(cls,request->token)?"Costume changed and remembered for the next launch.":
                    "Costume changed for this session; next-launch choice could not be updated.";
            ready &= !refresh_failed;++live_generation;
            live_key=LiveKey{party,control,actor,unit,camera,cls,map,ready,binding_generation()};
        }
    }
    D2AppearanceSnapshot out={};out.serial=++live_serial;out.generation=live_generation;out.class_id=cls;out.ready=ready;
    if(unit) for(unsigned i=0;i<48;++i) {unsigned c=vm_read8(unit+0x650+i);if(!c) break;out.character[i]=c>=32 && c<127?char(c):'?';}
    if(auto binding=binding_for(cls)) build_live_choices(out,cls,*binding);
    out.ready &= out.count>1;
    std::snprintf(out.status,sizeof out.status,"%s",(ready || refresh_failed)?live_status:"Appearance switching is available in the castle after loading and messages finish.");
    {std::lock_guard<std::mutex> hold(live_lock);published_live=out;}
}
