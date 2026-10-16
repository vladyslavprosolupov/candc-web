#pragma once
#include "Common/AudioEventInfo.h"
enum PlayPortion {PP_Attack, PP_Sound, PP_Decay, PP_Done};
class AudioEventRTS {
    AudioEventInfo info;
public:
    AudioEventRTS(const char *filename, int priority) : info{priority, filename} {}
    PlayPortion getNextPlayPortion() const { return PP_Sound; }
    AsciiString getAttackFilename() const { return info.m_audioName; }
    AsciiString getFilename() const { return info.m_audioName; }
    AsciiString getDecayFilename() const { return info.m_audioName; }
    const AudioEventInfo *getAudioEventInfo() const { return &info; }
    bool isPositionalAudio() const { return false; }
};
