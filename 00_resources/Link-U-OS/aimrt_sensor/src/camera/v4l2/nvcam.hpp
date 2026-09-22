// Copyright (c) 2025, AgiBot Inc.
// All rights reserved.

#pragma once

#include <cstdint>
#include <fcntl.h>
#include <sys/ioctl.h>

extern "C" {
#include <linux/videodev2.h>
}

#include "src/all_in_one/include/aimrte.h"
// #include "src/thirdparty/nv_multimedia/NvBufSurface.h"
#include "NvBufSurface.h"

#define V4L2_BUFFER_NUM 16
#define V4L2_VIDEO_FORMAT V4L2_PIX_FMT_YUYV

namespace aima {
namespace sensors {
namespace camera {

/* Correlate v4l2 pixel format and NvBuffer color format */
typedef struct {
  unsigned int v4l2_pixfmt;
  NvBufSurfaceColorFormat nvbuff_color;
} nv_color_fmt;

typedef struct {
        unsigned char *start;
        unsigned int size;
        int dmabuff_fd;
} nv_buffer;

typedef struct {
    int ts_sec;
    int ts_nsec;
    int width;
    int height;
    uint8_t *data_ptr;
    int data_len;
    int dma_fd;
} rawimg_buffer;


class NvCam {
    public:
        struct Option {
            int width;
            int height;
            int fps;
            int pixfmt;
            int pipeid;
            int index;
        };
        
        NvCam();
        virtual ~NvCam();
        int Init(Option option);
        int Release();
        int Start();
        int Stop();
        // return buf index
        int DataPoll(std::shared_ptr<rawimg_buffer> img);
        int GetData(std::shared_ptr<rawimg_buffer> img);
        int GetFd();

    private:
        bool checkCapabilities();
        bool initDevice();
        bool setFormat();
        bool startCapture();
        bool stopCapture();
        inline int xioctl(int fd, int request, void *arg);
        int getTsOffset();
        void cpuToRealtime(timeval cpu_time, timespec* real_time);

        inline NvBufSurfaceColorFormat getNvBufferColorFormat(uint32_t v4l2_pixfmt);

        Option opt_;
        int32_t fd_;
        uint32_t pixel_format_ = V4L2_PIX_FMT_YUYV;
        std::string dev_name_;
        nv_buffer *nvbuff_;
        NvBufSurface *pSurf_[V4L2_BUFFER_NUM] = {NULL};
        struct pollfd fds_[1];
        uint64_t nsec_offset_ = 0;
};

}
}
}