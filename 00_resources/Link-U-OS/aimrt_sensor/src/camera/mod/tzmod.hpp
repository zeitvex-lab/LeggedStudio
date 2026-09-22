// Copyright (c) 2025, AgiBot Inc.
// All rights reserved.

# pragma once

#include <memory>
#include <sys/wait.h>
#include <sys/epoll.h>
#include <sys/ioctl.h>
#include <fcntl.h>
#include <bitset>
#include <opencv2/opencv.hpp>

// tzcam sdk
#include <hb_vin_interface.h>
#include <camera_sys.h>

#include "src/all_in_one/include/aimrte.h"
#include "src/camera/v4l2/nvcam.hpp"
#include <sensor_msgs/msg/image.hpp>
#include <sensor_msgs/msg/compressed_image.hpp>
#include <foxglove_msgs/msg/compressed_video.hpp>
#include "src/camera/convert/yuv2bgr.hpp"
#include "src/camera/utils/calibration.hpp"
#include "aimdk/protocol/hal/sensors/cameras_intrinsic.h"
#include "src/camera/convert/yuv2jpg.hpp"
#include "src/camera/stream/stream.hpp"
#include "src/camera/stream/h264raw.hpp"

#define MAX_CAMERA_NUM 16

namespace aima::sensors::camera {

struct TzCamera {
    std::string name;
    std::shared_ptr<NvCam> nv_cam;
    std::shared_ptr<ImgConverter> img_converter;
    std::shared_ptr<Yuyv2Jpg> compressed_converter;
    std::shared_ptr<isx031c_calibration_data> calibration;
    std::shared_ptr<Streamer> streamer;
    int output_width;
    int output_height;
};

class TzCameraMod : public aimrte::Mod {
    public:
        struct Port {
            int pipeid;
            std::string topic_name;
            std::string compressed_topic_name;
            std::string streamer_topic_name;
            std::string name;
            int output_width;
            int output_height;
            std::string converter;
            std::string compressed_converter;
            std::string streamer;
            std::string i2c_dev;
            int i2c_addr;
        };

        struct Option {
            std::string cfg_path;
            std::map<std::string, std::vector<std::string>> work_mode;
            std::vector<Port> ports;
            std::string calibration_path;
            bool enable_after_startup;
        };
        
    protected:
        void OnConfigure(aimrte::ctx::ModuleCfg& cfg) override;
        bool OnInitialize() override;
        bool OnStart() override;
        void OnShutdown() override;

    private:
        int sensor_system(const char *pCmd);
        bool reset_camera();
        int reset_power();
        aimrte::Co<void> publish_image(int pipeid);
        aimrte::Co<void> publish_stream(int pipeid);
        bool start_camera();
        void stop_camera();
        int read_calibration(std::string dev, int addr, std::string camera_name, std::shared_ptr<isx031c_calibration_data> cali);
        
        // v4l2 camera map; key is pipeid
        std::map<int, TzCamera> camera_map_;
        std::map<int, aimrte::Pub<sensor_msgs::msg::Image>> channel_map_;
        std::map<int, aimrte::Pub<sensor_msgs::msg::CompressedImage>> compressed_channel_map_;
        std::map<int, aimrte::Pub<foxglove_msgs::msg::CompressedVideo>> stream_map_;
        Option option_;
        std::atomic<bool> is_capturing_{false};
        std::atomic<bool> is_paused_{false};
        // -2 not stop -1 stopping, 1 starting, 2 started
        std::atomic<int> is_start_{false};
        // 0 deactive, 1 normal mode, 2 data collection mode
        std::atomic<int> active_{false};
        aimrte::Exe exe_{"tzcamera"};
        struct epoll_event ev_[MAX_CAMERA_NUM];
        int reset_times_{0};
        std::map<std::string, std::bitset<8>> mode_set_;
        std::bitset<8> current_mode_;

        // rpc
        aimdk::protocol::res::CamerasIntrinsicService srv_intrinsic_;
};

}