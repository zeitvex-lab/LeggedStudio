// ========================================================================================
// navigation_dog_2.cpp — 任务赛导航节点（★ 新机构版：一次吸两箱，10 节点布局）
// ========================================================================================
//
// 与 navigation_dog 的区别:
//   - 取货: 站一个点同时吸2个箱（点2→09+10, 点3→11+12, 点4→05+06, 点5→07+08）
//   - 放货: zone→放货点 1对1（zone1→点6, zone2→点7, zone3→点8, zone4→点9）
//   - 10 节点布局（无点13/14），无转圈倒车，无 U 型避障
//
// 状态机:
//   IDLE → OCR_SOLVE → BOX_SCAN_PHASE0(点0) → GOTO_POINT1 → BOX_SCAN_PHASE1(点1) → 合并+计划
//        → [循环4轮: GOTO_PICKUP → PICKUP → GOTO_TARGET → PLACE_BOX → GOTO_TARGET → PLACE_BOX] → DONE
//
// 运行:
//   ros2 run dog_nav navigation_dog_2 --ros-args \
//     --params-file src/dog_nav/config/task_race_2.yaml \
//     -p auto_start:=true

#include <rclcpp/rclcpp.hpp>
#include <dog_nav/msg/dog_nav_command.hpp>
#include <nav_msgs/msg/odometry.hpp>
#include <sensor_msgs/msg/joint_state.hpp>
#include <std_msgs/msg/bool.hpp>
#include <tf2/LinearMath/Quaternion.h>
#include <tf2/LinearMath/Matrix3x3.h>
#include "dog_nav/field_path_planner.hpp"
#include "dog_nav/delivery_planner.hpp"
#include "dog_nav/sucker_dual.hpp"        // ★ 双吸控制器（一次吸两箱）
#include "dog_nav/squat_controller.hpp"

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
using dog_nav::SuckerDual;
using dog_nav::SquatController;
using dog_nav::Point3D;
using dog_nav::BoxInfo;
using dog_nav::PickupRound;

// ========================================================================================
// 状态枚举
// ========================================================================================

enum class NavState
{
  IDLE = 0,
  OCR_SOLVE,
  BOX_SCAN_PHASE0,
  GOTO_POINT1,
  BOX_SCAN_PHASE1,    // = MERGE
  GOTO_PICKUP,
  PICKUP,
  GOTO_TARGET,
  PLACE_BOX,
  DONE
};

inline const char * NavStateStr(NavState s)
{
  switch (s) {
    case NavState::IDLE:           return "IDLE";
    case NavState::OCR_SOLVE:      return "OCR_SOLVE";
    case NavState::BOX_SCAN_PHASE0: return "BOX_SCAN_PHASE0";
    case NavState::GOTO_POINT1:    return "GOTO_POINT1";
    case NavState::BOX_SCAN_PHASE1: return "BOX_SCAN_PHASE1";
    case NavState::GOTO_PICKUP:    return "GOTO_PICKUP";
    case NavState::PICKUP:         return "PICKUP";
    case NavState::GOTO_TARGET:    return "GOTO_TARGET";
    case NavState::PLACE_BOX:      return "PLACE_BOX";
    case NavState::DONE:           return "DONE";
    default:                       return "UNKNOWN";
  }
}

// ========================================================================================
// 节点
// ========================================================================================

class NavigationDog2Node : public rclcpp::Node
{
public:
  NavigationDog2Node()
  : Node("navigation_dog_2_node")
  {
    // =========================
    // 1. 声明参数
    // =========================
    this->declare_parameter("loop_rate_hz", 20);
    this->declare_parameter("nav_vx", 0.3);
    this->declare_parameter("nav_height", 0.25);
    this->declare_parameter("field_side", std::string("left"));
    this->declare_parameter("box_scanner_path", std::string(
      "/home/zhy/himdog/src/dog_nav/resource/vision/box_detector_rknn.py"));
    this->declare_parameter("solver_path", std::string(
      "/home/zhy/himdog/src/dog_nav/resource/vision/solver.py"));

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

    // 吸盘
    this->declare_parameter("sucker_port", std::string("/dev/ttyUSB0"));
    this->declare_parameter("sucker_baudrate", 115200);
    this->declare_parameter("sucker_move_sec", 3.0);
    this->declare_parameter("sucker_hold_sec", 0.5);

    // 蹲下
    this->declare_parameter("stand_pose", std::vector<double>(12, 0.0));
    this->declare_parameter("squat_pose", std::vector<double>{
      0.0, 0.0, -0.8, 0.0, 0.0, 0.8, 0.0, -0.1, -0.8, 0.0, 0.1, 0.8});
    this->declare_parameter("squat_interp_sec", 1.0);
    this->declare_parameter("squat_hold_sec", 5.0);

    // 推流
    this->declare_parameter("stream_enable", true);
    this->declare_parameter("stream_port", 8765);

    // 坐标参数
    DeclareCoordParams();

    // =========================
    // 2. 读取参数
    // =========================
    nav_vx_ = static_cast<float>(this->get_parameter("nav_vx").as_double());
    nav_height_ = static_cast<float>(this->get_parameter("nav_height").as_double());
    field_side_ = this->get_parameter("field_side").as_string();
    box_scanner_path_ = this->get_parameter("box_scanner_path").as_string();
    solver_path_ = this->get_parameter("solver_path").as_string();
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
      squat_ctrl_.SetStandPose(stand);
      squat_ctrl_.SetSquatPose(squat);
      squat_ctrl_.SetInterpSec(this->get_parameter("squat_interp_sec").as_double());
      squat_ctrl_.SetHoldSec(this->get_parameter("squat_hold_sec").as_double());
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
    // 3. 构建规划器（V2 图）+ 坐标 + 映射
    // =========================
    planner_ = std::make_unique<FieldPathPlanner>();
    planner_->BuildFieldGraphV2();
    planner_->BuildFieldCoordsDefaultV2();
    LoadCoordsFromParams();
    blocked_ = {};
    LoadStaticMaps();

    // mod4 → zone（按 field_side）
    if (field_side_ == "right") {
      mod4_target_ = {4, 3, 2, 1};
    } else {
      mod4_target_ = {1, 2, 3, 4};
    }

    // =========================
    // 4. 发布/订阅
    // =========================
    nav_cmd_pub_ = this->create_publisher<DogNavCommand>("/nav_cmd", 10);
    joint_state_pub_ = this->create_publisher<sensor_msgs::msg::JointState>("/joint_states", 10);
    policy_mode_pub_ = this->create_publisher<std_msgs::msg::Bool>("/policy_mode", 10);

    odom_sub_ = this->create_subscription<nav_msgs::msg::Odometry>(
      odom_topic_, rclcpp::QoS(10).best_effort(),
      std::bind(&NavigationDog2Node::OdomCallback, this, std::placeholders::_1));
    RCLCPP_INFO(this->get_logger(), "订阅里程计: %s", odom_topic_.c_str());

    // =========================
    // 5. 定时器
    // =========================
    const int rate_hz = this->get_parameter("loop_rate_hz").as_int();
    const auto period = std::chrono::milliseconds(1000 / std::max(1, rate_hz));
    timer_ = this->create_wall_timer(period, std::bind(&NavigationDog2Node::TimerCallback, this));
    node_start_time_ = std::chrono::steady_clock::now();

    // =========================
    // 6. 吸盘串口
    // =========================
    sucker_.SetMoveSec(sucker_move_sec_);
    sucker_.SetHoldSec(sucker_hold_sec_);
    sucker_.Open(sucker_port_, sucker_baudrate_);

    // =========================
    // 7. 键盘线程
    // =========================
    if (!auto_start_) {
      keyboard_running_ = true;
      keyboard_thread_ = std::thread(&NavigationDog2Node::KeyboardListener, this);
      RCLCPP_INFO(this->get_logger(), "navigation_dog_2 — 按 'y' + 回车 启动");
    } else {
      RCLCPP_INFO(this->get_logger(), "navigation_dog_2 — auto_start=true");
    }

    // 打印坐标
    for (int i = 0; i <= 9; ++i) {
      const auto & c = planner_->GetCoord(i);
      RCLCPP_INFO(this->get_logger(), "  点位 %02d: (%.3f, %.3f, %.1f°)", i, c.x, c.y, c.theta);
    }

    if (auto_start_) {
      state_ = NavState::OCR_SOLVE;
      RCLCPP_INFO(this->get_logger(), "★ 开始 OCR 求解...");
    }
  }

  ~NavigationDog2Node()
  {
    keyboard_running_ = false;
    if (keyboard_thread_.joinable()) {
      keyboard_thread_.join();
    }
    StopStreamer();
  }

private:

  // ========================================================================================
  // 坐标参数声明/加载（V2: point_1-5 + place_6-9）
  // ========================================================================================
  void DeclareCoordParams()
  {
    this->declare_parameter("start_pose", std::vector<double>{0.0, 0.0, 0.0});
    const std::vector<std::string> pickup_names = {"point_1", "point_2", "point_3", "point_4", "point_5"};
    for (const auto & name : pickup_names) {
      this->declare_parameter("pickup_positions." + name, std::vector<double>{0.0, 0.0, 0.0});
    }
    const std::vector<std::string> place_names = {"point_6", "point_7", "point_8", "point_9"};
    for (const auto & name : place_names) {
      this->declare_parameter("place_positions." + name, std::vector<double>{0.0, 0.0, 0.0});
    }
  }

  void LoadCoordsFromParams()
  {
    LoadAndSetCoord("start_pose", 0);
    const std::vector<std::pair<std::string, int>> pickup_map = {
      {"pickup_positions.point_1", 1}, {"pickup_positions.point_2", 2},
      {"pickup_positions.point_3", 3}, {"pickup_positions.point_4", 4},
      {"pickup_positions.point_5", 5},
    };
    for (const auto & [p, id] : pickup_map) LoadAndSetCoord(p, id);

    const std::vector<std::pair<std::string, int>> place_map = {
      {"place_positions.point_6", 6}, {"place_positions.point_7", 7},
      {"place_positions.point_8", 8}, {"place_positions.point_9", 9},
    };
    for (const auto & [p, id] : place_map) LoadAndSetCoord(p, id);
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
  // 静态映射（V2: 新取货映射 + zone→放货点 1对1）
  // ========================================================================================
  void LoadStaticMaps()
  {
    // type_zone_map: 按 field_side 切换（与 navigation_dog 一致）
    if (field_side_ == "right") {
      type_zone_map_ = {{"medicine", 1}, {"instrument", 2}, {"tool", 3}, {"food", 4}};
    } else {
      type_zone_map_ = {{"food", 1}, {"tool", 2}, {"instrument", 3}, {"medicine", 4}};
    }

    // ★ V2: zone → 放货点 1对1（无吸盘侧反查，无转圈）
    zone_to_place_ = {
      {1, 6},   // zone1 → 点6
      {2, 7},   // zone2 → 点7
      {3, 8},   // zone3 → 点8
      {4, 9},   // zone4 → 点9
    };

    // ★ V2 取货映射: 取货点 → 一对箱子（一次吸2个）
    //   点2→09+10, 点3→11+12, 点4→05+06, 点5→07+08
    pickup_box_pairs_ = {
      {2, 9, 10},
      {3, 11, 12},
      {4, 5, 6},
      {5, 7, 8},
    };
  }

  // ========================================================================================
  // GenerateDeliveryPlan — 4 轮，每轮 = 1 取货点吸 2 箱 → 按类型定 2 个 zone → 放 2 次
  // ========================================================================================
  void GenerateDeliveryPlan()
  {
    delivery_plan_.clear();
    RCLCPP_INFO(this->get_logger(), "★ 生成取放计划（一站吸两箱）");

    for (const auto & [pickup_point, box_a, box_b] : pickup_box_pairs_) {
      PickupRound round;
      round.pickup_point_left = pickup_point;
      round.pickup_point_right = pickup_point;  // 同一个点吸两个

      FillBoxInfo(round.left, box_a);
      FillBoxInfo(round.right, box_b);

      if (round.left.valid || round.right.valid) {
        delivery_plan_.push_back(round);
        RCLCPP_INFO(this->get_logger(),
          "  点%d: 箱%02d(%s)→zone%d, 箱%02d(%s)→zone%d",
          pickup_point,
          box_a, round.left.type.c_str(), round.left.zone,
          box_b, round.right.type.c_str(), round.right.zone);
      }
    }
    RCLCPP_INFO(this->get_logger(), "★ 共 %zu 轮", delivery_plan_.size());
  }

  void FillBoxInfo(BoxInfo & info, int box_num)
  {
    info.box_num = box_num;
    info.direction = "left";  // V2 不区分左右吸盘（一次吸两个），direction 占位

    auto type_it = box_type_map_.find(box_num);
    if (type_it == box_type_map_.end()) return;
    info.type = type_it->second;
    info.valid = true;

    auto zone_it = type_zone_map_.find(info.type);
    if (zone_it == type_zone_map_.end()) return;
    info.zone = zone_it->second;

    auto place_it = zone_to_place_.find(info.zone);
    if (place_it != zone_to_place_.end()) {
      info.place_point = place_it->second;
    }
  }

  // ========================================================================================
  // StartDeliveryRound
  // ========================================================================================
  void StartDeliveryRound()
  {
    if (round_idx_ >= static_cast<int>(delivery_plan_.size())) {
      RCLCPP_INFO(this->get_logger(), "★ 全部 %zu 轮取放完成", delivery_plan_.size());
      state_ = NavState::DONE;
      return;
    }

    const auto & round = delivery_plan_[round_idx_];
    sub_step_ = 0;
    pickup_executed_ = false;
    place_executed_ = false;
    RCLCPP_INFO(this->get_logger(), "★ 第 %d/%zu 轮 → 去取货点%d",
      round_idx_ + 1, delivery_plan_.size(), round.pickup_point_left);

    if (StartNavTo(round.pickup_point_left, NavState::PICKUP)) {
      state_ = NavState::GOTO_PICKUP;
    } else {
      state_ = NavState::DONE;
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
          if (state_ == NavState::IDLE) {
            state_ = NavState::OCR_SOLVE;
            RCLCPP_INFO(this->get_logger(), "★ 收到 'y'，开始 OCR...");
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
      case NavState::IDLE:
        cmd.vx = 0.0f; cmd.vy = 0.0f; cmd.wz = 0.0f;
        break;

      // --------------------------------------------------
      case NavState::OCR_SOLVE: {
        cmd.vx = 0.0f; cmd.vy = 0.0f; cmd.wz = 0.0f;
        if (!ocr_started_) {
          ocr_started_ = true;
          StartStreamer();

          // OCR（solver.py 内部会逐步输出 [1]OCR启动 [2]拍照 [3]识别式子 [4]结果 [5]播报）
          int target = -1;
          for (int retry = 0; retry < 3; ++retry) {
            int mod4 = RunSolver();
            if (mod4 >= 0 && mod4 < 4) {
              target = mod4_target_[mod4];
              RCLCPP_INFO(this->get_logger(), "★ OCR 完成 → 高分归位区 zone%d", target);
              break;
            }
            RCLCPP_WARN(this->get_logger(), "★ OCR 第 %d 次失败，重试...", retry + 1);
          }
          if (target < 0) {
            target = mod4_target_[0];
            RCLCPP_WARN(this->get_logger(), "★ OCR 失败，用默认 zone%d", target);
          }
          deliver_zone_ = target;

          state_ = NavState::BOX_SCAN_PHASE0;
        }
        break;
      }

      // --------------------------------------------------
      case NavState::BOX_SCAN_PHASE0: {
        cmd.vx = 0.0f; cmd.vy = 0.0f; cmd.wz = 0.0f;
        if (!scan0_done_) {
          scan0_done_ = true;
          RCLCPP_INFO(this->get_logger(), "★ 开启物资箱识别（点0 远看 8 箱）...");
          RunBoxScan(deliver_zone_);
          phase0_map_ = box_type_map_;
          RCLCPP_INFO(this->get_logger(), "★ 识别成功，识别到 %zu 箱", phase0_map_.size());

          current_pos_ = 0;
          if (StartNavTo(1, NavState::BOX_SCAN_PHASE1)) {
            state_ = NavState::GOTO_POINT1;
          } else {
            state_ = NavState::DONE;
          }
        }
        break;
      }

      // --------------------------------------------------
      case NavState::GOTO_POINT1:
      case NavState::GOTO_PICKUP:
      case NavState::GOTO_TARGET:
        HandleNavigation(cmd, now_sec);
        break;

      // --------------------------------------------------
      case NavState::BOX_SCAN_PHASE1: {
        cmd.vx = 0.0f; cmd.vy = 0.0f; cmd.wz = 0.0f;
        if (!scan1_done_) {
          scan1_done_ = true;
          RCLCPP_INFO(this->get_logger(), "★ 物资箱识别（点1 近看 4 箱）...");
          RunBoxScan(deliver_zone_);

          // 合并（Phase1 覆盖 Phase0）
          for (const auto & [k, v] : box_type_map_) phase0_map_[k] = v;
          box_type_map_ = phase0_map_;

          // 校验: 4 种类型 × 每种 2 个
          std::map<std::string, int> type_count;
          for (const auto & [k, v] : box_type_map_) type_count[v]++;
          bool ok = true;
          for (const auto & t : {"food", "tool", "instrument", "medicine"}) {
            if (type_count[t] != 2) {
              RCLCPP_WARN(this->get_logger(), "★ 校验: %s 有 %d 个（应 2）", t, type_count[t]);
              ok = false;
            }
          }

          // 打印识别结果（8 箱类型汇总）
          RCLCPP_INFO(this->get_logger(), "★ 识别结果汇总:");
          for (const auto & [pt, tp] : box_type_map_) {
            RCLCPP_INFO(this->get_logger(), "    箱%02d → %s", pt, tp.c_str());
          }
          if (ok) {
            RCLCPP_INFO(this->get_logger(), "★ 校验通过: 4 类型 × 每种 2 个");
          } else {
            RCLCPP_WARN(this->get_logger(), "★ 校验失败，用当前结果继续");
          }

          GenerateDeliveryPlan();
          StopStreamer();

          if (delivery_plan_.empty()) {
            RCLCPP_ERROR(this->get_logger(), "★ 计划为空，退出");
            state_ = NavState::DONE;
          } else {
            round_idx_ = 0;
            StartDeliveryRound();
          }
        }
        break;
      }

      // --------------------------------------------------
      // ★ PICKUP — 蹲下取 2 箱（新机构一次吸两箱）
      // --------------------------------------------------
      case NavState::PICKUP: {
        cmd.vx = 0.0f; cmd.vy = 0.0f; cmd.wz = 0.0f;
        const auto & round = delivery_plan_[round_idx_];

        if (sub_step_ == 0) sub_step_ = 1;

        // 蹲下完成 → 推进（去放第一个箱）
        if (!squat_ctrl_.IsActive() && pickup_executed_ && pickup_suck_started_ && !sucker_.IsActive()) {
          RCLCPP_INFO(this->get_logger(), "★ 抓取完成");
          GoDeliverFirst();
          break;
        }

        // 蹲下中 → 保持期触发吸盘
        if (squat_ctrl_.IsActive()) {
          ApplySquatFrame(squat_ctrl_.Update(now_sec));
          if (squat_ctrl_.IsInHoldPhase() && !pickup_suck_started_) {
            // ★ V2 双吸: 左右同时下→吸→抬（SuckerDual.StartPick 不带 direction）
            RCLCPP_INFO(this->get_logger(), "★ 抓取中...");
            sucker_.StartPick(now_sec);
            pickup_suck_started_ = true;
          }
          if (sucker_.IsActive()) sucker_.Update(now_sec);
          break;
        }

        // 首次进入: 启动蹲下
        if (!pickup_executed_) {
          pickup_executed_ = true;
          pickup_suck_started_ = false;
          current_pos_ = round.pickup_point_left;
          active_direction_ = "left";
          sucker_direction_ = "left";
          RCLCPP_INFO(this->get_logger(),
            "★ 抓取 箱%02d(%s) + 箱%02d(%s) ← 取货点%d",
            round.left.box_num, round.left.type.c_str(),
            round.right.box_num, round.right.type.c_str(),
            round.pickup_point_left);
          ApplySquatFrame(squat_ctrl_.StartSquat(now_sec));
        }
        break;
      }

      // --------------------------------------------------
      // ★ PLACE_BOX — 蹲下放箱（sub_step 3=放第一个, 5=放第二个）
      // --------------------------------------------------
      case NavState::PLACE_BOX: {
        cmd.vx = 0.0f; cmd.vy = 0.0f; cmd.wz = 0.0f;
        const auto & round = delivery_plan_[round_idx_];

        if (sub_step_ == 2) sub_step_ = 3;
        else if (sub_step_ == 4) sub_step_ = 5;

        // 蹲下完成 → 推进
        if (!squat_ctrl_.IsActive() && place_executed_ && place_suck_started_ && !sucker_.IsActive()) {
          if (sub_step_ == 3 && round.right.valid) {
            // 放完第一个，去放第二个
            RCLCPP_INFO(this->get_logger(), "★ 放置完成（箱%02d），去放第二个", active_box_num_);
            active_direction_ = "right";
            active_box_num_ = round.right.box_num;
            active_box_type_ = round.right.type;
            active_deliver_point_ = round.right.place_point;
            active_zone_ = round.right.zone;
            sub_step_ = 4;
            place_executed_ = false;
            if (StartNavTo(round.right.place_point, NavState::PLACE_BOX)) {
              state_ = NavState::GOTO_TARGET;
            } else {
              state_ = NavState::DONE;
            }
          } else {
            // 本轮全部放完
            RCLCPP_INFO(this->get_logger(), "★ 第 %d/%zu 轮取放完成",
              round_idx_ + 1, delivery_plan_.size());
            round_idx_++;
            StartDeliveryRound();
          }
          break;
        }

        // 蹲下中 → 保持期放箱
        if (squat_ctrl_.IsActive()) {
          ApplySquatFrame(squat_ctrl_.Update(now_sec));
          if (squat_ctrl_.IsInHoldPhase() && !place_suck_started_ && sucker_direction_.has_value()) {
            sucker_.StartPlace(*sucker_direction_, now_sec);
            place_suck_started_ = true;
          }
          if (sucker_.IsActive()) sucker_.Update(now_sec);
          break;
        }

        // 首次进入: 启动蹲下放箱
        if (!place_executed_) {
          place_executed_ = true;
          place_suck_started_ = false;
          RCLCPP_INFO(this->get_logger(),
            "★ 放置 箱%02d(%s) → zone%d（放货点%d）",
            active_box_num_, active_box_type_.c_str(), active_zone_, active_deliver_point_);
          RCLCPP_INFO(this->get_logger(), "★ 放置中...");
          sucker_direction_ = active_direction_;
          ApplySquatFrame(squat_ctrl_.StartSquat(now_sec));
        }
        break;
      }

      // --------------------------------------------------
      case NavState::DONE:
        cmd.vx = 0.0f; cmd.vy = 0.0f; cmd.wz = 0.0f;
        break;
    }

    nav_cmd_pub_->publish(cmd);
  }

  void GoDeliverFirst()
  {
    const auto & round = delivery_plan_[round_idx_];
    if (round.left.valid) {
      active_direction_ = "left";
      active_box_num_ = round.left.box_num;
      active_box_type_ = round.left.type;
      active_deliver_point_ = round.left.place_point;
      active_zone_ = round.left.zone;
      sub_step_ = 2;
      pickup_executed_ = false;
      place_executed_ = false;
      RCLCPP_INFO(this->get_logger(),
        "★ 去放 箱%02d(%s) → zone%d（点%d）",
        round.left.box_num, round.left.type.c_str(),
        round.left.zone, round.left.place_point);
      if (StartNavTo(round.left.place_point, NavState::PLACE_BOX)) {
        state_ = NavState::GOTO_TARGET;
      } else {
        state_ = NavState::DONE;
      }
    } else if (round.right.valid) {
      active_direction_ = "right";
      active_box_num_ = round.right.box_num;
      active_box_type_ = round.right.type;
      active_deliver_point_ = round.right.place_point;
      active_zone_ = round.right.zone;
      sub_step_ = 4;
      place_executed_ = false;
      RCLCPP_INFO(this->get_logger(),
        "★ 去放 箱%02d(%s) → zone%d（点%d）",
        round.right.box_num, round.right.type.c_str(),
        round.right.zone, round.right.place_point);
      if (StartNavTo(round.right.place_point, NavState::PLACE_BOX)) {
        state_ = NavState::GOTO_TARGET;
      } else {
        state_ = NavState::DONE;
      }
    } else {
      RCLCPP_WARN(this->get_logger(), "★ 本轮无有效箱，跳过");
      round_idx_++;
      StartDeliveryRound();
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
  // 蹲下姿态发布
  // ========================================================================================
  void ApplySquatFrame(const SquatController::Frame & frame)
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
  // HandleNavigation（横移螃蟹步）
  // ========================================================================================
  void HandleNavigation(DogNavCommand & cmd, double now_sec)
  {
    if (!nav_task_.active || nav_task_.finished) {
      cmd.vx = 0.0f; cmd.vy = 0.0f; cmd.wz = 0.0f;
      return;
    }

    if (nav_task_.seg_start_time <= 0.0) {
      nav_task_.seg_start_time = now_sec;
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

  bool StartNavTo(int target, NavState next_state)
  {
    // V2: 无逐边禁用（placed_zones 空），无 blocked
    auto path = planner_->BFS(current_pos_, target, blocked_, {});
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
  // RunSolver（调 solver.py）
  // ========================================================================================
  int RunSolver()
  {
    std::string cmd = "python3 " + solver_path_ + " 2>&1";
    RCLCPP_INFO(this->get_logger(), "★ 执行: %s", cmd.c_str());
    FILE * pipe = popen(cmd.c_str(), "r");
    if (!pipe) {
      RCLCPP_ERROR(this->get_logger(), "★ 无法执行 solver.py");
      return -1;
    }

    std::string output;
    char buf[512];
    while (fgets(buf, sizeof(buf), pipe)) output += buf;
    pclose(pipe);

    auto pos = output.find("PROBLEM_RESULT_JSON=");
    if (pos == std::string::npos) return -1;
    std::string json_str = output.substr(pos + 20);
    auto nl = json_str.find('\n');
    if (nl != std::string::npos) json_str = json_str.substr(0, nl);

    if (json_str.find("\"success\":true") == std::string::npos &&
        json_str.find("\"success\": true") == std::string::npos) return -1;

    int mod4 = -1;
    if (sscanf(json_str.c_str(), "{\"success\":true,\"expression\":\"%*[^\"]\",\"raw_result\":%*d,\"mod4\":%d", &mod4) != 1) {
      if (sscanf(json_str.c_str(), "{\"success\": true, \"expression\": \"%*[^\"]\", \"raw_result\": %*d, \"mod4\": %d", &mod4) != 1) {
        return -1;
      }
    }
    RCLCPP_INFO(this->get_logger(), "★ solver mod4=%d", mod4);
    return mod4;
  }

  // ========================================================================================
  // RunBoxScan（调 box_detector scan_all）
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
    pclose(pipe);

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
  // StartStreamer / StopStreamer
  // ========================================================================================
  void StartStreamer()
  {
    if (!stream_enable_ || streamer_pid_ > 0) return;

    std::string cmd = "python3 " + streamer_path_ + " --port " +
                      std::to_string(stream_port_) + " > /tmp/d435i_stream.log 2>&1 &";
    FILE * pipe = popen(cmd.c_str(), "r");
    if (!pipe) {
      RCLCPP_WARN(this->get_logger(), "★ 推流启动失败");
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
          "★ 推流就绪 (pid=%d, port=%d)", streamer_pid_, stream_port_);
        return;
      }
      std::this_thread::sleep_for(std::chrono::milliseconds(100));
    }
    RCLCPP_WARN(this->get_logger(), "★ 推流 5s 未就绪");
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

  NavState state_{NavState::IDLE};
  NavState next_state_{NavState::DONE};
  int current_pos_{0};
  bool ocr_started_{false};
  bool scan0_done_{false};
  bool scan1_done_{false};
  int deliver_zone_{0};

  std::vector<PickupRound> delivery_plan_;
  int round_idx_{0};
  int sub_step_{0};
  bool pickup_executed_{false};
  bool pickup_suck_started_{false};
  bool place_executed_{false};
  bool place_suck_started_{false};
  std::optional<std::string> sucker_direction_;

  int active_deliver_point_{0};
  std::string active_direction_;
  int active_box_num_{0};
  std::string active_box_type_;
  int active_zone_{0};

  SuckerDual sucker_;            // ★ 双吸（一次吸两箱，左右同步）
  SquatController squat_ctrl_;

  std::map<std::string, int> type_zone_map_;
  std::map<int, int> zone_to_place_;
  std::vector<std::tuple<int, int, int>> pickup_box_pairs_;
  std::array<int, 4> mod4_target_{1, 2, 3, 4};

  NavTask nav_task_;
  std::unordered_set<int> blocked_;
  std::unordered_set<int> placed_zones_;

  std::map<int, std::string> box_type_map_;
  std::map<int, std::string> phase0_map_;

  float nav_vx_{0.3f};
  float nav_height_{0.25f};
  std::string field_side_{"left"};
  std::string box_scanner_path_;
  std::string solver_path_;
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
  rclcpp::spin(std::make_shared<NavigationDog2Node>());
  rclcpp::shutdown();
  return 0;
}
