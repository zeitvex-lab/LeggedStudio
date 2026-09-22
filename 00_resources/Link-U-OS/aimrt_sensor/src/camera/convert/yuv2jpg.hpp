// Copyright (c) 2025, AgiBot Inc.
// All rights reserved.

#pragma once

#include "convert.hpp"
#include "NvBufSurface.h"
#include "NvJpegEncoder.h"
#include <memory>

namespace aima::sensors::camera {

class Yuyv2Jpg : public ImgConverter {
    public:
    Yuyv2Jpg(int input_width, int input_height, int output_width, int output_height);
    ~Yuyv2Jpg();

    void convert(const uint8_t* input, uint8_t* output) override;
    int convert_from_fd(int src_fd, uint8_t* output) override;

    private:
    int dst_dma_fd_;
    NvJPEGEncoder* jpeg_encoder_ = nullptr;
    int quality_ = 90; // JPEG quality, default is 90
};

}