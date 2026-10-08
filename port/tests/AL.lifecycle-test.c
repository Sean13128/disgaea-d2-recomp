/* Deferred stop reaches polling and blocking workers, without leaving CV locks held. */
#include "runtime/platform/guest_poll.h"
#include "runtime/platform/thread_lifecycle.h"
#include <assert.h>
#include <stdatomic.h>
#include <stdio.h>
#include <stdlib.h>
#include <unistd.h>
uint8_t* vm_base;
extern void ps3_guest_workers_request_stop(void);
extern int ps3_guest_workers_stopped(void);
extern void ps3_guest_workers_join(void);
static pthread_mutex_t lock = PTHREAD_MUTEX_INITIALIZER;
static pthread_cond_t cv = PTHREAD_COND_INITIALIZER;
static atomic_uint ready;
static void* waiter(void* arg)
{
    ps3_guest_worker_register(arg == NULL);
    ps3_poll_thread_start("AL blocking worker", 0);
    pthread_mutex_lock(&lock); ready++;
    for (;;) pthread_cond_wait(&cv, &lock);
    return arg;
}
static void* poller(void* arg)
{
    ps3_guest_worker_register(1);
    ps3_poll_thread_start("AL polling worker", 0); ready++;
    for (;;) ps3_poll_backoff(40, 0, vm_base, 4);
    return arg;
}
static void* joiner(void* arg)
{
    ps3_guest_worker_register(1);
    ps3_poll_thread_start("AL guest join owner", 0);
    /* Like sys_ppu_thread_join, join only a registered target; an unregistered one stays joinable for shutdown. */
    while (ready != 6) usleep(1000);
    ready++;
    ps3_guest_worker_join(*(pthread_t*)arg);
    return NULL;
}
int main(void)
{
    vm_base = calloc(1, 4096);
    pthread_t threads[7];
    for (unsigned i=0; i<4; i++) assert(!pthread_create(&threads[i], NULL, waiter, NULL));
    assert(!pthread_create(&threads[4], NULL, poller, NULL));
    pthread_attr_t attr; pthread_attr_init(&attr);
    pthread_attr_setdetachstate(&attr, PTHREAD_CREATE_DETACHED);
    assert(!pthread_create(&threads[5], &attr, waiter, (void*)1));
    pthread_attr_destroy(&attr);
    assert(!pthread_create(&threads[6], NULL, joiner, &threads[4]));
    while (ready != 7) usleep(1000);
    ps3_guest_workers_request_stop();
    for (unsigned i=0; i<5000 && !ps3_guest_workers_stopped(); i++) usleep(1000);
    assert(ps3_guest_workers_stopped());
    ps3_guest_workers_join();
    assert(!pthread_mutex_trylock(&lock)); pthread_mutex_unlock(&lock);
    free(vm_base);
    puts("[AL-lifecycle] polling + shared-CV workers joined, cancelled guest join, detached worker rendezvous, mutex released: PASS");
    return 0;
}
