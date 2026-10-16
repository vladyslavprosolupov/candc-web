#pragma once
#include "Common/file.h"
#include "libavcodec/avcodec.h"
#include <functional>
#include <vector>
extern unsigned int fixtureSamples;
extern unsigned int fixtureChannels;
extern unsigned int fixtureBytesPerSample;
class FFmpegFile {
    File *file = nullptr;
    bool emitted = false;
    void *user = nullptr;
    std::function<void(AVFrame *, int, int, void *)> callback;
public:
    ~FFmpegFile() { close(); }
    bool open(File *value) { file = value; return true; }
    void close() { delete file; file = nullptr; }
    void setFrameCallback(std::function<void(AVFrame *, int, int, void *)> value) { callback = value; }
    void setUserData(void *value) { user = value; }
    int getSizeForSamples(int samples) const { return samples * fixtureChannels * fixtureBytesPerSample; }
    int getNumChannels() const { return fixtureChannels; }
    int getBytesPerSample() const { return fixtureBytesPerSample; }
    int getSampleRate() const { return 22050; }
    bool decodePacket() {
        if (emitted) return false;
        emitted = true;
        std::vector<uint8_t> pcm(getSizeForSamples(fixtureSamples), 0);
        AVFrame frame = {};
        frame.nb_samples = fixtureSamples;
        frame.format = AV_SAMPLE_FMT_S16;
        frame.data[0] = pcm.data();
        callback(&frame, 0, AVMEDIA_TYPE_AUDIO, user);
        return true;
    }
};
