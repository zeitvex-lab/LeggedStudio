// Copyright (c) 2025, AgiBot Inc.
// All rights reserved.

#include "src/dcw2/module/dcw2_module.hpp"

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
namespace dcw2 {

namespace {

double GetFrameTime() {
    AIMRTE_DEBUG_STREAM("timestamp type: system time");
    auto now = std::chrono::system_clock::now();
    auto now_sec
        = std::chrono::time_point_cast<std::chrono::milliseconds>(now).time_since_epoch().count()
          / 1000.0;
    return now_sec;
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

void SaveSingleIntrinsicsYaml(const OBCameraIntrinsic &intr,
                              const OBCameraDistortion &dist,
                              const std::string &camera_name,
                              const std::string &file_path) {
    YAML::Emitter out;

    out << YAML::BeginMap;
    out << YAML::Key << "model_type" << YAML::Value << "PINHOLE";  // dcw2相机固定为针孔
    out << YAML::Key << "camera_name" << YAML::Value << camera_name;
    out << YAML::Key << "image_width" << YAML::Value << intr.width;
    out << YAML::Key << "image_height" << YAML::Value << intr.height;

    out << YAML::Key << "distortion_parameters" << YAML::Value;
    out << YAML::BeginMap;
    out << YAML::Key << "k1" << YAML::Value << dist.k1;
    out << YAML::Key << "k2" << YAML::Value << dist.k2;
    out << YAML::Key << "p1" << YAML::Value << dist.p1;
    out << YAML::Key << "p2" << YAML::Value << dist.p2;
    out << YAML::EndMap;

    out << YAML::Key << "projection_parameters" << YAML::Value;
    out << YAML::BeginMap;
    out << YAML::Key << "fx" << YAML::Value << intr.fx;
    out << YAML::Key << "fy" << YAML::Value << intr.fy;
    out << YAML::Key << "cx" << YAML::Value << intr.cx;
    out << YAML::Key << "cy" << YAML::Value << intr.cy;
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

void Dcw2Mod::OnConfigure(aimrte::ctx::ModuleCfg &cfg) {
    using namespace aimrte::cfg;
    cfg[Module::Basic].Config(config_);

    if (config_.color_topic_name.has_value()) {
        AIMRTE_INFO_STREAM("Pub color image topic: " << config_.color_topic_name.value());
        color_pub_ = aimrte::Pub<sensor_msgs::msg::Image>(config_.color_topic_name.value());
        cfg[Ch::ros2].Def(color_pub_);
    }

    if (config_.depth_topic_name.has_value()) {
        AIMRTE_INFO_STREAM("Pub depth image topic: " << config_.depth_topic_name.value());
        depth_pub_ = aimrte::Pub<sensor_msgs::msg::Image>(config_.depth_topic_name.value());
        cfg[Ch::ros2].Def(depth_pub_);
    }
}

bool Dcw2Mod::OnInitialize() {
    // -> 扫描并过滤 Dcw2
    // -> 如果有多个 Dcw2，选第一个
    // -> 如果没有 Dcw2，初始化失败

    try {
        AIMRTE_INFO_STREAM("Start scan orbbec devices.");
        // 1. 扫描 RealSense 设备
        ob::Context ctx;
        auto devices = ctx.queryDeviceList();

        if (devices->deviceCount() == 0) {
            AIMRTE_ERROR_STREAM("No orbbec devices found.");
            return false;
        }

        selected_device_ = devices->getDevice(0);

        if (!selected_device_) {
            AIMRTE_ERROR_STREAM("Get first obrrec device failed.");
            return false;
        }

        // 2. 配置流参数
        pipeline_ = std::make_shared<ob::Pipeline>(selected_device_);

        auto color_profiles = pipeline_->getStreamProfileList(OB_SENSOR_COLOR);
        auto depth_profiles = pipeline_->getStreamProfileList(OB_SENSOR_DEPTH);

        auto color_profile = color_profiles->getVideoStreamProfile(config_.color_width,
                                                                   config_.color_height,
                                                                   OB_FORMAT_MJPEG,
                                                                   config_.color_fps);

        auto depth_profile = depth_profiles->getVideoStreamProfile(config_.depth_width,
                                                                   config_.depth_height,
                                                                   OB_FORMAT_Y11,
                                                                   config_.depth_fps);

        cfg_ = std::make_shared<ob::Config>();
        cfg_->enableStream(color_profile);
        cfg_->enableStream(depth_profile);
        cfg_->setAlignMode(ALIGN_D2C_HW_MODE);
    } catch (const ob::Error &e) {
        AIMRTE_ERROR_STREAM("initializ orbbec error: " << e.getMessage());
        return false;
    } catch (const std::exception &e) {
        AIMRTE_ERROR_STREAM("Standard exception during initialization: " << e.what());
        return false;
    }

    return true;
}

bool Dcw2Mod::OnStart() {
    // 启动
    try {
        // 让SDK检查配置并抛出异常，这里不用额外精力去做参数的有效性判断
        pipeline_->start(cfg_);

        // 每次模块启动，获取并保存内参到本地文件
        SaveIntrinsics(pipeline_->getCameraParam());

        // 接收并发布数据的工作线程
        pub_img_thread_ = std::jthread([this](std::stop_token st) {
            this->SetThreadName("publish_image");
            this->PublishImage(st);
        });
    } catch (const ob::Error &e) {
        AIMRTE_ERROR_STREAM("Orbbec error during pipeline start:\n" << e.getMessage());
        return false;
    } catch (const std::exception &e) {
        AIMRTE_ERROR_STREAM("Standard exception: " << e.what());
        return false;
    }

    return true;
}

void Dcw2Mod::OnShutdown() {
    AIMRTE_INFO_STREAM("receive stop signal, start stop work thread");
    pub_img_thread_.request_stop();
    pub_img_thread_.join();
    AIMRTE_INFO_STREAM("work thread stop done. start stop dcw2 pipeline");
    pipeline_->stop();
    AIMRTE_INFO_STREAM("dcw2 pipeline stop done");
}

void Dcw2Mod::PublishImage(std::stop_token st) {
    AIMRTE_INFO_STREAM("start PublishImage thread");

    // pass context pointer to subthread
    GetContextPtr()->LetMe();

    const unsigned int kWaitTimeoutMs = 1000;  // 1s

    try {
        while (!st.stop_requested()) {
            try {
                // 1s超时等待，避免pipeline被意外停止导致长时间等待
                auto frame_set = pipeline_->waitForFrames(kWaitTimeoutMs);
                if (!frame_set) {
                    AIMRTE_WARN_STREAM("waitForFrames() returned null frameset");
                    continue;
                }

                const auto msg_stamp = ToBuiltinTime(GetFrameTime());

                // 获取彩色帧
                auto color_frame = frame_set->colorFrame();
                if (color_frame && color_pub_.IsValid()) {
                    size_t data_size = color_frame->dataSize();
                    const uint8_t *data_ptr = static_cast<const uint8_t *>(color_frame->data());

                    if (!data_ptr || data_size == 0) {
                        AIMRTE_WARN_STREAM("color_frame data invalid");
                        continue;
                    }

                    std::vector<uint8_t> jpeg_data(data_ptr, data_ptr + data_size);

                    cv::Mat color_bgr;
                    try {
                        color_bgr = cv::imdecode(jpeg_data, cv::IMREAD_COLOR);
                    } catch (const cv::Exception &e) {
                        AIMRTE_ERROR_STREAM("cv::imdecode exception: " << e.what());
                        continue;
                    }

                    if (color_bgr.empty()) {
                        AIMRTE_WARN_STREAM("mjpg decode failed");
                        continue;
                    }

                    auto color_msg =
                        cv_bridge::CvImage(std_msgs::msg::Header(), "bgr8", color_bgr).toImageMsg();
                    color_msg->header.frame_id = config_.color_frame_id;
                    color_msg->header.stamp = msg_stamp;

                    color_pub_.Publish(*color_msg);
                }

                // 获取深度帧
                auto depth_frame = frame_set->depthFrame();
                if (depth_frame && depth_pub_.IsValid()) {
                    void *depth_ptr = depth_frame->data();
                    if (!depth_ptr) {
                        AIMRTE_WARN_STREAM("depth_frame data invalid");
                        continue;
                    }

                    cv::Mat depth_img(cv::Size(depth_frame->width(), depth_frame->height()),
                                      CV_16UC1,
                                      depth_ptr,
                                      cv::Mat::AUTO_STEP);

                    auto depth_msg =
                        cv_bridge::CvImage(std_msgs::msg::Header(), "16UC1", depth_img).toImageMsg();
                    depth_msg->header.stamp = msg_stamp;
                    depth_msg->header.frame_id = config_.depth_frame_id;

                    depth_pub_.Publish(*depth_msg);
                }
            }
            catch (const std::exception &e) {
                AIMRTE_ERROR_STREAM("Standard exception in PublishImage loop: " << e.what());
            }
            catch (...) {
                AIMRTE_ERROR_STREAM("Unknown exception in PublishImage loop");
            }
        }
    }
    catch (const std::exception &e) {
        AIMRTE_ERROR_STREAM("Fatal exception in PublishImage main loop: " << e.what());
    }
    catch (...) {
        AIMRTE_ERROR_STREAM("Fatal unknown exception in PublishImage main loop");
    }

    AIMRTE_INFO_STREAM("stop PublishImage thread");
}


void Dcw2Mod::SetThreadName(const std::string &name) {
#if defined(__linux__)
    // pthread_setname_np 限制线程名长度最多16字节（包含 '\0'）
    std::string truncated = name.substr(0, 15);
    pthread_setname_np(pthread_self(), truncated.c_str());
#endif
}

void Dcw2Mod::SaveIntrinsics(const OBCameraParam &camera_param) {
    try {
        std::string color_yaml
            = config_.color_intrinsics_path.value_or("/tmp/dcw2_head_front_color.yaml");
        std::string depth_yaml
            = config_.depth_intrinsics_path.value_or("/tmp/dcw2_head_front_depth.yaml");

        SaveSingleIntrinsicsYaml(camera_param.rgbIntrinsic,
                                 camera_param.rgbDistortion,
                                 "dcw2_color",
                                 color_yaml);
        SaveSingleIntrinsicsYaml(camera_param.depthIntrinsic,
                                 camera_param.depthDistortion,
                                 "dcw2_depth",
                                 depth_yaml);
    } catch (const ob::Error &e) {
        AIMRTE_ERROR_STREAM("Failed to get intrinsics: " << e.getMessage());
    } catch (const std::exception &e) {
        AIMRTE_ERROR_STREAM("Exception while saving intrinsics: " << e.what());
    }
}

}  // namespace dcw2
}  // namespace camera
}  // namespace sensor
}  // namespace aima