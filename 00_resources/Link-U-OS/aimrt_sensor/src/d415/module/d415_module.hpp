// Copyright (c) 2025, AgiBot Inc.
// All rights reserved.

#pragma once

#include <iostream>
#include <vector>
#include <map>
#include <memory>
#include <sensor_msgs/msg/compressed_image.hpp>
#include <sensor_msgs/msg/image.hpp>
#include <foxglove_msgs/msg/compressed_video.hpp>
#include <thread>

#include "librealsense2/rs.hpp"
#include "src/all_in_one/include/aimrte.h"
#include "src/camera/convert/yuv2bgr.hpp"

namespace aima {
namespace sensor {
namespace camera {
namespace d415 {


class RealtimeStats {
public:
    explicit RealtimeStats(const std::string& name)
        : count_(0),
          avg_(0.0),
          min_(std::numeric_limits<double>::max()),
          max_(std::numeric_limits<double>::lowest()),
          name_(name),
          last_ts_(-1.0) {}

    void update(double ts) {
        std::lock_guard<std::mutex> lock(mtx_);
        if (last_ts_ >= 0) {
            double dt = ts - last_ts_;

            dt_history_.push_back(dt);

            count_++;
            avg_ += (dt - avg_) / count_;
            if (dt < min_) min_ = dt;
            if (dt > max_) max_ = dt;
        }
        last_ts_ = ts;
    }

    void print(bool reset_after_print = false) {
        std::lock_guard<std::mutex> lock(mtx_);
        if (count_ == 0) {
            return;
        }

        // 基础统计打印
        AIMRTE_INFO("[{}] cnt={} avg={} min={} max={}",
                    name_, count_,
                    static_cast<int>(avg_ * 1000),
                    static_cast<int>(min_ * 1000),
                    static_cast<int>(max_ * 1000));

        std::ostringstream oss;
        oss << "[" << name_ << "] ";
        for (size_t i = 0; i < dt_history_.size(); ++i) {
            oss << static_cast<int>(dt_history_[i] * 1000);
            if (i + 1 < dt_history_.size())
                oss << ", ";
        }
        AIMRTE_INFO("{}", oss.str());

        if (reset_after_print)
            reset();
    }


    void reset() {
        count_ = 0;
        avg_ = 0.0;
        min_ = std::numeric_limits<double>::max();
        max_ = std::numeric_limits<double>::lowest();
        last_ts_ = -1.0;
        dt_history_.clear();
    }

    size_t getCount() const {
        return count_;
    }

private:
    mutable std::mutex mtx_;
    size_t count_;
    double avg_, min_, max_;
    std::string name_;
    double last_ts_;
    std::vector<double> dt_history_;
};


class RGBDStatsManager {
public:
    explicit RGBDStatsManager(size_t report_interval)
        : color_stats_("Color Δt ms"),
          depth_stats_("Depth Δt ms"),
          report_interval_(report_interval) {}

    void updateColor(double color_ts) {
        color_stats_.update(color_ts);

        // 以颜色通道帧数为基准触发打印
        if (color_stats_.getCount() >= report_interval_) {
            printAndReset();
        }
    }

    void updateDepth(double depth_ts) {
        depth_stats_.update(depth_ts);
    }

private:
    void printAndReset() {
        color_stats_.print(true); // 打印后重置
        depth_stats_.print(true);
    }

private:
    RealtimeStats color_stats_;
    RealtimeStats depth_stats_;
    size_t report_interval_;
};


class D415Mod : public aimrte::Mod {
   public:
    // default config, reflect from config file
    struct D415Config {
        bool enable_device{true};

        // color
        bool pub_color_topic{true};
        std::string color_frame_id{"d415"};
        int color_height{720};
        int color_width{1280};
        int color_fps{15};
        // depth
        bool pub_depth_topic{true};
        std::string depth_frame_id{"d415"};
        int depth_height{720};
        int depth_width{1280};
        int depth_fps{15};
        // h264
        bool pub_color_h264_topic{false};
        // compressed
        bool pub_color_compressed_topic{false};

        void Print(const std::string& prefix = "") const {
            auto p = [&](const std::string& key, auto value) {
                std::cout << prefix << "  " << key << ": " << value << "\n";
            };

            p("enable_device", enable_device);
            p("pub_color_topic", pub_color_topic);
            p("color_frame_id", color_frame_id);
            p("color_height", color_height);
            p("color_width", color_width);
            p("color_fps", color_fps);

            p("pub_depth_topic", pub_depth_topic);
            p("depth_frame_id", depth_frame_id);
            p("depth_height", depth_height);
            p("depth_width", depth_width);
            p("depth_fps", depth_fps);

            p("pub_color_h264_topic", pub_color_h264_topic);
            p("pub_color_compressed_topic", pub_color_compressed_topic);
        }
    };

    struct Configs {
        bool enable_after_startup{false};
        int reinit_after_no_data_ms{3000};
        // topic name
        std::string color_topic_name{"/aima/hal/rgbd_camera/head_front/color"};
        std::string depth_topic_name{"/aima/hal/rgbd_camera/head_front/depth"};
        std::string color_h264_topic_name{"/aima/hal/rgbd_camera/head_front/color/h264"};
        std::string color_compressed_topic_name{"/aima/hal/rgbd_camera/head_front/color/compressed"}; // data collector模式发布这个
        // intrinsic path
        std::string color_intrinsics_path{"/agibot/data/param/hal/intrinsic/head_front_color.yaml"};
        std::string depth_intrinsics_path{"/agibot/data/param/hal/intrinsic/head_front_depth.yaml"};
        // mode
        std::string default_mode{"normal_mode"};
        std::unordered_map<std::string, std::string> sm_state_to_mode_map;
        // camera config
        std::unordered_map<std::string, D415Config> mode_to_cfg_map;

        void Print(const std::string& prefix = "") const {
            auto p = [&](const std::string& key, auto value) {
                std::cout << prefix << key << ": " << value << "\n";
            };

            std::cout << prefix << "Configs:\n";
            p("enable_after_startup", enable_after_startup);
            p("reinit_after_no_data_ms", reinit_after_no_data_ms);
            p("color_topic_name", color_topic_name);
            p("depth_topic_name", depth_topic_name);
            p("color_h264_topic_name", color_h264_topic_name);
            p("color_compressed_topic_name", color_compressed_topic_name);
            p("color_intrinsics_path", color_intrinsics_path);
            p("depth_intrinsics_path", depth_intrinsics_path);
            p("default_mode", default_mode);

            std::cout << prefix << "sm_state_to_mode_map:\n";
            for (const auto& [key, val] : sm_state_to_mode_map) {
                std::cout << prefix << "  " << key << " => " << val << "\n";
            }

            std::cout << prefix << "mode_to_cfg_map:\n";
            for (const auto& [mode, cfg] : mode_to_cfg_map) {
                std::cout << prefix << "  [" << mode << "]\n";
                cfg.Print(prefix + "    ");
            }
        }
    };

   protected:
    void OnConfigure(aimrte::ctx::ModuleCfg& cfg) override;
    bool OnInitialize() override;
    bool OnStart() override;
    void OnShutdown() override;
    
   private:
    bool StartPipeline();
    void StopPipeline();
    void PublishImage(std::stop_token st);
    void SetThreadName(const std::string& name);
    void SaveIntrinsics(const rs2::pipeline_profile& profile);
    std::string GetTargetMode(const std::string& sm_target_state);
    void SetD415Mode(const std::string& current_sm_state = "normal_mode");
    void HandleRestartRequested(std::stop_token st);

   private:
    Configs configs_;
    D415Config current_config_;
    std::string current_mode_{"shutdown_mode"};  // 默认不工作

    std::jthread pub_img_thread_;
    std::atomic<bool> is_running_{false};         // 表示当前 pipeline 是否在运行
    std::mutex stop_mutex_;           // 用于保护 Start/Stop 的并发调用
    std::jthread pipeline_init_thread_;

    std::jthread restart_manager_thread_;
    std::atomic<bool> pipeline_restart_requested_{false};

    aimrte::Pub<sensor_msgs::msg::Image> color_pub_;
    aimrte::Pub<sensor_msgs::msg::Image> depth_pub_;
    aimrte::Pub<foxglove_msgs::msg::CompressedVideo> color_h264_pub_;
    aimrte::Pub<sensor_msgs::msg::CompressedImage> color_compressed_pub_;

    std::unique_ptr<aima::sensors::camera::Yuyv2Bgr> yuyv_converter_;
    std::vector<uint8_t> bgr_buffer_;

    rs2::pipeline pipeline_;
    rs2::config cfg_;

    RGBDStatsManager ts_diff_stats_{15};
};

}  // namespace d415
}  // namespace camera
}  // namespace sensor
}  // namespace aima
