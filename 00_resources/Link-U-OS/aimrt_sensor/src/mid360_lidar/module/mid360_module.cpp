// Copyright (c) 2025, AgiBot Inc.
// All rights reserved.

#include "src/mid360_lidar/module/mid360_module.hpp"

#include <cmath>

#include "builtin_interfaces/msg/time.hpp"

namespace aima {
namespace sensor{
namespace lidar{
namespace mid360{

namespace {

constexpr double G_TO_MPS2   = 9.80665;         // 1 g  = 9.80665 m/s²
constexpr double DEG_TO_RAD  = M_PI / 180.0;    // 1°   = π/180 rad


builtin_interfaces::msg::Time toBuiltinTime(double time_sec)
{
  builtin_interfaces::msg::Time t;

  int32_t sec = static_cast<int32_t>(std::floor(time_sec));

  double frac = time_sec - static_cast<double>(sec);          // 0 <= frac < 1
  uint32_t nsec = static_cast<uint32_t>(frac * 1e9);          // 0 <= nsec < 1e9

  t.sec     = sec;
  t.nanosec = nsec;
  return t;
}

// ----------------------------------------------------------------------------
//  PointT → PointCloud2
// ----------------------------------------------------------------------------
sensor_msgs::msg::PointCloud2 ToPointCloud2(const PointCloudMsg & src, const std::string & frame_id = "lidar_link")
{
  sensor_msgs::msg::PointCloud2 dst;

  /* ---------------- header ---------------- */
  dst.header.frame_id = frame_id;
  // dst.header.seq = src.seq; // ros2 header delete seq 
  dst.header.stamp = toBuiltinTime(src.timestamp);

  /* ---------------- geometry ---------------- */
  dst.height      = 1;
  dst.width       = static_cast<uint32_t>(src.points.size());
  dst.is_dense    = true;
  dst.is_bigendian = false;                       // ARM/ x86 默认小端

  /* ---------------- field 描述 ---------------- */
    sensor_msgs::msg::PointField field_x;
    field_x.name = "x";
    field_x.offset = 0;
    field_x.datatype = sensor_msgs::msg::PointField::FLOAT32;
    field_x.count = 1;

    sensor_msgs::msg::PointField field_y;
    field_y.name = "y";
    field_y.offset = 4;
    field_y.datatype = sensor_msgs::msg::PointField::FLOAT32;
    field_y.count = 1;

    sensor_msgs::msg::PointField field_z;
    field_z.name = "z";
    field_z.offset = 8;
    field_z.datatype = sensor_msgs::msg::PointField::FLOAT32;
    field_z.count = 1;

    sensor_msgs::msg::PointField field_intensity;
    field_intensity.name = "intensity";
    field_intensity.offset = 12;
    field_intensity.datatype = sensor_msgs::msg::PointField::FLOAT32;
    field_intensity.count = 1;

    sensor_msgs::msg::PointField field_feature;
    field_feature.name = "tag";
    field_feature.offset = 16;
    field_feature.datatype = sensor_msgs::msg::PointField::UINT8;
    field_feature.count = 1;

    sensor_msgs::msg::PointField field_line;
    field_line.name = "line";
    field_line.offset = 17;
    field_line.datatype = sensor_msgs::msg::PointField::UINT8;
    field_line.count = 1;


    sensor_msgs::msg::PointField field_timestamp;
    field_timestamp.name = "timestamp";
    field_timestamp.offset = 18;
    field_timestamp.datatype = sensor_msgs::msg::PointField::FLOAT64;
    field_timestamp.count = 1;

    dst.fields = {
        field_x,
        field_y,
        field_z,
        field_intensity,
        field_feature,
        field_line,
        field_timestamp,
    };

  /* ---------------- 数据拷贝 ---------------- */
  dst.point_step = sizeof(PointT);                 // =26

  /* ---------- 尺寸自检 ---------- */
  const std::size_t num_pts = src.points.size();

  dst.row_step   = dst.point_step * dst.width;

  dst.data.resize(num_pts * dst.point_step);
  if (num_pts) {
    std::memcpy(dst.data.data(),
                src.points.data(),
                dst.data.size());
  }

  return dst;
}


sensor_msgs::msg::Imu ToRosImu(const ImuData &src, const std::string &frame_id = "imu_link")
{
  sensor_msgs::msg::Imu dst;

  // ---------------- Header ----------------
  dst.header.stamp = toBuiltinTime(src.timestamp);
  dst.header.frame_id = frame_id;

  // ---------------- Orientation -----------
  dst.orientation.x = src.orientation_x;
  dst.orientation.y = src.orientation_y;
  dst.orientation.z = src.orientation_z;
  dst.orientation.w = src.orientation_w;

  // Accelerations should be in m/s^2 (not in g's), and rotational velocity should be in rad/sec
  dst.angular_velocity.x = src.angular_velocity_x;
  dst.angular_velocity.y = src.angular_velocity_y;
  dst.angular_velocity.z = src.angular_velocity_z;

  // Linear acceleration: g 
  // 这里下游要求单位是g！！！
  dst.linear_acceleration.x = src.linear_acceleration_x;
  dst.linear_acceleration.y = src.linear_acceleration_y;
  dst.linear_acceleration.z = src.linear_acceleration_z;

  // ---------------- Covariances ------------
  // A covariance matrix of all zeros will be interpreted as covariance unknown, and to use the
  // data a covariance will have to be assumed or gotten from some other source
  std::fill(std::begin(dst.orientation_covariance), std::end(dst.orientation_covariance), 0.0);
  std::fill(std::begin(dst.angular_velocity_covariance), std::end(dst.angular_velocity_covariance), 0.0);
  std::fill(std::begin(dst.linear_acceleration_covariance), std::end(dst.linear_acceleration_covariance), 0.0);

  return dst;
}

}

void Mid360Mod::OnConfigure(aimrte::ctx::ModuleCfg& cfg) {
  using namespace aimrte::cfg;
  cfg[Module::Basic].Config(config_);
  
  pointcloud_pub_ = aimrte::Pub<sensor_msgs::msg::PointCloud2>(config_.pointcloud_topic_name);
  cfg[Ch::ros2].Def(pointcloud_pub_);

  imu_pub_ = aimrte::Pub<sensor_msgs::msg::Imu>(config_.imu_topic_name);
  cfg[Ch::ros2].Def(imu_pub_);
}

bool Mid360Mod::OnInitialize() {
  // init param
  RSDriverParam param_;
  param_.input_type            = InputType::ONLINE_LIDAR;
  param_.input_param.msop_port = config_.lidar_port;
  param_.input_param.difop_port= config_.log_port;
  param_.input_param.imu_port  = config_.imu_port;
  param_.lidar_type            = LidarType::LivoxMid360;
  param_.decoder_param.use_lidar_clock = config_.use_lidar_clock;  // 配合时间同步，拿同步后的时间。如果设置为false就是主机软件时间戳
  param_.decoder_param.wait_time_sync_s = config_.wait_time_sync_s;  // 若超过等待时间没有同步成功则降级到软件时间戳
  param_.decoder_param.time_sync_success_diff_s = config_.time_sync_success_diff_s;  // 认定时间同步成功的阈值，系统收到udp包时间 - udp包内lidar时间

  // 以下为适配rs_driver进行的配置，无需修改
  param_.decoder_param.wait_for_difop = false;   // difop为robosense里lidar信息的udp包，这里不等待，直接输出数据
  param_.decoder_param.ts_first_point = true;    // 和之前保持一致，第一个点的时间戳
  param_.decoder_param.check_packet_len = false; // 不检查，livox中储存了点的个数，可能是不定长的
  param_.decoder_param.check_packet_id = false;  // livox格式定义不同于rs，所里这里一定不能检查
  param_.decoder_param.dense_points = true;      // 不存在无效点
  param_.decoder_param.use_offset_timestamp = true; // 使用相对时间戳

  param_.print();

  driver_.regPointCloudCallback(
    [this]() {
      return pointcloud_? pointcloud_ : std::make_shared<PointCloudMsg>();
    },
    [this](const std::shared_ptr<PointCloudMsg>& cloud) {
      this->PubPointCloudMsg(cloud);
    }
  );

  driver_.regImuDataCallback(
    [this]() {
      return imu_data_? imu_data_ : std::make_shared<ImuData>();
    },
    [this](std::shared_ptr<ImuData> imu_data) {
      this->PubImuMsg(imu_data);
    }
  );

  driver_.regExceptionCallback(
    [this](const Error& code) {
      AIMRTE_ERROR_STREAM(code.toString()); // TODO(SJ): intergate error handle into aima
    }
  );

  if (!driver_.init(param_))
  {
    AIMRTE_ERROR_STREAM("Driver Initialize Error...");
    return false;
  }

  return true;
}

bool Mid360Mod::OnStart() {
  if (!driver_.start())
  {
      AIMRTE_ERROR_STREAM("Driver start failed...");
      return false;
  }

  return true;
}

void Mid360Mod::OnShutdown() {
  driver_.stop();
}

void Mid360Mod::PubPointCloudMsg(const std::shared_ptr<PointCloudMsg>& cloud)
{
    if (!cloud) {
        AIMRTE_ERROR_STREAM("Mid360Mod: Received null point cloud.");
        return;
    }

    AIMRTE_DEBUG_STREAM("AiryLidar receive pointcloud: " << std::dec<<std::to_string(cloud->timestamp));

    ts_diff_stats_.updateLidar(cloud->timestamp);

    sensor_msgs::msg::PointCloud2 ros_msg = ToPointCloud2(*cloud, config_.lidar_frame_id);

    // pass context pointer to subthread
    GetContextPtr()->LetMe();

    pointcloud_pub_.Publish(ros_msg);

}

void Mid360Mod::PubImuMsg(const std::shared_ptr<ImuData>& imu)
{
    if (!imu) {
        AIMRTE_ERROR_STREAM("Mid360Mod: Received null IMU data.");
        return;
    }

    AIMRTE_DEBUG_STREAM("AiryLidar receive imu: " << std::dec<<std::to_string(imu->timestamp));

    ts_diff_stats_.updateImu(imu->timestamp);

    sensor_msgs::msg::Imu ros_msg = ToRosImu(*imu, config_.imu_frame_id);

    // pass context pointer to subthread
    GetContextPtr()->LetMe();

    imu_pub_.Publish(ros_msg);
}

}
}
}
}