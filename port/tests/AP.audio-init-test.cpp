#include "../src/d2_audio.cpp"
#include <atomic>
#include <cassert>
static std::atomic<uint64_t> published;
static std::atomic<bool> ready;
static uint64_t registered_key;
extern "C" uint64_t vm_read64(uint64_t ea)
{ assert(ea==0x10500); return published.load(); }
extern "C" uint32_t sys_event_find_queue_by_key(uint64_t key)
{ return ready && key==0x8000CAFE02460300ULL ? 3 : 0; }
extern "C" int32_t cellAudioSetNotifyEventQueue(uint64_t key)
{ registered_key=key; return key ? 0 : CELL_AUDIO_ERROR_EVENT_QUEUE; }
extern "C" void ps3_hle_register_ctx(uint32_t n, const char*, void (*f)(ppu_context*))
{ assert(n==0x377E0CD9 && f==notify_queue); }
void func_00308234(ppu_context*) {}
extern "C" void ppu_register_function(uint64_t, void (*)(ppu_context*)) {}
int main()
{
    d2_register_audio();
    ppu_context ctx{}; ctx.lr=0x306514; ctx.gpr[30]=0x10000;
    std::thread publisher([] {
        std::this_thread::sleep_for(std::chrono::milliseconds(20));
        published=0x8000CAFE02460300ULL;
        std::this_thread::sleep_for(std::chrono::milliseconds(20)); ready=true;
    });
    notify_queue(&ctx); publisher.join();
    assert(ctx.gpr[3]==0 && registered_key==published);
    ctx.gpr[3]=published; notify_queue(&ctx); assert(ctx.gpr[3]==0);
    ctx.lr=0; ctx.gpr[3]=0; notify_queue(&ctx);
    assert(ctx.gpr[3]==(uint32_t)CELL_AUDIO_ERROR_EVENT_QUEUE);
    puts("[AP audio init] late queue key + late queue creation, normal path, unrelated zero key: PASS");
}
