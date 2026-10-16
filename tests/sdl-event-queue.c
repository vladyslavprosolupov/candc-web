// Public SDL regression: browser callbacks and the game worker share this queue.
#include <SDL3/SDL.h>
#include <pthread.h>
#include <stdint.h>
#include <stdio.h>

typedef struct Producer {
    int count;
    SDL_AtomicInt done;
} Producer;

static int push_events(Producer *producer)
{
    for (int sequence = 0; sequence < producer->count; ++sequence) {
        SDL_Event event;
        SDL_zero(event);
        event.type = SDL_EVENT_USER;
        event.user.code = sequence;
        if (!SDL_PushEvent(&event)) {
            SDL_SetAtomicInt(&producer->done, 1);
            return 1;
        }
    }
    SDL_SetAtomicInt(&producer->done, 1);
    return 0;
}
static int SDLCALL sdl_produce(void *userdata)
{
    return push_events((Producer *)userdata);
}
static void *raw_produce(void *userdata)
{
    return (void *)(intptr_t)push_events((Producer *)userdata);
}

static bool exercise_queue(bool raw, int rounds)
{
    const int batch = 4096; // Far below SDL's queue capacity, even before consumption.
    int total = 0;
    const Uint64 deadline = SDL_GetTicks() + 15000;
    for (int round = 0; round < rounds; ++round) {
        Producer producer = {.count = batch};
        pthread_t pthread;
        SDL_Thread *thread = NULL;
        if (raw) {
            if (pthread_create(&pthread, NULL, raw_produce, &producer) != 0) {
                fprintf(stderr, "FAIL raw pthread creation\n");
                return false;
            }
        } else {
            thread = SDL_CreateThread(sdl_produce, "event-queue-regression", &producer);
            if (!thread) {
                fprintf(stderr, "FAIL SDL_CreateThread: %s\n", SDL_GetError());
                return false;
            }
        }
        int consumed = 0;
        bool ordered = true;
        while (consumed < batch && SDL_GetTicks() < deadline) {
            // Read before polling: done=true guarantees the producer cannot add
            // a final event immediately after this poll returns empty.
            const bool done = SDL_GetAtomicInt(&producer.done) != 0;
            SDL_Event received;
            if (SDL_PollEvent(&received)) {
                if (received.type != SDL_EVENT_USER || received.user.code != consumed) ordered = false;
                ++consumed;
            } else if (done) {
                break;
            }
        }
        int result;
        if (raw) {
            void *status = NULL;
            pthread_join(pthread, &status);
            result = (int)(intptr_t)status;
        } else {
            SDL_WaitThread(thread, &result);
        }
        // Public API only: after the producer joins, there must be no events.
        const int remaining = SDL_PeepEvents(NULL, 0, SDL_PEEKEVENT, SDL_EVENT_FIRST, SDL_EVENT_LAST);
        total += consumed;
        if (result != 0 || consumed != batch || !ordered || remaining != 0) {
            fprintf(stderr, "FAIL %s round=%d consumed=%d/%d ordered=%d remaining=%d producer=%d\n",
                    raw ? "pthread" : "SDL", round, consumed, batch, ordered, remaining, result);
            return false;
        }
    }
    printf("PASS %s queue: %d/%d ordered events, empty after every batch\n",
           raw ? "raw pthread" : "SDL thread", total, rounds * batch);
    return true;
}
int main(void)
{
    SDL_SetHint(SDL_HINT_POLL_SENTINEL, "0");
    if (!SDL_Init(SDL_INIT_EVENTS)) {
        fprintf(stderr, "FAIL SDL_Init: %s\n", SDL_GetError());
        return 1;
    }
    SDL_FlushEvents(SDL_EVENT_FIRST, SDL_EVENT_LAST);
#ifndef GX_QUEUE_RAW_ONLY
    if (!exercise_queue(false, 1)) return 1;
#endif
    if (!exercise_queue(true, 128)) return 1;
    SDL_Quit();
    return 0;
}
