// Copyright (c) 2025, AgiBot Inc.
// All rights reserved.

#pragma once

#include "convert.hpp"

#include <vpi/VPI.h>
#include <vpi/Image.h>
#include <vpi/Stream.h>
#include <vpi/algo/ConvertImageFormat.h>
#include <vpi/algo/Remap.h>
#include <vpi/LensDistortionModels.h>

#define CHECK_VPI(x)                                                       \
    do {                                                                   \
        VPIStatus _st = (x);                                               \
        if (_st != VPI_SUCCESS) {                                          \
            AIMRTE_ERROR("VPI call failed: {} at {}:{}, expr: {}\n",    \
                    vpiStatusGetName(_st), __FILE__, __LINE__, #x);        \
            return _st;                                                    \
        }                                                                  \
    } while (0)

namespace aima::sensors::camera {

class Yuyv2Bgr : public ImgConverter {
    public:
    Yuyv2Bgr(int input_width, int input_height, int output_width, int output_height)
        : ImgConverter(input_width, input_height, output_width, output_height) {}
    // TODO: unmap dma fd
    ~Yuyv2Bgr();
    
    void convert(const uint8_t* input, uint8_t* output) override;
    int convert_from_fd(int src_fd, uint8_t* output) override;
    int init(const std::string& model, std::shared_ptr<isx031c_calibration_data> param) override;

    private:
    void yuyv_to_bgr(
        const uint8_t* yuyv_host,
        uint8_t* bgr_host,
        uint8_t* yuyv_dev,
        uint8_t* bgr_dev,
        int width,
        int height
    );

    NvBufSurf::NvCommonTransformParams transform_params_;
    int bgr_dma_fd_ = 0;
    NvBufSurfaceParams param = {0};
    NvBufSurface *nvbuf_surf = 0;
};

class Yuyv2BgrAndLDC : public ImgConverter {
    public:
    Yuyv2BgrAndLDC(int input_width, int input_height, int output_width, int output_height)
        : ImgConverter(input_width, input_height, output_width, output_height) {}

    void convert(const uint8_t* input, uint8_t* output) override;
    int convert_from_fd(int src_fd, uint8_t* output) override;
    int init(const std::string& model, std::shared_ptr<isx031c_calibration_data> param) override;

    NvBufSurf::NvCommonTransformParams transform_params_;
    int nv12_dma_fd_ = 0;
    int nv12_dma_fd2_ = 0;
    int bgr_dma_fd_ = 0;
    NvBufSurfaceParams param = {0};
    NvBufSurface *nvbuf_surf = 0;

    VPIPayload payload_ = nullptr;
    VPIStream stream_ = nullptr;
    VPIImage input_image_ = nullptr;
    VPIImage middle_image_ = nullptr;
    VPIImage output_image_ = nullptr;    
};

}