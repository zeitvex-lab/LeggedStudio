// ========================================================================================
// dog_nav_fallback.cpp — 任务赛兜底节点（放弃 OCR，点0 扫描后只取箱11、12）
// ========================================================================================
//
// 与 navigation_dog 的区别（兜底 = OCR/全量扫描不可靠时的保底动作）:
//   - 无 OCR（不调 solver.py）
//   - 只在起点(点0)跑一次 box_detector scan_all，只取箱11、12 的类型 → 定 zone
//   - 只 1 轮取放：点4左吸箱11、点5右吸箱12，再分放两个归位区
//
// 取放时序、蹲下控制、吸盘、导航、推流、U型避障 与 navigation_dog 完全一致。
//
// 状态机:
//   IDLE ──(按y/auto_start)──→ SCAN_AT_START ──→ [GOTO_PICKUP/PICKUP/GOTO_TARGET/PLACE_AVOID?/PLACE_BOX]×1 ──→ DONE
//
// 运行:
//   ros2 run dog_nav dog_nav_fallback --ros-args
//     --params-file src/dog_nav/config/task_race_point.yaml
//     -p auto_start:=true

#include <rclcpp/rclcpp.hpp>
#include <dog_nav/msg/dog_nav_command.hpp>
#include <nav_msgs/msg/odometry.hpp>
#include <sensor_msgs/msg/joint_state.hpp>
#include <std_msgs/msg/bool.hpp>
#include <tf2/LinearMath/Quaternion.h>
#include <tf2/LinearMath/Matrix3x3.h>
#include "dog_nav/field_path_planner.hpp"
#include "dog_nav/delivery_planner.hpp"  // BoxInfo, PickupRound
#include "dog_nav/sucker_controller.hpp"
#include "dog_nav/squat_controller.hpp"
#include "dog_nav/pick_place_actor.hpp"

#include <cmath>
#include <chrono>
#include <string>
#include <vector>
#include <array>
#include <cstdio>
#include <cerrno>
#include <cstring>
#include <csignal>
#include <fcntl.h>
#include <unistd.h>
#include <sys/wait.h>
#include <memory>
#include <thread>
#include <atomic>
#include <iostream>
#include <unordered_set>
#include <unordered_map>
#include <map>
#include <optional>
#include <sstream>

using dog_nav::msg::DogNavCommand;
using dog_nav::FieldPathPlanner;
using dog_nav::NavTask;
using dog_nav::SuckerController;
using dog_nav::SquatController;
using dog_nav::Point3D;
using dog_nav::PickPlaceActor;
using dog_nav::BoxInfo;
using dog_nav::PickupRound;

// ========================================================================================
// 状态枚举
// ========================================================================================

enum class FbState
{
  IDLE = 0,         // 等待启动
  SCAN_AT_START,    // 点0 扫描箱11,12 → 定 zone → 反查站位
  GOTO_PICKUP,      // 导航到取货站位(点4/点5)
  PICKUP,           // 蹲下取箱
  GOTO_TARGET,      // 导航到放货站位
  PLACE_AVOID,      // U型避障（横向通道被已放箱归位区挡住时）
  PLACE_BOX,        // 蹲下放箱
  DONE
};

inline const char * FbStateStr(FbState s)
{
  switch (s) {
    case FbState::IDLE:           return "IDLE";
    case FbState::SCAN_AT_START:  return "SCAN_AT_START";
    case FbState::GOTO_PICKUP:    return "GOTO_PICKUP";
    case FbState::PICKUP:         return "PICKUP";
    case FbState::GOTO_TARGET:    return "GOTO_TARGET";
    case FbState::PLACE_AVOID:    return "PLACE_AVOID";
    case FbState::PLACE_BOX:      return "PLACE_BOX";
    case FbState::DONE:           return "DONE";
    default:                      return "UNKNOWN";
  }
}

// ========================================================================================
// 兜底节点
// ========================================================================================

class FallbackNode : public rclcpp::Node
{
public:
  FallbackNode()
  : Node("dog_nav_fallback_node")
  {
    // =========================
    // 1. 声明参数（同 navigation_dog，去掉 OCR/pickup_points 等不需要的）
    // =========================
    this->declare_parameter("loop_rate_hz", 20);
    this->declare_parameter("nav_vx", 0.3);
    this->declare_parameter("nav_height", 0.25);
    this->declare_parameter("field_side", std::string("left"));
    this->declare_parameter("box_scanner_path", std::string(
      "/home/zhy/himdog/src/dog_nav/resource/vision/box_detector_rknn.py"));

    this->declare_parameter("odom_topic", std::string("/lio/odom"));
    this->declare_parameter("pos_tolerance", 0.05);
    this->declare_parameter("yaw_tolerance", 0.087);
    this->declare_parameter("nav_kp_xy", 0.8);
    this->declare_parameter("nav_kp_yaw", 1.5);
    this->declare_parameter("nav_max_vx", 0.5);
    this->declare_parameter("nav_max_vy", 0.3);
    this->declare_parameter("nav_max_wz", 1.0);
    this->declare_parameter("nav_timeout_sec", 15.0);
    this->declare_parameter("segment_time_sec", 3.0);
    this->declare_parameter("auto_start", false);

    // 吸盘串口参数
    this->declare_parameter("sucker_port", std::string("/dev/ttyUSB0"));
    this->declare_parameter("sucker_baudrate", 115200);
    this->declare_parameter("sucker_move_sec", 3.0);
    this->declare_parameter("sucker_hold_sec", 0.5);

    // 蹲下取箱参数
    this->declare_parameter("stand_pose", std::vector<double>(12, 0.0));
    this->declare_parameter("squat_pose", std::vector<double>{
      0.0, 0.7, -1.4, 0.0, 0.7, -1.4, 0.0, 0.7, -1.4, 0.0, 0.7, -1.4});
    this->declare_parameter("squat_interp_sec", 1.0);
    this->declare_parameter("squat_hold_sec", 1.0);

    // D435i 推流参数
    this->declare_parameter("stream_enable", true);
    this->declare_parameter("stream_port", 8765);

    // 场地坐标参数
    DeclareCoordParams();

    // =========================
    // 2. 读取参数
    // =========================
    nav_vx_ = static_cast<float>(this->get_parameter("nav_vx").as_double());
    nav_height_ = static_cast<float>(this->get_parameter("nav_height").as_double());
    field_side_ = this->get_parameter("field_side").as_string();
    box_scanner_path_ = this->get_parameter("box_scanner_path").as_string();
    segment_time_sec_ = this->get_parameter("segment_time_sec").as_double();
    auto_start_ = this->get_parameter("auto_start").as_bool();

    sucker_port_ = this->get_parameter("sucker_port").as_string();
    sucker_baudrate_ = this->get_parameter("sucker_baudrate").as_int();
    sucker_move_sec_ = this->get_parameter("sucker_move_sec").as_double();
    sucker_hold_sec_ = this->get_parameter("sucker_hold_sec").as_double();

    {
      std::array<double, SquatController::kNumDofs> stand{};
      std::array<double, SquatController::kNumDofs> squat{};
      auto sp = this->get_parameter("stand_pose").as_double_array();
      auto qp = this->get_parameter("squat_pose").as_double_array();
      for (int i = 0; i < SquatController::kNumDofs && i < static_cast<int>(sp.size()); ++i) stand[i] = sp[i];
      for (int i = 0; i < SquatController::kNumDofs && i < static_cast<int>(qp.size()); ++i) squat[i] = qp[i];
      actor_.ConfigureSquat(stand, squat,
        this->get_parameter("squat_interp_sec").as_double(),
        this->get_parameter("squat_hold_sec").as_double());
    }

    stream_enable_ = this->get_parameter("stream_enable").as_bool();
    stream_port_ = this->get_parameter("stream_port").as_int();

    odom_topic_ = this->get_parameter("odom_topic").as_string();
    pos_tolerance_ = this->get_parameter("pos_tolerance").as_double();
    yaw_tolerance_ = this->get_parameter("yaw_tolerance").as_double();
    nav_kp_xy_ = this->get_parameter("nav_kp_xy").as_double();
    nav_kp_yaw_ = this->get_parameter("nav_kp_yaw").as_double();
    nav_max_vx_ = this->get_parameter("nav_max_vx").as_double();
    nav_max_vy_ = this->get_parameter("nav_max_vy").as_double();
    nav_max_wz_ = this->get_parameter("nav_max_wz").as_double();
    nav_timeout_sec_ = this->get_parameter("nav_timeout_sec").as_double();

    // =========================
    // 3. 构建路径规划器 + 加载坐标 + 静态映射表
    // =========================
    planner_ = std::make_unique<FieldPathPlanner>();
    LoadCoordsFromParams();
    blocked_ = {};
    LoadStaticMaps();

    // =========================
    // 4. 发布者 + 订阅者
    // =========================
    nav_cmd_pub_ = this->create_publisher<DogNavCommand>("/nav_cmd", 10);
    joint_state_pub_ = this->create_publisher<sensor_msgs::msg::JointState>("/joint_states", 10);
    policy_mode_pub_ = this->create_publisher<std_msgs::msg::Bool>("/policy_mode", 10);

    odom_sub_ = this->create_subscription<nav_msgs::msg::Odometry>(
      odom_topic_, rclcpp::QoS(10).best_effort(),
      std::bind(&FallbackNode::OdomCallback, this, std::placeholders::_1));
    RCLCPP_INFO(this->get_logger(), "订阅里程计: %s", odom_topic_.c_str());

    // =========================
    // 5. 定时器
    // =========================
    const int rate_hz = this->get_parameter("loop_rate_hz").as_int();
    const auto period = std::chrono::milliseconds(1000 / std::max(1, rate_hz));
    timer_ = this->create_wall_timer(period, std::bind(&FallbackNode::TimerCallback, this));
    node_start_time_ = std::chrono::steady_clock::now();

    // =========================
    // 6. 吸盘串口
    // =========================
    actor_.ConfigureSucker(sucker_move_sec_, sucker_hold_sec_);
    if (!actor_.OpenSucker(sucker_port_, sucker_baudrate_)) {
      RCLCPP_WARN(this->get_logger(),
        "★ 吸盘串口 %s 打开失败，取放动作将无法吸合（蹲下仍可用）",
        sucker_port_.c_str());
    }

    // =========================
    // 7. 键盘监听
    // =========================
    if (!auto_start_) {
      keyboard_running_ = true;
      keyboard_thread_ = std::thread(&FallbackNode::KeyboardListener, this);
      RCLCPP_INFO(this->get_logger(), "dog_nav_fallback — 按 'y' + 回车 启动兜底流程");
    } else {
      RCLCPP_INFO(this->get_logger(), "dog_nav_fallback — auto_start=true, 自动开始");
    }

    // 打印坐标
    for (int i = 0; i <= 14; ++i) {
      const auto & c = planner_->GetCoord(i);
      RCLCPP_INFO(this->get_logger(), "  点位 %02d: (%.3f, %.3f, %.1f°)", i, c.x, c.y, c.theta);
    }

    if (auto_start_) {
      state_ = FbState::SCAN_AT_START;
      RCLCPP_INFO(this->get_logger(), "★ 开始兜底: 点0 扫描箱11,12...");
    }
  }

  ~FallbackNode()
  {
    keyboard_running_ = false;
    if (keyboard_thread_.joinable()) {
      keyboard_thread_.join();
    }
    StopStreamer();
  }

private:

  // ========================================================================================
  // 坐标参数声明/加载（与 navigation_dog 一致）
  // ========================================================================================
  void DeclareCoordParams()
  {
    this->declare_parameter("start_pose", std::vector<double>{0.0, 0.0, 0.0});
    const std::vector<std::string> pickup_names = {
      "point_1", "point_2", "point_3", "point_4", "point_5",
      "point_6", "point_7", "point_8", "point_9"};
    for (const auto & name : pickup_names) {
      this->declare_parameter("pickup_positions." + name, std::vector<double>{0.0, 0.0, 0.0});
    }
    const std::vector<std::string> place_names = {
      "point_10", "point_11", "point_12", "point_13", "point_14"};
    for (const auto & name : place_names) {
      this->declare_parameter("place_positions." + name, std::vector<double>{0.0, 0.0, 0.0});
    }
    const std::vector<std::string> zone_names = {"zone_1", "zone_2", "zone_3", "zone_4"};
    for (const auto & name : zone_names) {
      this->declare_parameter("return_zones." + name, std::vector<double>{0.0, 0.0, 0.0});
    }
  }

  void LoadCoordsFromParams()
  {
    LoadAndSetCoord("start_pose", 0);
    const std::vector<std::pair<std::string, int>> pickup_map = {
      {"pickup_positions.point_1", 1}, {"pickup_positions.point_2", 2},
      {"pickup_positions.point_3", 3}, {"pickup_positions.point_4", 4},
      {"pickup_positions.point_5", 5}, {"pickup_positions.point_6", 6},
      {"pickup_positions.point_7", 7}, {"pickup_positions.point_8", 8},
      {"pickup_positions.point_9", 9},
    };
    for (const auto & [p, id] : pickup_map) LoadAndSetCoord(p, id);

    const std::vector<std::pair<std::string, int>> place_map = {
      {"place_positions.point_10", 10}, {"place_positions.point_11", 11},
      {"place_positions.point_12", 12}, {"place_positions.point_13", 13},
      {"place_positions.point_14", 14},
    };
    for (const auto & [p, id] : place_map) LoadAndSetCoord(p, id);

    const std::vector<std::pair<std::string, int>> zone_map = {
      {"return_zones.zone_1", 1}, {"return_zones.zone_2", 2},
      {"return_zones.zone_3", 3}, {"return_zones.zone_4", 4},
    };
    for (const auto & [p, id] : zone_map) {
      try {
        auto vals = this->get_parameter(p).as_double_array();
        if (vals.size() >= 2) {
          zone_coords_[id] = {vals[0], vals[1], vals.size() >= 3 ? vals[2] : 0.0};
        }
      } catch (const std::exception & e) {
        RCLCPP_WARN(this->get_logger(),
          "★ 归位区参数 %s 未找到或格式错误，zone%d 坐标缺失（归位将失败）: %s",
          p.c_str(), id, e.what());
      }
    }
  }

  void LoadAndSetCoord(const std::string & param_name, int point_id)
  {
    try {
      auto vals = this->get_parameter(param_name).as_double_array();
      if (vals.size() >= 3) {
        planner_->SetCoord(point_id, vals[0], vals[1], vals[2]);
      } else if (vals.size() >= 2) {
        planner_->SetCoord(point_id, vals[0], vals[1], 0.0);
      }
    } catch (const std::exception & e) {
      RCLCPP_WARN(this->get_logger(), "参数 %s 未找到，点位 %d 用默认: %s",
        param_name.c_str(), point_id, e.what());
    }
  }

  // ========================================================================================
  // 静态映射表（与 navigation_dog LoadStaticMaps 一致）
  // ========================================================================================
  void LoadStaticMaps()
  {
    // type_zone_map: 按 field_side 切换
    if (field_side_ == "right") {
      type_zone_map_ = {{"medicine", 1}, {"instrument", 2}, {"tool", 3}, {"food", 4}};
    } else {
      type_zone_map_ = {{"food", 1}, {"tool", 2}, {"instrument", 3}, {"medicine", 4}};
    }

    // place_zone_map（含点13/14 消转圈）
    place_zone_map_ = {
      {10, {{"left", 1},  {"right", 2}}},
      {11, {{"left", 2},  {"right", 3}}},
      {12, {{"left", 3},  {"right", 4}}},
      {13, {{"right", 1}}},
      {14, {{"left", 4}}},
    };

    // 反查表
    for (const auto & [pp, side_map] : place_zone_map_) {
      for (const auto & [dir, zone] : side_map) {
        reverse_place_map_[dir][zone] = pp;
      }
    }
  }

  // ========================================================================================
  // KeyboardListener
  // ========================================================================================
  void KeyboardListener()
  {
    while (keyboard_running_) {
      std::string input;
      if (std::getline(std::cin, input)) {
        auto trimmed = input;
        trimmed.erase(0, trimmed.find_first_not_of(" \t\r\n"));
        trimmed.erase(trimmed.find_last_not_of(" \t\r\n") + 1);
        if (trimmed == "y" || trimmed == "Y") {
          if (state_ == FbState::IDLE) {
            state_ = FbState::SCAN_AT_START;
            RCLCPP_INFO(this->get_logger(), "★ 收到 'y'，开始兜底: 点0 扫描箱11,12...");
          }
        }
      }
    }
  }

  // ========================================================================================
  // TimerCallback — 主循环
  // ========================================================================================
  void TimerCallback()
  {
    DogNavCommand cmd;
    cmd.header.stamp = this->now();
    cmd.header.frame_id = "base_link";
    cmd.height = nav_height_;
    cmd.model_path = "";

    double now_sec = std::chrono::duration<double>(
      std::chrono::steady_clock::now() - node_start_time_).count();

    switch (state_) {
      case FbState::IDLE:
        cmd.vx = 0.0f; cmd.vy = 0.0f; cmd.wz = 0.0f;
        break;

      // --------------------------------------------------
      // ★ SCAN_AT_START — 点0 扫描箱11,12 → 定 zone → 反查站位
      // --------------------------------------------------
      case FbState::SCAN_AT_START: {
        cmd.vx = 0.0f; cmd.vy = 0.0f; cmd.wz = 0.0f;
        if (!scan_done_) {
          scan_done_ = true;

          // ① 启动推流（独占 D435i + shm 喂帧给 box_detector）
          StartStreamer();

          // ② 点0 scan_all（target_zone 任意，只要 BOX_SCAN_MAP 全量结果）
          RCLCPP_INFO(this->get_logger(), "★ 点0 扫描（scan_all）...");
          RunBoxScan(0);

          // ③ 停止推流（释放相机）
          StopStreamer();

          // ④ 从 box_type_map_ 取箱11,12 类型 → 定 zone → 反查站位
          BuildFallbackPlan();

          // ⑤ 进 GOTO_PICKUP（sub_step 0：导航到左取货点4）
          if (round_.left.valid || round_.right.valid) {
            sub_step_ = 0;
            current_pos_ = 0;
            if (round_.left.valid) {
              RCLCPP_INFO(this->get_logger(), "★ 开始取放: 先导航到左取货点%d(吸箱%02d)",
                round_.pickup_point_left, round_.left.box_num);
              if (StartNavTo(round_.pickup_point_left, FbState::PICKUP)) {
                state_ = FbState::GOTO_PICKUP;
              } else {
                state_ = FbState::DONE;
              }
            } else {
              // 左箱无效，直接右箱
              sub_step_ = 2;
              if (StartNavTo(round_.pickup_point_right, FbState::PICKUP)) {
                state_ = FbState::GOTO_PICKUP;
              } else {
                state_ = FbState::DONE;
              }
            }
          } else {
            RCLCPP_ERROR(this->get_logger(), "★ 箱11/12 均未识别，兜底失败退出");
            state_ = FbState::DONE;
          }
        }
        break;
      }

      // --------------------------------------------------
      case FbState::GOTO_PICKUP:
      case FbState::GOTO_TARGET:
        HandleNavigation(cmd, now_sec);
        break;

      // --------------------------------------------------
      // ★ PICKUP — 蹲下取箱（sub_step 1=左点取箱11, 3=右点取箱12）
      // 蹲下+吸盘时序由 actor_ 编排（pick_place_actor.hpp）
      // --------------------------------------------------
      case FbState::PICKUP: {
        cmd.vx = 0.0f; cmd.vy = 0.0f; cmd.wz = 0.0f;

        if (sub_step_ == 0) sub_step_ = 1;
        else if (sub_step_ == 2) sub_step_ = 3;

        // 首次进入：记录取箱信息 + 启动 actor（发首帧后本 tick 不再 Tick）
        if (actor_.IsIdle()) {
          if (sub_step_ == 1 && round_.left.valid) {
            current_pos_ = round_.pickup_point_left;
            active_direction_ = "left";
            active_box_num_ = round_.left.box_num;
            active_box_type_ = round_.left.type;
            active_zone_ = round_.left.zone;
            RCLCPP_INFO(this->get_logger(),
              "★ 左取货点%d: 左吸盘吸箱%02d(%s)→zone%d（蹲下取箱）",
              round_.pickup_point_left, round_.left.box_num,
              round_.left.type.c_str(), round_.left.zone);
            ApplyActorFrame(actor_.StartPickup("left", now_sec));
          } else if (sub_step_ == 3 && round_.right.valid) {
            current_pos_ = round_.pickup_point_right;
            active_direction_ = "right";
            active_box_num_ = round_.right.box_num;
            active_box_type_ = round_.right.type;
            active_zone_ = round_.right.zone;
            RCLCPP_INFO(this->get_logger(),
              "★ 右取货点%d: 右吸盘吸箱%02d(%s)→zone%d（蹲下取箱）",
              round_.pickup_point_right, round_.right.box_num,
              round_.right.type.c_str(), round_.right.zone);
            ApplyActorFrame(actor_.StartPickup("right", now_sec));
          } else {
            AdvanceAfterPickup();
          }
          break;
        }

        // 蹲下+吸盘进行中 → 每 tick 推进 actor
        auto tr = actor_.Tick(now_sec);
        ApplyActorFrame(tr.frame);
        if (tr.action_done) {
          AdvanceAfterPickup();
        }
        break;
      }

      // --------------------------------------------------
      // ★ PLACE_BOX — 蹲下放箱（sub_step 5=放左箱, 7=放右箱）
      // 蹲下+吸盘时序由 actor_ 编排（pick_place_actor.hpp）
      // --------------------------------------------------
      case FbState::PLACE_BOX: {
        cmd.vx = 0.0f; cmd.vy = 0.0f; cmd.wz = 0.0f;

        if (sub_step_ == 4) sub_step_ = 5;
        else if (sub_step_ == 6) sub_step_ = 7;

        // 首次进入：启动 actor（发首帧后本 tick 不再 Tick）
        // 注: 放货点站位已保证吸盘对准归位区，无需转身（CalcPlaceTurnAngle 暂不用）
        if (actor_.IsIdle()) {
          RCLCPP_INFO(this->get_logger(),
            "★ 放置: 点%d, %s吸盘, 箱%02d(%s)→zone%d（蹲下放箱）",
            active_deliver_point_, active_direction_.c_str(),
            active_box_num_, active_box_type_.c_str(), active_zone_);

          ApplyActorFrame(actor_.StartPlace(active_direction_, now_sec));
          break;
        }

        // 蹲下+吸盘进行中 → 每 tick 推进 actor
        auto tr = actor_.Tick(now_sec);
        ApplyActorFrame(tr.frame);
        if (tr.action_done) {
          placed_zones_.insert(active_zone_);
          RCLCPP_INFO(this->get_logger(), "★ zone%d 已放置", active_zone_);
          AdvanceAfterPlace();
        }
        break;
      }

      // --------------------------------------------------
      case FbState::PLACE_AVOID:
        HandlePlaceAvoid(cmd, now_sec);
        break;

      // --------------------------------------------------
      case FbState::DONE:
        cmd.vx = 0.0f; cmd.vy = 0.0f; cmd.wz = 0.0f;
        break;
    }

    nav_cmd_pub_->publish(cmd);
  }

  // ========================================================================================
  // BuildFallbackPlan — 从扫描结果取箱11,12 → 定 zone → 反查站位（兜底专用）
  // ========================================================================================
  void BuildFallbackPlan()
  {
    // 兜底只取第2轮那对：点4左吸箱11，点5右吸箱12
    round_.pickup_point_left = 4;
    round_.pickup_point_right = 5;
    round_.left = {};
    round_.right = {};

    FillBoxInfo(round_.left, 11, "left");
    FillBoxInfo(round_.right, 12, "right");

    RCLCPP_INFO(this->get_logger(), "★ 兜底取放计划:");
    if (round_.left.valid) {
      RCLCPP_INFO(this->get_logger(),
        "  左点4吸箱11(%s)→zone%d→点%d",
        round_.left.type.c_str(), round_.left.zone, round_.left.place_point);
    } else {
      RCLCPP_WARN(this->get_logger(), "  箱11 未识别");
    }
    if (round_.right.valid) {
      RCLCPP_INFO(this->get_logger(),
        "  右点5吸箱12(%s)→zone%d→点%d",
        round_.right.type.c_str(), round_.right.zone, round_.right.place_point);
    } else {
      RCLCPP_WARN(this->get_logger(), "  箱12 未识别");
    }
  }

  // 填充单个 BoxInfo：查类型 → zone → 反查放货站位
  void FillBoxInfo(BoxInfo & info, int box_num, const std::string & direction)
  {
    info.box_num = box_num;
    info.direction = direction;

    auto type_it = box_type_map_.find(box_num);
    if (type_it == box_type_map_.end()) {
      RCLCPP_WARN(this->get_logger(), "★ 箱%02d 未在扫描结果中，跳过", box_num);
      return;
    }

    info.type = type_it->second;
    info.valid = true;

    auto zone_it = type_zone_map_.find(info.type);
    if (zone_it == type_zone_map_.end()) {
      RCLCPP_WARN(this->get_logger(),
        "★ 箱%02d 类型'%s'不在 type_zone_map，标记 valid 但 zone=0（放货点反查会失败）",
        box_num, info.type.c_str());
      return;
    }
    info.zone = zone_it->second;

    // 由 吸盘侧 + zone 反查放货站位
    auto dir_it = reverse_place_map_.find(direction);
    if (dir_it == reverse_place_map_.end()) {
      RCLCPP_WARN(this->get_logger(),
        "★ 反查表无吸盘侧'%s'，箱%02d place_point 保持 0（可能回起点）",
        direction.c_str(), box_num);
      return;
    }
    auto pp_it = dir_it->second.find(info.zone);
    if (pp_it == dir_it->second.end()) {
      RCLCPP_WARN(this->get_logger(),
        "★ 反查表无 %s/zone%d，箱%02d place_point 保持 0（可能回起点）",
        direction.c_str(), info.zone, box_num);
      return;
    }
    info.place_point = pp_it->second;
  }

  // ========================================================================================
  // AdvanceAfterPickup / GoDeliverFirst / AdvanceAfterPlace（同 navigation_dog 单轮逻辑）
  // ========================================================================================
  void AdvanceAfterPickup()
  {
    if (sub_step_ == 1) {
      // 左箱取完 → 去右取货点
      sub_step_ = 2;
      if (round_.right.valid) {
        RCLCPP_INFO(this->get_logger(), "★ 左箱取完，导航到右取货点%d", round_.pickup_point_right);
        if (StartNavTo(round_.pickup_point_right, FbState::PICKUP)) {
          state_ = FbState::GOTO_PICKUP;
        } else {
          state_ = FbState::DONE;
        }
      } else {
        RCLCPP_INFO(this->get_logger(), "★ 右箱无效，直接去放左箱");
        GoDeliverFirst();
      }
    } else if (sub_step_ == 3) {
      // 右箱取完 → 去放第一个箱（左箱）
      RCLCPP_INFO(this->get_logger(), "★ 两箱取完，去放第一个箱");
      GoDeliverFirst();
    }
  }

  void GoDeliverFirst()
  {
    if (round_.left.valid) {
      active_direction_ = "left";
      active_box_num_ = round_.left.box_num;
      active_box_type_ = round_.left.type;
      active_deliver_point_ = round_.left.place_point;
      active_zone_ = round_.left.zone;
      sub_step_ = 4;
      RCLCPP_INFO(this->get_logger(),
        "★ 去放第一个箱(左): 箱%02d(%s)→zone%d→点%d",
        round_.left.box_num, round_.left.type.c_str(),
        round_.left.zone, round_.left.place_point);
      if (StartNavTo(round_.left.place_point, FbState::PLACE_BOX)) {
        state_ = FbState::GOTO_TARGET;
      } else {
        state_ = FbState::DONE;
      }
    } else if (round_.right.valid) {
      // 左箱无效，直接放右箱
      active_direction_ = "right";
      active_box_num_ = round_.right.box_num;
      active_box_type_ = round_.right.type;
      active_deliver_point_ = round_.right.place_point;
      active_zone_ = round_.right.zone;
      sub_step_ = 6;
      RCLCPP_INFO(this->get_logger(),
        "★ 左箱无效，直接放右箱: 箱%02d(%s)→zone%d→点%d",
        round_.right.box_num, round_.right.type.c_str(),
        round_.right.zone, round_.right.place_point);
      if (StartNavTo(round_.right.place_point, FbState::PLACE_BOX)) {
        state_ = FbState::GOTO_TARGET;
      } else {
        state_ = FbState::DONE;
      }
    } else {
      RCLCPP_WARN(this->get_logger(), "★ 无有效箱子，兜底结束");
      state_ = FbState::DONE;
    }
  }

  void AdvanceAfterPlace()
  {
    if (sub_step_ == 5 && round_.right.valid) {
      // 放完左箱 → 去放右箱
      int dest_point = round_.right.place_point;
      bool need_avoid = NeedPlaceAvoid(active_deliver_point_, dest_point);

      active_direction_ = "right";
      active_box_num_ = round_.right.box_num;
      active_box_type_ = round_.right.type;
      active_deliver_point_ = dest_point;
      active_zone_ = round_.right.zone;
      sub_step_ = 6;

      RCLCPP_INFO(this->get_logger(),
        "★ 去放第二个箱: 箱%02d(%s)→zone%d→点%d %s",
        round_.right.box_num, round_.right.type.c_str(),
        round_.right.zone, dest_point, need_avoid ? "★需U型绕行" : "");

      if (need_avoid) {
        StartPlaceAvoid(dest_point);
        state_ = FbState::PLACE_AVOID;
      } else {
        if (StartNavTo(dest_point, FbState::PLACE_BOX)) {
          state_ = FbState::GOTO_TARGET;
        } else {
          state_ = FbState::DONE;
        }
      }
    } else {
      // 全部放完
      RCLCPP_INFO(this->get_logger(), "★ ★ ★ 兜底取放完成！ ★ ★ ★");
      state_ = FbState::DONE;
    }
  }

  // ========================================================================================
  // OdomCallback
  // ========================================================================================
  void OdomCallback(const nav_msgs::msg::Odometry::SharedPtr msg)
  {
    cur_x_ = msg->pose.pose.position.x;
    cur_y_ = msg->pose.pose.position.y;
    tf2::Quaternion q(
      msg->pose.pose.orientation.x, msg->pose.pose.orientation.y,
      msg->pose.pose.orientation.z, msg->pose.pose.orientation.w);
    tf2::Matrix3x3 m(q);
    double roll, pitch, yaw;
    m.getRPY(roll, pitch, yaw);
    cur_yaw_ = yaw;
    odom_received_ = true;
  }

  // ========================================================================================
  // 蹲下姿态发布（ApplyActorFrame / PublishJointPose / PublishPolicyMode）
  // ========================================================================================
  void ApplyActorFrame(const PickPlaceActor::Frame & frame)
  {
    if (frame.policy_mode.has_value()) {
      PublishPolicyMode(*frame.policy_mode);
    }
    if (frame.has_pose) {
      PublishJointPose(frame.pose);
    }
  }

  void PublishJointPose(const std::array<double, SquatController::kNumDofs> & pose)
  {
    sensor_msgs::msg::JointState js;
    js.header.stamp = this->now();
    js.header.frame_id = "base_link";
    js.name = {
      "FL_hip", "FL_thigh", "FL_calf",
      "FR_hip", "FR_thigh", "FR_calf",
      "RL_hip", "RL_thigh", "RL_calf",
      "RR_hip", "RR_thigh", "RR_calf"
    };
    js.position.assign(pose.begin(), pose.end());
    joint_state_pub_->publish(js);
  }

  void PublishPolicyMode(bool hold)
  {
    std_msgs::msg::Bool msg;
    msg.data = hold;
    policy_mode_pub_->publish(msg);
    RCLCPP_INFO(this->get_logger(), "★ /policy_mode = %s", hold ? "true(挂起)" : "false(恢复)");
  }

  // ========================================================================================
  // NormalizeAngle
  // ========================================================================================
  static double NormalizeAngle(double a)
  {
    while (a > M_PI) a -= 2.0 * M_PI;
    while (a < -M_PI) a += 2.0 * M_PI;
    return a;
  }

  // ========================================================================================
  // HandleNavigation（横移螃蟹步，同 navigation_dog）
  // ========================================================================================
  void HandleNavigation(DogNavCommand & cmd, double now_sec)
  {
    if (!nav_task_.active || nav_task_.finished) {
      cmd.vx = 0.0f; cmd.vy = 0.0f; cmd.wz = 0.0f;
      return;
    }

    if (nav_task_.seg_start_time <= 0.0) {
      nav_task_.seg_start_time = now_sec;
      if (!odom_received_) {
        RCLCPP_WARN(this->get_logger(), "★ 未收到里程计，使用时间导航");
      }
      RCLCPP_INFO(this->get_logger(), "★ 走段: %d → %d (%zu/%zu)",
        nav_task_.From(), nav_task_.To(),
        nav_task_.wp_idx + 1, nav_task_.path.size() - 1);
    }

    int target_point = nav_task_.To();
    const auto & target_coord = planner_->GetCoord(target_point);

    double elapsed = now_sec - nav_task_.seg_start_time;
    if (elapsed > nav_timeout_sec_) {
      RCLCPP_WARN(this->get_logger(), "★ 导航超时(%.1fs)，强制到达 %d", elapsed, target_point);
      FinishWaypoint(cmd, now_sec);
      return;
    }

    if (!odom_received_) {
      if (elapsed < segment_time_sec_) {
        cmd.vx = nav_vx_; cmd.vy = 0.0f; cmd.wz = 0.0f;
      } else {
        FinishWaypoint(cmd, now_sec);
      }
      return;
    }

    double target_yaw_rad = target_coord.theta * M_PI / 180.0;
    double dx = target_coord.x - cur_x_;
    double dy = target_coord.y - cur_y_;
    double dist = std::sqrt(dx * dx + dy * dy);
    double yaw_error_final = NormalizeAngle(target_yaw_rad - cur_yaw_);

    if (dist < pos_tolerance_) {
      if (std::abs(yaw_error_final) < yaw_tolerance_) {
        RCLCPP_INFO(this->get_logger(), "★ 到达点位 %d (dist=%.3fm, yaw=%.1f°)",
          target_point, dist, yaw_error_final * 180.0 / M_PI);
        FinishWaypoint(cmd, now_sec);
        return;
      }
      double wz = std::clamp(nav_kp_yaw_ * yaw_error_final, -nav_max_wz_, nav_max_wz_);
      cmd.vx = 0.0f; cmd.vy = 0.0f;
      cmd.wz = static_cast<float>(wz);
      return;
    }

    // 横移螃蟹步
    double cos_yaw = std::cos(cur_yaw_);
    double sin_yaw = std::sin(cur_yaw_);
    double vx_body =  dx * cos_yaw + dy * sin_yaw;
    double vy_body = -dx * sin_yaw + dy * cos_yaw;

    double vx = std::clamp(nav_kp_xy_ * vx_body, -nav_max_vx_, nav_max_vx_);
    double vy = std::clamp(nav_kp_xy_ * vy_body, -nav_max_vy_, nav_max_vy_);

    cmd.vx = static_cast<float>(vx);
    cmd.vy = static_cast<float>(vy);
    cmd.wz = 0.0f;
  }

  void FinishWaypoint(DogNavCommand & cmd, double now_sec)
  {
    cmd.vx = 0.0f; cmd.vy = 0.0f; cmd.wz = 0.0f;
    nav_task_.wp_idx++;
    nav_task_.seg_start_time = now_sec;
    RCLCPP_INFO(this->get_logger(), "★ 到达点位 %d", nav_task_.path[nav_task_.wp_idx]);

    if (nav_task_.wp_idx + 1 >= nav_task_.path.size()) {
      nav_task_.finished = true;
      nav_task_.active = false;
      current_pos_ = nav_task_.path.back();
      RCLCPP_INFO(this->get_logger(), "★ 路径走完，到达 %d", current_pos_);
      state_ = next_state_;
    }
  }

  // ========================================================================================
  // StartNavTo
  // ========================================================================================
  bool StartNavTo(int target, FbState next_state)
  {
    auto path = planner_->BFS(current_pos_, target, blocked_, placed_zones_);
    if (path.empty()) {
      RCLCPP_ERROR(this->get_logger(), "★ 无法规划路径: %d → %d", current_pos_, target);
      return false;
    }
    RCLCPP_INFO(this->get_logger(), "★ 导航路径 %s", planner_->PathStr(path).c_str());
    nav_task_.Start(path);
    next_state_ = next_state;
    return true;
  }

  // ========================================================================================
  // CalcPlaceTurnAngle（同 navigation_dog）
  // ========================================================================================
  double CalcPlaceTurnAngle(int place_point, const std::string & direction)
  {
    const auto & place_coord = planner_->GetCoord(place_point);
    double px = place_coord.x;
    double py = place_coord.y;

    int zone_id = 0;
    auto pzm = place_zone_map_.find(place_point);
    if (pzm != place_zone_map_.end()) {
      auto dit = pzm->second.find(direction);
      if (dit != pzm->second.end()) zone_id = dit->second;
    }
    if (zone_id == 0) {
      RCLCPP_WARN(this->get_logger(), "★ 放货点%d/%s 归位区映射缺失，用默认±90°",
        place_point, direction.c_str());
      return (direction == "left") ? (-M_PI / 2.0) : (M_PI / 2.0);
    }

    auto it = zone_coords_.find(zone_id);
    if (it == zone_coords_.end()) {
      RCLCPP_WARN(this->get_logger(), "★ 归位区 %d 坐标未配置，用默认±90°", zone_id);
      return (direction == "left") ? (-M_PI / 2.0) : (M_PI / 2.0);
    }
    double zx = it->second.x;
    double zy = it->second.y;

    double zone_angle = std::atan2(zy - py, zx - px);
    double sucker_angle = (direction == "left")
      ? (cur_yaw_ + M_PI / 2.0)
      : (cur_yaw_ - M_PI / 2.0);
    double turn = NormalizeAngle(zone_angle - sucker_angle);

    RCLCPP_INFO(this->get_logger(),
      "★ 自动计算转身: 放置点%d(%.2f,%.2f) → zone%d(%.2f,%.2f), turn=%.1f°",
      place_point, px, py, zone_id, zx, zy, turn * 180.0 / M_PI);
    return turn;
  }

  // ========================================================================================
  // NeedPlaceAvoid / StartPlaceAvoid / HandlePlaceAvoid（U型避障，同 navigation_dog）
  // ========================================================================================
  bool NeedPlaceAvoid(int from_point, int to_point)
  {
    auto is_place_row = [](int p) { return p == 10 || p == 11 || p == 12; };
    if (!is_place_row(from_point) || !is_place_row(to_point)) return false;
    if (from_point == to_point) return false;

    int lo = std::min(from_point, to_point);
    int hi = std::max(from_point, to_point);
    if (lo == 10 && hi == 11) return placed_zones_.count(2) > 0;
    if (lo == 11 && hi == 12) return placed_zones_.count(3) > 0;
    if (lo == 10 && hi == 12) return placed_zones_.count(2) > 0 || placed_zones_.count(3) > 0;
    return false;
  }

  void StartPlaceAvoid(int dest_point)
  {
    const auto & dest = planner_->GetCoord(dest_point);
    avoid_maneuver_.active = true;
    avoid_maneuver_.phase = 0;
    avoid_maneuver_.start_x = cur_x_;
    avoid_maneuver_.start_y = cur_y_;
    avoid_maneuver_.dest_x = dest.x;
    avoid_maneuver_.dest_y = dest.y;
    avoid_maneuver_.phase_start_time = this->now().seconds();
    RCLCPP_INFO(this->get_logger(),
      "★ 启动 U型避障: 当前(%.2f,%.2f) → 目标点%d(%.2f,%.2f)",
      cur_x_, cur_y_, dest_point, dest.x, dest.y);
  }

  void HandlePlaceAvoid(DogNavCommand & cmd, double now_sec)
  {
    const double pos_tol = 0.05;
    const double timeout = 10.0;

    double target_x = cur_x_, target_y = cur_y_;
    switch (avoid_maneuver_.phase) {
      case 0: target_x = avoid_maneuver_.start_x;
              target_y = avoid_maneuver_.start_y - place_avoid_dist_; break;
      case 1: target_x = avoid_maneuver_.dest_x;
              target_y = avoid_maneuver_.start_y - place_avoid_dist_; break;
      case 2: target_x = avoid_maneuver_.dest_x;
              target_y = avoid_maneuver_.dest_y; break;
    }

    double dx = target_x - cur_x_;
    double dy = target_y - cur_y_;
    double dist = std::hypot(dx, dy);
    double elapsed = now_sec - avoid_maneuver_.phase_start_time;

    if (dist < pos_tol || elapsed > timeout) {
      RCLCPP_INFO(this->get_logger(), "★ U型 phase%d 完成", avoid_maneuver_.phase);
      avoid_maneuver_.phase++;
      avoid_maneuver_.phase_start_time = now_sec;
      if (avoid_maneuver_.phase > 2) {
        avoid_maneuver_.active = false;
        current_pos_ = active_deliver_point_;
        state_ = FbState::PLACE_BOX;
        cmd.vx = 0.0f; cmd.vy = 0.0f; cmd.wz = 0.0f;
        return;
      }
      cmd.vx = 0.0f; cmd.vy = 0.0f; cmd.wz = 0.0f;
      return;
    }

    double vx_body = dx * std::cos(cur_yaw_) + dy * std::sin(cur_yaw_);
    double vy_body = -dx * std::sin(cur_yaw_) + dy * std::cos(cur_yaw_);
    double vx = std::clamp(nav_kp_xy_ * vx_body, -nav_max_vx_, nav_max_vx_);
    double vy = std::clamp(nav_kp_xy_ * vy_body, -nav_max_vy_, nav_max_vy_);
    cmd.vx = static_cast<float>(vx);
    cmd.vy = static_cast<float>(vy);
    cmd.wz = 0.0f;
  }

  // ========================================================================================
  // RunBoxScan（点0 scan_all，解析 BOX_SCAN_MAP，同 navigation_dog）
  // ========================================================================================
  void RunBoxScan(int target_zone)
  {
    std::string cmd = "python3 " + box_scanner_path_ +
      " --mode scan_all --target-zone " + std::to_string(target_zone) +
      " --field-side " + field_side_ + " 2>&1";

    RCLCPP_INFO(this->get_logger(), "★ 执行: %s", cmd.c_str());
    FILE * pipe = popen(cmd.c_str(), "r");
    if (!pipe) {
      RCLCPP_ERROR(this->get_logger(), "★ 无法执行 box_detector_rknn.py");
      return;
    }

    std::string output;
    char buf[512];
    while (fgets(buf, sizeof(buf), pipe)) output += buf;
    (void)pclose(pipe);

    RCLCPP_INFO(this->get_logger(), "★ box_scanner 输出:\n%s", output.c_str());

    // 解析 BOX_SCAN_MAP=11:food,12:tool,...
    auto map_pos = output.find("BOX_SCAN_MAP=");
    if (map_pos == std::string::npos) {
      RCLCPP_ERROR(this->get_logger(), "★ box_scanner 未输出 BOX_SCAN_MAP");
      return;
    }
    std::string map_str = output.substr(map_pos + 13);
    auto map_nl = map_str.find('\n');
    if (map_nl != std::string::npos) map_str = map_str.substr(0, map_nl);
    map_str.erase(0, map_str.find_first_not_of(" \t\r"));
    map_str.erase(map_str.find_last_not_of(" \t\r") + 1);

    box_type_map_.clear();
    std::istringstream map_iss(map_str);
    std::string entry;
    while (std::getline(map_iss, entry, ',')) {
      auto colon = entry.find(':');
      if (colon != std::string::npos) {
        try {
          int pt = std::stoi(entry.substr(0, colon));
          std::string tp = entry.substr(colon + 1);
          tp.erase(0, tp.find_first_not_of(" \t\r"));
          tp.erase(tp.find_last_not_of(" \t\r") + 1);
          box_type_map_[pt] = tp;
        } catch (...) {}
      }
    }
    RCLCPP_INFO(this->get_logger(), "★ 场地箱子映射:");
    for (const auto & [pt, tp] : box_type_map_) {
      RCLCPP_INFO(this->get_logger(), "  箱%d → %s", pt, tp.c_str());
    }
  }

  // ========================================================================================
  // StartStreamer / StopStreamer（推流，同 navigation_dog）
  // ========================================================================================
  void StartStreamer()
  {
    if (!stream_enable_ || streamer_pid_ > 0) return;

    std::string cmd = "python3 " + streamer_path_ + " --port " +
                      std::to_string(stream_port_) + " > /tmp/d435i_stream.log 2>&1 &";
    FILE * pipe = popen(cmd.c_str(), "r");
    if (!pipe) {
      RCLCPP_WARN(this->get_logger(), "★ 推流启动失败（box_detector 将回退直接开相机）");
      return;
    }
    char buf[64] = {0};
    if (fgets(buf, sizeof(buf), pipe)) streamer_pid_ = atoi(buf);
    pclose(pipe);

    if (streamer_pid_ <= 0) {
      FILE * gp = popen("pgrep -f d435i_stream.py", "r");
      if (gp) {
        if (fgets(buf, sizeof(buf), gp)) streamer_pid_ = atoi(buf);
        pclose(gp);
      }
    }

    const char * shm = "/dev/shm/d435i_frame.npz";
    for (int i = 0; i < 50; ++i) {
      if (access(shm, F_OK) == 0) {
        RCLCPP_INFO(this->get_logger(),
          "★ 推流就绪 (pid=%d, port=%d)，Foxglove 连 ws://<上位机IP>:%d",
          streamer_pid_, stream_port_, stream_port_);
        return;
      }
      std::this_thread::sleep_for(std::chrono::milliseconds(100));
    }
    RCLCPP_WARN(this->get_logger(), "★ 推流 5s 未就绪（box_detector 将回退直接开相机）");
  }

  void StopStreamer()
  {
    if (streamer_pid_ <= 0) return;
    RCLCPP_INFO(this->get_logger(), "★ 停止推流 pid=%d", streamer_pid_);
    kill(streamer_pid_, SIGTERM);
    for (int i = 0; i < 10; ++i) {
      int status = 0;
      pid_t r = waitpid(streamer_pid_, &status, WNOHANG);
      if (r == streamer_pid_ || r == -1) break;
      std::this_thread::sleep_for(std::chrono::milliseconds(100));
    }
    if (waitpid(streamer_pid_, nullptr, WNOHANG) == 0) {
      kill(streamer_pid_, SIGKILL);
      waitpid(streamer_pid_, nullptr, 0);
    }
    streamer_pid_ = -1;
    unlink("/dev/shm/d435i_frame.npz");
  }

  // =========================
  // 成员变量
  // =========================
  rclcpp::Publisher<DogNavCommand>::SharedPtr nav_cmd_pub_;
  rclcpp::Publisher<sensor_msgs::msg::JointState>::SharedPtr joint_state_pub_;
  rclcpp::Publisher<std_msgs::msg::Bool>::SharedPtr policy_mode_pub_;
  rclcpp::TimerBase::SharedPtr timer_;
  rclcpp::Subscription<nav_msgs::msg::Odometry>::SharedPtr odom_sub_;

  std::unique_ptr<FieldPathPlanner> planner_;

  // 状态机
  FbState state_{FbState::IDLE};
  FbState next_state_{FbState::DONE};
  int current_pos_{0};
  bool scan_done_{false};

  // 取放（单轮）
  PickupRound round_;
  int sub_step_{0};

  int active_deliver_point_{0};
  std::string active_direction_;
  int active_box_num_{0};
  std::string active_box_type_;
  int active_zone_{0};

  std::unordered_set<int> placed_zones_;

  // U型避障
  struct AvoidManeuver {
    bool active{false};
    int phase{0};
    double start_x{0.0}, start_y{0.0};
    double dest_x{0.0}, dest_y{0.0};
    double phase_start_time{0.0};
  } avoid_maneuver_;
  double place_avoid_dist_{1.0};

  // 控制器（蹲下+吸盘 编排器，封装 squat_ctrl_ + sucker_ + 取放时序 flags）
  PickPlaceActor actor_;

  // 静态映射表
  std::map<std::string, int> type_zone_map_;
  std::map<int, std::map<std::string, int>> place_zone_map_;
  std::map<std::string, std::map<int, int>> reverse_place_map_;

  // 导航任务
  NavTask nav_task_;
  std::unordered_set<int> blocked_;

  // 扫描结果
  std::map<int, std::string> box_type_map_;

  // 坐标
  std::map<int, Point3D> zone_coords_;

  // 参数
  float nav_vx_{0.3f};
  float nav_height_{0.25f};
  std::string field_side_{"left"};
  std::string box_scanner_path_;
  double segment_time_sec_{3.0};
  bool auto_start_{false};

  std::string sucker_port_{"/dev/ttyUSB0"};
  int sucker_baudrate_{115200};
  double sucker_move_sec_{3.0};
  double sucker_hold_sec_{0.5};

  bool stream_enable_{true};
  int stream_port_{8765};
  pid_t streamer_pid_{-1};
  std::string streamer_path_{
    std::string("/home/zhy/himdog/src/dog_nav/resource/vision/d435i_stream.py")};

  std::string odom_topic_{"/lio/odom"};
  double pos_tolerance_{0.05};
  double yaw_tolerance_{0.087};
  double nav_kp_xy_{0.8};
  double nav_kp_yaw_{1.5};
  double nav_max_vx_{0.5};
  double nav_max_vy_{0.3};
  double nav_max_wz_{1.0};
  double nav_timeout_sec_{15.0};

  std::chrono::steady_clock::time_point node_start_time_;
  std::thread keyboard_thread_;
  std::atomic<bool> keyboard_running_{false};

  double cur_x_{0.0}, cur_y_{0.0}, cur_yaw_{0.0};
  bool odom_received_{false};
};

int main(int argc, char ** argv)
{
  rclcpp::init(argc, argv);
  rclcpp::spin(std::make_shared<FallbackNode>());
  rclcpp::shutdown();
  return 0;
}
