// Copyright (c) 2025, AgiBot Inc.
// All rights reserved.

#pragma once

#include <cstdint>
#include <foxglove_msgs/msg/compressed_video.hpp>
#include "src/all_in_one/include/aimrte.h"

namespace aima::sensors::camera {

class Streamer {
    public:
        Streamer(int input_width, int input_height, int output_width, int output_height, int rate, const std::string& format)
            : input_width_(input_width), input_height_(input_height), output_width_(output_width), 
                output_height_(output_height), rate_(rate), format_(format) {}
        virtual ~Streamer() {}
        virtual int Init(const std::string& name) = 0;
        virtual int Start() = 0;
        virtual void Stop() = 0;
        virtual void PushImage(uint8_t* input) = 0;
        virtual void PushImageFd(int src_fd) = 0;
        virtual std::shared_ptr<foxglove_msgs::msg::CompressedVideo> GetFrame() = 0;

    protected:
        int input_width_;
        int input_height_;
        int output_width_;
        int output_height_;
        int rate_;
        std::string format_;
};

}