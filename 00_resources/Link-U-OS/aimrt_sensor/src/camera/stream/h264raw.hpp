// Copyright (c) 2025, AgiBot Inc.
// All rights reserved.

#pragma once

#include "stream.hpp"

#include <queue>
#include <vector>
#include <mutex>
#include <condition_variable>
#include <rclcpp/rclcpp.hpp>

#include "NvBufSurface.h"
#include <NvVideoEncoder.h>

namespace aima::sensors::camera {

class H264RawStreamer : public Streamer {
    public:
    H264RawStreamer(int input_width, int input_height, int output_width, int output_height, int rate, const std::string& format)
        : Streamer(input_width, input_height, output_width, output_height, rate, format) {}
    ~H264RawStreamer();

    int Init(const std::string& name) override;
    int Start() override;
    void Stop() override;
    void PushImage(uint8_t* input) override;
    void PushImageFd(int src_fd) override;
    std::shared_ptr<foxglove_msgs::msg::CompressedVideo> GetFrame() override;

    private:
    int createVideoEncoder(const std::string& name);
    static bool encoderCallback(struct v4l2_buffer* v4l2_buf, NvBuffer* buffer, NvBuffer *shared_buffer, void* arg) {
        H264RawStreamer *thiz = static_cast<H264RawStreamer*>(arg);
        return thiz->encoderCallbackImpl(v4l2_buf, buffer, shared_buffer);
    }
    bool encoderCallbackImpl(struct v4l2_buffer* v4l2_buf, NvBuffer* buffer, NvBuffer* shared_buffer);

    std::mutex queue_mtx_;
    std::queue<std::shared_ptr<foxglove_msgs::msg::CompressedVideo>> video_queue_;
    std::condition_variable cond_var_;

    std::vector<int> dma_fd_pool_;
    int dma_fd_pool_size_ = 128;
    NvBufSurf::NvCommonTransformParams transform_params_;
    NvVideoEncoder *video_encoder_ = nullptr;
    int default_bitrate_ = 4000000; // 4Mbps
    int frame_index_ = 0;
    std::atomic<bool> running_{false};
};

}