// Copyright (c) 2025, AgiBot Inc.
// All rights reserved.

#include <chrono>
#include <time.h>

#include "tzmod.hpp"

namespace aima::sensors::camera {

void TzCameraMod::OnConfigure(aimrte::ctx::ModuleCfg &cfg) {
  using namespace aimrte::cfg;

  cfg[Module::Basic].Config(option_);
  cfg[Module::Executor].Declare(exe_);
  cfg[Rpc::mqtt | Rpc::http].Def(srv_intrinsic_);

  for (const auto &mode : option_.work_mode) {
    std::bitset<8> bs;
    auto vec = mode.second;
    if (std::find(vec.begin(), vec.end(), "raw") != vec.end()) {
        bs.set(0);
    }

    if (std::find(vec.begin(), vec.end(), "compressed") != vec.end()) {
        bs.set(1);
    }

    if (std::find(vec.begin(), vec.end(), "stream") != vec.end()) {
        bs.set(2);
    }
  
    mode_set_.emplace(mode.first, bs);
  }

  for (const auto &port : option_.ports) {
    if (!port.topic_name.empty()) {
      auto pub = aimrte::Pub<sensor_msgs::msg::Image>{port.topic_name};
      channel_map_.emplace(port.pipeid, pub);
      cfg[Ch::ros2].Def(channel_map_[port.pipeid]);
    }

    if (!port.compressed_topic_name.empty()) {
      auto compressed_pub =
          aimrte::Pub<sensor_msgs::msg::CompressedImage>{port.compressed_topic_name};
      compressed_channel_map_.emplace(port.pipeid, compressed_pub);
      cfg[Ch::ros2].Def(compressed_channel_map_[port.pipeid]);
    }

    if (!port.streamer_topic_name.empty()) {
      auto streamer_pub = aimrte::Pub<foxglove_msgs::msg::CompressedVideo>{
          port.streamer_topic_name};
      stream_map_.emplace(port.pipeid, streamer_pub);
      cfg[Ch::ros2].Def(stream_map_[port.pipeid]);
    }
  }
}

bool TzCameraMod::OnInitialize() {
  return true;
}

bool TzCameraMod::OnStart() {
  if(option_.enable_after_startup) {
    AIMRTE_INFO("Start camera on startup");
    start_camera();
    current_mode_ = mode_set_["Normal"];
    active_.store(1);
  }
  return true;
}

void TzCameraMod::OnShutdown() {
  stop_camera();
}

bool TzCameraMod::start_camera() {
  if (is_start_.load() > 0) {
    AIMRTE_WARN("Camera is already started");
    return true;
  }

  is_start_.store(1);

  // reset camera
  reset_power();
  camera_map_.clear();

  // hb init
  if (hb_vin_init(0, option_.cfg_path.c_str()) < 0) {
    AIMRTE_ERROR("Failed to init hb vin");
    return false;
  }

  for (const auto &port : option_.ports) {
    uint32_t video, width, height, fps, format;
    hb_port_mapping(port.pipeid, &video, &width, &height, &fps, &format);

    NvCam::Option cam_opt = {
        .width = (int)width,
        .height = (int)height,
        .fps = (int)fps,
        .pixfmt = (int)format,
        .pipeid = port.pipeid,
        .index = (int)video,
    };

    auto nv_cam = std::make_shared<NvCam>();
    if (nv_cam->Init(cam_opt) < 0) {
      AIMRTE_ERROR("Failed to init nv cam");
      return false;
    }

    std::shared_ptr<ImgConverter> converter = nullptr;
    if (port.converter == "yuyv2bgr") {
        converter = std::make_shared<Yuyv2Bgr>(
            (int)width, (int)height, port.output_width, port.output_height);
    } else if (port.converter == "yuyv2bgr_ldc") {
      converter = std::make_shared<Yuyv2BgrAndLDC>(
          (int)width, (int)height, port.output_width, port.output_height);
    }

    std::shared_ptr<Yuyv2Jpg> compressed_converter = nullptr;
    if (port.compressed_converter == "yuyv2jpeg") {
      compressed_converter = std::make_shared<Yuyv2Jpg>(
          (int)width, (int)height, port.output_width, port.output_height);
    }

    std::shared_ptr<Streamer> streamer = nullptr;

    if (port.streamer == "yuyv2h264") {
      streamer = std::make_shared<H264RawStreamer>(
          (int)width, (int)height, port.output_width, port.output_height, 30,
          "YUY2");
      streamer->Init(port.name);
    }

    // read calibration
    std::shared_ptr<isx031c_calibration_data> cali =
        std::make_shared<isx031c_calibration_data>();
    if (read_calibration(port.i2c_dev, port.i2c_addr,
                         port.name,
                         cali) < 0) {
      AIMRTE_ERROR("Failed to read calibration data");
      return false;
    }

    // TODO: camera model input
    if (converter)
      converter->init("pinhole", cali);

    TzCamera tz_cam = {
        .name = port.name,
        .nv_cam = nv_cam,
        .img_converter = converter,
        .compressed_converter = compressed_converter,
        .calibration = cali,
        .streamer = streamer,
        .output_width = port.output_width,
        .output_height = port.output_height,
    };

    camera_map_.emplace(port.pipeid, tz_cam);

    //TODO: start camera exe directly
    is_capturing_.store(true);
    if (tz_cam.nv_cam->Start() < 0) {
      AIMRTE_ERROR("Failed to start nv cam for pipeid {}", port.pipeid);
      return false;
    }

    AIMRTE_INFO("Camera pipeid {} started", port.pipeid);
    exe_.Post([this, pipeid = port.pipeid]() -> aimrte::Co<void> {
      while (is_capturing_.load()) {
        co_await publish_image(pipeid);
      }

      co_return;
    });

    if (tz_cam.streamer) {
      AIMRTE_INFO("Starting streamer for pipeid {}", port.pipeid);
      if (tz_cam.streamer->Start() < 0) {
        return false;
      }

      exe_.Post([this, pipeid = port.pipeid]() -> aimrte::Co<void> {
        while (is_capturing_.load()) {
          co_await publish_stream(pipeid);
        }
        co_return;
      });
    }
  }

  is_start_.store(2);
  return true;
}

void TzCameraMod::stop_camera() {
  if (!is_start_.load() < 0) {
    AIMRTE_WARN("Camera is already stopped");
    return;
  }

  while (is_start_.load() == 1) {
    AIMRTE_INFO("Waiting for camera to start...");
    usleep(100 * 1000);
  }

  is_start_.store(-1);
  is_capturing_.store(false);

  for (auto &[pipeid, cam] : camera_map_) {
    if (cam.streamer) {
      cam.streamer->Stop();
    }

    usleep(100 * 1000);

    if (cam.nv_cam->Release() < 0) {
      AIMRTE_ERROR("Failed to release nv cam for pipeid {}", pipeid);
    }
  }

  hb_vin_deinit(0);
  camera_map_.clear();

  reset_power();

  is_start_.store(-2);
}

aimrte::Co<void> TzCameraMod::publish_image(int pipeid) {
  auto buf = std::make_shared<rawimg_buffer>();

  if (is_paused_.load()) {
    AIMRTE_DEBUG("Camera {} is paused, skipping data poll", pipeid);
    co_return;
  }

  auto it = camera_map_.find(pipeid);
  if (it == camera_map_.end()) {
    AIMRTE_ERROR("Pipe ID {} not found in camera_map_", pipeid);
    co_return;
  }

  auto cam = it->second;
  int ret = cam.nv_cam->DataPoll(buf);
  if (ret < 0) {
    AIMRTE_ERROR("Failed to poll data from nv cam");
    reset_times_ += 1;
    if (reset_times_ > 5) {
      AIMRTE_ERROR("Reset {} camera times > 5, please check camera", pipeid);
    } else {
      AIMRTE_WARN("Reset camera, retry times: {}", reset_times_);
      reset_camera();
    }
    co_return;
  }

  if (cam.img_converter && current_mode_.test(0)) {
    cv::Mat bgr_frame(cam.output_height, cam.output_width, CV_8UC3);
    sensor_msgs::msg::Image img_msg;
    img_msg.header.stamp.sec = buf->ts_sec;
    img_msg.header.stamp.nanosec = buf->ts_nsec;
    AIMRTE_DEBUG("{} pipeid img hard timestamp is {}.{:09d}", pipeid, img_msg.header.stamp.sec,
                img_msg.header.stamp.nanosec);
    img_msg.width = bgr_frame.cols;
    img_msg.height = bgr_frame.rows;
    img_msg.encoding = "bgr8";
    img_msg.step = bgr_frame.step;
    img_msg.data.resize(bgr_frame.total() * bgr_frame.elemSize());
    cam.img_converter->convert_from_fd(buf->dma_fd, img_msg.data.data());

    auto it2 = channel_map_.find(pipeid);
    if (it2 != channel_map_.end()) {
      AIMRTE_DEBUG("{} pipe Publishing image at is {}.{:09d}", pipeid, img_msg.header.stamp.sec, img_msg.header.stamp.nanosec);
      it2->second.Publish(img_msg);
      AIMRTE_DEBUG("{} pipe Publishing image done", pipeid);
    } else {
      AIMRTE_ERROR("Channel map key not found");
    }
  }

  if (cam.compressed_converter && current_mode_.test(1)) {
    sensor_msgs::msg::CompressedImage compressed_msg;
    compressed_msg.data.resize(cam.output_height * cam.output_width * 3 / 2);
    int size = cam.compressed_converter->convert_from_fd(
        buf->dma_fd, compressed_msg.data.data());
    if (size < 0) {
      AIMRTE_ERROR("Failed to convert image from fd");
    } else {
      compressed_msg.header.stamp = rclcpp::Time(
          std::chrono::high_resolution_clock::now().time_since_epoch().count());
      compressed_msg.format = "jpeg";
      compressed_msg.data.resize(size);

      auto it2 = compressed_channel_map_.find(pipeid);
      if (it2 != compressed_channel_map_.end()) {
        AIMRTE_DEBUG("{} pipe Publishing compressed image", pipeid);
        it2->second.Publish(compressed_msg);
      } else {
        AIMRTE_ERROR("Compressed channel map key not found");
      }
    }
  }

  if (cam.streamer && current_mode_.test(2)) {
    cam.streamer->PushImageFd(buf->dma_fd);
  }

  co_return;
}

aimrte::Co<void> TzCameraMod::publish_stream(int pipeid) {
  auto it = camera_map_.find(pipeid);
  if (it == camera_map_.end()) {
    AIMRTE_ERROR("Pipe ID {} not found in camera_map_", pipeid);
    co_return;
  }

  auto cam = it->second;
  if (!cam.streamer) {
    AIMRTE_ERROR("Streamer not initialized for pipeid {}", pipeid);
    co_return;
  }

  auto frame_ptr = cam.streamer->GetFrame();
  if (!frame_ptr) {
    AIMRTE_WARN("Failed to get frame from streamer for pipeid {}", pipeid);
    co_return;
  }

  frame_ptr->frame_id = "camera_frame";

  auto it2 = stream_map_.find(pipeid);
  if (it2 != stream_map_.end()) {
    AIMRTE_DEBUG("{} pipe Publishing stream", pipeid);
    it2->second.Publish(*frame_ptr);
  } else {
    AIMRTE_ERROR("Stream map key not found");
  }

  co_return;
}

int TzCameraMod::sensor_system(const char *pCmd) {
  pid_t pid;
  struct sigaction sa, intr, quit;
  int status = 0;

  if (pCmd == NULL) {
    return 1;
  }

  sa.sa_handler = SIG_IGN;
  sa.sa_flags = 0;
  sigemptyset(&sa.sa_mask);
  if ((sigaction(SIGINT, &sa, &intr) < 0) ||
      (sigaction(SIGQUIT, &sa, &quit) < 0)) {
    return -1;
  }

  pid = vfork();
  if (pid == 0) {
    char achCmd[2048] = {0};
    strncpy(achCmd, pCmd, sizeof(achCmd) - 1);
    char *achArgv[4] = {(char *)"/bin/sh", (char *)"-c", achCmd, NULL};
    for (int nfd = 3; nfd < 4096; nfd++) {
      if (close(nfd) != 0) {
        break;
      }
    }
    (void)sigaction(SIGINT, &intr, (struct sigaction *)NULL);
    (void)sigaction(SIGQUIT, &quit, (struct sigaction *)NULL);

    int childRet = execv("/bin/sh", achArgv);
    if (childRet < 0) {
      printf("%s failed %d errno =%d  %s!\n", pCmd, childRet, errno,
             strerror(errno));
      _exit(childRet);
    }
  } else if (pid < 0) {
    return -1;
  } else {
    int n;

    do {
      n = waitpid(pid, &status, 0);
    } while (n == -1 && errno == EINTR);

    if (n != pid) {
      status = -1;
    }
  }

  if (sigaction(SIGINT, &intr, (struct sigaction *)NULL) ||
      sigaction(SIGQUIT, &quit, (struct sigaction *)NULL) != 0) {
    return -1;
  }
  return status;
}

bool TzCameraMod::reset_camera() {
  if (is_paused_.load()) {
    AIMRTE_WARN("Camera is already resetting, skipping reset");
    return true;
  }

  is_paused_.store(true);
  AIMRTE_INFO("Resetting cameras...");
  usleep(500 * 1000);
  hb_vin_deinit(0);
  usleep(1000 * 1000);
  reset_power();
  usleep(1000 * 1000);

  // hb init
  if (hb_vin_init(0, option_.cfg_path.c_str()) < 0) {
    AIMRTE_ERROR("Failed to init hb vin");
    return false;
  }

  usleep(1000 * 1000);
  AIMRTE_INFO("resetting camera finised");
  is_paused_.store(false);

  return true;
}

int TzCameraMod::reset_power() {
  int board_id = camera_sys_get_board_id();
  AIMRTE_INFO("start reset power\n");
  // 解串器下电
  sensor_system(
      "echo 0 > /sys/class/tz_gpio/camera_0_1-power/value"); // cam host0
  sensor_system(
      "echo 0 > /sys/class/tz_gpio/camera_2_3-power/value"); // cam host2
  sensor_system(
      "echo 0 > /sys/class/tz_gpio/camera_4_5-power/value"); // cam host3
  sensor_system(
      "echo 0 > /sys/class/tz_gpio/camera_6_7-power/value"); // cam host3
  AIMRTE_INFO("power off\n");
  if (board_id == GEAC91 || board_id == GEAC90 || board_id == GEACJX ||
      board_id == GEAC91VP) {
    usleep(3000 * 1000);
  } else if (board_id == T24DG26TYA_ORIN || board_id == T24DG26TYB_ORIN) {
    // 通过20087对相机下电
    sensor_system("i2ctransfer -f -y 7 w2@0x28 0x01 0x10");
    sensor_system("i2ctransfer -f -y 7 w2@0x29 0x01 0x10");
    usleep(100 * 1000);
    // 通过20087对相机上电
    sensor_system("i2ctransfer -f -y 7 w2@0x28 0x01 0x1f");
    sensor_system("i2ctransfer -f -y 7 w2@0x29 0x01 0x1f");
  } else if (board_id == C24HH01 || board_id == T24DG26TYA_NX ||
             board_id == T24DG26TYB_NX) {
    // 通过20087对相机下电
    sensor_system("i2ctransfer -f -y 1 w2@0x28 0x01 0x10");
    sensor_system("i2ctransfer -f -y 1 w2@0x29 0x01 0x10");
    usleep(100 * 1000);
    // 通过20087对相机上电
    sensor_system("i2ctransfer -f -y 1 w2@0x28 0x01 0x1f");
    sensor_system("i2ctransfer -f -y 1 w2@0x29 0x01 0x1f");
  } else {
    // 通过20087对相机下电
    sensor_system("i2ctransfer -f -y 7 w2@0x28 0x01 0x10");
    sensor_system("i2ctransfer -f -y 7 w2@0x29 0x01 0x10");
    sensor_system("i2ctransfer -f -y 8 w2@0x28 0x01 0x10");
    sensor_system("i2ctransfer -f -y 8 w2@0x29 0x01 0x10");
    usleep(100 * 1000);
    // 通过20087对相机上电
    sensor_system("i2ctransfer -f -y 7 w2@0x28 0x01 0x1f");
    sensor_system("i2ctransfer -f -y 7 w2@0x29 0x01 0x1f");
    sensor_system("i2ctransfer -f -y 8 w2@0x28 0x01 0x1f");
    sensor_system("i2ctransfer -f -y 8 w2@0x29 0x01 0x1f");
  }
  // 解串器上电
  sensor_system(
      "echo 1 > /sys/class/tz_gpio/camera_0_1-power/value"); // cam host0
  sensor_system(
      "echo 1 > /sys/class/tz_gpio/camera_2_3-power/value"); // cam host2
  sensor_system(
      "echo 1 > /sys/class/tz_gpio/camera_4_5-power/value"); // cam host3
  sensor_system(
      "echo 1 > /sys/class/tz_gpio/camera_6_7-power/value"); // cam host3
  AIMRTE_INFO("power on\n");
  return 0;
}

int TzCameraMod::read_calibration(
    std::string dev, int addr, std::string camera_name,
    std::shared_ptr<isx031c_calibration_data> cali) {
  int ret = get_isx031c_calibration(dev, (uint8_t)addr, cali.get());
  if (ret < 0) {
    AIMRTE_ERROR("Failed to get calibration data");
    return -1;
  }

  AIMRTE_DEBUG(""
               "Calibration data: sn={}, width={}, height={}, model={}, fx={}, "
               "fy={}, cx={}, cy={}, k1={}, k2={}, p1={}, p2={}, k3={}, k4={}, "
               "k5={}, k6={}",
               cali->sn, cali->width, cali->height, cali->model, cali->fx,
               cali->fy, cali->cx, cali->cy, cali->k1, cali->k2, cali->p1,
               cali->p2, cali->k3, cali->k4, cali->k5, cali->k6);

  auto SavePinHoleIntrinsic = [&camera_name, &cali](YAML::Emitter& out){
    out << YAML::BeginMap;
    out << YAML::Key << "model_type" << YAML::Value << "PINHOLE";
    out << YAML::Key << "camera_name" << YAML::Value << camera_name;
    out << YAML::Key << "image_width" << YAML::Value << cali->width;
    out << YAML::Key << "image_height" << YAML::Value << cali->height;

    out << YAML::Key << "distortion_parameters" << YAML::Value;
    out << YAML::BeginMap;
    out << YAML::Key << "k1" << YAML::Value << cali->k1;
    out << YAML::Key << "k2" << YAML::Value << cali->k2;
    out << YAML::Key << "p1" << YAML::Value << cali->p1;
    out << YAML::Key << "p2" << YAML::Value << cali->p2;
    out << YAML::Key << "k3" << YAML::Value << cali->k3;
    out << YAML::Key << "k4" << YAML::Value << cali->k4;
    out << YAML::Key << "k5" << YAML::Value << cali->k5;
    out << YAML::Key << "k6" << YAML::Value << cali->k6;
    out << YAML::EndMap;

    out << YAML::Key << "projection_parameters" << YAML::Value;
    out << YAML::BeginMap;
    out << YAML::Key << "fx" << YAML::Value << cali->fx;
    out << YAML::Key << "fy" << YAML::Value << cali->fy;
    out << YAML::Key << "cx" << YAML::Value << cali->cx;
    out << YAML::Key << "cy" << YAML::Value << cali->cy;
    out << YAML::EndMap;

    out << YAML::EndMap;
  };

  auto SaveFishEyeIntrinsic = [&camera_name, &cali](YAML::Emitter& out){
    out << YAML::BeginMap;
    out << YAML::Key << "model_type" << YAML::Value << "KANNALA_BRANDT";
    out << YAML::Key << "camera_name" << YAML::Value << camera_name;
    out << YAML::Key << "image_width" << YAML::Value << cali->width;
    out << YAML::Key << "image_height" << YAML::Value << cali->height;

    out << YAML::Key << "projection_parameters" << YAML::Value;
    out << YAML::BeginMap;
    // 这里注意我们标定使用的模型公式和相机输出的模型公式对应关系
    // 标定的 k2, k3, k4, k5 对应
    // 相机的 k1, k2, k3, k4
    out << YAML::Key << "k2" << YAML::Value << cali->k1;
    out << YAML::Key << "k3" << YAML::Value << cali->k2;
    out << YAML::Key << "k4" << YAML::Value << cali->k3;
    out << YAML::Key << "k5" << YAML::Value << cali->k4;
    // 焦距
    out << YAML::Key << "mu" << YAML::Value << cali->fx;
    out << YAML::Key << "mv" << YAML::Value << cali->fy;
    // 轴心坐标
    out << YAML::Key << "u0" << YAML::Value << cali->cx;
    out << YAML::Key << "v0" << YAML::Value << cali->cy;
    out << YAML::EndMap;

    out << YAML::EndMap;
  };

  auto SaveUnsupportIntrinsic = [&camera_name](YAML::Emitter& out){
    out << YAML::BeginMap;
    out << YAML::Key << "model_type" << YAML::Value << "UNSUPPORT";
    out << YAML::Key << "camera_name" << YAML::Value << camera_name;
    out << YAML::EndMap;
  };

  YAML::Emitter out;

  if(cali->model == 1) {
    SavePinHoleIntrinsic(out);
  } else if (cali->model == 2) {
    SaveFishEyeIntrinsic(out);
  } else {
    SaveUnsupportIntrinsic(out);
  }

  try {
    std::string path = option_.calibration_path + "/" + camera_name + ".yaml";
    // Create the path if it doesn't exist
    std::filesystem::path dir_path = std::filesystem::path(path).parent_path();
    if (!std::filesystem::exists(dir_path)) {
      std::filesystem::create_directories(dir_path);
    }

    std::ofstream fout(path);
    if (!fout.is_open()) {
      AIMRTE_ERROR("Failed to open file {}", path);
      return -2;
    }

    fout << "%YAML:1.0\n";
    fout << "---\n";
    fout << out.c_str();
    fout << "\n";
    fout.close();

    AIMRTE_INFO("Calibration data saved to {}", path);
    return 0;
  } catch (const std::exception &e) {
    AIMRTE_ERROR("Exception occurred while saving calibration data: {}",
                 e.what());
    return -3;
  }
}

} // namespace aima::sensors::camera