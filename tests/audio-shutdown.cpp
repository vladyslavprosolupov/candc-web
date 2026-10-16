// Actual manager destructor/closeDevice bodies and production cache are linked separately.
#include "OpenALAudioCache.h"
#include "Common/AudioEventRTS.h"
#include "Common/FileSystem.h"
#include <emscripten.h>
#include <cstdio>

unsigned int fixtureEncodedBytes = 8, fixtureSamples = 128, fixtureChannels = 2, fixtureBytesPerSample = 2;
static FixtureFileSystem filesystem;
FixtureFileSystem *TheFileSystem = &filesystem;
OpenALAudioManager *TheAudio = nullptr;
static int failures, stops;
static bool stoppedWithContext, sourceDeleted;
static void check(bool ok, const char *message) {
    printf("%s %s\n", ok ? "PASS" : "FAIL", message);
    if (!ok) ++failures;
}
void OpenALAudioManager::stopAllAudioImmediately() {
    ++stops;
    stoppedWithContext = alcGetCurrentContext() == m_alcContext;
    if (fixtureSource) {
        const ALuint previous = fixtureSource;
        alDeleteSources(1, &fixtureSource);
        sourceDeleted = !alIsSource(previous);
        fixtureSource = 0;
    }
    if (fixtureBuffer) {
        m_audioCache->closeBuffer(fixtureBuffer);
        fixtureBuffer = 0;
    }
}
void OpenALAudioManager::closeAnySamplesUsingFile(const void *) {
    // A late cache callback cannot repair deletion after the context is cleared.
    if (fixtureSource) alDeleteSources(1, &fixtureSource);
    fixtureSource = 0;
    if (fixtureBuffer) m_audioCache->closeBuffer(fixtureBuffer);
    fixtureBuffer = 0;
}
int main() {
    OpenALAudioManager *manager = new OpenALAudioManager();
    TheAudio = manager;
    manager->m_audioCache = new OpenALAudioFileCache();
    manager->m_alcDevice = alcOpenDevice(nullptr);
    manager->m_alcContext = alcCreateContext(manager->m_alcDevice, nullptr);
    check(manager->m_alcContext && alcMakeContextCurrent(manager->m_alcContext), "real OpenAL context initializes");
    if (failures) return 1;
    AudioEventRTS event("shutdown-pcm", 1);
    manager->fixtureBuffer = manager->m_audioCache->getBufferForFile(OpenFileInfo(&event));
    alGenSources(1, &manager->fixtureSource);
    alSourcei(manager->fixtureSource, AL_BUFFER, manager->fixtureBuffer);
    check(alIsBuffer(manager->fixtureBuffer) && alIsSource(manager->fixtureSource), "actual source owns cached PCM before shutdown");
    delete manager;
    check(stops == 1 && stoppedWithContext && sourceDeleted, "manager stops and deletes actual sources before clearing the context");
    check(EM_ASM_INT({ return Object.values(AL.buffers).filter(b => b && b.id).length; }) == 0,
          "manager shutdown deletes every actual OpenAL buffer");
    check(EM_ASM_INT({ return Object.values(AL.buffers).reduce((n,b) => n + (b?.audioBuf ? b.audioBuf.length * b.audioBuf.numberOfChannels * 4 : 0), 0); }) == 0,
          "manager shutdown leaves no retained WebAudio Float32 PCM");
    check(EM_ASM_INT({ return Object.keys(AL.contexts).length; }) == 0 && alcGetCurrentContext() == nullptr,
          "manager shutdown destroys and clears its context");
    check(EM_ASM_INT({ return Object.keys(AL.deviceRefCounts).length; }) == 0,
          "manager shutdown releases the device after its final buffer reference");
    check(TheAudio == nullptr, "manager shutdown clears the global owner");
    printf("Audio shutdown regression: %d failure(s)\n", failures);
    return failures ? 1 : 0;
}
