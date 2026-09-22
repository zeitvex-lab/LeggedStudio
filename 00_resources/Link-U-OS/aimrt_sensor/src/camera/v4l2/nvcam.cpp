// Copyright (c) 2025, AgiBot Inc.
// All rights reserved.

// TODO: 把所有 v4l2 摄像头都放到一起，使用 epoll
// 来监听所有摄像头的数据，然后在回调函数中处理数据

#include "nvcam.hpp"

#include <cstddef>
#include <cstdint>
#include <cstring>
#include <sys/poll.h>

namespace aima {
namespace sensors {
namespace camera {

nv_color_fmt nvcolor_fmt[] = {
    /* TODO: add more pixel format mapping */
    {V4L2_PIX_FMT_UYVY, NVBUF_COLOR_FORMAT_UYVY},
    {V4L2_PIX_FMT_VYUY, NVBUF_COLOR_FORMAT_VYUY},
    {V4L2_PIX_FMT_YUYV, NVBUF_COLOR_FORMAT_YUYV},
    {V4L2_PIX_FMT_YVYU, NVBUF_COLOR_FORMAT_YVYU},
    {V4L2_PIX_FMT_GREY, NVBUF_COLOR_FORMAT_GRAY8},
    {V4L2_PIX_FMT_YUV420M, NVBUF_COLOR_FORMAT_YUV420},
};

NvCam::NvCam() {}

NvCam::~NvCam() {}

int NvCam::Init(Option option) {
  opt_ = option;
  dev_name_ = "/dev/gmslcam" + std::to_string(opt_.index);
  getTsOffset();

  do {
    fd_ = open(dev_name_.c_str(), O_RDWR, 0);
    if (fd_ < 0) {
      AIMRTE_ERROR("Failed to open device: {}", dev_name_);
      break;
    }

    if (!checkCapabilities()) {
      AIMRTE_ERROR("Check capabilities failed: {}", dev_name_);
      break;
    }

    if (!setFormat()) {
      AIMRTE_ERROR("Set format failed: {}", dev_name_);
      break;
    }

    if (!initDevice()) {
      AIMRTE_ERROR("Init device failed: {}", dev_name_);
      break;
    }

    return 0;
  } while (0);

  if (fd_ >= 0) {
    close(fd_);
    fd_ = -1;
  }

  return 0;
}

int NvCam::Release() {
  if (!stopCapture()) {
    AIMRTE_WARN("Stop capture failed: {}", dev_name_);
  }

  if (fd_ >= 0) {
    close(fd_);
    fd_ = -1;
  }

  for (int i = 0; i < V4L2_BUFFER_NUM; i++) {
    if (pSurf_[i]) {
      // TODO: 目前只支持单平面格式
      NvBufSurfaceUnMap(pSurf_[i], 0, 0);
      pSurf_[i] = NULL;
    }

    if (nvbuff_[i].dmabuff_fd) {
      NvBufSurf::NvDestroy(nvbuff_[i].dmabuff_fd);
    }
  }
  free(nvbuff_);
  nvbuff_ = NULL;

  return 0;
}

int NvCam::Start() {
  if (!startCapture()) {
    AIMRTE_ERROR("Start capture failed: {}", dev_name_);
    return -1;
  }
  return 0;
}

int NvCam::Stop() {
  if (!stopCapture()) {
    AIMRTE_ERROR("Stop capture failed: {}", dev_name_);
    return -1;
  }
  return 0;
}

int NvCam::DataPoll(std::shared_ptr<rawimg_buffer> img) {
  if (fd_ < 0) {
    AIMRTE_ERROR("Invalid file descriptor, dev {}", dev_name_);
    return -1;
  }

  fds_[0].fd = fd_;
  fds_[0].events = POLLIN;

  if (poll(fds_, 1, 1000) < 0) {
    AIMRTE_ERROR("Poll error: {}, dev {}", errno, dev_name_);
    return -3;
  }

  if (fds_[0].revents & POLLIN) {
    struct v4l2_buffer buf;
    memset(&buf, 0, sizeof(struct v4l2_buffer));
    buf.type = V4L2_BUF_TYPE_VIDEO_CAPTURE;
    buf.memory = V4L2_MEMORY_DMABUF;
    if (ioctl(fd_, VIDIOC_DQBUF, &buf) < 0) {
      AIMRTE_ERROR("Failed to dequeue buffer, dev {}", dev_name_);
      return -5;
    }

    if (NvBufSurfaceSyncForDevice(pSurf_[buf.index], 0, 0) < 0) {
      AIMRTE_ERROR("Failed to sync buffer for device, dev {}", dev_name_);
      return -6;
    }

    struct timespec realtime;
    cpuToRealtime(buf.timestamp, &realtime);

    img->ts_sec = realtime.tv_sec;
    img->ts_nsec = realtime.tv_nsec;
    img->width = opt_.width;
    img->height = opt_.height;
    img->data_ptr =
        (uint8_t *)pSurf_[buf.index]->surfaceList[0].mappedAddr.addr[0];
    img->data_len = pSurf_[buf.index]->surfaceList[0].dataSize;
    img->dma_fd = nvbuff_[buf.index].dmabuff_fd;

    if (ioctl(fd_, VIDIOC_QBUF, &buf) < 0) {
      AIMRTE_ERROR("Failed to queue buffer, dev {}", dev_name_);
      return -7;
    }

    return buf.index;
  } else {
    AIMRTE_ERROR("Event poll failed, dev {}", dev_name_);
    return -4;
  }
}

int NvCam::GetData(std::shared_ptr<rawimg_buffer> img) {
  if (fd_ < 0) {
    AIMRTE_ERROR("Invalid file descriptor, dev {}", dev_name_);
    return -1;
  }

  struct v4l2_buffer buf;
  memset(&buf, 0, sizeof(struct v4l2_buffer));
  buf.type = V4L2_BUF_TYPE_VIDEO_CAPTURE;
  buf.memory = V4L2_MEMORY_DMABUF;
  if (ioctl(fd_, VIDIOC_DQBUF, &buf) < 0) {
    AIMRTE_ERROR("Failed to dequeue buffer, dev {}", dev_name_);
    return -5;
  }

  if (NvBufSurfaceSyncForDevice(pSurf_[buf.index], 0, 0) < 0) {
    AIMRTE_ERROR("Failed to sync buffer for device, dev {}", dev_name_);
    return -6;
  }

  struct timespec realtime;
  cpuToRealtime(buf.timestamp, &realtime);

  img->ts_sec = realtime.tv_sec;
  img->ts_nsec = realtime.tv_nsec;
  img->width = opt_.width;
  img->height = opt_.height;
  img->data_ptr =
      (uint8_t *)pSurf_[buf.index]->surfaceList[0].mappedAddr.addr[0];
  img->data_len = pSurf_[buf.index]->surfaceList[0].dataSize;
  img->dma_fd = nvbuff_[buf.index].dmabuff_fd;

  if (ioctl(fd_, VIDIOC_QBUF, &buf) < 0) {
    AIMRTE_ERROR("Failed to queue buffer, dev {}", dev_name_);
    return -7;
  }

  return buf.index;
}

int NvCam::GetFd() { return fd_; }

bool NvCam::checkCapabilities() {
  struct v4l2_capability cap;
  if (ioctl(fd_, VIDIOC_QUERYCAP, &cap) < 0) {
    AIMRTE_ERROR("Failed to query capabilities");
    return false;
  }

  if (!(cap.capabilities & V4L2_CAP_VIDEO_CAPTURE)) {
    AIMRTE_ERROR("Device does not support video capture");
    return false;
  }

  if (!(cap.capabilities & V4L2_CAP_STREAMING)) {
    AIMRTE_ERROR("Device does not support streaming");
    return false;
  }

  return true;
}

bool NvCam::initDevice() {
  NvBufSurf::NvCommonAllocateParams camparams = {0};
  int fd[V4L2_BUFFER_NUM] = {0};

  nvbuff_ = (nv_buffer *)calloc(V4L2_BUFFER_NUM, sizeof(nv_buffer));
  if (nvbuff_ == NULL) {
    AIMRTE_ERROR("Failed to allocate memory for nvbuff");
    return false;
  }

  camparams.memType = NVBUF_MEM_SURFACE_ARRAY;
  camparams.width = opt_.width;
  camparams.height = opt_.height;
  camparams.layout = NVBUF_LAYOUT_PITCH;
  camparams.colorFormat = getNvBufferColorFormat(pixel_format_);
  camparams.memtag = NvBufSurfaceTag_CAMERA;
  if (NvBufSurf::NvAllocate(&camparams, V4L2_BUFFER_NUM, fd)) {
    AIMRTE_ERROR("Failed to allocate memory for nvbuff");
    return false;
  }

  for (int i = 0; i < V4L2_BUFFER_NUM; i++) {
    nvbuff_[i].dmabuff_fd = fd[i];
    if (NvBufSurfaceFromFd(fd[i], (void **)(&pSurf_[i])) < 0) {
      AIMRTE_ERROR("Failed to get NvBufSurface from fd");
      return false;
    }

    // TODO: 目前只支持单平面格式，也就是 YUYV
    if (NvBufSurfaceMap(pSurf_[i], 0, 0, NVBUF_MAP_READ_WRITE) < 0) {
      AIMRTE_ERROR("Failed to map NvBufSurface");
      return false;
    }

    nvbuff_[i].start = (unsigned char *)pSurf_[i]->surfaceList[0].dataPtr;
    nvbuff_[i].size = pSurf_[i]->surfaceList[0].dataSize;
  }

  struct v4l2_requestbuffers rb;
  memset(&rb, 0, sizeof(rb));
  rb.count = V4L2_BUFFER_NUM;
  rb.type = V4L2_BUF_TYPE_VIDEO_CAPTURE;
  rb.memory = V4L2_MEMORY_DMABUF;

  if (ioctl(fd_, VIDIOC_REQBUFS, &rb) < 0) {
    AIMRTE_ERROR("Failed to request buffers");
    return false;
  }

  if (rb.count != V4L2_BUFFER_NUM) {
    AIMRTE_ERROR("V4l2 buffer number is not as desired");
    return false;
  }

  for (int i = 0; i < V4L2_BUFFER_NUM; i++) {
    struct v4l2_buffer buf;
    memset(&buf, 0, sizeof(buf));
    buf.type = V4L2_BUF_TYPE_VIDEO_CAPTURE;
    buf.memory = V4L2_MEMORY_DMABUF;
    buf.index = i;
    buf.m.fd = nvbuff_[i].dmabuff_fd;

    if (ioctl(fd_, VIDIOC_QUERYBUF, &buf) < 0) {
      AIMRTE_ERROR("Failed to queue buffer, error {}", errno);
      return false;
    }

    buf.m.fd = (unsigned long)nvbuff_[i].dmabuff_fd;
    if (buf.length != nvbuff_[i].size) {
      AIMRTE_ERROR("Camera v4l2 buf length is not expected");
      nvbuff_[i].size = buf.length;
    }
  }

  return true;
}

bool NvCam::setFormat() {
  switch (opt_.pixfmt) {
  case 0:
    pixel_format_ = V4L2_PIX_FMT_SRGGB12;
    break;
  case 1:
    pixel_format_ = V4L2_PIX_FMT_YUYV;
    break;
  case 2:
    pixel_format_ = V4L2_PIX_FMT_UYVY;
    break;
  default:
    pixel_format_ = V4L2_PIX_FMT_YUYV;
    break;
  }

  struct v4l2_format fmt;
  memset(&fmt, 0, sizeof(fmt));

  fmt.type = V4L2_BUF_TYPE_VIDEO_CAPTURE;
  fmt.fmt.pix.width = opt_.width;
  fmt.fmt.pix.height = opt_.height;
  fmt.fmt.pix.pixelformat = pixel_format_;
  fmt.fmt.pix.field = V4L2_FIELD_INTERLACED;

  if (ioctl(fd_, VIDIOC_S_FMT, &fmt) < 0) {
    AIMRTE_ERROR("Failed to set format, {}", dev_name_);
    return false;
  }

  return true;
}

bool NvCam::startCapture() {
  if (fd_ < 0) {
    AIMRTE_ERROR("Invalid file descriptor, dev {}", dev_name_);
    return false;
  }

  for (int i = 0; i < V4L2_BUFFER_NUM; i++) {
    struct v4l2_buffer buf;
    memset(&buf, 0, sizeof(buf));
    buf.type = V4L2_BUF_TYPE_VIDEO_CAPTURE;
    buf.memory = V4L2_MEMORY_DMABUF;
    buf.index = i;
    buf.m.fd = (unsigned long)nvbuff_[i].dmabuff_fd;

    if (ioctl(fd_, VIDIOC_QBUF, &buf) < 0) {
      AIMRTE_ERROR("Failed to queue buffer, error {}", errno);
      return false;
    }
  }

  enum v4l2_buf_type type = V4L2_BUF_TYPE_VIDEO_CAPTURE;
  if (ioctl(fd_, VIDIOC_STREAMON, &type) < 0) {
    AIMRTE_ERROR("Failed to stream on, error {}", errno);
    return false;
  }

  return true;
}

bool NvCam::stopCapture() {
  if (fd_ < 0) {
    AIMRTE_ERROR("Invalid file descriptor, dev {}", dev_name_);
    return false;
  }

  enum v4l2_buf_type type = V4L2_BUF_TYPE_VIDEO_CAPTURE;
  if (ioctl(fd_, VIDIOC_STREAMOFF, &type) < 0) {
    AIMRTE_ERROR("Failed to stream off, error {}", errno);
    return false;
  }

  return true;
}

inline int NvCam::xioctl(int fd, int request, void *arg) {
  int r;
  do {
    r = ioctl(fd, request, arg);
  } while (-1 == r && EINTR == errno);
  return r;
}

inline NvBufSurfaceColorFormat
NvCam::getNvBufferColorFormat(uint32_t v4l2_pixfmt) {
  unsigned i;

  for (i = 0; i < sizeof(nvcolor_fmt) / sizeof(nvcolor_fmt[0]); i++) {
    if (v4l2_pixfmt == nvcolor_fmt[i].v4l2_pixfmt)
      return nvcolor_fmt[i].nvbuff_color;
  }

  return NVBUF_COLOR_FORMAT_INVALID;
}

int NvCam::getTsOffset() {
  // read /sys/devices/system/clocksource/clocksource0/offset_ns get int value
  FILE *fp = fopen(
      "/sys/devices/system/clocksource/clocksource0/offset_ns", "r");
  if (fp == NULL) {
    // read offset from register
    unsigned long raw_nsec, tsc_ns;
    unsigned long cycles, frq;
    struct timespec tp;

    asm volatile("mrs %0, cntfrq_el0" : "=r"(frq));
    asm volatile("mrs %0, cntvct_el0" : "=r"(cycles));

    clock_gettime(CLOCK_MONOTONIC_RAW, &tp);

    tsc_ns = (cycles * 100 / (frq / 10000)) * 1000;
    raw_nsec = tp.tv_sec * 1000000000 + tp.tv_nsec;
    nsec_offset_ = (uint64_t) llabs(tsc_ns-raw_nsec);
  } else {
    char buf[128] = {0};
    fgets(buf, sizeof(buf), fp);
    nsec_offset_ = atol(buf);
    fclose(fp);
  }

  return 0;
}

void NvCam::cpuToRealtime(timeval cpu_time, timespec* real_time) {
  struct timespec real_sample, monotonic_sample, monotonic_time, time_diff;
  const int64_t NSEC_PER_SEC = 1000000000;

  long long ns = cpu_time.tv_sec * NSEC_PER_SEC + cpu_time.tv_usec * 1000 - nsec_offset_;
  monotonic_time.tv_sec = ns / NSEC_PER_SEC;
  monotonic_time.tv_nsec = ns % NSEC_PER_SEC;

  clock_gettime(CLOCK_MONOTONIC_RAW, &monotonic_sample);
  clock_gettime(CLOCK_REALTIME, &real_sample);

  time_diff.tv_sec = real_sample.tv_sec - monotonic_sample.tv_sec;
  time_diff.tv_nsec = real_sample.tv_nsec - monotonic_sample.tv_nsec;

  real_time->tv_sec = monotonic_time.tv_sec + time_diff.tv_sec;
  real_time->tv_nsec = monotonic_time.tv_nsec + time_diff.tv_nsec;
  if (real_time->tv_nsec >= NSEC_PER_SEC)
  {
          ++real_time->tv_sec;
          real_time->tv_nsec -= NSEC_PER_SEC;
  }
  else if (real_time->tv_nsec < 0)
  {
          --real_time->tv_sec;
          real_time->tv_nsec += NSEC_PER_SEC;
  }
  return;
}

} // namespace camera
} // namespace sensors
} // namespace aima