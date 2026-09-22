#ifndef CONVERT_CUDA_CUH
#define CONVERT_CUDA_CUH

#include <cstdint>
#include <cuda_runtime.h>

extern "C" void yuyv_to_bgr_cuda(
    const uint8_t* YUYV,
    uint8_t* BGR,
    int width, 
    int height
);

extern "C" void yuyv_to_bgr_and_resize_cuda(
    const uint8_t* YUYV,
    uint8_t* BGR,
    uint8_t* DST_BGR,
    int width,
    int height,
    int dst_width,
    int dst_height
);

extern "C" void crop_yuyv_row_cuda(
    const uint32_t* src, int src_width, int src_height,
    uint32_t* dest, int dest_height, int y_start
);

extern "C" void bgra_to_bgr_cuda(
    const uint8_t* BGRA,
    uint8_t* BGR,
    int width,
    int height
);

#endif