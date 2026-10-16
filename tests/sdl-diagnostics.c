// TEMPORARY investigation regression: exercise the actual patched SDL event queue.
#include <SDL3/SDL.h>
#include <stdio.h>
#include <pthread.h>
#include <stdint.h>
#include <string.h>

extern void SDL_GXSetInputDiagnosticsEnabled(bool enabled);
extern void SDL_GXGetInputDiagnostics(Uint32 out[13]);

enum { PUSH, FILTERED, ENQUEUED, FAILED, FULL, ALLOCATION, INACTIVE, POLLS, SENTINELS, ACTIVE, QUEUED, HAS_HEAD, HAS_TAIL };
static int failures;
static void check(bool ok, const char *message)
{
    printf("%s %s\n", ok ? "PASS" : "FAIL", message);
    if (!ok) ++failures;
}
static bool SDLCALL reject(void *userdata, SDL_Event *event)
{
    (void)userdata;
    (void)event;
    return false;
}
static SDL_Event user_event(void)
{
    SDL_Event event;
    SDL_zero(event);
    event.type = SDL_EVENT_USER;
    return event;
}
static int SDLCALL produce(void *userdata)
{
    const int count = *(int *)userdata;
    for (int i = 0; i < count; ++i) {
        SDL_Event event = user_event();
        event.user.code = i;
        if (!SDL_PushEvent(&event)) return 1;
    }
    return 0;
}

#ifdef GX_TEST_RAW_PTHREAD_STRESS
static SDL_AtomicInt raw_done;
static void *raw_produce(void *userdata)
{
    const int result = produce(userdata);
    SDL_SetAtomicInt(&raw_done, 1);
    return (void *)(intptr_t)result;
}
static int raw_stress(void)
{
    const int rounds = 128;
    int count = 4096, total = 0, inconsistent = 0;
    bool valid = true;
    const Uint64 deadline = SDL_GetTicks() + 15000;
    for (int round = 0; round < rounds && valid; ++round) {
        pthread_t thread;
        SDL_SetAtomicInt(&raw_done, 0);
        if (pthread_create(&thread, NULL, raw_produce, &count) != 0) {
            check(false, "raw pthread stress producer starts");
            return 1;
        }
        int consumed = 0;
        while (consumed < count && SDL_GetTicks() < deadline) {
            const bool done = SDL_GetAtomicInt(&raw_done) != 0;
            SDL_Event received;
            if (SDL_PollEvent(&received)) {
                if (received.type != SDL_EVENT_USER || received.user.code != consumed) valid = false;
                ++consumed;
            } else if (done) {
                break;
            }
        }
        void *result = NULL;
        pthread_join(thread, &result);
        Uint32 sample[13] = {0};
        SDL_GXGetInputDiagnostics(sample);
        const bool empty = sample[QUEUED] == 0 && sample[HAS_HEAD] == 0 && sample[HAS_TAIL] == 0;
        if (!empty) ++inconsistent;
        if (result != NULL || consumed != count || !empty) {
            fprintf(stderr, "stress round=%d consumed=%d/%d count=%u head=%u tail=%u\n",
                    round, consumed, count, sample[QUEUED], sample[HAS_HEAD], sample[HAS_TAIL]);
            valid = false;
        }
        total += consumed;
    }
    printf("Raw pthread stress: consumed=%d expected=%d inconsistent=%d\n", total, rounds * count, inconsistent);
    check(valid && total == rounds * count, "concurrent raw pthread queue preserves sequence, totals and empty invariants");
    // A broken baseline queue may have corrupt links; do not traverse them on cleanup.
    if (valid) SDL_Quit();
    return valid ? 0 : 1;
}
#endif

int main(void)
{
    Uint32 before[13] = {0}, after[13] = {0};
    SDL_Event event, received;
    SDL_SetHint(SDL_HINT_POLL_SENTINEL, "0");
    check(SDL_Init(SDL_INIT_EVENTS), "events initialize without video");
    if (failures) return 1;
    SDL_FlushEvents(SDL_EVENT_FIRST, SDL_EVENT_LAST);
    SDL_GXSetInputDiagnosticsEnabled(true);
#ifdef GX_TEST_RAW_PTHREAD_STRESS
    return raw_stress();
#endif
    SDL_GXGetInputDiagnostics(before);
    check(before[ACTIVE] == 1, "active gauge reflects initialized queue");

    event = user_event();
    check(SDL_PushEvent(&event), "push succeeds");
    check(SDL_PollEvent(&received) && received.type == SDL_EVENT_USER, "poll returns pushed event unchanged");
    SDL_GXGetInputDiagnostics(after);
    check(after[PUSH] == before[PUSH] + 1 && after[ENQUEUED] == before[ENQUEUED] + 1 &&
          after[POLLS] == before[POLLS] + 1 && after[FAILED] == before[FAILED], "successful pipeline exact counter deltas");

    SDL_SetEventFilter(reject, NULL);
    SDL_GXGetInputDiagnostics(before);
    event = user_event();
    check(!SDL_PushEvent(&event), "filter rejection remains false");
    SDL_GXGetInputDiagnostics(after);
    check(after[PUSH] == before[PUSH] + 1 && after[FILTERED] == before[FILTERED] + 1 &&
          after[ENQUEUED] == before[ENQUEUED] && after[FAILED] == before[FAILED], "filter rejection is distinct from enqueue failure");
    SDL_SetEventFilter(NULL, NULL);

    SDL_FlushEvents(SDL_EVENT_FIRST, SDL_EVENT_LAST);
    SDL_GXGetInputDiagnostics(before);
    int queued = 0;
    for (int i = 0; i < 65535; ++i) {
        event = user_event();
        if (!SDL_PushEvent(&event)) break;
        ++queued;
    }
    check(queued == 65535, "retail SDL queue capacity remains 65535");
    event = user_event();
    check(!SDL_PushEvent(&event), "full queue push remains false");
    SDL_GXGetInputDiagnostics(after);
    check(after[PUSH] == before[PUSH] + 65536 && after[ENQUEUED] == before[ENQUEUED] + 65535 &&
          after[FULL] == before[FULL] + 1 && after[FAILED] == before[FAILED] + 1 &&
          after[ALLOCATION] == before[ALLOCATION], "full queue distinguishes capacity from allocation failure");
    SDL_FlushEvents(SDL_EVENT_FIRST, SDL_EVENT_LAST);

    SDL_GXSetInputDiagnosticsEnabled(false);
    SDL_GXGetInputDiagnostics(before);
    event = user_event();
    check(SDL_PushEvent(&event) && SDL_PollEvent(&received), "runtime-disabled probes preserve queue behavior");
    SDL_GXGetInputDiagnostics(after);
    check(memcmp(before, after, 8 * sizeof(Uint32)) == 0, "runtime-disabled cumulative counters do not advance");
    SDL_GXSetInputDiagnosticsEnabled(true);

    int count = 4096, result = -1, consumed = 0;
    bool monotonic = true, ordered = true;
    Uint32 previous[13] = {0};
    SDL_GXGetInputDiagnostics(before);
    memcpy(previous, before, sizeof(previous));
    SDL_Thread *thread = SDL_CreateThread(produce, "diagnostic-events", &count);
    check(thread != NULL, "event producer thread starts");
    if (!thread) fprintf(stderr, "SDL_CreateThread: %s\n", SDL_GetError());
    if (thread) {
        const Uint64 deadline = SDL_GetTicks() + 10000;
        while (consumed < count && SDL_GetTicks() < deadline) {
            if (SDL_PollEvent(&received) && received.type == SDL_EVENT_USER) {
                if (received.user.code != consumed) ordered = false;
                ++consumed;
            }
            SDL_GXGetInputDiagnostics(after);
            for (int i = 0; i < 8; ++i) if (after[i] < previous[i]) monotonic = false;
            memcpy(previous, after, sizeof(previous));
        }
        SDL_WaitThread(thread, &result);
        SDL_GXGetInputDiagnostics(after);
        check(result == 0 && consumed == count && ordered, "concurrent producer/consumer delivers every event once in order");
        check(monotonic && after[PUSH] == before[PUSH] + count && after[ENQUEUED] == before[ENQUEUED] + count &&
              after[FAILED] == before[FAILED], "cross-thread atomic counters are monotonic with exact totals");
    }

    SDL_Quit();
    SDL_GXGetInputDiagnostics(before);
    check(before[ACTIVE] == 0 && before[SENTINELS] == 0, "shutdown gauges reflect inactive empty queue");
    event = user_event();
    check(!SDL_PushEvent(&event), "inactive queue push remains false");
    SDL_GXGetInputDiagnostics(after);
    check(after[PUSH] == before[PUSH] + 1 && after[FAILED] == before[FAILED] + 1 &&
          after[INACTIVE] == before[INACTIVE] + 1 && after[ENQUEUED] == before[ENQUEUED], "shutdown enqueue failure is tracked separately");
    SDL_GXSetInputDiagnosticsEnabled(false);
    printf("SDL diagnostics regression: %d failure(s)\n", failures);
    return failures ? 1 : 0;
}
