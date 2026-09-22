// Copyright (c) 2025, AgiBot Inc.
// All rights reserved.

#include "src/d415/module/d415_module.hpp"

#include <cv_bridge/cv_bridge.h>
#include <pthread.h>
#include <yaml-cpp/yaml.h>

#include <builtin_interfaces/msg/time.hpp>
#include <chrono>
#include <opencv2/imgcodecs.hpp>
#include <thread>

namespace aima {
namespace sensor {
namespace camera {
namespace d415 {

namespace {

double GetFrameTime(const rs2::frame &frame) {
    rs2_timestamp_domain domain = frame.get_frame_timestamp_domain();
    if (domain == RS2_TIMESTAMP_DOMAIN_GLOBAL_TIME) {
        AIMRTE_DEBUG_STREAM("timestamp type: RS2_TIMESTAMP_DOMAIN_GLOBAL_TIME");
        // 使用 RealSense 设备提供的硬件时间戳（更精确）
        return frame.get_timestamp() / 1000.0;  // 默认是毫秒，转换为秒
    } else {
        // 退化到系统时间
        AIMRTE_DEBUG_STREAM("timestamp type: system time");
        auto now = std::chrono::system_clock::now();
        auto now_sec = std::chrono::time_point_cast<std::chrono::milliseconds>(now)
                           .time_since_epoch()
                           .count()
                       / 1000.0;
        return now_sec;
    }
}

builtin_interfaces::msg::Time ToBuiltinTime(double time_sec) {
    builtin_interfaces::msg::Time t;

    int32_t sec = static_cast<int32_t>(std::floor(time_sec));

    double frac = time_sec - static_cast<double>(sec);  // 0 <= frac < 1
    uint32_t nsec = static_cast<uint32_t>(frac * 1e9);  // 0 <= nsec < 1e9

    t.sec = sec;
    t.nanosec = nsec;
    return t;
}

sensor_msgs::msg::CompressedImage ConvertToCompressedImage(
    const cv::Mat &img,
    const builtin_interfaces::msg::Time &stamp,
    const std::string &frame_id,
    const std::string &format = "jpeg") {
    sensor_msgs::msg::CompressedImage msg;
    msg.header.stamp = stamp;
    msg.header.frame_id = frame_id;
    msg.format = format;

    std::vector<uchar> buf;
    cv::imencode("." + format, img, buf);
    msg.data.assign(buf.begin(), buf.end());

    return msg;
}

void SaveSingleIntrinsicsYaml(const rs2_intrinsics &intr,
                              const std::string &camera_name,
                              const std::string &file_path) {
    YAML::Emitter out;

    out << YAML::BeginMap;
    out << YAML::Key << "model_type" << YAML::Value << "PINHOLE";  // D415相机固定为针孔
    out << YAML::Key << "camera_name" << YAML::Value << camera_name;
    out << YAML::Key << "image_width" << YAML::Value << intr.width;
    out << YAML::Key << "image_height" << YAML::Value << intr.height;

    out << YAML::Key << "distortion_parameters" << YAML::Value;
    out << YAML::BeginMap;
    out << YAML::Key << "k1" << YAML::Value << intr.coeffs[0];
    out << YAML::Key << "k2" << YAML::Value << intr.coeffs[1];
    out << YAML::Key << "p1" << YAML::Value << intr.coeffs[2];
    out << YAML::Key << "p2" << YAML::Value << intr.coeffs[3];
    out << YAML::EndMap;

    out << YAML::Key << "projection_parameters" << YAML::Value;
    out << YAML::BeginMap;
    out << YAML::Key << "fx" << YAML::Value << intr.fx;
    out << YAML::Key << "fy" << YAML::Value << intr.fy;
    out << YAML::Key << "cx" << YAML::Value << intr.ppx;
    out << YAML::Key << "cy" << YAML::Value << intr.ppy;
    out << YAML::EndMap;

    out << YAML::EndMap;

    namespace fs = std::filesystem;

    fs::path dir = fs::path(file_path).parent_path();
    if (!fs::exists(dir)) {
        AIMRTE_INFO_STREAM("Intrinsic target folder not exist, create: " << dir);
        fs::create_directories(dir);
    }

    std::ofstream fout(file_path);
    if (!fout.is_open()) {
        std::cerr << "Failed to open file: " << file_path << std::endl;
        AIMRTE_ERROR_STREAM("Failed to open intrinsic file: " << file_path);
        return;
    }

    fout << "%YAML:1.0\n";
    fout << "---\n";
    fout << out.c_str();
    fout << "\n";
    fout.close();

    AIMRTE_INFO_STREAM("Saved intrinsics to: " << file_path);
}

}  // namespace

bool D415Mod::StartPipeline() {
    if (is_running_) {
        AIMRTE_WARN_STREAM("StartPipeline() called but previous still running, do nothing");
        return true;
    }

    // 启动 jthread 异步初始化 pipeline
    pipeline_init_thread_ = std::jthread([this](std::stop_token st) {
        is_running_ = true;
        this->SetThreadName("init_device");

        const auto retry_interval_ms = 3000;

        AIMRTE_INFO_STREAM("Start RealSense D415 async initialization...");

        while (!st.stop_requested()) {
            try {
                rs2::device_list devices;
                try {
                    AIMRTE_INFO_STREAM("Scanning for RealSense devices...");
                    rs2::context ctx;
                    devices = ctx.query_devices();
                } catch (const rs2::error &e) {
                    AIMRTE_ERROR_STREAM("RealSense error during pipeline start:\n"
                                        << "  Function: " << e.get_failed_function() << "\n"
                                        << "  Args: " << e.get_failed_args() << "\n"
                                        << "  Message: " << e.what());
                } catch (const std::exception &e) {
                    AIMRTE_ERROR_STREAM("Pipeline start failed: " << e.what());
                }
                

                if (st.stop_requested()) break;

                if (devices.size() == 0) {
                    AIMRTE_WARN_STREAM("No RealSense devices found. Retrying...");
                    std::this_thread::sleep_for(std::chrono::milliseconds(retry_interval_ms));
                    continue;
                }

                rs2::device selected_device;
                for (auto &&dev : devices) {
                    std::string name = dev.get_info(RS2_CAMERA_INFO_NAME);
                    std::string serial = dev.get_info(RS2_CAMERA_INFO_SERIAL_NUMBER);
                    AIMRTE_INFO_STREAM("Found device: " << name << " (S/N: " << serial << ")");

                    if (name.find("D415") != std::string::npos) {
                        selected_device = dev;
                        AIMRTE_INFO_STREAM("Selected D415: " << serial);
                        break;  // 找到第一个 D415
                    }
                }

                if (!selected_device) {
                    AIMRTE_WARN_STREAM("No D415 device found. Retrying in 3 seconds...");
                    std::this_thread::sleep_for(std::chrono::milliseconds(retry_interval_ms));
                    continue;
                }

                // 配置 pipeline
                auto device_serial = selected_device.get_info(RS2_CAMERA_INFO_SERIAL_NUMBER);
                cfg_.enable_device(device_serial);

                cfg_.enable_stream(RS2_STREAM_COLOR, current_config_.color_width,
                                   current_config_.color_height, rs2_format::RS2_FORMAT_YUYV,
                                   current_config_.color_fps);
                cfg_.enable_stream(RS2_STREAM_DEPTH, current_config_.depth_width,
                                   current_config_.depth_height, RS2_FORMAT_Z16,
                                   current_config_.depth_fps);

                AIMRTE_INFO_STREAM("Current color config: " << current_config_.color_width << "x" << current_config_.color_height << "@" << current_config_.color_fps);
                AIMRTE_INFO_STREAM("Current depth config: " << current_config_.depth_width << "x" << current_config_.depth_height << "@" << current_config_.depth_fps);

                AIMRTE_INFO_STREAM("RealSense D415 configuration complete.");

                if (!yuyv_converter_) {
                    AIMRTE_INFO_STREAM("D415 config output color format: RS2_FORMAT_YUYV");
                    yuyv_converter_ = std::make_unique<aima::sensors::camera::Yuyv2Bgr>(
                        current_config_.color_width, current_config_.color_height,
                        current_config_.color_width, current_config_.color_height);
                    yuyv_converter_->init("test", nullptr);
                }

                try {
                    AIMRTE_INFO_STREAM("Start pipeline...");
                    auto profile = pipeline_.start(cfg_);
                    SaveIntrinsics(profile);
                } catch (const rs2::error &e) {
                    AIMRTE_ERROR_STREAM("RealSense error during pipeline start:\n"
                                        << "  Function: " << e.get_failed_function() << "\n"
                                        << "  Args: " << e.get_failed_args() << "\n"
                                        << "  Message: " << e.what());
                } catch (const std::exception &e) {
                    AIMRTE_ERROR_STREAM("Pipeline start failed: " << e.what());
                }

                // 启动图像发布线程
                pub_img_thread_ = std::jthread([this](std::stop_token st_pub) {
                    this->SetThreadName("publish_image");
                    this->PublishImage(st_pub);
                });

                
                AIMRTE_INFO_STREAM("Pipeline started successfully.");
                break;  // 成功后退出循环
            } catch (const rs2::error &e) {
                AIMRTE_ERROR_STREAM("RealSense error during pipeline start:\n"
                                    << "  Function: " << e.get_failed_function() << "\n"
                                    << "  Args: " << e.get_failed_args() << "\n"
                                    << "  Message: " << e.what());
            } catch (const std::exception &e) {
                AIMRTE_ERROR_STREAM("Pipeline start failed: " << e.what());
            }

            if (st.stop_requested()) break;

            cfg_ = rs2::config();
            yuyv_converter_.reset();
            AIMRTE_WARN_STREAM("Init failed. Retrying in 3 seconds...");
            std::this_thread::sleep_for(std::chrono::milliseconds(retry_interval_ms));
        }

        AIMRTE_INFO_STREAM("Pipeline initialization thread exiting.");
    });

    return true;  // 异步触发，立即返回
}



void D415Mod::PublishImage(std::stop_token st) {
    AIMRTE_INFO_STREAM("start PublishImage thread");

    // pass context pointer to subthread
    GetContextPtr()->LetMe();

    rs2::align align_to_color(RS2_STREAM_COLOR);

    bool trigger_restart = false;

    try {
        while (!st.stop_requested()) {
            try {
                // 1s超时等待，避免pipeline被意外停止导致长时间等待
                // 如果超时1s没有获取到数据，则直接进入catch部分，打印日志，然后进入下一轮等待
                rs2::frameset frames = pipeline_.wait_for_frames(configs_.reinit_after_no_data_ms);

                AIMRTE_DEBUG_STREAM(">>>>>>> one frameset handle start");

                // 对齐深度到彩色
                AIMRTE_DEBUG_STREAM(" >> align depth to color start");
                rs2::frameset aligned_frames = align_to_color.process(frames);
                AIMRTE_DEBUG_STREAM("    align depth to color end <<");

                // 获取彩色帧
                rs2::video_frame color_frame = aligned_frames.get_color_frame();
                if (color_frame && (color_pub_.IsValid() || color_compressed_pub_.IsValid())) {
                    void *bgr_data_ptr = (void *)color_frame.get_data();

                    rs2_format fmt = color_frame.get_profile().format();
                    if (fmt == RS2_FORMAT_YUYV && yuyv_converter_) {
                        auto bgr_data_size = color_frame.get_width() * color_frame.get_height() * 3;
                        if (bgr_buffer_.size() != bgr_data_size) {
                            bgr_buffer_.resize(bgr_data_size);
                        }

                        AIMRTE_DEBUG_STREAM(" >> convert yuyv to bgr start");
                        yuyv_converter_->convert(
                            reinterpret_cast<const uint8_t *>(color_frame.get_data()),
                            bgr_buffer_.data());
                        AIMRTE_DEBUG_STREAM("    convert yuyv to bgr end <<");

                        bgr_data_ptr = (void *)bgr_buffer_.data();
                    }

                    cv::Mat color_img(cv::Size(color_frame.get_width(), color_frame.get_height()),
                                      CV_8UC3,
                                      bgr_data_ptr,
                                      cv::Mat::AUTO_STEP);

                    const auto color_ts = GetFrameTime(color_frame);
                    const auto msg_stamp = ToBuiltinTime(color_ts);

                    if (color_pub_.IsValid() && current_config_.pub_color_topic) {
                        auto color_msg =
                            cv_bridge::CvImage(std_msgs::msg::Header(), "bgr8", color_img)
                                .toImageMsg();
                        color_msg->header.frame_id = current_config_.color_frame_id;
                        color_msg->header.stamp = msg_stamp;
                        AIMRTE_DEBUG_STREAM(">> pub color img start");
                        color_pub_.Publish(*color_msg);
                        AIMRTE_DEBUG_STREAM("   pub color img end <<");
                        ts_diff_stats_.updateColor(color_ts);
                    }

                    if (color_compressed_pub_.IsValid() && current_config_.pub_color_compressed_topic) {
                        // TODO: data
                        // collector模式下才会发布压缩格式，这个模式下cpu资源足够，先使用CPU进行压缩，后续优化可以使用硬件加速
                        auto compressed_msg = ConvertToCompressedImage(
                            color_img, msg_stamp, current_config_.color_frame_id, "jpeg");
                        AIMRTE_DEBUG_STREAM(">> pub compressed color img start");
                        color_compressed_pub_.Publish(compressed_msg);
                        AIMRTE_DEBUG_STREAM("   pub compressed color img end <<");
                    }
                }

                // 获取深度帧
                rs2::depth_frame depth_frame = aligned_frames.get_depth_frame();
                if (depth_frame && depth_pub_.IsValid() && current_config_.pub_depth_topic) {
                    cv::Mat depth_img(cv::Size(depth_frame.get_width(), depth_frame.get_height()),
                                      CV_16UC1,
                                      (void *)depth_frame.get_data(),
                                      cv::Mat::AUTO_STEP);

                    auto depth_msg =
                        cv_bridge::CvImage(std_msgs::msg::Header(), "16UC1", depth_img).toImageMsg();
                    const auto depth_ts = GetFrameTime(depth_frame);
                    depth_msg->header.stamp = ToBuiltinTime(depth_ts);
                    depth_msg->header.frame_id = current_config_.depth_frame_id;

                    AIMRTE_DEBUG_STREAM(">> pub depth img start");
                    depth_pub_.Publish(*depth_msg);
                    AIMRTE_DEBUG_STREAM("   pub depth img end <<");
                    ts_diff_stats_.updateDepth(depth_ts);
                }

                AIMRTE_DEBUG_STREAM(" one frameset handle done <<<<<<<<<");
            }
            catch (const rs2::error &e) {
                AIMRTE_ERROR_STREAM("RealSense SDK error caught in PublishImage():");
                AIMRTE_ERROR_STREAM("  Function: " << e.get_failed_function());
                AIMRTE_ERROR_STREAM("  Args: " << e.get_failed_args());
                AIMRTE_ERROR_STREAM("  Message: " << e.what());
                AIMRTE_ERROR_STREAM("  Reinitializing pipeline...");
                AIMRTE_WARN_STREAM("Pipeline error detected, attempting recovery...");

                trigger_restart = true;
            }
            catch (const std::exception &e) {
                AIMRTE_ERROR_STREAM("Standard exception caught in PublishImage(): "
                                    << e.what());
                trigger_restart = true;
            }
            catch (...) {
                AIMRTE_ERROR_STREAM("Unknown exception caught in PublishImage().");
                trigger_restart = true;
            }

            if(trigger_restart) {
                break;
            }
        }
    }
    catch (const std::exception &e) {
        AIMRTE_ERROR_STREAM("Fatal exception in PublishImage main loop: " << e.what());
        trigger_restart = true;
    }
    catch (...) {
        AIMRTE_ERROR_STREAM("Fatal unknown exception in PublishImage main loop.");
        trigger_restart = true;
    }

    AIMRTE_INFO_STREAM("stop PublishImage thread");

    if(trigger_restart) {
        pipeline_restart_requested_.store(true);
        AIMRTE_INFO_STREAM("Trigger restart");
    }
}

void D415Mod::SetThreadName(const std::string &name) {
#if defined(__linux__)
    // pthread_setname_np 限制线程名长度最多16字节（包含 '\0'）
    std::string truncated = name.substr(0, 15);
    pthread_setname_np(pthread_self(), truncated.c_str());
#endif
}

void D415Mod::SaveIntrinsics(const rs2::pipeline_profile &profile) {
    try {
        auto color_stream = profile.get_stream(RS2_STREAM_COLOR).as<rs2::video_stream_profile>();
        auto depth_stream = profile.get_stream(RS2_STREAM_DEPTH).as<rs2::video_stream_profile>();

        rs2_intrinsics color_intrinsics = color_stream.get_intrinsics();
        rs2_intrinsics depth_intrinsics = depth_stream.get_intrinsics();

        SaveSingleIntrinsicsYaml(color_intrinsics, "d415_color", configs_.color_intrinsics_path);
        SaveSingleIntrinsicsYaml(depth_intrinsics, "d415_depth", configs_.depth_intrinsics_path);
    } catch (const rs2::error &e) {
        AIMRTE_ERROR_STREAM("Failed to get intrinsics: " << e.what());
    } catch (const std::exception &e) {
        AIMRTE_ERROR_STREAM("Exception while saving intrinsics: " << e.what());
    }
}

void D415Mod::StopPipeline() {
    AIMRTE_INFO_STREAM("receive stop signal, start stop work thread");

    // 停止 pipeline 初始化线程
    if (pipeline_init_thread_.joinable()) {
        pipeline_init_thread_.request_stop();
        pipeline_init_thread_.join();
    }

    AIMRTE_INFO_STREAM("stop init thread done");

    // 停止线程
    if (pub_img_thread_.joinable()) {
        pub_img_thread_.request_stop();
        pub_img_thread_.join();
    }

    AIMRTE_INFO_STREAM("stop pub image thread done");

    try {
        AIMRTE_INFO_STREAM("realsense pipeline is running, start stop");
        pipeline_.stop();
    } catch (const rs2::error& e) {
        AIMRTE_ERROR_STREAM("pipeline stop failed: " << e.what());
    }  catch (...) {
        AIMRTE_WARN_STREAM("Unknown error during pipeline stop.");
    }

    AIMRTE_INFO_STREAM("stop realsense pipeline done");


    // 2. 清空旧的配置（防止设备句柄残留）
    cfg_ = rs2::config();
    yuyv_converter_.reset();

    AIMRTE_INFO_STREAM("release resource done");

    is_running_ = false;
}


void D415Mod::OnConfigure(aimrte::ctx::ModuleCfg &cfg) {
    using namespace aimrte::cfg;
    cfg[Module::Basic].Config(configs_);

    configs_.Print();

    // 只能运行一次，所以在最开始将所有可能发布的topic进行初始化
    AIMRTE_INFO_STREAM("Pub color image topic: " << configs_.color_topic_name);
    color_pub_ = aimrte::Pub<sensor_msgs::msg::Image>(configs_.color_topic_name);
    cfg[Ch::ros2].Def(color_pub_);

    AIMRTE_INFO_STREAM("Pub depth image topic: " << configs_.depth_topic_name);
    depth_pub_ = aimrte::Pub<sensor_msgs::msg::Image>(configs_.depth_topic_name);
    cfg[Ch::ros2].Def(depth_pub_);

    AIMRTE_INFO_STREAM("Pub color h264 image topic: " << configs_.color_h264_topic_name);
    color_h264_pub_ = aimrte::Pub<foxglove_msgs::msg::CompressedVideo>(configs_.color_h264_topic_name);
    cfg[Ch::ros2].Def(color_h264_pub_);

    AIMRTE_INFO_STREAM("Pub color compressed image topic: " << configs_.color_compressed_topic_name);
    color_compressed_pub_ = aimrte::Pub<sensor_msgs::msg::CompressedImage>(
        configs_.color_compressed_topic_name);
    cfg[Ch::ros2].Def(color_compressed_pub_);
}

std::string D415Mod::GetTargetMode(const std::string& sm_target_state) {
    std::string mode = configs_.default_mode;
    if(configs_.sm_state_to_mode_map.find(sm_target_state) != configs_.sm_state_to_mode_map.end()) {
        mode = configs_.sm_state_to_mode_map.at(sm_target_state);
    }
    return mode;
}

void D415Mod::SetD415Mode(const std::string& d415_target_mode) {
    // 使用默认配置初始化，未收到SM命令时使用默认工作模式工作
    if(configs_.mode_to_cfg_map.find(d415_target_mode) != configs_.mode_to_cfg_map.end()) {
        current_config_ = configs_.mode_to_cfg_map.at(d415_target_mode);
        current_mode_ = d415_target_mode;
        AIMRTE_INFO_STREAM("update current_mode_ to: " << d415_target_mode);
    } else {
        AIMRTE_WARN_STREAM("cannot find d415_target_mode: " << d415_target_mode << " in configs_.mode_to_cfg_map, please check config");
    }
}

bool D415Mod::OnInitialize() {
    AIMRTE_INFO_STREAM("OnInitialize: skipping actual initialization");
    return true;
}

void D415Mod::HandleRestartRequested(std::stop_token st) {
    while (!st.stop_requested()) {
        if (pipeline_restart_requested_.exchange(false)) {
            AIMRTE_INFO_STREAM("pipeline_restart_requested is true, restart pipeline");
            StopPipeline();
            StartPipeline();
        }
        std::this_thread::sleep_for(std::chrono::milliseconds(1000)); // 每1s检查一次
    }
}


bool D415Mod::OnStart() {
    restart_manager_thread_ = std::jthread([this](std::stop_token st) {
        this->SetThreadName("restart_mgr");
        this->HandleRestartRequested(st);
    });

    if(!configs_.enable_after_startup) {
        AIMRTE_INFO_STREAM("enable_after_startup is false, wait sm enable signal");
        return true;
    }

    SetD415Mode(configs_.default_mode);

    return StartPipeline();
}

void D415Mod::OnShutdown() {
    StopPipeline();

    if (restart_manager_thread_.joinable()) {
        restart_manager_thread_.request_stop();
        restart_manager_thread_.join();
    }
    AIMRTE_INFO_STREAM("stop init thread done");

    AIMRTE_INFO_STREAM("shutdown done");
}


}  // namespace d415
}  // namespace camera
}  // namespace sensor
}  // namespace aima