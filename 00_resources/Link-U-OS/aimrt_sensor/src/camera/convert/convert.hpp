// Copyright (c) 2025, AgiBot Inc.
// All rights reserved.

#pragma once

#include <cstdint>
#include <memory>
#include <cuda_runtime.h>
#include "NvBufSurface.h"

#include "src/camera/utils/calibration.hpp"
#include "src/all_in_one/include/aimrte.h"

namespace aima::sensors::camera {

class ImgConverter {
    public:
        ImgConverter(int input_width, int input_height, int output_width, int output_height);
        ~ImgConverter();
        virtual void convert(const uint8_t* input, uint8_t* output) = 0;
        virtual int convert_from_fd(int src_fd, uint8_t* output) { return 0; }
        virtual int init(const std::string& model, std::shared_ptr<isx031c_calibration_data> param) { return 0; }

    protected:
        int bgra_to_bgr(const uint8_t* input, uint8_t* output);
        int input_width_;
        int input_height_;
        int output_width_;
        int output_height_;
        uint8_t* yuyv_cuda_buf_;
        uint8_t* bgr_cuda_buf_;
        uint8_t* reserve_cuda_buf_;
        std::string camera_model_;

    private:
        void init_cuda_device_buffer(
            uint8_t** input_dev,
            uint8_t** output_dev,
            uint8_t** reserve_dev,
            int width,
            int height
        );

        void free_cuda_device_buffer(
            uint8_t* input_dev,
            uint8_t* output_dev,
            uint8_t* reserve_dev
        );
};

}