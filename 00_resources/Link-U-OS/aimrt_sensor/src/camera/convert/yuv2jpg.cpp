// Copyright (c) 2025, AgiBot Inc.
// All rights reserved.

#include "yuv2jpg.hpp"

namespace aima::sensors::camera {

Yuyv2Jpg::Yuyv2Jpg(int input_width, int input_height, int output_width, int output_height)
    : ImgConverter(input_width, input_height, output_width, output_height) {    
    // YUY420 dma buf
    NvBufSurf::NvCommonAllocateParams params;
    params.memType = NVBUF_MEM_SURFACE_ARRAY;
    params.width = output_width;
    params.height = output_height;
    params.layout = NVBUF_LAYOUT_BLOCK_LINEAR;
    params.colorFormat = NVBUF_COLOR_FORMAT_YUV420;
    params.memtag = NvBufSurfaceTag_VIDEO_CONVERT;

    NvBufSurf::NvAllocate(&params, 1, &dst_dma_fd_);
    jpeg_encoder_ = NvJPEGEncoder::createJPEGEncoder("jpenenc");
}

Yuyv2Jpg::~Yuyv2Jpg() {
    if (dst_dma_fd_ > 0) {
        NvBufSurf::NvDestroy(dst_dma_fd_);
        dst_dma_fd_ = -1;
    }

    if (jpeg_encoder_) {
        delete jpeg_encoder_;
        jpeg_encoder_ = nullptr;
    }
}

void Yuyv2Jpg::convert(const uint8_t* input, uint8_t* output) {}

int Yuyv2Jpg::convert_from_fd(int src_fd, uint8_t *output) {
    // transform
    auto expect_height = (input_width_ * output_height_) / output_width_;
    int src_top = 0;
    if (expect_height < input_height_) {
      // 裁剪
      src_top = (input_height_ - expect_height) / 2;
    }
    NvBufSurf::NvCommonTransformParams transform_params;
    transform_params.src_top = src_top;
    transform_params.src_left = 0;
    transform_params.src_width = input_width_;
    transform_params.src_height = expect_height;
    transform_params.dst_top = 0;
    transform_params.dst_left = 0;
    transform_params.dst_width = output_width_;
    transform_params.dst_height = output_height_;
    transform_params.flag = NVBUFSURF_TRANSFORM_CROP_SRC;
    transform_params.flip = NvBufSurfTransform_None;
    transform_params.filter = NvBufSurfTransformInter_Nearest;

    int ret = NvBufSurf::NvTransform(&transform_params, src_fd, dst_dma_fd_);
    if (ret < 0) {
        return -1;
    }
    
    unsigned long out_size = output_width_ * output_height_ * 3 / 2; // YUV420 size

    ret = jpeg_encoder_->encodeFromFd(dst_dma_fd_, JCS_YCbCr, &output, out_size, quality_);

    if (ret < 0) {
        return -2;
    }

    return out_size;
}

}