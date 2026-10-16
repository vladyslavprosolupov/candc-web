// Compile the production cache implementation; only file decoding/WebAudio are fixtures.
#include "OpenALAudioCache.h"
#include "OpenALBufferLease.h"
#include "Common/AudioEventRTS.h"
#include "Common/FileSystem.h"
#include <emscripten.h>
#include <cstdio>
#include <list>
#include <unordered_map>

unsigned int fixtureEncodedBytes = 8;
unsigned int fixtureSamples = 128;
unsigned int fixtureChannels = 2;
unsigned int fixtureBytesPerSample = 2;
static FixtureFileSystem filesystem;
FixtureFileSystem *TheFileSystem = &filesystem;
static OpenALAudioManager manager;
OpenALAudioManager *TheAudio = &manager;
static int failures = 0, stops = 0;
static void check(bool ok, const char *message) {
    printf("%s %s\n", ok ? "PASS" : "FAIL", message);
    if (!ok) ++failures;
}
class Cache : public OpenALAudioFileCache {
public:
    void budget(unsigned int bytes) { m_maxSize = bytes; }
    unsigned int leases(ALuint buffer) const {
        for (const auto &item : m_openFiles) if (item.second.m_buffer == buffer) return item.second.m_openCount;
        return 0;
    }
    bool owns(ALuint buffer) const {
        for (const auto &item : m_openFiles) if (item.second.m_buffer == buffer) return true;
        return false;
    }
    bool decoderAlive(ALuint buffer) const {
        for (const auto &item : m_openFiles) if (item.second.m_buffer == buffer) return item.second.m_ffmpegFile != nullptr;
        return false;
    }
    size_t entries() const { return m_openFiles.size(); }
};
static Cache *currentCache;
static std::unordered_map<ALuint, ALuint> tracked;
static ALuint source(ALuint buffer, bool track = true) {
    ALuint handle = 0;
    alGenSources(1, &handle);
    alSourcei(handle, AL_BUFFER, buffer);
    if (track) tracked[buffer] = handle;
    return handle;
}
void OpenALAudioManager::closeAnySamplesUsingFile(const void *value) {
    ++stops;
    const ALuint buffer = (ALuint)(uintptr_t)value;
    auto item = tracked.find(buffer);
    if (item != tracked.end()) {
        ALuint handle = item->second;
        alDeleteSources(1, &handle);
        tracked.erase(item);
        currentCache->closeBuffer(buffer);
    }
}
static void detach(ALuint buffer) {
    auto item = tracked.find(buffer);
    if (item != tracked.end()) {
        ALuint handle = item->second;
        alDeleteSources(1, &handle);
        tracked.erase(item);
    }
}
static int liveBuffers() {
    return EM_ASM_INT({ return Object.values(AL.buffers).filter(b => b && b.id !== 0).length; });
}
static int liveBytes() {
    return EM_ASM_INT({ return Object.values(AL.buffers).reduce((n,b) => n + (b?.audioBuf ? b.audioBuf.length * b.audioBuf.numberOfChannels * 4 : 0), 0); });
}

static void leases() {
    AudioEventRTS event("leases", 1);
    Cache cache; currentCache = &cache;
    ALuint first = cache.getBufferForFile(OpenFileInfo(&event));
    check(first && cache.leases(first) == 1, "cache miss owns one playback lease");
    ALuint second = cache.getBufferForFile(OpenFileInfo(&event));
    check(second == first && cache.leases(first) == 2, "cache hit owns a second lease");
    cache.closeBuffer(first);
    check(cache.leases(first) == 1, "first close leaves the other lease active");
    cache.closeBuffer(second);
    check(cache.leases(first) == 0, "second close reaches zero without unsigned underflow");
    cache.closeBuffer(first);
    check(cache.leases(first) == 0, "unmatched close cannot underflow zero leases");
}
static void activeEviction() {
    AudioEventRTS low("active-low", 1), high("active-high", 2);
    Cache cache; currentCache = &cache;
    ALuint a = cache.getBufferForFile(OpenFileInfo(&low));
    cache.budget(cache.getCurrentlyUsedSize());
    source(a);
    const int before = stops;
    ALuint b = cache.getBufferForFile(OpenFileInfo(&high));
    check(b != 0 && stops == before + 1, "active eviction calls the real source cleanup path");
    check(!alIsBuffer(a), "eviction actually deletes the previously attached OpenAL buffer");
    check(!cache.owns(a) && cache.entries() == 1, "successful eviction replaces the cache entry");
    // Clean up a broken baseline too, so later tests do not inherit leaked handles.
    detach(a);
    if (alIsBuffer(a)) alDeleteBuffers(1, &a);
    cache.closeBuffer(b);
    alGetError();
}
static void refusedDeletion() {
    AudioEventRTS low("untracked-low", 1), high("untracked-high", 2);
    Cache cache; currentCache = &cache;
    ALuint a = cache.getBufferForFile(OpenFileInfo(&low));
    const unsigned int charge = cache.getCurrentlyUsedSize();
    cache.budget(charge);
    ALuint untracked = source(a, false);
    ALuint rejected = cache.getBufferForFile(OpenFileInfo(&high));
    check(rejected == 0 && cache.owns(a) && cache.decoderAlive(a) && alIsBuffer(a), "failed OpenAL deletion retains the original owned handle");
    check(cache.getCurrentlyUsedSize() == charge, "failed eviction preserves resident accounting");
    alDeleteSources(1, &untracked);
    cache.closeBuffer(a);
    ALuint replacement = cache.getBufferForFile(OpenFileInfo(&high));
    check(replacement != 0 && !alIsBuffer(a), "eviction succeeds after the external source releases its buffer");
    if (replacement) cache.closeBuffer(replacement);
    if (rejected && rejected != replacement) cache.closeBuffer(rejected);
    if (alIsBuffer(a) && !cache.owns(a)) alDeleteBuffers(1, &a);
    alGetError();
}
static void oldOrderNegativeControl() {
    AudioEventRTS oldPortion("old-order-a", 1), nextPortion("old-order-b", 1);
    Cache cache; currentCache = &cache;
    ALuint old = cache.getBufferForFile(OpenFileInfo(&oldPortion));
    const ALuint oldId = old;
    cache.budget(cache.getCurrentlyUsedSize());
    ALuint handle = source(old, false);
    alSourceStop(handle);
    cache.closeBuffer(old); // Historical order: release the lease while AL_BUFFER remains attached.
    ALuint blocked = cache.getBufferForFile(OpenFileInfo(&nextPortion));
    check(blocked == 0 && cache.owns(oldId) && alIsBuffer(oldId),
          "old transition order blocks eviction while the stopped source retains the buffer");
    // The lease was already closed by the negative control; only detach now.
    releaseOpenALBufferLease(handle, old, [](ALuint) {});
    ALuint next = cache.getBufferForFile(OpenFileInfo(&nextPortion));
    check(old == 0 && next != 0 && !alIsBuffer(oldId),
          "detaching the old-order source permits retry without closing its lease twice");
    alDeleteSources(1, &handle);
    if (next) cache.closeBuffer(next);
    if (blocked && blocked != next) cache.closeBuffer(blocked);
    alGetError();
}
static void portionTransition() {
    AudioEventRTS oldPortion("old-portion", 1), nextPortion("next-portion", 1);
    Cache cache; currentCache = &cache;
    ALuint old = cache.getBufferForFile(OpenFileInfo(&oldPortion));
    const ALuint oldId = old;
    cache.budget(cache.getCurrentlyUsedSize());
    ALuint handle = source(old, false);
    alSourceStop(handle); // A stopped source still owns its AL_BUFFER reference.
    ALint bound = 0;
    alGetSourcei(handle, AL_BUFFER, &bound);
    check(bound == (ALint)old, "stopped portion source still retains its buffer");
    bool detachedBeforeClose = false;
    releaseOpenALBufferLease(handle, old, [&](ALuint buffer) {
        alGetSourcei(handle, AL_BUFFER, &bound);
        detachedBeforeClose = bound == 0;
        cache.closeBuffer(buffer);
    });
    check(detachedBeforeClose && old == 0, "production lease helper detaches the source before closing the lease");
    ALuint next = cache.getBufferForFile(OpenFileInfo(&nextPortion));
    check(next != 0 && !alIsBuffer(oldId), "next equal-priority portion can evict the detached old buffer");
    alDeleteSources(1, &handle);
    if (next) cache.closeBuffer(next);
    alGetError();
}
#ifdef GX_TEST_CACHE_ACCOUNTING
static void residentAccounting() {
    fixtureSamples = 4096;
    for (unsigned int bytes : {1u, 2u}) {
        fixtureBytesPerSample = bytes;
        AudioEventRTS event("compressed-tiny-decoded-large", 1);
        Cache cache; currentCache = &cache;
        ALuint buffer = cache.getBufferForFile(OpenFileInfo(&event));
        ALint pcmBytes = 0;
        alGetBufferi(buffer, AL_SIZE, &pcmBytes);
        const unsigned int expectedPCM = fixtureSamples * fixtureChannels * bytes;
        const unsigned int expectedFloat = fixtureSamples * fixtureChannels * 4;
        check(buffer && pcmBytes == (ALint)expectedPCM && expectedPCM > fixtureEncodedBytes,
              "actual OpenAL PCM size follows decoded samples, not compressed file size");
        check(liveBytes() == (int)expectedFloat && cache.getCurrentlyUsedSize() == expectedFloat,
              "cache budget charges actual WebAudio float32 residency for decoded 8/16-bit PCM");
        {
            Cache tooSmall; currentCache = &tooSmall;
            tooSmall.budget(expectedPCM);
            const int beforeBuffers = liveBuffers();
            ALuint rejected = tooSmall.getBufferForFile(OpenFileInfo(&event));
            check(rejected == 0 && tooSmall.entries() == 0 && tooSmall.getCurrentlyUsedSize() == 0 &&
                  liveBuffers() == beforeBuffers,
                  "decoded Float32 sample above the cache budget is rejected without leaking or admission");
            if (rejected) tooSmall.closeBuffer(rejected);
        }
        currentCache = &cache;
        cache.closeBuffer(buffer);
    }
    fixtureSamples = 128;
    fixtureBytesPerSample = 2;
}
#endif
static void repeatedEviction() {
    std::list<AudioEventRTS> events;
    Cache cache; currentCache = &cache;
    const int base = liveBuffers(), baseBytes = liveBytes();
    ALuint last = 0;
    bool bounded = true;
    for (int index = 0; index < 64; ++index) {
        const std::string name = "cycle-" + std::to_string(index);
        events.emplace_back(name.c_str(), index + 1);
        ALuint buffer = cache.getBufferForFile(OpenFileInfo(&events.back()));
        if (!buffer) { bounded = false; break; }
        if (index == 0) cache.budget(cache.getCurrentlyUsedSize());
        source(buffer);
        if (liveBuffers() != base + 1 || liveBytes() != baseBytes + int(fixtureSamples * fixtureChannels * 4)) bounded = false;
        // Keep a broken baseline bounded during testing without hiding its failure.
        if (last && alIsBuffer(last) && !cache.owns(last)) {
            detach(last); alDeleteBuffers(1, &last); alGetError();
        }
        last = buffer;
    }
    check(bounded, "repeated tiny-cache evictions bound actual OpenAL buffers and float32 bytes");
    if (last) { detach(last); cache.closeBuffer(last); }
}
int main() {
    ALCdevice *device = alcOpenDevice(nullptr);
    ALCcontext *context = alcCreateContext(device, nullptr);
    check(device && context && alcMakeContextCurrent(context), "actual Emscripten OpenAL context initializes");
    if (failures) return 1;
    leases();
    activeEviction();
    refusedDeletion();
    oldOrderNegativeControl();
    portionTransition();
    repeatedEviction();
#ifdef GX_TEST_CACHE_ACCOUNTING
    residentAccounting();
#endif
    check(liveBuffers() == 0, "cache destruction releases every actual OpenAL buffer");
    alcMakeContextCurrent(nullptr);
    alcDestroyContext(context);
    alcCloseDevice(device);
    printf("Audio cache regression: %d failure(s)\n", failures);
    return failures ? 1 : 0;
}
