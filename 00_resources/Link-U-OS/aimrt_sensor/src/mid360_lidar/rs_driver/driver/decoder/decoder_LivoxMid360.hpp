/*********************************************************************************************************************
Copyright (c) 2020 RoboSense
All rights reserved

By downloading, copying, installing or using the software you agree to this license. If you do not agree to this
license, do not download, install, copy or use the software.

License Agreement
For RoboSense LiDAR SDK Library
(3-clause BSD License)

Redistribution and use in source and binary forms, with or without modification, are permitted provided that the
following conditions are met:

1. Redistributions of source code must retain the above copyright notice, this list of conditions and the following
disclaimer.

2. Redistributions in binary form must reproduce the above copyright notice, this list of conditions and the following
disclaimer in the documentation and/or other materials provided with the distribution.

3. Neither the names of the RoboSense, nor Suteng Innovation Technology, nor the names of other contributors may be used
to endorse or promote products derived from this software without specific prior written permission.

THIS SOFTWARE IS PROVIDED BY THE COPYRIGHT HOLDERS AND CONTRIBUTORS "AS IS" AND ANY EXPRESS OR IMPLIED WARRANTIES,
INCLUDING, BUT NOT LIMITED TO, THE IMPLIED WARRANTIES OF MERCHANTABILITY AND FITNESS FOR A PARTICULAR PURPOSE ARE
DISCLAIMED. IN NO EVENT SHALL THE COPYRIGHT OWNER OR CONTRIBUTORS BE LIABLE FOR ANY DIRECT, INDIRECT, INCIDENTAL,
SPECIAL, EXEMPLARY, OR CONSEQUENTIAL DAMAGES (INCLUDING, BUT NOT LIMITED TO, PROCUREMENT OF SUBSTITUTE GOODS OR
SERVICES; LOSS OF USE, DATA, OR PROFITS; OR BUSINESS INTERRUPTION) HOWEVER CAUSED AND ON ANY THEORY OF LIABILITY,
WHETHER IN CONTRACT, STRICT LIABILITY, OR TORT (INCLUDING NEGLIGENCE OR OTHERWISE) ARISING IN ANY WAY OUT OF THE USE OF
THIS SOFTWARE, EVEN IF ADVISED OF THE POSSIBILITY OF SUCH DAMAGE.
*********************************************************************************************************************/

#pragma once
#include <rs_driver/driver/decoder/decoder_mech.hpp>
#include <iomanip>

// 协议说明
// 1. livox为小端序，现在主机均为小端序，所以解析原始数据的时候直接类型强转就能用
// 2. 每个UDP包数据包中点的数量不固定，通过dot_num来确定数量（虽然看数据lidar都是96个点，imu都是1帧数据）
// 3. 一帧完整的点云包含多个UDP包，是怎么判断哪些udp包组成一帧完整点云的？
//    使用udp包中的时间戳来组，udp包中的时间跨度大于100ms则组成1帧
// 4. 我看了抓包的数据udp包是稳定输出的，并不是每100ms集中输出。那么10HZ是谁控制的呢？ 
//    是持续扫描持续输出的，10hz是时间戳来控制

namespace livox
{
namespace lidar
{

using namespace robosense::lidar;

static const uint32_t local_time_now_key_gt = 0x00088009; // 小端 
static const uint32_t last_sync_time_key_gt = 0x0008800A; // 小端 

#pragma pack(push, 1)

typedef struct {
  uint8_t todo[337];
  // device local time
  uint32_t local_time_now_key;    // idex: 337 338 339 340
  uint64_t local_time_now_value;  //idex: 341, 342, 343, 344, 345, 346, 347, 348
  // last_sync_time
  uint32_t last_sync_time_key;    // idex: 349 350 351 352
  uint64_t last_sync_time_value;
  uint8_t pad[425 - 337 - 12 -12];
} LivoxLidarInfoPacket;


typedef struct {
  uint8_t version;
  uint16_t length;
  uint16_t time_interval;      /**< 这帧点云数据中最后一个点减去第一个点时间(单位0.1us) */
  uint16_t dot_num;
  uint16_t udp_cnt;
  uint8_t frame_cnt;
  uint8_t data_type;
  uint8_t time_type;
  uint8_t rsvd[12];
  uint32_t crc32;
  uint64_t timestamp;
  uint8_t data[1];             /**< Point cloud data. */
} LivoxLidarEthernetPacket;
typedef struct {
  float gyro_x;
  float gyro_y;
  float gyro_z;
  float acc_x;
  float acc_y;
  float acc_z;
} LivoxLidarImuRawPoint;
typedef struct {
  int32_t x;            /**< X axis, Unit:mm */
  int32_t y;            /**< Y axis, Unit:mm */
  int32_t z;            /**< Z axis, Unit:mm */
  uint8_t reflectivity; /**< Reflectivity */
  uint8_t tag;          /**< Tag */
} LivoxLidarCartesianHighRawPoint;

#pragma pack(pop)

template <typename T_PointCloud>
class DecoderLivoxMid360 : public DecoderMech<T_PointCloud>
{
public:
  constexpr static float FSR_BASE = 32768.0;
  virtual void decodeDifopPkt(const uint8_t* pkt, size_t size);
  virtual bool decodeMsopPkt(const uint8_t* pkt, size_t size);
  void decodeImuPkt(const uint8_t* pkt, size_t size) override;
  virtual ~DecoderLivoxMid360() = default;

  explicit DecoderLivoxMid360(const RSDecoderParam& param);
  virtual bool isNewFrame(const uint8_t* packet) override;
#ifndef UNIT_TEST
protected:
#endif

  static RSDecoderMechConstParam& getConstParam();

  uint16_t u16ChannelNum_{1};
  bool bInit_{ false };
  bool loaded_install_info_{false};
  uint16_t install_mode_{0xFF};
  double buffer_first_timestamp_{0.0}; // 记录当前缓存点云的最旧时间戳，使用时间戳来组帧

  uint16_t difop_pkt_num{0};  // 用来记录收到的difop pkt数量
  bool time_sync_success{false};

};

template <typename T_PointCloud>
inline RSDecoderMechConstParam& DecoderLivoxMid360<T_PointCloud>::getConstParam()
{
  static RSDecoderMechConstParam param;

  // TODO(SJ): check

  return param;
}

template <typename T_PointCloud>
inline DecoderLivoxMid360<T_PointCloud>::DecoderLivoxMid360(const RSDecoderParam& param)
  : DecoderMech<T_PointCloud>(getConstParam(), param)
{}

template <typename T_PointCloud>
inline void DecoderLivoxMid360<T_PointCloud>::decodeImuPkt(const uint8_t* packet, size_t size)
{
  auto pkt = reinterpret_cast<const LivoxLidarEthernetPacket*>(packet);
  if (this->imuDataPtr_ && this->cb_imu_data_)  // TODO: airy会先从difop中读取IMU标定信息，然后再输出IMU，这里先去掉
  {
    if (this->param_.use_lidar_clock && time_sync_success)
    {
      this->imuDataPtr_->timestamp = pkt->timestamp * 1e-9;
      // auto sys_time = getTimeHostWithNs() * 1e-9;
      // auto diff = sys_time - this->imuDataPtr_->timestamp;
      // AIMRTE_INFO_STREAM("imu pkt time sys-hardwar s: " << diff);
    }
    else
    {
      this->imuDataPtr_->timestamp = getTimeHostWithNs() * 1e-9;
    }

    // 看格式定义，一包UDP数据包里只会有一帧IMU数据
    auto imu_data_ptr = reinterpret_cast<const LivoxLidarImuRawPoint*>(pkt->data);

    this->imuDataPtr_->linear_acceleration_x = imu_data_ptr->acc_x;
    this->imuDataPtr_->linear_acceleration_y = imu_data_ptr->acc_y;
    this->imuDataPtr_->linear_acceleration_z = imu_data_ptr->acc_z;

    this->imuDataPtr_->angular_velocity_x = imu_data_ptr->gyro_x;
    this->imuDataPtr_->angular_velocity_y = imu_data_ptr->gyro_y;
    this->imuDataPtr_->angular_velocity_z = imu_data_ptr->gyro_z;

    this->imuDataPtr_->state = true;

    this->cb_imu_data_();
  }
}

template <typename T_PointCloud>
inline void DecoderLivoxMid360<T_PointCloud>::decodeDifopPkt(const uint8_t* packet, size_t size)
{
  // 暂未实现，后续可以解析lidar推送的log消息
  AIMRTE_DEBUG_STREAM("Recive livox control packet, packet len: " << size);
  auto livox_pkt = reinterpret_cast<const ::livox::lidar::LivoxLidarInfoPacket*>(packet);

  if (this->param_.use_lidar_clock && !time_sync_success) {
    if(livox_pkt->local_time_now_key == ::livox::lidar::local_time_now_key_gt) {
      auto sys_time_now_s = getTimeHostWithNs() * 1e-9;
      auto device_time_now_s = livox_pkt->local_time_now_value * 1e-9;
      auto time_diff_s = sys_time_now_s - device_time_now_s;

      AIMRTE_INFO_STREAM("device time: " << std::fixed << device_time_now_s  << ", sys time: " << sys_time_now_s << ", sys-device diff time: " << sys_time_now_s-device_time_now_s);

      if(std::fabs(time_diff_s) < this->param_.time_sync_success_diff_s) {
        AIMRTE_INFO_STREAM("time sync finish, use hardware time");
        time_sync_success = true;
      } else {
        AIMRTE_WARN_STREAM("time diff too large, wait...");
      }

      if(difop_pkt_num++ > this->param_.wait_time_sync_s) { // 最多等待10s，如果10s没有通过时间同步检查则回退使用软件时间戳
        AIMRTE_WARN_STREAM("time sync failed, fallback to use software timestamp");
        this->param_.use_lidar_clock  = false;  // 启动校验失败后则本次启动一直使用软件时间戳，这里置为false，避免后续再进行判断
        time_sync_success = false;
      } 
    }
  }

}

template <typename T_PointCloud>
inline bool DecoderLivoxMid360<T_PointCloud>::decodeMsopPkt(const uint8_t* pkt, size_t size)
{
  auto msopPkt = reinterpret_cast<const LivoxLidarEthernetPacket*>(pkt);
  bool ret = false;

  // 该UDP包的时间戳，也是第一个lidar点的时间戳
  double pkt_ts = 0;
  if (this->param_.use_lidar_clock && time_sync_success)
  {
    pkt_ts = msopPkt->timestamp * 1e-9;
  }
  else
  {
    pkt_ts = getTimeHostWithNs() * 1e-9;
  }

  // 记录缓存的第一个lidar点时间戳用来组帧
  if(this->point_cloud_->points.empty()) {
    this->first_point_ts_ = pkt_ts;
  }

  const uint16_t lidar_points_num = msopPkt->dot_num;

  // 相邻两个lidar点的时间戳间隔
  const double lidar_point_interval_s = lidar_points_num > 1 ? 0.1 * msopPkt->time_interval * 1e-6 / (lidar_points_num - 1) : 0;
  double lidar_point_ts = pkt_ts;

  // 点云数据
  auto lidar_points_ptr = reinterpret_cast<const LivoxLidarCartesianHighRawPoint*>(msopPkt->data);
  for(uint16_t i = 0; i < lidar_points_num; i++) {
    // 计算每个lidar点的时间戳
    lidar_point_ts = pkt_ts + i * lidar_point_interval_s;

    double postprocess_ts = lidar_point_ts;
    if(this->param_.use_offset_timestamp) {
       // 每个点相对于该帧点云第一个点的时间差，单位ns
      postprocess_ts = std::floor((lidar_point_ts - this->first_point_ts_) * 1e9);
      // 避免异常值，这个值最大约100ms左右
      postprocess_ts = std::clamp(postprocess_ts, 0.0, 150.0*1e6);
    }

    // 下面填值的函数会根据传入类型，自动选择是否填值
    typename T_PointCloud::PointT point;
    setX(point, lidar_points_ptr[i].x * 0.001f);           // m
    setY(point, lidar_points_ptr[i].y * 0.001f);           // m
    setZ(point, lidar_points_ptr[i].z * 0.001f);           // m
    setIntensity(point, static_cast<float>(lidar_points_ptr[i].reflectivity)); // 透传
    setFeature(point, lidar_points_ptr[i].tag);            // 透传
    setRing(point, 4);                                     // 没有意义，但是为了保持和之前一致写成4
    setTimestamp(point, postprocess_ts); 
    this->point_cloud_->points.emplace_back(point);
  }

  // 记录最后一个lidar点的时间戳，可以作为该帧msg header timestamp
  this->prev_point_ts_ = lidar_point_ts;
  this->prev_pkt_ts_ = pkt_ts;

  // 通过lidar点时间差是否大于100ms来判断是否组帧完成，若完成调用发布的回调
  // TODO:(SJ) 这里注意，在lidar卡顿然后恢复的场景，会导致存在旧数据没有被清理的情况。因为使用的不是host的定时器，而是lidar点的时间戳
  if (this->prev_point_ts_ - this->first_point_ts_ > 0.1)
  {
    AIMRTE_DEBUG_STREAM("prev_point_ts_: " << this->prev_point_ts_ << ", first_point_ts_: " << this->first_point_ts_);
    this->cb_split_frame_(this->u16ChannelNum_, this->cloudTs());
    ret = true;
  }

  return ret;
}

template <typename T_PointCloud>
inline bool DecoderLivoxMid360<T_PointCloud>::isNewFrame(const uint8_t* packet)
{
  // 这个函数只有在输入为PCAP文件的时候用，所以不用管，直接return false
  return false;
}

}  // namespace lidar
}  // namespace livox
