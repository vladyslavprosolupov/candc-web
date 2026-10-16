#pragma once
#include <stdint.h>
typedef enum AVSampleFormat {AV_SAMPLE_FMT_S16} AVSampleFormat;
enum {AVMEDIA_TYPE_AUDIO = 1};
typedef struct AVFrame {
    int nb_samples;
    int format;
    uint8_t *data[8];
} AVFrame;
static inline int av_sample_fmt_is_planar(AVSampleFormat format) { (void)format; return 0; }
