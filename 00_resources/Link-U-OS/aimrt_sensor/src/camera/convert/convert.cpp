// Copyright (c) 2025, AgiBot Inc.
// All rights reserved.

#include "convert.hpp"
#include "convert.cuh"

#include <algorithm>

namespace aima::sensors::camera {

ImgConverter::ImgConverter(int input_width, int input_height, int output_width,
                           int output_height)
    : input_width_(input_width), input_height_(input_height),
    output_width_(output_width), output_height_(output_height) {
  auto width = std::max(input_width_, output_width_);
  auto height = std::max(input_height, output_height);
  init_cuda_device_buffer(&yuyv_cuda_buf_, &bgr_cuda_buf_, &reserve_cuda_buf_,
                          width, height);
}

ImgConverter::~ImgConverter() {
  free_cuda_device_buffer(yuyv_cuda_buf_, bgr_cuda_buf_, reserve_cuda_buf_);
}

void yuyv_to_bgr(const uint8_t *yuyv_host, uint8_t *bgr_host, uint8_t *yuyv_dev,
                 uint8_t *bgr_dev, int width, int height) {
  // 拷贝数据到设备
  cudaMemcpy(yuyv_dev, yuyv_host, width * height * 2, cudaMemcpyHostToDevice);

  // 启动核函数
  yuyv_to_bgr_cuda(yuyv_dev, bgr_dev, width, height);

  // 拷贝结果回主机
  cudaMemcpy(bgr_host, bgr_dev, width * height * 3, cudaMemcpyDeviceToHost);
}

void yuyv_to_bgr_and_resize(const uint8_t *yuyv_host, uint8_t *bgr_host,
                            uint8_t *yuyv_dev, uint8_t *bgr_dev,
                            uint8_t *reserve_dev, int width, int height,
                            int dst_width, int dst_height) {
  // 拷贝数据到设备
  cudaMemcpy(yuyv_dev, yuyv_host, width * height * 2, cudaMemcpyHostToDevice);

  // 启动核函数
  yuyv_to_bgr_and_resize_cuda(yuyv_dev, reserve_dev, bgr_dev, width, height,
                              dst_width, dst_height);

  // 拷贝结果回主机
  cudaMemcpy(bgr_host, bgr_dev, dst_width * dst_height * 3,
             cudaMemcpyDeviceToHost);
}

void ImgConverter::init_cuda_device_buffer(uint8_t **input_dev,
                                           uint8_t **output_dev,
                                           uint8_t **reserve_dev, int width,
                                           int height) {
  auto buffer_size =
      width * height * 2 * 5; // enough space for most img formats
  cudaMalloc(input_dev, buffer_size);
  cudaMalloc(output_dev, buffer_size);
  cudaMalloc(reserve_dev, buffer_size);
}

void ImgConverter::free_cuda_device_buffer(uint8_t *input_dev,
                                           uint8_t *output_dev,
                                           uint8_t *reserve_dev) {
  cudaFree(input_dev);
  cudaFree(output_dev);
  cudaFree(reserve_dev);
}

int ImgConverter::bgra_to_bgr(const uint8_t* input, uint8_t* output) {
  cudaMemcpy(reserve_cuda_buf_, input, output_width_ * output_height_ * 4, cudaMemcpyHostToDevice);

  bgra_to_bgr_cuda(reserve_cuda_buf_, bgr_cuda_buf_, output_width_, output_height_);

  // // 拷贝结果回主机
  cudaMemcpy(output, bgr_cuda_buf_, output_width_ * output_height_ * 3,
             cudaMemcpyDeviceToHost);
  return output_width_ * output_height_ * 3;
}

} // namespace aima::sensors::camera