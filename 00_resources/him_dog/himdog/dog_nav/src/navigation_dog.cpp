// ========================================================================================
// navigation_dog.cpp — 任务赛导航节点（BFS 路径规划 + 状态机 + OCR）
// ========================================================================================
//
// 场地布局（15 个可走点位）:
//   点0=起点, 点1=左右半场枢纽(连第一排全部取货点)
//   点2-5=第一排取货点, 点6-9=第二排取货点
//   点10/11/12=放货站位(归位区01-04的中间站位)
//   点13=归位区01左侧站位(右吸盘放zone1), 点14=归位区04右侧站位(左吸盘放zone4)
//   物资箱(05-12)不是路径节点，狗站在取货点上左/右吸盘取货
//
// 正式比赛流程:
//   IDLE → OCR_SOLVE(点0, OCR+播报)
//        → BOX_SCAN_PHASE0(点0, 远看8箱)
//        → GOTO_POINT1(0→1)
//        → BOX_SCAN_PHASE1(点1, 近看4箱)
//        → BOX_SCAN_MERGE(合并+校验+生成计划)
//        → [循环 4 轮取放，每轮 sub_step 0-7]
//        → DONE
//
// 启动方式:
//   1. auto_start:=true 自动开始
//   2. 运行后按 'y' + 回车 触发
//
// 运行命令：
// ros2 run dog_nav navigation_dog --ros-args
//   --params-file src/dog_nav/config/task_race_point.yaml
//   -p auto_start:=true

#include <rclcpp/rclcpp.hpp>
#include <dog_nav/msg/dog_nav_command.hpp>
#include <nav_msgs/msg/odometry.hpp>
#include <sensor_msgs/msg/joint_state.hpp>
#include <std_msgs/msg/bool.hpp>
#include <tf2/LinearMath/Quaternion.h>
#include <tf2/LinearMath/Matrix3x3.h>
#include "dog_nav/field_path_planner.hpp"
#include "dog_nav/delivery_planner.hpp"
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
#include <fcntl.h>
#include <unistd.h>
#include <termios.h>
#include <sys/wait.h>
#include <csignal>
#include <memory>
#include <thread>
#include <atomic>
#include <iostream>
#include <unordered_set>
#include <map>
#include <set>
#include <optional>

using dog_nav::msg::DogNavCommand;
using dog_nav::FieldPathPlanner;
using dog_nav::NavTask;
using dog_nav::DeliveryPlanner;
using dog_nav::BoxInfo;
using dog_nav::PickupRound;
using dog_nav::Point3D;
using dog_nav::SuckerController;
using dog_nav::SquatController;
using dog_nav::PickPlaceActor;

// ========================================================================================
// 状态枚举
// ========================================================================================

enum class NavState
{
  IDLE = 0,           // 等待启动
  OCR_SOLVE,          // 在点0停车，调用 solver.py + 语音播报（只做一次）
  BOX_SCAN_PHASE0,    // 在点0远距离扫描8箱
  GOTO_POINT1,        // 从点0移动到点1（近距离扫描位置）
  BOX_SCAN_PHASE1,    // 在点1近距离扫描中间4箱
  BOX_SCAN_MERGE,     // 合并 Phase0 + Phase1 结果，生成取货计划
  GOTO_PICKUP,        // 导航到取货站位（成对取货的第一/第二个取货点）
  PICKUP,             // 到达取货站位，吸盘取箱子
  GOTO_TARGET,        // 导航到放货站位
  PLACE_AVOID,        // ★ U型避障机动（后退1m→横移→前进1m），横向通道被已放箱归位区挡住时
  PLACE_BOX,          // 放箱
  DONE                // 完成
};

inline const char * StateStr(NavState s)
{
  switch (s) {
    case NavState::IDLE:           return "IDLE";
    case NavState::OCR_SOLVE:      return "OCR_SOLVE";
    case NavState::BOX_SCAN_PHASE0:return "BOX_SCAN_P0";
    case NavState::GOTO_POINT1:    return "GOTO_POINT1";
    case NavState::BOX_SCAN_PHASE1:return "BOX_SCAN_P1";
    case NavState::BOX_SCAN_MERGE: return "BOX_SCAN_MERGE";
    case NavState::GOTO_PICKUP:    return "GOTO_PICKUP";
    case NavState::PICKUP:         return "PICKUP";
    case NavState::GOTO_TARGET:    return "GOTO_TARGET";
    case NavState::PLACE_AVOID:    return "PLACE_AVOID";
    case NavState::PLACE_BOX:      return "PLACE_BOX";
    case NavState::DONE:           return "DONE";
    default:                       return "UNKNOWN";
  }
}

// ========================================================================================
// 导航节点
// ========================================================================================

class NavigationDogNode : public rclcpp::Node
{
public:
  NavigationDogNode()
  : Node("navigation_dog_node")
  {
    // =========================
    // 1. 声明参数
    // =========================
    this->declare_parameter("loop_rate_hz", 20);
    this->declare_parameter("nav_vx", 0.3);
    this->declare_parameter("nav_height", 0.25);
    this->declare_parameter("field_side", std::string("left"));
    this->declare_parameter("solver_path", std::string(
      "/home/zhy/himdog/src/dog_nav/resource/vision/solver.py"));
    this->declare_parameter("box_scanner_path", std::string(
      "/home/zhy/himdog/src/dog_nav/resource/vision/box_detector_rknn.py"));
    this->declare_parameter("ocr_max_retries", 3);

    // ★ 物资箱识别模式开关
    //   yolo   — 调 box_detector_rknn.py（YOLO/RKNN）扫描识别（默认，赛前自动）
    //   manual — 跳过相机/YOLO，直接用赛前手填的 manual_box_types 读入箱子类别
    this->declare_parameter("box_scan_mode", std::string("yolo"));
    // 手动模式专用: 每个箱子(05-12)的类别，留空=未指定
    // 合法类别: food(食物) / tool(工具) / instrument(仪器) / medicine(药品)
    for (int bn = 5; bn <= 12; ++bn) {
      char buf[16];
      std::snprintf(buf, sizeof(buf), "box_%02d", bn);
      this->declare_parameter(std::string("manual_box_types.") + buf, std::string());
    }

    // ★ 雷达定位参数
    this->declare_parameter("odom_topic", std::string("/lio/odom"));
    this->declare_parameter("pos_tolerance", 0.05);    // 位置到达容差（米）
    this->declare_parameter("yaw_tolerance", 0.087);    // 角度到达容差（弧度）
    this->declare_parameter("nav_kp_xy", 0.8);         // 位置控制比例增益
    this->declare_parameter("nav_kp_yaw", 1.5);        // 角度控制比例增益
    this->declare_parameter("nav_max_vx", 0.5);        // 最大前进速度
    this->declare_parameter("nav_max_vy", 0.3);        // 最大侧移速度
    this->declare_parameter("nav_max_wz", 1.0);        // 最大角速度
    this->declare_parameter("nav_timeout_sec", 15.0);  // 单段导航超时（秒）

    // ★ 抓取参数
    this->declare_parameter("pickup_point", 2);        // 单次取货站位 (2-5)
    this->declare_parameter("pickup_points", std::vector<long>{2});  // 多次取货站位列表
    this->declare_parameter("deliver_point", -1);      // 放货站位 (6-9)，-1=由扫描决定
    this->declare_parameter("pickup_direction", std::string("left"));  // 取货方向: left/right
    this->declare_parameter("segment_time_sec", 3.0);  // 两点间行走时间（秒，备用超时）
    this->declare_parameter("auto_start", false);       // 是否自动开始

    // ★ 吸盘舵机串口参数
    this->declare_parameter("sucker_port", std::string("/dev/ttyUSB0"));
    this->declare_parameter("sucker_baudrate", 115200);
    this->declare_parameter("sucker_move_sec", 3.0);    // 舵机 0↔270 满程转动时间（秒）
    this->declare_parameter("sucker_hold_sec", 0.5);    // 下到位后保持时间（建真空/释放）

    // ★ 蹲下取箱参数（test_13 联动：挂起 RL → 蹲下 → 吸 → 站起 → 恢复 RL）
    // 关节角顺序：FL_hip, FL_thigh, FL_calf, FR_hip, FR_thigh, FR_calf,
    //             RL_hip, RL_thigh, RL_calf, RR_hip, RR_thigh, RR_calf（js_pos 空间）
    // stand_pose 默认全零 = dog_control 默认站姿（与 policy 关 RL 时发的一致）
    // squat_pose 默认占位值，需用实测站/蹲姿态标定后填入 yaml
    this->declare_parameter("stand_pose", std::vector<double>(12, 0.0));
    this->declare_parameter("squat_pose", std::vector<double>{
      0.0, 0.7, -1.4, 0.0, 0.7, -1.4, 0.0, 0.7, -1.4, 0.0, 0.7, -1.4});
    this->declare_parameter("squat_interp_sec", 1.0);   // 站↔蹲姿态插值时间（秒）
    this->declare_parameter("squat_hold_sec", 1.0);     // 蹲下到位后保持时间（吸盘动作期间）

    // ★ D435i 推流参数（OCR_SOLVE 启动 → 识别完 8 箱后停止，推到电脑端 Foxglove）
    this->declare_parameter("stream_enable", true);     // 是否启动推流
    this->declare_parameter("stream_port", 8765);       // Foxglove WebSocket 端口

    // ★ 场地坐标参数（从 YAML 加载）
    DeclareCoordParams();

    nav_vx_ = static_cast<float>(this->get_parameter("nav_vx").as_double());
    nav_height_ = static_cast<float>(this->get_parameter("nav_height").as_double());
    field_side_ = this->get_parameter("field_side").as_string();
    solver_path_ = this->get_parameter("solver_path").as_string();
    box_scanner_path_ = this->get_parameter("box_scanner_path").as_string();
    {
      std::string mode = this->get_parameter("box_scan_mode").as_string();
      if (mode != "yolo" && mode != "manual") {
        RCLCPP_WARN(this->get_logger(),
          "★ 未知 box_scan_mode='%s'，回退为 'yolo'", mode.c_str());
        mode = "yolo";
      }
      box_scan_mode_ = mode;
    }
    ocr_max_retries_ = this->get_parameter("ocr_max_retries").as_int();
    deliver_point_ = this->get_parameter("deliver_point").as_int();
    segment_time_sec_ = this->get_parameter("segment_time_sec").as_double();
    auto_start_ = this->get_parameter("auto_start").as_bool();

    // 读取吸盘串口参数
    sucker_port_ = this->get_parameter("sucker_port").as_string();
    sucker_baudrate_ = this->get_parameter("sucker_baudrate").as_int();
    sucker_move_sec_ = this->get_parameter("sucker_move_sec").as_double();
    sucker_hold_sec_ = this->get_parameter("sucker_hold_sec").as_double();

    // 读取蹲下取箱参数 → 配置 actor_(内部 squat_ctrl_ + sucker_)
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

    // 读取推流参数
    stream_enable_ = this->get_parameter("stream_enable").as_bool();
    stream_port_ = this->get_parameter("stream_port").as_int();

    // 读取取货点位列表
    {
      auto pp = this->get_parameter("pickup_points").as_integer_array();
      pickup_points_.assign(pp.begin(), pp.end());
    }
    // 兼容：如果 pickup_points 只有默认值 [2]，但 pickup_point 指定了其他值
    pickup_point_ = this->get_parameter("pickup_point").as_int();
    if (pickup_points_.size() == 1 && pickup_points_[0] == 2 && pickup_point_ != 2) {
      pickup_points_[0] = pickup_point_;
    }

    // mod4 → 高分归位区编号 (zone 1~4)，传给 box_detector 当 target_zone 筛选"先送哪个箱"
    // 左场: 0→zone1, 1→zone2, 2→zone3, 3→zone4（与 yaml mod4_target_left 一致）
    // 右场: 逆序（与 yaml mod4_target_right 一致）
    // 注: 箱子最终送哪个 zone 由扫描结果 + type_zone_map_(按 field_side 切换) 决定，
    //     此处只决定"先送哪个"，不影响取箱/送箱正确性
    if (field_side_ == "right") {
      mod4_target_ = {4, 3, 2, 1};
    } else {
      mod4_target_ = {1, 2, 3, 4};
    }

    // =========================
    // 2. 构建路径规划器 + 加载坐标
    // =========================
    planner_ = std::make_unique<FieldPathPlanner>();
    LoadCoordsFromParams();

    // 新布局：箱子不是路径节点，初始没有 blocked 点
    blocked_ = {};

    // 加载静态映射表（从配置）
    LoadStaticMaps();

    // 读取雷达定位参数
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
    // 3. 创建发布者 + 订阅者
    // =========================
    nav_cmd_pub_ = this->create_publisher<DogNavCommand>("/nav_cmd", 10);
    // ★ 蹲下取箱：挂起 RL 时 nav 成为 /joint_states 唯一发布者
    joint_state_pub_ = this->create_publisher<sensor_msgs::msg::JointState>("/joint_states", 10);
    // ★ /policy_mode: true=挂起 policy 发布（交出控制权），false=恢复
    policy_mode_pub_ = this->create_publisher<std_msgs::msg::Bool>("/policy_mode", 10);

    // 订阅 Super-LIO 里程计
    odom_sub_ = this->create_subscription<nav_msgs::msg::Odometry>(
      odom_topic_, rclcpp::QoS(10).best_effort(),
      std::bind(&NavigationDogNode::OdomCallback, this, std::placeholders::_1));
    RCLCPP_INFO(this->get_logger(), "订阅里程计: %s", odom_topic_.c_str());

    // =========================
    // 4. 创建定时器
    // =========================
    const int rate_hz = this->get_parameter("loop_rate_hz").as_int();
    const auto period = std::chrono::milliseconds(1000 / std::max(1, rate_hz));
    timer_ = this->create_wall_timer(
      period,
      std::bind(&NavigationDogNode::TimerCallback, this));

    node_start_time_ = std::chrono::steady_clock::now();

    // =========================
    // 5. 键盘监听线程（按 'y' + 回车启动）
    // =========================
    if (!auto_start_) {
      keyboard_running_ = true;
      keyboard_thread_ = std::thread(&NavigationDogNode::KeyboardListener, this);
      RCLCPP_INFO(this->get_logger(),
        "navigation_dog_node started — 按 'y' + 回车 启动导航");
    } else {
      RCLCPP_INFO(this->get_logger(),
        "navigation_dog_node started — auto_start=true, 自动开始");
    }

    RCLCPP_INFO(this->get_logger(),
      "参数: pickup_points=%s, deliver=%d, field_side=%s",
      PickupPointsStr().c_str(), deliver_point_, field_side_.c_str());

    // 打印加载的坐标
    for (int i = 0; i <= 14; ++i) {
      const auto & c = planner_->GetCoord(i);
      RCLCPP_INFO(this->get_logger(),
        "  点位 %02d: (%.3f, %.3f, %.1f°)", i, c.x, c.y, c.theta);
    }

    // 打开吸盘舵机串口（初始化到存储位，泵 OFF）
    actor_.ConfigureSucker(sucker_move_sec_, sucker_hold_sec_);
    if (!actor_.OpenSucker(sucker_port_, sucker_baudrate_)) {
      RCLCPP_WARN(this->get_logger(),
        "★ 吸盘串口 %s 打开失败，取放动作将无法吸合（蹲下仍可用）",
        sucker_port_.c_str());
    }

    if (auto_start_) {
      state_ = NavState::OCR_SOLVE;
      RCLCPP_INFO(this->get_logger(), "★ 开始 OCR 识别...");
    }
  }

  ~NavigationDogNode()
  {
    keyboard_running_ = false;
    if (keyboard_thread_.joinable()) {
      keyboard_thread_.join();
    }
    StopStreamer();  // 兜底：节点退出时确保推流进程关闭
    // sucker_ 析构会自动关串口
  }

private:

  // ========================================================================================
  // DeclareCoordParams — 声明所有点位坐标参数
  // ========================================================================================
  void DeclareCoordParams()
  {
    // start_pose: [x, y, theta]
    this->declare_parameter("start_pose", std::vector<double>{0.0, 0.0, 0.0});

    // pickup_positions: {point_1: [x,y,theta], ...}
    const std::vector<std::string> pickup_names = {
      "point_1", "point_2", "point_3", "point_4", "point_5",
      "point_6", "point_7", "point_8", "point_9"
    };
    for (const auto & name : pickup_names) {
      this->declare_parameter("pickup_positions." + name, std::vector<double>{0.0, 0.0, 0.0});
    }

    // place_positions: {point_10: [x,y,theta], ...}（放货站位，归位区旁）
    const std::vector<std::string> place_names = {
      "point_10", "point_11", "point_12", "point_13", "point_14"
    };
    for (const auto & name : place_names) {
      this->declare_parameter("place_positions." + name, std::vector<double>{0.0, 0.0, 0.0});
    }

    // return_zones: {zone_1: [x,y,theta], ...}
    const std::vector<std::string> zone_names = {
      "zone_1", "zone_2", "zone_3", "zone_4"
    };
    for (const auto & name : zone_names) {
      this->declare_parameter("return_zones." + name, std::vector<double>{0.0, 0.0, 0.0});
    }
  }

  // ========================================================================================
  // LoadCoordsFromParams — 从 ROS 2 参数加载坐标到 planner
  // ========================================================================================
  void LoadCoordsFromParams()
  {
    // 起点
    LoadAndSetCoord("start_pose", 0);

    // 取货站位点（point_1~9 → 路径节点 1~9）
    const std::vector<std::pair<std::string, int>> pickup_map = {
      {"pickup_positions.point_1", 1},
      {"pickup_positions.point_2", 2},
      {"pickup_positions.point_3", 3},
      {"pickup_positions.point_4", 4},
      {"pickup_positions.point_5", 5},
      {"pickup_positions.point_6", 6},
      {"pickup_positions.point_7", 7},
      {"pickup_positions.point_8", 8},
      {"pickup_positions.point_9", 9},
    };
    for (const auto & [param_name, point_id] : pickup_map) {
      LoadAndSetCoord(param_name, point_id);
    }

    // 放货站位点（point_10~14 → 路径节点 10~14，归位区旁）
    const std::vector<std::pair<std::string, int>> place_map = {
      {"place_positions.point_10", 10},
      {"place_positions.point_11", 11},
      {"place_positions.point_12", 12},
      {"place_positions.point_13", 13},
      {"place_positions.point_14", 14},
    };
    for (const auto & [param_name, point_id] : place_map) {
      LoadAndSetCoord(param_name, point_id);
    }

    // 归位区坐标（不是路径节点，单独存储）
    const std::vector<std::pair<std::string, int>> zone_map = {
      {"return_zones.zone_1", 1},
      {"return_zones.zone_2", 2},
      {"return_zones.zone_3", 3},
      {"return_zones.zone_4", 4},
    };
    for (const auto & [param_name, zone_id] : zone_map) {
      try {
        auto vals = this->get_parameter(param_name).as_double_array();
        if (vals.size() >= 2) {
          zone_coords_[zone_id] = {vals[0], vals[1], vals.size() >= 3 ? vals[2] : 0.0};
        }
      } catch (const std::exception & e) {
        RCLCPP_WARN(this->get_logger(),
          "★ 归位区参数 %s 未找到或格式错误，zone%d 坐标缺失（归位将失败）: %s",
          param_name.c_str(), zone_id, e.what());
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
      RCLCPP_WARN(this->get_logger(),
        "参数 %s 未找到或格式错误，点位 %d 使用默认坐标: %s",
        param_name.c_str(), point_id, e.what());
    }
  }

  // ========================================================================================
  // KeyboardListener — 后台线程监听键盘输入
  // ========================================================================================
  void KeyboardListener()
  {
    while (keyboard_running_) {
      std::string input;
      if (std::getline(std::cin, input)) {
        // 去掉前后空白
        auto trimmed = input;
        trimmed.erase(0, trimmed.find_first_not_of(" \t\r\n"));
        trimmed.erase(trimmed.find_last_not_of(" \t\r\n") + 1);
        if (trimmed == "y" || trimmed == "Y") {
          if (state_ == NavState::IDLE) {
            state_ = NavState::OCR_SOLVE;
            RCLCPP_INFO(this->get_logger(), "★ 收到 'y' 键启动命令，开始 OCR 识别...");
          } else {
            RCLCPP_WARN(this->get_logger(), "★ 已经在运行中（状态: %s），忽略 'y'", StateStr(state_));
          }
        }
      }
    }
  }

  // ========================================================================================
  // ★ StartNavTo — 规划并开始导航到指定点位
  // ========================================================================================
  bool StartNavTo(int target, NavState next_state)
  {
    // ★ BFS 传入 placed_zones_：放箱后归位区横向通道逐边禁用
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
  // ★ StartGrabDeliver — 封装一次完整的「取货 → 放货」流程
  // ========================================================================================
  //
  // 参数:
  //   pickup_pt  — 取货站位 (2-5)
  //   deliver_pt — 放货站位 (6-9)
  //   direction  — 取货方向 "left"/"right"
  //
  // 流程: 导航到取货站位 → 转身抓取 → 导航到放货站位 → 放箱
  //
  bool StartGrabDeliver(int pickup_pt, int deliver_pt)
  {
    active_pickup_point_ = pickup_pt;
    active_deliver_point_ = deliver_pt;

    RCLCPP_INFO(this->get_logger(),
      "★ StartGrabDeliver: 拿取点=%d, 放置点=%d, 当前位置=%d",
      pickup_pt, deliver_pt, current_pos_);

    // 开始导航到拿取点
    if (StartNavTo(pickup_pt, NavState::PICKUP)) {
      state_ = NavState::GOTO_PICKUP;
      return true;
    } else {
      RCLCPP_ERROR(this->get_logger(),
        "★ StartGrabDeliver: 无法规划到拿取点 %d", pickup_pt);
      state_ = NavState::DONE;
      return false;
    }
  }

  // ========================================================================================
  // ★ TimerCallback — 主循环
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
      // --------------------------------------------------
      case NavState::IDLE:
        cmd.vx = 0.0f; cmd.vy = 0.0f; cmd.wz = 0.0f;
        break;

      // --------------------------------------------------
      case NavState::OCR_SOLVE:
        cmd.vx = 0.0f; cmd.vy = 0.0f; cmd.wz = 0.0f;

        // 重试等待
        if (ocr_retry_count_ > 0 && !ocr_started_) {
          double elapsed = now_sec - ocr_retry_start_;
          if (elapsed < ocr_retry_delay_sec_) {
            break;
          }
        }

        if (!ocr_started_) {
          ocr_started_ = true;
          RCLCPP_INFO(this->get_logger(), "★ 开始 OCR 求解...");

          // 启动 D435i 推流（独占相机，solver/box_detector 从 shm 取帧）
          StartStreamer();

          // 确定目标归位区
          int target = -1;

          if (deliver_point_ > 0) {
            // 手动指定了放货点位，跳过 OCR
            target = deliver_point_;
            RCLCPP_INFO(this->get_logger(), "★ 使用手动指定目标: %d", target);
          } else {
            // 调用 OCR
            int mod4_result = RunSolver();
            if (mod4_result >= 0 && mod4_result <= 3) {
              target = mod4_target_[mod4_result];
              RCLCPP_INFO(this->get_logger(),
                "★ OCR 结果: mod4=%d → 目标归位区=%d (%s)",
                mod4_result, target, field_side_.c_str());
            }
          }

          if (target > 0) {
            deliver_target_ = target;
            current_pos_ = 0;
            ocr_started_ = false;
            ocr_retry_count_ = 0;
            // OCR 完成 → Phase0 扫描（在点0远看8箱）
            state_ = NavState::BOX_SCAN_PHASE0;
            box_scan_started_ = false;
            RCLCPP_INFO(this->get_logger(),
              "★ OCR 成功，目标归位区=%d，开始 Phase0 扫描（点0远看）...", deliver_target_);
          } else {
            // OCR 失败，重试
            ocr_retry_count_++;
            if (ocr_retry_count_ < ocr_max_retries_) {
              RCLCPP_WARN(this->get_logger(),
                "★ OCR 失败 (第%d次/%d次)，%.0f秒后重试...",
                ocr_retry_count_, ocr_max_retries_, ocr_retry_delay_sec_);
              ocr_started_ = false;
              ocr_retry_start_ = now_sec;
            } else {
              RCLCPP_ERROR(this->get_logger(),
                "★ OCR 连续%d次失败，使用默认目标(点位%d)",
                ocr_max_retries_, mod4_target_[0]);
              deliver_target_ = mod4_target_[0];
              current_pos_ = 0;
              ocr_started_ = false;
              ocr_retry_count_ = 0;
              state_ = NavState::BOX_SCAN_PHASE0;
              box_scan_started_ = false;
              RCLCPP_INFO(this->get_logger(),
                "★ 使用默认目标归位区=%d，开始 Phase0 扫描...", deliver_target_);
            }
          }
        }
        break;

      // --------------------------------------------------
      case NavState::BOX_SCAN_PHASE0:
        // Phase0：在点0远距离扫描8箱（手动模式则跳过扫描，直接读入手填类别）
        cmd.vx = 0.0f; cmd.vy = 0.0f; cmd.wz = 0.0f;
        if (!box_scan_started_) {
          box_scan_started_ = true;

          // ★ 手动模式: 不开相机/YOLO，直接用赛前手填的箱子类别，跳过 Phase1
          if (box_scan_mode_ == "manual") {
            RCLCPP_INFO(this->get_logger(), "★ 手动模式: 跳过 YOLO 扫描，读入手填箱子类别...");
            LoadManualBoxTypes();
            FinalizeBoxScan();   // 校验 + 生成计划 + 停推流 + 启动首轮（含状态转移）
            break;
          }

          RCLCPP_INFO(this->get_logger(), "★ Phase0: 在点0远距离扫描8箱...");
          // 调用 box_detector_rknn.py --mode scan_all（无 phase 参数）
          auto scanned = RunBoxScan(deliver_target_);
          // 保存 Phase0 结果
          phase0_map_ = box_type_map_;
          if (!scanned.empty()) {
            RCLCPP_INFO(this->get_logger(),
              "★ Phase0 完成，识别到 %zu 个箱子", phase0_map_.size());
            // 移动到点1
            if (StartNavTo(1, NavState::BOX_SCAN_PHASE1)) {
              state_ = NavState::GOTO_POINT1;
              box_scan_started_ = false;
            } else {
              RCLCPP_ERROR(this->get_logger(), "★ 无法规划到点1");
              state_ = NavState::DONE;
            }
          } else {
            RCLCPP_WARN(this->get_logger(), "★ Phase0 无结果，仍移动到点1重试");
            if (StartNavTo(1, NavState::BOX_SCAN_PHASE1)) {
              state_ = NavState::GOTO_POINT1;
              box_scan_started_ = false;
            } else {
              state_ = NavState::DONE;
            }
          }
        }
        break;

      // --------------------------------------------------
      case NavState::GOTO_POINT1:
        // 从点0移动到点1
        HandleNavigation(cmd, now_sec);
        break;

      // --------------------------------------------------
      case NavState::BOX_SCAN_MERGE:
      case NavState::BOX_SCAN_PHASE1:
        // Phase1：在点1近距离扫描中间4箱
        cmd.vx = 0.0f; cmd.vy = 0.0f; cmd.wz = 0.0f;
        if (!box_scan_started_) {
          box_scan_started_ = true;
          current_pos_ = 1;
          RCLCPP_INFO(this->get_logger(), "★ Phase1: 在点1近距离扫描4箱...");
          auto scanned = RunBoxScan(deliver_target_);

          // 合并 Phase0 + Phase1
          auto phase1_map = box_type_map_;
          auto merged = phase0_map_;  // 以 Phase0 为基础

          for (const auto & [bn, tp] : phase1_map) {
            if (merged.find(bn) == merged.end()) {
              merged[bn] = tp;
              RCLCPP_INFO(this->get_logger(), "  箱%d: %s (补充)", bn, tp.c_str());
            } else if (merged[bn] == tp) {
              RCLCPP_INFO(this->get_logger(), "  箱%d: %s (✓验证一致)", bn, tp.c_str());
            } else {
              std::string old_tp = merged[bn];
              merged[bn] = tp;
              RCLCPP_INFO(this->get_logger(), "  箱%d: %s (覆盖，旧=%s)", bn, tp.c_str(), old_tp.c_str());
            }
          }

          box_type_map_ = merged;

          // 校验 + 生成计划 + 停推流 + 启动首轮
          FinalizeBoxScan();
        }
        break;

      // --------------------------------------------------
      case NavState::GOTO_PICKUP:
      case NavState::GOTO_TARGET:
        HandleNavigation(cmd, now_sec);
        break;

      // --------------------------------------------------
      case NavState::PICKUP:
          // 成对取货：sub_step 1=左点取箱, 3=右点取箱
          // ★ 蹲下+吸盘时序由 actor_ 编排（pick_place_actor.hpp）
        cmd.vx = 0.0f; cmd.vy = 0.0f; cmd.wz = 0.0f;
        {
          const auto & round = delivery_plan_[round_idx_];

          // 进入 PICKUP 时推进 sub_step: 0→1(左点取), 2→3(右点取)
          if (sub_step_ == 0) sub_step_ = 1;
          else if (sub_step_ == 2) sub_step_ = 3;

          // 首次进入：记录取箱信息 + 启动 actor（发首帧后本 tick 不再 Tick）
          if (actor_.IsIdle()) {
            if (sub_step_ == 1 && round.left.valid) {
              current_pos_ = round.pickup_point_left;
              active_direction_ = "left";
              active_box_num_ = round.left.box_num;
              active_box_type_ = round.left.type;
              active_zone_ = round.left.zone;
              RCLCPP_INFO(this->get_logger(),
                "★ 左取货点%d: 左吸盘吸箱%02d(%s)→zone%d（蹲下取箱）",
                round.pickup_point_left, round.left.box_num,
                round.left.type.c_str(), round.left.zone);
              ApplyActorFrame(actor_.StartPickup("left", now_sec));
            } else if (sub_step_ == 3 && round.right.valid) {
              current_pos_ = round.pickup_point_right;
              active_direction_ = "right";
              active_box_num_ = round.right.box_num;
              active_box_type_ = round.right.type;
              active_zone_ = round.right.zone;
              RCLCPP_INFO(this->get_logger(),
                "★ 右取货点%d: 右吸盘吸箱%02d(%s)→zone%d（蹲下取箱）",
                round.pickup_point_right, round.right.box_num,
                round.right.type.c_str(), round.right.zone);
              ApplyActorFrame(actor_.StartPickup("right", now_sec));
            } else {
              // box 无效，跳过蹲下+吸盘，直接推进
              AdvanceAfterPickup(round);
            }
            break;
          }

          // 蹲下+吸盘进行中 → 每 tick 推进 actor
          auto tr = actor_.Tick(now_sec);
          ApplyActorFrame(tr.frame);
          if (tr.action_done) {
            AdvanceAfterPickup(round);
          }
        }
        break;

      // --------------------------------------------------
      case NavState::PLACE_BOX:
          // ★ 蹲下+吸盘时序由 actor_ 编排（pick_place_actor.hpp）
        cmd.vx = 0.0f; cmd.vy = 0.0f; cmd.wz = 0.0f;
        {
          const auto & round = delivery_plan_[round_idx_];

          // 进入 PLACE_BOX 时推进 sub_step: 4→5(放第一个), 6→7(放第二个)
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
            RCLCPP_INFO(this->get_logger(),
              "★ zone%d 已放置，placed_zones 更新", active_zone_);
            AdvanceAfterPlace(round);
          }
        }
        break;

      // --------------------------------------------------
      // ★ PLACE_AVOID — U型避障机动（后退1m → 横移 → 前进1m）
      // --------------------------------------------------
      // 触发: 放完第一个箱后，去第二个放货点时横向通道被已放箱归位区挡住
      // 执行: 狗朝向固定 +y，本体坐标:
      //   phase 0: 后退 place_avoid_dist_ (世界 -y)
      //   phase 1: 横移到目标站位 x (世界 ±x，距离动态)
      //   phase 2: 前进 place_avoid_dist_ (世界 +y，到目标站位)
      // 完成 → 回 PLACE_BOX 放箱
      //
      case NavState::PLACE_AVOID:
        HandlePlaceAvoid(cmd, now_sec);
        break;

      // --------------------------------------------------
      case NavState::DONE:
        cmd.vx = 0.0f; cmd.vy = 0.0f; cmd.wz = 0.0f;
        break;
    }

    nav_cmd_pub_->publish(cmd);
  }

  // ========================================================================================
  // ★ OdomCallback — 接收 Super-LIO 里程计
  // ========================================================================================
  void OdomCallback(const nav_msgs::msg::Odometry::SharedPtr msg)
  {
    cur_x_ = msg->pose.pose.position.x;
    cur_y_ = msg->pose.pose.position.y;

    // 从四元数提取 yaw
    tf2::Quaternion q(
      msg->pose.pose.orientation.x,
      msg->pose.pose.orientation.y,
      msg->pose.pose.orientation.z,
      msg->pose.pose.orientation.w);
    tf2::Matrix3x3 m(q);
    double roll, pitch, yaw;
    m.getRPY(roll, pitch, yaw);
    cur_yaw_ = yaw;  // 弧度
    odom_received_ = true;
  }

  // ========================================================================================
  // ★ 蹲下取箱（蹲下姿态时序由 actor_ 管控，这里只做 ROS 发布）
  // ========================================================================================
  //
  // actor_（PickPlaceActor）内部封装 squat_ctrl_ + sucker_，算每帧该发什么姿态、
  // 何时切 /policy_mode、何时触发吸盘；nav 通过 ApplyActorFrame 把 Frame 落到发布器。
  // 时序: 挂起RL→站→蹲插值→保持(吸盘动作)→蹲→站插值→恢复RL
  //

  // 把 actor_ 返回的 Frame 应用到 ROS 发布器
  void ApplyActorFrame(const PickPlaceActor::Frame & frame)
  {
    if (frame.policy_mode.has_value()) {
      PublishPolicyMode(*frame.policy_mode);
    }
    if (frame.has_pose) {
      PublishJointPose(frame.pose);
    }
  }

  // 发布一帧 /joint_states（12 维 js_pos）
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

  // 发布 /policy_mode（true=挂起 policy，false=恢复）
  void PublishPolicyMode(bool hold)
  {
    std_msgs::msg::Bool msg;
    msg.data = hold;
    policy_mode_pub_->publish(msg);
    RCLCPP_INFO(this->get_logger(), "★ /policy_mode = %s", hold ? "true(挂起)" : "false(恢复)");
  }

  // ========================================================================================
  // ★ NormalizeAngle — 将角度归一化到 [-PI, PI]
  // ========================================================================================
  static double NormalizeAngle(double a)
  {
    while (a > M_PI) a -= 2.0 * M_PI;
    while (a < -M_PI) a += 2.0 * M_PI;
    return a;
  }

  // ========================================================================================
  // ★ HandleNavigation — 雷达定位反馈导航（GOTO_* 状态共用）
  // ========================================================================================
  //
  // 逻辑:
  //   1. 获取当前位姿 (cur_x_, cur_y_, cur_yaw_)
  //   2. 获取目标点位坐标 (target.x, target.y, target.theta)
  //   3. 先转向目标方向，再走直线，到达后转到目标朝向
  //   4. 位置误差 < pos_tolerance_ 且角度误差 < yaw_tolerance_ → 到达
  //   5. 超时 → 强制到达
  //
  void HandleNavigation(DogNavCommand & cmd, double now_sec)
  {
    if (!nav_task_.active || nav_task_.finished) {
      cmd.vx = 0.0f; cmd.vy = 0.0f; cmd.wz = 0.0f;
      return;
    }

    // 首次进入
    if (nav_task_.seg_start_time <= 0.0) {
      nav_task_.seg_start_time = now_sec;
      if (!odom_received_) {
        RCLCPP_WARN(this->get_logger(), "★ 未收到里程计数据，使用时间导航");
      }
      RCLCPP_INFO(this->get_logger(),
        "★ 走段: %d → %d (%zu/%zu)",
        nav_task_.From(), nav_task_.To(),
        nav_task_.wp_idx + 1, nav_task_.path.size() - 1);
    }

    int target_point = nav_task_.To();
    const auto & target_coord = planner_->GetCoord(target_point);

    // 超时保护
    double elapsed = now_sec - nav_task_.seg_start_time;
    if (elapsed > nav_timeout_sec_) {
      RCLCPP_WARN(this->get_logger(),
        "★ 导航超时 (%.1f秒)，强制到达点位 %d", elapsed, target_point);
      FinishWaypoint(cmd, now_sec);
      return;
    }

    // 如果没有里程计数据，回退到时间导航
    if (!odom_received_) {
      if (elapsed < segment_time_sec_) {
        cmd.vx = nav_vx_;
        cmd.vy = 0.0f;
        cmd.wz = 0.0f;
      } else {
        FinishWaypoint(cmd, now_sec);
      }
      return;
    }

    // ====== 雷达定位反馈导航 ======
    double target_yaw_rad = target_coord.theta * M_PI / 180.0;

    // 计算位置误差（世界坐标系）
    double dx = target_coord.x - cur_x_;
    double dy = target_coord.y - cur_y_;
    double dist = std::sqrt(dx * dx + dy * dy);

    // 角度误差：当前朝向 → 目标点方向
    double angle_to_target = std::atan2(dy, dx);
    [[maybe_unused]] double yaw_error_to_point = NormalizeAngle(angle_to_target - cur_yaw_);

    // 角度误差：当前朝向 → 目标最终朝向
    double yaw_error_final = NormalizeAngle(target_yaw_rad - cur_yaw_);

    // 判断是否到达
    if (dist < pos_tolerance_) {
      // 位置到达，检查朝向
      if (std::abs(yaw_error_final) < yaw_tolerance_) {
        RCLCPP_INFO(this->get_logger(),
          "★ 到达点位 %d (误差: dist=%.3fm, yaw=%.1f°)",
          target_point, dist, yaw_error_final * 180.0 / M_PI);
        FinishWaypoint(cmd, now_sec);
        return;
      }
      // 位置到了但朝向不对，原地旋转
      double wz = std::clamp(nav_kp_yaw_ * yaw_error_final, -nav_max_wz_, nav_max_wz_);
      cmd.vx = 0.0f;
      cmd.vy = 0.0f;
      cmd.wz = static_cast<float>(wz);
      return;
    }

    // ====== 横移导航（不转向，螃蟹步） ======
    // 将世界坐标系的 (dx, dy) 分解到机器人本体坐标系
    //   vx: 前进方向（机器人朝向）
    //   vy: 左侧方向（横移）
    double cos_yaw = std::cos(cur_yaw_);
    double sin_yaw = std::sin(cur_yaw_);

    // 本体坐标系下的误差
    double vx_body =  dx * cos_yaw + dy * sin_yaw;   // 前进分量
    double vy_body = -dx * sin_yaw + dy * cos_yaw;   // 左横移分量

    // P 控制 + 限幅
    double vx = std::clamp(nav_kp_xy_ * vx_body, -nav_max_vx_, nav_max_vx_);
    double vy = std::clamp(nav_kp_xy_ * vy_body, -nav_max_vy_, nav_max_vy_);
    double wz = 0.0;  // 不转向

    cmd.vx = static_cast<float>(vx);
    cmd.vy = static_cast<float>(vy);
    cmd.wz = static_cast<float>(wz);
  }

  // 到达一个 waypoint，推进到下一个
  void FinishWaypoint(DogNavCommand & cmd, double now_sec)
  {
    cmd.vx = 0.0f;
    cmd.vy = 0.0f;
    cmd.wz = 0.0f;

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
  // ★ LoadManualBoxTypes — 手动模式: 从 manual_box_types 参数读入箱子类别
  // 填充 box_type_map_（key=箱子编号 5-12，value=类别），返回是否至少读到一个
  // ========================================================================================
  bool LoadManualBoxTypes()
  {
    box_type_map_.clear();
    static const std::set<std::string> kValid{
      "food", "tool", "instrument", "medicine"};

    for (int bn = 5; bn <= 12; ++bn) {
      char buf[16];
      std::snprintf(buf, sizeof(buf), "box_%02d", bn);
      std::string tp = this->get_parameter(std::string("manual_box_types.") + buf).as_string();
      // trim
      tp.erase(0, tp.find_first_not_of(" \t\r\n"));
      tp.erase(tp.find_last_not_of(" \t\r\n") + 1);
      if (tp.empty()) {
        continue;
      }
      if (kValid.count(tp) == 0) {
        RCLCPP_WARN(this->get_logger(),
          "★ manual_box_types.box_%02d='%s' 不是合法类别（food/tool/instrument/medicine），已忽略",
          bn, tp.c_str());
        continue;
      }
      box_type_map_[bn] = tp;
    }

    RCLCPP_INFO(this->get_logger(), "★ 手动模式: 读入 %zu 个箱子类别:", box_type_map_.size());
    for (const auto & [bn, tp] : box_type_map_) {
      RCLCPP_INFO(this->get_logger(), "  箱%02d → %s", bn, tp.c_str());
    }
    return !box_type_map_.empty();
  }

  // ========================================================================================
  // ★ FinalizeBoxScan — 扫描收尾: 校验 box_type_map_、生成取放计划、停推流、启动首轮
  // Phase1 扫描完成 与 手动模式 共用
  // ========================================================================================
  void FinalizeBoxScan()
  {
    // 校验: 每种类型必须恰好2个（8箱4种）
    std::map<std::string, int> type_count;
    for (const auto & [bn, tp] : box_type_map_) {
      type_count[tp]++;
    }
    bool valid = true;
    if (type_count.size() != 4) {
      RCLCPP_ERROR(this->get_logger(), "★ 类型数=%zu，期望4种", type_count.size());
      valid = false;
    }
    for (const auto & [tp, cnt] : type_count) {
      if (cnt != 2) {
        RCLCPP_ERROR(this->get_logger(), "★ 类型 %s 出现 %d 次，期望2次", tp.c_str(), cnt);
        valid = false;
      }
    }
    if (valid) {
      RCLCPP_INFO(this->get_logger(), "✅ 扫描结果校验通过");
    } else {
      RCLCPP_WARN(this->get_logger(), "❌ 扫描结果校验失败，使用当前结果继续");
    }

    GenerateDeliveryPlan();

    // 8 箱识别完、计划生成完，停止推流（释放 D435i）
    StopStreamer();

    if (delivery_plan_.empty()) {
      RCLCPP_ERROR(this->get_logger(), "★ 生成取放计划失败，退出");
      state_ = NavState::DONE;
    } else {
      round_idx_ = 0;
      StartDeliveryRound();
    }
  }

  // ========================================================================================
  // ★ RunBoxScan — 调用 box_detector_rknn.py --mode scan_all，返回匹配的拿取点列表
  // ========================================================================================
  std::vector<int> RunBoxScan(int target_zone)
  {
    std::string cmd = "python3 " + box_scanner_path_ +
      " --mode scan_all --target-zone " + std::to_string(target_zone) +
      " --field-side " + field_side_ + " 2>&1";

    RCLCPP_INFO(this->get_logger(), "★ 执行: %s", cmd.c_str());

    FILE * pipe = popen(cmd.c_str(), "r");
    if (!pipe) {
      RCLCPP_ERROR(this->get_logger(), "★ 无法执行 box_detector_rknn.py");
      return {};
    }

    std::string output;
    char buf[512];
    while (fgets(buf, sizeof(buf), pipe)) {
      output += buf;
    }
    (void)pclose(pipe);

    RCLCPP_INFO(this->get_logger(), "★ box_scanner 输出:\n%s", output.c_str());

    // 解析 BOX_SCAN_PICKUP=12,16
    std::vector<int> points;
    auto pos = output.find("BOX_SCAN_PICKUP=");
    if (pos == std::string::npos) {
      RCLCPP_ERROR(this->get_logger(), "★ box_scanner 未输出 BOX_SCAN_PICKUP");
      return {};
    }

    std::string pickup_str = output.substr(pos + 17);
    auto newline = pickup_str.find('\n');
    if (newline != std::string::npos) {
      pickup_str = pickup_str.substr(0, newline);
    }
    // trim
    pickup_str.erase(0, pickup_str.find_first_not_of(" \t\r"));
    pickup_str.erase(pickup_str.find_last_not_of(" \t\r") + 1);

    if (pickup_str.empty()) {
      RCLCPP_WARN(this->get_logger(), "★ BOX_SCAN_PICKUP 为空（没有匹配的箱子）");
      return {};
    }

    // 解析逗号分隔的整数
    std::istringstream iss(pickup_str);
    std::string token;
    while (std::getline(iss, token, ',')) {
      try {
        points.push_back(std::stoi(token));
      } catch (...) {
        RCLCPP_WARN(this->get_logger(), "★ 解析 pickup 点位失败: '%s'", token.c_str());
      }
    }

    // 解析 BOX_SCAN_MAP=11:food,12:tool,...（完整的点位→类型映射）
    auto map_pos = output.find("BOX_SCAN_MAP=");
    if (map_pos != std::string::npos) {
      std::string map_str = output.substr(map_pos + 13);
      auto map_nl = map_str.find('\n');
      if (map_nl != std::string::npos) {
        map_str = map_str.substr(0, map_nl);
      }
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
      RCLCPP_INFO(this->get_logger(), "★ 场地箱子映射（已存储到 box_type_map_）:");
      for (const auto & [pt, tp] : box_type_map_) {
        RCLCPP_INFO(this->get_logger(), "  点位 %d → %s", pt, tp.c_str());
      }
    } else {
      RCLCPP_WARN(this->get_logger(),
        "★ box_scanner 未输出 BOX_SCAN_MAP，box_type_map_ 为空（FillBoxInfo 将全部跳过）");
    }

    return points;
  }

  // ========================================================================================
  // ★ StartStreamer — 启动 d435i_stream.py 推流进程（独占 D435i + shm 喂帧）
  // ========================================================================================
  //
  // 在 OCR_SOLVE 调 RunSolver 之前调用，让 D435i 就绪，solver/box_detector 从 shm 取帧。
  // popen 后台启动，轮询 /dev/shm/d435i_frame.npz 出现确认就绪（超时 5s 不阻断）。
  // 失败只打 WARN，不阻断流程 —— vision 脚本读不到 shm 会回退直接开 D435i。
  //
  void StartStreamer()
  {
    if (!stream_enable_ || streamer_pid_ > 0) return;

    std::string cmd = "python3 " + streamer_path_ + " --port " +
                      std::to_string(stream_port_) + " > /tmp/d435i_stream.log 2>&1 &";

    FILE * pipe = popen(cmd.c_str(), "r");
    if (!pipe) {
      RCLCPP_WARN(this->get_logger(), "★ 推流启动失败（vision 脚本将回退直接开 D435i）");
      return;
    }
    // 读一行获取后台进程 pid（python3 ... & 的 shell 会回显 PID）
    char buf[64] = {0};
    if (fgets(buf, sizeof(buf), pipe)) {
      streamer_pid_ = atoi(buf);
    }
    pclose(pipe);

    if (streamer_pid_ <= 0) {
      // 没拿到 pid 也允许（推流是辅助），用 pgrep 兜底
      FILE * gp = popen("pgrep -f d435i_stream.py", "r");
      if (gp) {
        if (fgets(buf, sizeof(buf), gp)) streamer_pid_ = atoi(buf);
        pclose(gp);
      }
    }

    // 轮询 shm 就绪（超时不阻断）
    const char * shm = "/dev/shm/d435i_frame.npz";
    for (int i = 0; i < 50; ++i) {  // 最多 ~5s
      if (access(shm, F_OK) == 0) {
        RCLCPP_INFO(this->get_logger(),
          "★ 推流已就绪 (pid=%d, ws port=%d)，电脑端 Foxglove 连 ws://<上位机IP>:%d",
          streamer_pid_, stream_port_, stream_port_);
        return;
      }
      std::this_thread::sleep_for(std::chrono::milliseconds(100));
    }
    RCLCPP_WARN(this->get_logger(),
      "★ 推流进程已启动但 shm 5s 内未就绪（vision 脚本将回退直接开 D435i）");
  }

  // ========================================================================================
  // ★ StopStreamer — 停止推流进程（8 箱识别完、计划生成后调用）
  // ========================================================================================
  void StopStreamer()
  {
    if (streamer_pid_ <= 0) return;
    RCLCPP_INFO(this->get_logger(), "★ 停止推流进程 pid=%d", streamer_pid_);
    kill(streamer_pid_, SIGTERM);
    // 等 1s，未退出则 SIGKILL
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

  // ========================================================================================
  // ★ RunSolver — 调用 solver.py，返回 mod4 结果（-1 表示失败）
  // ========================================================================================
  int RunSolver()
  {
    std::string cmd = "python3 " + solver_path_ + " 2>&1";
    FILE * pipe = popen(cmd.c_str(), "r");
    if (!pipe) {
      RCLCPP_ERROR(this->get_logger(), "★ 无法执行 solver.py");
      return -1;
    }

    std::string output;
    char buf[256];
    while (fgets(buf, sizeof(buf), pipe)) {
      output += buf;
    }
    (void)pclose(pipe);

    RCLCPP_INFO(this->get_logger(), "★ solver.py 输出:\n%s", output.c_str());

    auto pos = output.find("PROBLEM_RESULT_JSON=");
    if (pos == std::string::npos) {
      RCLCPP_ERROR(this->get_logger(), "★ solver.py 未输出 PROBLEM_RESULT_JSON");
      return -1;
    }

    std::string json_str = output.substr(pos + 20);
    auto newline = json_str.find('\n');
    if (newline != std::string::npos) {
      json_str = json_str.substr(0, newline);
    }

    if (json_str.find("\"success\": true") == std::string::npos &&
        json_str.find("\"success\":true") == std::string::npos) {
      RCLCPP_ERROR(this->get_logger(), "★ solver.py 计算失败: %s", json_str.c_str());
      return -1;
    }

    auto mod4_pos = json_str.find("\"mod4\":");
    if (mod4_pos == std::string::npos) {
      RCLCPP_ERROR(this->get_logger(), "★ solver.py 未输出 mod4: %s", json_str.c_str());
      return -1;
    }

    int mod4_val = -1;
    sscanf(json_str.c_str() + mod4_pos, "\"mod4\": %d", &mod4_val);
    return mod4_val;
  }

  // ========================================================================================
  // ★ CalcPlaceTurnAngle — 自动计算放置时的转身角度
  // ========================================================================================
  //
  // 原理:
  //   1. 获取放置点坐标 (px, py) 和归位区坐标 (zx, zy)
  //   2. 计算归位区相对于放置点的方向角: zone_angle = atan2(zy-py, zx-px)
  //   3. 吸盘在身体两侧（左=机器人左侧，右=机器人右侧）
  //   4. 左吸盘有箱 → 需要让左侧对准归位区 → turn = zone_angle - (yaw + π/2)
  //   5. 右吸盘有箱 → 需要让右侧对准归位区 → turn = zone_angle - (yaw - π/2)
  //   6. 简化: turn = atan2(zy-py, zx-px) - cur_yaw ± π/2
  //
  double CalcPlaceTurnAngle(int place_point, const std::string & direction)
  {
    // 获取放置点坐标
    const auto & place_coord = planner_->GetCoord(place_point);
    double px = place_coord.x;
    double py = place_coord.y;

    // ★ 新布局: 归位区由 放货站位 × 吸盘侧 决定（place_zone_map_ 反查）
    //   点10: left→zone1, right→zone2
    //   点11: left→zone2, right→zone3
    //   点12: left→zone3, right→zone4
    //   点13: right→zone1
    //   点14: left→zone4
    // 狗子面朝归位区到达，吸盘已在 zone 大致方向，turn 通常≈0（仅微调）
    int zone_id = 0;
    auto pzm = place_zone_map_.find(place_point);
    if (pzm != place_zone_map_.end()) {
      auto dit = pzm->second.find(direction);
      if (dit != pzm->second.end()) zone_id = dit->second;
    }
    if (zone_id == 0) {
      RCLCPP_WARN(this->get_logger(),
        "★ 放货点%d/%s 归位区映射缺失，用默认±90°", place_point, direction.c_str());
      return (direction == "left") ? (-M_PI / 2.0) : (M_PI / 2.0);
    }

    auto it = zone_coords_.find(zone_id);
    if (it == zone_coords_.end()) {
      RCLCPP_WARN(this->get_logger(),
        "★ 归位区 %d 坐标未配置，使用默认 ±90°", zone_id);
      return (direction == "left") ? (-M_PI / 2.0) : (M_PI / 2.0);
    }

    double zx = it->second.x;
    double zy = it->second.y;

    // 归位区相对于放置点的方向（世界坐标系）
    double zone_angle = std::atan2(zy - py, zx - px);

    // 吸盘侧的角度偏移（相对于机器人朝向）
    // 左吸盘在机器人左侧 = yaw + π/2 方向
    // 右吸盘在机器人右侧 = yaw - π/2 方向
    double sucker_angle = (direction == "left")
      ? (cur_yaw_ + M_PI / 2.0)
      : (cur_yaw_ - M_PI / 2.0);

    // 转身角度 = 让吸盘方向对准归位区方向
    double turn = NormalizeAngle(zone_angle - sucker_angle);

    RCLCPP_INFO(this->get_logger(),
      "★ 自动计算转身: 放置点%d(%.2f,%.2f) → zone%d(%.2f,%.2f), "
      "zone_angle=%.1f°, sucker_angle=%.1f°, turn=%.1f°",
      place_point, px, py, zone_id, zx, zy,
      zone_angle * 180.0 / M_PI,
      sucker_angle * 180.0 / M_PI,
      turn * 180.0 / M_PI);

    return turn;
  }

  // ========================================================================================
  // ★ LoadStaticMaps — 加载静态映射表（从 YAML 配置）
  // ========================================================================================
  void LoadStaticMaps()
  {
    // pickup_pair_map: 成对取货点 (left_point, right_point, left_box, right_box)
    // 新布局每个取货点旁边只有一个箱，一轮跑两个点凑齐左右吸盘:
    //   第1轮: 左点2(吸09), 右点3(吸10)
    //   第2轮: 左点4(吸11), 右点5(吸12)
    //   第3轮: 左点6(吸05), 右点7(吸06)
    //   第4轮: 左点8(吸07), 右点9(吸08)
    pickup_pair_map_ = {
      {2, 3, 9,  10},
      {4, 5, 11, 12},
      {6, 7, 5,  6},
      {8, 9, 7,  8},
    };

    // type_zone_map: 箱子类型 → zone 编号
    // 01-04 归位区的颜色排列随左右场不同（zone 编号 1-4 指同一物理归位区位置）:
    //   左场: 01绿(food) 02灰(tool) 03蓝(instrument) 04红(medicine)
    //   右场: 01红(medicine) 02蓝(instrument) 03灰(tool) 04绿(food)  (逆序)
    // 05-12 颜色本身随机，其余映射（取货点位、站位×吸盘→zone）都不变，可复用
    if (field_side_ == "right") {
      type_zone_map_ = {
        {"medicine", 1}, {"instrument", 2}, {"tool", 3}, {"food", 4}
      };
    } else {
      type_zone_map_ = {
        {"food", 1}, {"tool", 2}, {"instrument", 3}, {"medicine", 4}
      };
    }

    // place_zone_map: 放货站位 × 吸盘侧 → 归位区编号
    //   点10: left→zone1(01), right→zone2(02)
    //   点11: left→zone2(02), right→zone3(03)
    //   点12: left→zone3(03), right→zone4(04)
    //   点13: right→zone1(01)  ← 右吸盘放zone1的自然站位（zone1在点13右侧）
    //   点14: left→zone4(04)   ← 左吸盘放zone4的自然站位（zone4在点14左侧）
    // 每个 (吸盘侧, zone) 都有唯一自然站位，无需转圈倒车
    place_zone_map_ = {
      {10, {{"left", 1},  {"right", 2}}},
      {11, {{"left", 2},  {"right", 3}}},
      {12, {{"left", 3},  {"right", 4}}},
      {13, {{"right", 1}}},
      {14, {{"left", 4}}},
    };

    // 反查表（吸盘侧 + 目标zone → 放货站位），GenerateDeliveryPlan 用
    //   左吸盘: zone1→点10, zone2→点11, zone3→点12, zone4→点14
    //   右吸盘: zone1→点13, zone2→点10, zone3→点11, zone4→点12
    // 全组合都有自然映射，无需转圈倒车补全
    reverse_place_map_ = BuildReversePlaceMap();
  }

  // 构造"吸盘侧 + zone → 放货站位"反查表
  std::map<std::string, std::map<int, int>> BuildReversePlaceMap()
  {
    std::map<std::string, std::map<int, int>> rev;
    for (const auto & [pp, side_map] : place_zone_map_) {
      for (const auto & [dir, zone] : side_map) {
        rev[dir][zone] = pp;
      }
    }
    return rev;
  }

  // ========================================================================================
  // ★ GenerateDeliveryPlan — 从扫描结果生成多轮取放计划
  // ========================================================================================
  //
  // 输入: box_type_map_ (箱子编号 → 类型，来自扫描)
  // 输出: delivery_plan_ (每轮 = 一对取货点，左吸盘从 left 点取，右吸盘从 right 点取)
  //
  // 逻辑:
  //   遍历 pickup_pair_map_（4 组成对点位）:
  //     左吸盘从 left_point 取 left_box，右吸盘从 right_point 取 right_box
  //     查箱子类型 → 目标归位区 zone
  //     由 吸盘侧 + zone 反查放货站位（reverse_place_map_）
  //   生成 PickupRound 列表
  //
  void GenerateDeliveryPlan()
  {
    delivery_plan_.clear();

    RCLCPP_INFO(this->get_logger(), "★ 生成取放计划:");

    for (const auto & [lp, rp, lb, rb] : pickup_pair_map_) {
      PickupRound round;
      round.pickup_point_left = lp;
      round.pickup_point_right = rp;

      // 左吸盘的箱
      FillBoxInfo(round.left, lb, "left");
      // 右吸盘的箱
      FillBoxInfo(round.right, rb, "right");

      if (round.left.valid || round.right.valid) {
        delivery_plan_.push_back(round);

        RCLCPP_INFO(this->get_logger(),
          "  左点%d吸%02d→(%s→zone%d→点%d), 右点%d吸%02d→(%s→zone%d→点%d)",
          lp, round.left.box_num, round.left.type.c_str(),
          round.left.zone, round.left.place_point,
          rp, round.right.box_num, round.right.type.c_str(),
          round.right.zone, round.right.place_point);
      }
    }

    RCLCPP_INFO(this->get_logger(),
      "★ 共 %zu 轮取放计划", delivery_plan_.size());
  }

  // 填充单个 BoxInfo：查类型 → zone → 反查放货站位
  void FillBoxInfo(BoxInfo & info, int box_num, const std::string & direction)
  {
    info.box_num = box_num;
    info.direction = direction;  // 记住吸盘侧，放货时用

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
  // ★ GoDeliverFirst — 取完两箱后，导航去放第一个箱（左箱）
  // ========================================================================================
  // 从 PICKUP 的 sub_step 3 调用，推进到 sub_step 4（去放左箱）
  // 如果左箱无效，直接放右箱（sub_step 6）
  //
  void GoDeliverFirst(const PickupRound & round)
  {
    if (round.left.valid) {
      active_direction_ = "left";
      active_box_num_ = round.left.box_num;
      active_box_type_ = round.left.type;
      active_deliver_point_ = round.left.place_point;
      active_zone_ = round.left.zone;
      sub_step_ = 4;

      RCLCPP_INFO(this->get_logger(),
        "★ 去放第一个箱(左): 箱%02d(%s)→zone%d→点%d",
        round.left.box_num, round.left.type.c_str(),
        round.left.zone, round.left.place_point);

      if (StartNavTo(round.left.place_point, NavState::PLACE_BOX)) {
        state_ = NavState::GOTO_TARGET;
      } else {
        state_ = NavState::DONE;
      }
    } else if (round.right.valid) {
      // 左箱无效，直接放右箱
      active_direction_ = "right";
      active_box_num_ = round.right.box_num;
      active_box_type_ = round.right.type;
      active_deliver_point_ = round.right.place_point;
      active_zone_ = round.right.zone;
      sub_step_ = 6;

      RCLCPP_INFO(this->get_logger(),
        "★ 左箱无效，直接放右箱: 箱%02d(%s)→zone%d→点%d",
        round.right.box_num, round.right.type.c_str(),
        round.right.zone, round.right.place_point);

      if (StartNavTo(round.right.place_point, NavState::PLACE_BOX)) {
        state_ = NavState::GOTO_TARGET;
      } else {
        state_ = NavState::DONE;
      }
    } else {
      RCLCPP_WARN(this->get_logger(), "★ 本轮无有效箱子，跳过");
      round_idx_++;
      StartDeliveryRound();
    }
  }

  // ========================================================================================
  // ★ NeedPlaceAvoid — 判断从 from_point 到 to_point 是否需要 U 型绕行
  // ========================================================================================
  //
  // 规则: 两点都在归位区行(10/11/12)，且横向通道被已放箱归位区挡住
  //   - 10↔11 边被 zone2 挡（02 放了箱）
  //   - 11↔12 边被 zone3 挡（03 放了箱）
  //   - 10↔12 直连：链式图里本不直连，但若经过 11 也会被挡
  //
  // 实现: 用 BFS（带 placed_zones_）试算路径，如果横向边全断（必须绕第二排），则需绕行
  // 简化判断: 两点都在 {10,11,12}，且它们之间的横向连接被 placed_zones_ 挡住
  //
  bool NeedPlaceAvoid(int from_point, int to_point)
  {
    // 只有归位区行内的移动才可能需要绕行
    auto is_place_row = [](int p) { return p == 10 || p == 11 || p == 12; };
    if (!is_place_row(from_point) || !is_place_row(to_point)) {
      return false;
    }
    if (from_point == to_point) return false;

    // 判断 from→to 之间是否被已放箱归位区挡住
    // 10↔11 之间有 zone2; 11↔12 之间有 zone3; 10↔12 之间有 zone2 和 zone3
    int lo = std::min(from_point, to_point);
    int hi = std::max(from_point, to_point);

    // lo=10,hi=11 → 检查 zone2
    // lo=11,hi=12 → 检查 zone3
    // lo=10,hi=12 → 检查 zone2 或 zone3（任一挡住就不能直连）
    if (lo == 10 && hi == 11) {
      return placed_zones_.count(2) > 0;
    }
    if (lo == 11 && hi == 12) {
      return placed_zones_.count(3) > 0;
    }
    if (lo == 10 && hi == 12) {
      return placed_zones_.count(2) > 0 || placed_zones_.count(3) > 0;
    }
    return false;
  }

  // ========================================================================================
  // ★ StartPlaceAvoid — 启动 U 型避障机动
  // ========================================================================================
  //
  // 记录起点（当前 odom 位姿）和终点（目标站位坐标），进入 phase 0（后退）
  // 狗朝向固定 +y，所以:
  //   后退 = 世界 -y 方向（离开归位区行）
  //   横移 = 世界 ±x（到目标站位 x）
  //   前进 = 世界 +y 方向（回到归位区行，到目标站位 y）
  //
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
      "★ 启动 U型避障: 当前(%.2f,%.2f) → 目标点%d(%.2f,%.2f), 后退%.1fm→横移→前进",
      cur_x_, cur_y_, dest_point, dest.x, dest.y, place_avoid_dist_);
  }

  // ========================================================================================
  // ★ HandlePlaceAvoid — 执行 U 型避障机动（3 个 phase）
  // ========================================================================================
  //
  // phase 0: 后退 place_avoid_dist_（目标 y = start_y - dist）
  // phase 1: 横移到 dest_x（目标 x = dest_x，y 保持后退后的位置）
  // phase 2: 前进到目标站位（目标 y = dest_y）
  //
  // 每个 phase 用世界坐标目标 + P 控制（复用 nav_kp_xy_），到位切下一 phase
  // 全部完成 → state_ = PLACE_BOX（狗已在目标站位，直接放箱）
  //
  void HandlePlaceAvoid(DogNavCommand & cmd, double now_sec)
  {
    const double pos_tol = 0.05;  // 到位容差
    const double timeout = 10.0;  // 单 phase 超时

    // 计算当前 phase 的世界坐标目标
    double target_x = cur_x_, target_y = cur_y_;
    switch (avoid_maneuver_.phase) {
      case 0:  // 后退：y 减小 place_avoid_dist_
        target_x = avoid_maneuver_.start_x;
        target_y = avoid_maneuver_.start_y - place_avoid_dist_;
        break;
      case 1:  // 横移：x 到 dest_x，y 保持
        target_x = avoid_maneuver_.dest_x;
        target_y = avoid_maneuver_.start_y - place_avoid_dist_;
        break;
      case 2:  // 前进：到目标站位
        target_x = avoid_maneuver_.dest_x;
        target_y = avoid_maneuver_.dest_y;
        break;
    }

    // 世界系误差
    double dx = target_x - cur_x_;
    double dy = target_y - cur_y_;
    double dist = std::hypot(dx, dy);

    double elapsed = now_sec - avoid_maneuver_.phase_start_time;

    // 到位或超时 → 切下一 phase
    if (dist < pos_tol || elapsed > timeout) {
      RCLCPP_INFO(this->get_logger(),
        "★ U型 phase%d 完成 (dist=%.3f, 用时%.1fs)",
        avoid_maneuver_.phase, dist, elapsed);

      avoid_maneuver_.phase++;
      avoid_maneuver_.phase_start_time = now_sec;

      if (avoid_maneuver_.phase > 2) {
        // 全部完成，狗已在目标站位，进入放箱
        avoid_maneuver_.active = false;
        current_pos_ = active_deliver_point_;
        state_ = NavState::PLACE_BOX;
        // actor_ 在 action_done 时已自动复位 flags，进 PLACE_BOX 会走首次进入分支执行放箱
        cmd.vx = 0.0f; cmd.vy = 0.0f; cmd.wz = 0.0f;
        return;
      }
      // 重新计算新 phase 的目标
      cmd.vx = 0.0f; cmd.vy = 0.0f; cmd.wz = 0.0f;
      return;
    }

    // P 控制：世界误差旋转到本体坐标（狗朝向 +y，yaw≈π/2）
    // vx_body =  dx*cos(yaw) + dy*sin(yaw)
    // vy_body = -dx*sin(yaw) + dy*cos(yaw)
    double vx_body = dx * std::cos(cur_yaw_) + dy * std::sin(cur_yaw_);
    double vy_body = -dx * std::sin(cur_yaw_) + dy * std::cos(cur_yaw_);

    double vx = std::clamp(nav_kp_xy_ * vx_body, -nav_max_vx_, nav_max_vx_);
    double vy = std::clamp(nav_kp_xy_ * vy_body, -nav_max_vy_, nav_max_vy_);

    cmd.vx = static_cast<float>(vx);
    cmd.vy = static_cast<float>(vy);
    cmd.wz = 0.0f;
  }

  // ========================================================================================
  // ★ StartDeliveryRound — 开始一轮取放（成对取货：左点取1 + 右点取1，再分放）
  // ========================================================================================
  //
  // sub_step_ 流程（成对取货版）:
  //   0 → 导航到左取货点(left_point)
  //   1 → 左吸盘取箱
  //   2 → 导航到右取货点(right_point)
  //   3 → 右吸盘取箱
  //   4 → 导航到第一个放货点（先放 left 箱）
  //   5 → 放第一个箱
  //   6 → 导航到第二个放货点（放 right 箱，可能需 PLACE_AVOID）
  //   7 → 放第二个箱
  //   → 本轮完成，进入下一轮
  //
  // ========================================================================================
  // AdvanceAfterPickup — 吸盘取箱动作完成后（或 box 无效跳过动作），推进 sub_step
  // ========================================================================================
  void AdvanceAfterPickup(const PickupRound & round)
  {
    if (sub_step_ == 1) {
      // 左箱取完 → 去右取货点
      sub_step_ = 2;
      if (round.right.valid) {
        RCLCPP_INFO(this->get_logger(), "★ 左箱取完，导航到右取货点%d",
          round.pickup_point_right);
        if (StartNavTo(round.pickup_point_right, NavState::PICKUP)) {
          state_ = NavState::GOTO_PICKUP;
        } else {
          state_ = NavState::DONE;
        }
      } else {
        // 右箱无效，直接去放左箱
        RCLCPP_INFO(this->get_logger(), "★ 右箱无效，直接去放左箱");
        GoDeliverFirst(round);
      }
    } else if (sub_step_ == 3) {
      // 右箱取完 → 去放第一个箱（左箱）
      RCLCPP_INFO(this->get_logger(), "★ 两箱取完，去放第一个箱");
      GoDeliverFirst(round);
    }
  }

  // ========================================================================================
  // AdvanceAfterPlace — 吸盘放箱动作完成后，推进 sub_step
  // ========================================================================================
  void AdvanceAfterPlace(const PickupRound & round)
  {
    if (sub_step_ == 5 && round.right.valid) {
      // 放完第一个箱（左箱），去放第二个箱（右箱）
      int dest_point = round.right.place_point;
      bool need_avoid = NeedPlaceAvoid(active_deliver_point_, dest_point);

      active_direction_ = "right";
      active_box_num_ = round.right.box_num;
      active_box_type_ = round.right.type;
      active_deliver_point_ = dest_point;
      active_zone_ = round.right.zone;
      sub_step_ = 6;

      RCLCPP_INFO(this->get_logger(),
        "★ 去放第二个箱: 箱%02d(%s)→zone%d→点%d %s",
        round.right.box_num, round.right.type.c_str(),
        round.right.zone, dest_point, need_avoid ? "★需U型绕行" : "");

      if (need_avoid) {
        // 进入 U 型避障机动
        StartPlaceAvoid(dest_point);
        state_ = NavState::PLACE_AVOID;
      } else {
        if (StartNavTo(dest_point, NavState::PLACE_BOX)) {
          state_ = NavState::GOTO_TARGET;
        } else {
          state_ = NavState::DONE;
        }
      }
    } else {
      // 本轮全部放完
      RCLCPP_INFO(this->get_logger(),
        "★ === 第 %zu/%zu 轮取放完成 ===",
        round_idx_ + 1, delivery_plan_.size());

      round_idx_++;
      if (round_idx_ < delivery_plan_.size()) {
        StartDeliveryRound();
      } else {
        RCLCPP_INFO(this->get_logger(),
          "★ ★ ★ 全部 %zu 轮取放完成！ ★ ★ ★", delivery_plan_.size());
        state_ = NavState::DONE;
      }
    }
  }

  void StartDeliveryRound()
  {
    if (round_idx_ >= delivery_plan_.size()) {
      RCLCPP_INFO(this->get_logger(), "★ 全部 %zu 轮取放完成！", delivery_plan_.size());
      state_ = NavState::DONE;
      return;
    }

    const auto & round = delivery_plan_[round_idx_];
    sub_step_ = 0;

    RCLCPP_INFO(this->get_logger(),
      "★ === 第 %zu/%zu 轮: 左取货点%d(吸%02d) + 右取货点%d(吸%02d) ===",
      round_idx_ + 1, delivery_plan_.size(),
      round.pickup_point_left, round.left.box_num,
      round.pickup_point_right, round.right.box_num);

    // sub_step 0: 导航到左取货点
    if (StartNavTo(round.pickup_point_left, NavState::PICKUP)) {
      state_ = NavState::GOTO_PICKUP;
    } else {
      state_ = NavState::DONE;
    }
  }

  // =========================
  // 辅助方法
  // =========================
  std::string PickupPointsStr() const
  {
    std::ostringstream oss;
    oss << "[";
    for (size_t i = 0; i < delivery_plan_.size(); ++i) {
      if (i > 0) oss << ", ";
      // 成对取货点: 显示 (left,right)
      oss << "(" << delivery_plan_[i].pickup_point_left
          << "," << delivery_plan_[i].pickup_point_right << ")";
    }
    oss << "]";
    return oss.str();
  }

  // =========================
  // 成员变量
  // =========================
  rclcpp::Publisher<DogNavCommand>::SharedPtr nav_cmd_pub_;
  rclcpp::TimerBase::SharedPtr timer_;

  // 路径规划器
  std::unique_ptr<FieldPathPlanner> planner_;

  // 状态机
  NavState state_{NavState::IDLE};
  NavState next_state_{NavState::DONE};
  int current_pos_{0};

  // ★ 取放计划（支持多轮，每轮 = 一对取货点，左吸盘从 left 点取，右吸盘从 right 点取）
  std::vector<PickupRound> delivery_plan_;
  size_t round_idx_{0};                     // 当前轮次索引
  // sub_step_ (成对取货 + 两箱分放):
  //   0 = 导航到左取货点(left_point)
  //   1 = 左吸盘取箱
  //   2 = 导航到右取货点(right_point)
  //   3 = 右吸盘取箱
  //   4 = 导航到第一个放货点(先放 left 箱)
  //   5 = 放第一个箱
  //   6 = 导航到第二个放货点(放 right 箱，可能需 PLACE_AVOID)
  //   7 = 放第二个箱
  int sub_step_{0};
  int deliver_target_{0};                   // 目标放货站位（用于OCR mode）

  // 当前取放任务
  int active_pickup_point_{0};
  int active_deliver_point_{0};
  std::string active_direction_;
  int active_box_num_{0};
  std::string active_box_type_;
  int active_zone_{0};                      // 当前要放的归位区编号

  // ★ 已放箱归位区集合（用于 BFS 逐边禁用 + 绕行判断）
  std::unordered_set<int> placed_zones_;

  // ★ U型避障机动状态 (PLACE_AVOID)
  // phase: 0=后退1m, 1=横移到目标x, 2=前进1m到目标站位
  struct AvoidManeuver {
    bool active{false};
    int phase{0};                           // 0/1/2
    double start_x{0.0};                    // 机动起点（当前站位）
    double start_y{0.0};
    double dest_x{0.0};                     // 目标站位 x（横移终点）
    double dest_y{0.0};                     // 目标站位 y（前进终点 = 目标站位）
    double phase_start_time{0.0};
  } avoid_maneuver_;
  double place_avoid_dist_{1.0};            // U型机动后退/前进距离（米，纯避障用）

  // ★ 吸盘串口参数（构造时透传给 actor_）
  std::string sucker_port_{"/dev/ttyUSB0"};
  int sucker_baudrate_{115200};
  double sucker_move_sec_{3.0};             // 舵机 0↔270 满程转动时间（秒）
  double sucker_hold_sec_{0.5};             // 下到位后保持时间（建真空/释放）

  // ★ 蹲下+吸盘 编排器（封装 squat_ctrl_ + sucker_ + 取放时序 flags）
  // 时序: 挂起RL→站→蹲插值→保持(吸盘动作)→蹲→站插值→恢复RL
  PickPlaceActor actor_;
  rclcpp::Publisher<sensor_msgs::msg::JointState>::SharedPtr joint_state_pub_;
  rclcpp::Publisher<std_msgs::msg::Bool>::SharedPtr policy_mode_pub_;

  // ★ D435i 推流进程（OCR_SOLVE 启动 → 8 箱识别完停止）
  bool stream_enable_{true};
  int stream_port_{8765};
  pid_t streamer_pid_{-1};
  std::string streamer_path_{
    std::string("/home/zhy/himdog/src/dog_nav/resource/vision/d435i_stream.py")};

  // pickup_pair_map: 成对取货点 (left_point, right_point, left_box, right_box)
  std::vector<std::tuple<int, int, int, int>> pickup_pair_map_;
  // type_zone_map: 箱子类型 → zone编号
  std::map<std::string, int> type_zone_map_;
  // place_zone_map: 放货站位(10/11/12) × 吸盘侧 → 归位区
  std::map<int, std::map<std::string, int>> place_zone_map_;
  // reverse_place_map: 吸盘侧 × zone → 放货站位（转圈倒车情况已补全）
  std::map<std::string, std::map<int, int>> reverse_place_map_;

  // 导航任务
  NavTask nav_task_;

  // blocked 点集合
  std::unordered_set<int> blocked_;

  // OCR
  bool ocr_started_{false};
  int ocr_retry_count_{0};
  int ocr_max_retries_{3};
  static constexpr double ocr_retry_delay_sec_{2.0};
  double ocr_retry_start_{0.0};

  // 参数
  float nav_vx_{0.3f};
  float nav_height_{0.25f};
  std::string field_side_{"left"};
  std::string solver_path_;
  std::string box_scanner_path_;
  std::string box_scan_mode_{"yolo"};     // yolo=YOLO扫描 / manual=赛前手填
  std::array<int, 4> mod4_target_{1, 2, 3, 4};
  std::vector<int> pickup_points_;           // 多次取货站位列表
  int pickup_point_{2};                  // 默认取货站位
  int deliver_point_{-1};
  double segment_time_sec_{3.0};
  bool auto_start_{false};
  bool box_scan_started_{false};

  // 场地箱子类型映射
  std::map<int, std::string> box_type_map_;  // point_id → box_type（当前扫描）
  std::map<int, std::string> phase0_map_;    // Phase0 扫描结果

  // 归位区坐标（zone_id → 坐标，不是路径节点）
  std::map<int, Point3D> zone_coords_;

  std::chrono::steady_clock::time_point node_start_time_;

  // 键盘监听线程
  std::thread keyboard_thread_;
  std::atomic<bool> keyboard_running_{false};

  // ★ 雷达定位
  rclcpp::Subscription<nav_msgs::msg::Odometry>::SharedPtr odom_sub_;
  std::string odom_topic_{"/lio/odom"};
  double cur_x_{0.0};
  double cur_y_{0.0};
  double cur_yaw_{0.0};  // 弧度
  bool odom_received_{false};

  // 导航控制参数
  double pos_tolerance_{0.05};
  double yaw_tolerance_{0.087};
  double nav_kp_xy_{0.8};
  double nav_kp_yaw_{1.5};
  double nav_max_vx_{0.5};
  double nav_max_vy_{0.3};
  double nav_max_wz_{1.0};
  double nav_timeout_sec_{15.0};
};

int main(int argc, char ** argv)
{
  rclcpp::init(argc, argv);
  rclcpp::spin(std::make_shared<NavigationDogNode>());
  rclcpp::shutdown();
  return 0;
}