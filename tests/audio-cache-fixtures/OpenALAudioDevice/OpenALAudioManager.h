#pragma once
#include <AL/al.h>
#include <AL/alc.h>
#include <cstdint>
#include <functional>
#include <list>
#include <string>
#include <vector>
using Bool = bool;
using Int = int;
using UnsignedInt = unsigned int;
#define TRUE true
#define FALSE false
#define DEBUG_LOG(args) ((void)0)
#define DEBUG_CRASH(args) ((void)0)
#define DEBUG_ASSERTLOG(condition, args) ((void)0)
#define DEBUG_ASSERTCRASH(condition, args) ((void)0)
class AsciiString {
    std::string value;
public:
    AsciiString() = default;
    AsciiString(const char *text) : value(text) {}
    const char *str() const { return value.c_str(); }
    bool isEmpty() const { return value.empty(); }
    bool operator==(const AsciiString &other) const { return value == other.value; }
};
namespace std {
template<> struct hash<AsciiString> {
    size_t operator()(const AsciiString &value) const { return hash<string>()(value.str()); }
};
}
namespace rts {
template<class T> using hash = std::hash<T>;
template<class T> using equal_to = std::equal_to<T>;
}
class AudioEventInfo;
class AudioEventRTS;
class OpenALAudioStream;
enum PlayingAudioType {PAT_INVALID};
class OpenALAudioManager {
public:
    static ALenum getALFormat(int channels, int bits) {
        if (channels == 2) return bits == 16 ? AL_FORMAT_STEREO16 : AL_FORMAT_STEREO8;
        return bits == 16 ? AL_FORMAT_MONO16 : AL_FORMAT_MONO8;
    }
    void closeAnySamplesUsingFile(const void *buffer);
};
extern OpenALAudioManager *TheAudio;
