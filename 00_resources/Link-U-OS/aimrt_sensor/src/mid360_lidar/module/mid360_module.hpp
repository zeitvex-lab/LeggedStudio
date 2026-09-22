// Copyright (c) 2025, AgiBot Inc.
// All rights reserved.

# pragma once

#include <memory>

#include "src/all_in_one/include/aimrte.h"

#include "rs_driver/api/lidar_driver.hpp"

#ifdef ENABLE_PCL_POINTCLOUD
#include <rs_driver/msg/pcl_point_cloud_msg.hpp>
#else
#include <rs_driver/msg/point_cloud_msg.hpp>
#endif


#include <sensor_msgs/msg/point_cloud2.hpp>
#include <sensor_msgs/msg/imu.hpp>

namespace aima {
namespace sensor{
namespace lidar{
namespace mid360{

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

        AIMRTE_INFO_STREAM("[" << name_ << "] "
                  << "cnt=" << count_
                  << " avg=" << avg_ * 1000
                  << " min=" << min_ * 1000
                  << " max=" << max_ * 1000);

        if (reset_after_print)
            reset();
    }

    void reset() {
        count_ = 0;
        avg_ = 0.0;
        min_ = std::numeric_limits<double>::max();
        max_ = std::numeric_limits<double>::lowest();
        last_ts_ = -1.0;
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
};

class LidarImuStatsManager {
public:
    explicit LidarImuStatsManager(size_t lidar_report_interval)
        : lidar_stats_("LiDAR Δt ms"),
          imu_stats_("IMU Δt ms"),
          report_interval_(lidar_report_interval) {}

    void updateLidar(double lidar_ts) {
        lidar_stats_.update(lidar_ts);

        // 以 LiDAR 帧数为基准触发打印
        if (lidar_stats_.getCount() >= report_interval_) {
            printAndReset();
        }
    }

    void updateImu(double imu_ts) {
        imu_stats_.update(imu_ts);
    }

private:
    void printAndReset() {
        lidar_stats_.print(true); // LiDAR 打印后重置
        imu_stats_.print(true);
    }

private:
    RealtimeStats lidar_stats_;
    RealtimeStats imu_stats_;
    size_t report_interval_;
};


using namespace ::robosense::lidar;

typedef Mid360PointXYZIFRT      PointT;
typedef PointCloudT<PointT>    PointCloudMsg;

class Mid360Mod : public aimrte::Mod {

public:
    // default config, reflect from config file
    struct Mid360LidarConfig {
        std::string pointcloud_topic_name{"/aima/hal/lidar/neck/pointcloud"};
        std::string lidar_frame_id{"mid360_lidar"};
        uint16_t lidar_port{56301};
        std::string imu_topic_name{"/aima/hal/lidar/neck/imu"};
        std::string imu_frame_id{"mid360_imu"};
        uint16_t imu_port{56401};
        uint16_t log_port{56201};
        bool use_lidar_clock{false};
        uint16_t wait_time_sync_s{10};
        float time_sync_success_diff_s{0.5};
    };

protected:
    void OnConfigure(aimrte::ctx::ModuleCfg& cfg) override;
    bool OnInitialize() override;
    bool OnStart() override;
    void OnShutdown() override;

private:
    void PubPointCloudMsg(const std::shared_ptr<PointCloudMsg>& cloud);
    void PubImuMsg(const std::shared_ptr<ImuData>& imu);

private:
    Mid360LidarConfig config_;

    LidarDriver<PointCloudMsg> driver_;

    std::shared_ptr<PointCloudMsg> pointcloud_;  // 存放解析后的点云，每来一帧UDP包就会解析后塞进去，等到组帧完成一次性发出去
    std::shared_ptr<ImuData> imu_data_;          // 存放解析后的IMU数据

    aimrte::Pub<sensor_msgs::msg::PointCloud2> pointcloud_pub_;
    aimrte::Pub<sensor_msgs::msg::Imu> imu_pub_;

    uint32_t imu_seq_{0};

    LidarImuStatsManager ts_diff_stats_{10};
};

}
}
}
}