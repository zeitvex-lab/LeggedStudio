// Copyright (c) 2025, AgiBot Inc.
// All rights reserved.

#pragma once

#include <libobsensor/ObSensor.hpp>
#include <memory>
#include <sensor_msgs/msg/compressed_image.hpp>
#include <sensor_msgs/msg/image.hpp>
#include <thread>

#include "src/all_in_one/include/aimrte.h"

namespace aima {
namespace sensor {
namespace camera {
namespace dcw2 {

class Dcw2Mod : public aimrte::Mod {
   public:
    // default config, reflect from config file
    struct Dcw2Config {
        // color
        std::optional<std::string> color_topic_name;  // data collector模式无需原始图
        std::string color_frame_id{"dcw2"};
        std::optional<std::string> color_h264_topic_name;  // 正常模式发布这个
        int color_height{1280};
        int color_width{720};
        int color_fps{15};
        std::optional<std::string> color_intrinsics_path;

        // depth
        std::optional<std::string> depth_topic_name;
        std::string depth_frame_id{"dcw2"};
        int depth_height{1280};
        int depth_width{720};
        int depth_fps{15};
        std::optional<std::string> depth_intrinsics_path;
    };

   protected:
    void OnConfigure(aimrte::ctx::ModuleCfg& cfg) override;
    bool OnInitialize() override;
    bool OnStart() override;
    void OnShutdown() override;

   private:
    void PublishImage(std::stop_token st);
    void SetThreadName(const std::string& name);
    void SaveIntrinsics(const OBCameraParam& camera_param);

   private:
    Dcw2Config config_;

    std::jthread pub_img_thread_;

    aimrte::Pub<sensor_msgs::msg::Image> color_pub_;
    aimrte::Pub<sensor_msgs::msg::Image> depth_pub_;
    aimrte::Pub<sensor_msgs::msg::CompressedImage> color_compressed_pub_;

    std::shared_ptr<ob::Pipeline> pipeline_;
    std::shared_ptr<ob::Config> cfg_;
    std::shared_ptr<ob::Device> selected_device_;
};

}  // namespace dcw2
}  // namespace camera
}  // namespace sensor
}  // namespace aima
