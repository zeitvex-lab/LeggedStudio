// Copyright (c) 2025, AgiBot Inc.
// All rights reserved.

#include "yuv2bgr.hpp"
#include "convert.cuh"

namespace aima::sensors::camera {

Yuyv2Bgr::~Yuyv2Bgr() {}

void Yuyv2Bgr::convert(const uint8_t *input, uint8_t *output) {
  yuyv_to_bgr(input, output, yuyv_cuda_buf_, bgr_cuda_buf_, input_width_,
              input_height_);
}

void Yuyv2Bgr::yuyv_to_bgr(const uint8_t *yuyv_host, uint8_t *bgr_host,
                           uint8_t *yuyv_dev, uint8_t *bgr_dev, int width,
                           int height) {
  // 拷贝数据到设备
  cudaMemcpy(yuyv_dev, yuyv_host, width * height * 2, cudaMemcpyHostToDevice);

  // 启动核函数
  yuyv_to_bgr_cuda(yuyv_dev, bgr_dev, width, height);

  // 拷贝结果回主机
  cudaMemcpy(bgr_host, bgr_dev, width * height * 3, cudaMemcpyDeviceToHost);
}

int Yuyv2Bgr::init(const std::string &model, std::shared_ptr<isx031c_calibration_data> param) {
  auto expect_height = (input_width_ * output_height_) / output_width_;
  int src_top = 0;
  if (expect_height < input_height_) {
      // 裁剪
      src_top = (input_height_ - expect_height) / 2;
  }

  NvBufSurf::NvCommonAllocateParams nvbuf_params;
  nvbuf_params.memType = NVBUF_MEM_SURFACE_ARRAY;
  nvbuf_params.width = output_width_;
  nvbuf_params.height = output_height_;
  nvbuf_params.layout = NVBUF_LAYOUT_PITCH;
  nvbuf_params.colorFormat = NVBUF_COLOR_FORMAT_BGRA;
  nvbuf_params.memtag = NvBufSurfaceTag_VIDEO_CONVERT;
  NvBufSurf::NvAllocate(&nvbuf_params, 1, &bgr_dma_fd_);
  NvBufSurfaceFromFd(bgr_dma_fd_, (void**)(&nvbuf_surf));
  NvBufSurfaceMap(nvbuf_surf, 0, 0, NVBUF_MAP_READ);

  transform_params_.src_top = src_top;
  transform_params_.src_left = 0;
  transform_params_.src_width = input_width_;
  transform_params_.src_height = expect_height;
  transform_params_.dst_top = 0;
  transform_params_.dst_left = 0;
  transform_params_.dst_width = output_width_;
  transform_params_.dst_height = output_height_;
  transform_params_.flag = NVBUFSURF_TRANSFORM_CROP_SRC;
  transform_params_.flip = NvBufSurfTransform_None;
  transform_params_.filter = NvBufSurfTransformInter_Nearest;

  return 0;
}

int Yuyv2Bgr::convert_from_fd(int src_fd, uint8_t *output) {
  int ret = NvBufSurf::NvTransform(&transform_params_, src_fd, bgr_dma_fd_);
  if (ret < 0) {
    AIMRTE_ERROR("NvTransform failed: {}", ret);
    return ret;
  }

  return bgra_to_bgr((uint8_t *)nvbuf_surf->surfaceList->mappedAddr.addr[0], output);
}

int Yuyv2BgrAndLDC::init(const std::string &model, std::shared_ptr<isx031c_calibration_data> param) {
  transform_params_.src_top = 0;
  transform_params_.src_left = 0;
  transform_params_.src_width = input_width_;
  transform_params_.src_height = input_height_;
  transform_params_.dst_top = 0;
  transform_params_.dst_left = 0;
  transform_params_.dst_width = output_width_;
  transform_params_.dst_height = output_height_;
  transform_params_.flag = NVBUFSURF_TRANSFORM_FILTER;
  transform_params_.flip = NvBufSurfTransform_None;
  transform_params_.filter = NvBufSurfTransformInter_Nearest;

  NvBufSurf::NvCommonAllocateParams nvbuf_params;
  nvbuf_params.memType = NVBUF_MEM_SURFACE_ARRAY;
  nvbuf_params.width = input_width_;
  nvbuf_params.height = input_height_;
  nvbuf_params.layout = NVBUF_LAYOUT_PITCH;
  nvbuf_params.colorFormat = NVBUF_COLOR_FORMAT_NV12_ER;
  nvbuf_params.memtag = NvBufSurfaceTag_VIDEO_CONVERT;

  NvBufSurf::NvAllocate(&nvbuf_params, 1, &nv12_dma_fd_);
  NvBufSurf::NvAllocate(&nvbuf_params, 1, &nv12_dma_fd2_);

  nvbuf_params.memType = NVBUF_MEM_SURFACE_ARRAY;
  nvbuf_params.width = output_width_;
  nvbuf_params.height = output_height_;
  nvbuf_params.layout = NVBUF_LAYOUT_PITCH;
  nvbuf_params.colorFormat = NVBUF_COLOR_FORMAT_BGRA;
  nvbuf_params.memtag = NvBufSurfaceTag_VIDEO_CONVERT;

  NvBufSurf::NvAllocate(&nvbuf_params, 1, &bgr_dma_fd_);

  NvBufSurfaceFromFd(bgr_dma_fd_, (void**)(&nvbuf_surf));
  NvBufSurfaceMap(nvbuf_surf, 0, 0, NVBUF_MAP_READ);

  VPIImageData img_data;
  memset(&img_data, 0, sizeof(img_data));
  img_data.bufferType = VPI_IMAGE_BUFFER_NVBUFFER;
  img_data.buffer.fd = nv12_dma_fd_;

  VPIImageData img_data2;
  memset(&img_data2, 0, sizeof(img_data2));
  img_data2.bufferType = VPI_IMAGE_BUFFER_NVBUFFER;
  img_data2.buffer.fd = nv12_dma_fd2_;

  VPIImageWrapperParams vpi_params;
  vpiInitImageWrapperParams(&vpi_params);

  CHECK_VPI(vpiImageCreateWrapper(&img_data, &vpi_params, VPI_BACKEND_VIC, &input_image_));
  CHECK_VPI(vpiImageCreateWrapper(&img_data2, &vpi_params, VPI_BACKEND_VIC, &middle_image_));  
  
  CHECK_VPI(vpiStreamCreate(VPI_BACKEND_VIC, &stream_));
  const VPICameraIntrinsic K = {
    { (float)param->fx, 0.0f, (float)param->cx },
    { 0.0f, (float)param->fy, (float)param->cy },
  };

  const VPICameraExtrinsic X = {
      { 1, 0, 0, 0 },
      { 0, 1, 0, 0 },
      { 0, 0, 1, 0 }
  };

  VPIPolynomialLensDistortionModel poly;
  memset(&poly, 0, sizeof(poly));
  poly.k1 = (float)param->k1;
  poly.k2 = (float)param->k2;
  poly.k3 = (float)param->k3;
  poly.k4 = (float)param->k4;
  poly.k5 = (float)param->k5;
  poly.k6 = (float)param->k6;
  poly.p1 = (float)param->p1;
  poly.p2 = (float)param->p2;

  VPIWarpMap warp_map_            = {};
  warp_map_.grid.numHorizRegions  = 1;
  warp_map_.grid.numVertRegions   = 1;
  warp_map_.grid.regionWidth[0]   = input_width_;
  warp_map_.grid.regionHeight[0]  = input_height_;
  warp_map_.grid.horizInterval[0] = 1;
  warp_map_.grid.vertInterval[0]  = 1;
  CHECK_VPI(vpiWarpMapAllocData(&warp_map_));

  CHECK_VPI(vpiWarpMapGenerateFromPolynomialLensDistortionModel(K, X, K, &poly, &warp_map_));

  CHECK_VPI(vpiCreateRemap(VPI_BACKEND_VIC, &warp_map_, &payload_));

  return VPI_SUCCESS;
}

void Yuyv2BgrAndLDC::convert(const uint8_t *input, uint8_t *output) {
  // not supported
}

int Yuyv2BgrAndLDC::convert_from_fd(int src_fd, uint8_t *output) {
  int ret = NvBufSurf::NvTransform(&transform_params_, src_fd, nv12_dma_fd_);
  if (ret < 0) return -1;

  CHECK_VPI(vpiSubmitRemap(stream_, VPI_BACKEND_VIC, payload_, input_image_, middle_image_, VPI_INTERP_CATMULL_ROM, VPI_BORDER_ZERO, 0));

  CHECK_VPI(vpiStreamSync(stream_));

  ret = NvBufSurf::NvTransform(&transform_params_, nv12_dma_fd2_, bgr_dma_fd_);
  if (ret < 0) return -2;

  return bgra_to_bgr((uint8_t *)nvbuf_surf->surfaceList->mappedAddr.addr[0], output);
}

} // namespace aima::sensors::camera
