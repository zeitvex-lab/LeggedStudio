#include "motor_ros2/motor_cfg.h"
#include "motor_ros2/controller_helpers.h"
#include "motor_ros2/leg_model.h"

#include "dog_control/msg/motor_feedback.hpp"
#include <rclcpp/rclcpp.hpp>
#include <sensor_msgs/msg/joint_state.hpp>
#include <std_msgs/msg/string.hpp>
#include <std_msgs/msg/bool.hpp>

#include <thread>
#include <unistd.h>
#include <atomic>
#include <unordered_map>
#include <mutex>
#include <chrono>
#include <array>
#include <string>
#include <vector>
#include <cmath>

namespace lm = motor_ros2::leg_model;


class MotorControlSample : public rclcpp::Node
{
public:
    MotorControlSample()
    : rclcpp::Node("real_motor_controller"),
      motors_{{
          RobStrideMotor("can0", 0xFF, 0x01, 0),
          RobStrideMotor("can0", 0xFF, 0x02, 0),
          RobStrideMotor("can0", 0xFF, 0x03, 0),

          RobStrideMotor("can1", 0xFF, 0x04, 0),
          RobStrideMotor("can1", 0xFF, 0x05, 0),
          RobStrideMotor("can1", 0xFF, 0x06, 0),

          RobStrideMotor("can3", 0xFF, 0x0A, 0),
          RobStrideMotor("can3", 0xFF, 0x0B, 0),
          RobStrideMotor("can3", 0xFF, 0x0C, 0),

          RobStrideMotor("can2", 0xFF, 0x07, 0),
          RobStrideMotor("can2", 0xFF, 0x08, 0),
          RobStrideMotor("can2", 0xFF, 0x09, 0)
      }}
    {
        static_assert(lm::kJointCount == 12, "real_motor_controller expects 12 joints");

        joint_names_ = lm::joint_names_vector();
        for (std::size_t i = 0; i < lm::kJointCount; ++i) {
            name_to_index_.emplace(lm::kJointNames[i], i);
        }
        build_hold_target_motor();

        joint_sub_ = this->create_subscription<sensor_msgs::msg::JointState>(
            "/joint_states", 10,
            std::bind(&MotorControlSample::joint_cb, this, std::placeholders::_1)
        );

        gait_params_sub_ = this->create_subscription<std_msgs::msg::String>(
            "/gait_params", 10,
            std::bind(&MotorControlSample::gait_params_cb, this, std::placeholders::_1)
        );

        // ★ 急停订阅：收到 true 后立即失能所有电机并退出
        emergency_stop_sub_ = this->create_subscription<std_msgs::msg::Bool>(
            "/emergency_stop", 10,
            [this](const std_msgs::msg::Bool::SharedPtr msg) {
                if (!msg || !msg->data) return;
                RCLCPP_ERROR(this->get_logger(),
                    "!!! EMERGENCY STOP received !!! Disabling all motors...");
                running_ = false;
                if (worker_thread_.joinable()) {
                    worker_thread_.join();
                }
                for (std::size_t i = 0; i < motors_.size(); ++i) {
                    if (enable_enabled_[i]) {
                        motors_[i].Disenable_Motor(0);
                    }
                }
                RCLCPP_ERROR(this->get_logger(), "All motors disabled. Shutting down.");
                rclcpp::shutdown();
            }
        );

        motor_feedback_pub_ = this->create_publisher<dog_control::msg::MotorFeedback>(
            "/motor_feedback", 10);

        enable_enabled_.fill(false);
        hold_zero_only_.fill(false);
        joint_cmd_seen_.fill(false);

        // ========== 12个电机独立开关 ==========
        enable_enabled_[0]  = true;   // FL_hip (左前-髋)
        enable_enabled_[1]  = true;   // FL_thigh (左前-大腿)
        enable_enabled_[2]  = true;   // FL_calf (左前-小腿)
        enable_enabled_[3]  = true;   // FR_hip (右前-髋)
        enable_enabled_[4]  = true;   // FR_thigh (右前-大腿)
        enable_enabled_[5]  = true;   // FR_calf (右前-小腿)
        enable_enabled_[6]  = true;   // RL_hip (左后-髋)
        enable_enabled_[7]  = true;   // RL_thigh (左后-大腿)
        enable_enabled_[8]  = true;   // RL_calf (左后-小腿)
        enable_enabled_[9]  = true;   // RR_hip (右后-髋)
        enable_enabled_[10] = true;   // RR_thigh (右后-大腿)
        enable_enabled_[11] = true;   // RR_calf (右后-小腿)
        // =======================================

        std::vector<std::string> failed_motors;
        for (std::size_t i = 0; i < motors_.size(); ++i)
        {
            if (!enable_enabled_[i]) continue;

            try {
                auto [p, v, tq, temp] = motors_[i].enable_motor();
                last_pos_fb_[i] = p;
                feedback_pos_[i] = p;
                feedback_vel_[i] = v;
                feedback_torque_[i] = tq;
                feedback_temp_[i] = temp;

                // 检查电机返回的错误码
                uint8_t err = motors_[i].error_code;
                if (err != 0) {
                    RCLCPP_WARN(this->get_logger(),
                                "Enable OK but error_code=%u: %-10s (%s, ID=0x%02X)",
                                static_cast<unsigned>(err),
                                joint_names_[i].c_str(),
                                motors_[i].iface.c_str(),
                                static_cast<unsigned>(motors_[i].motor_id));
                }

                RCLCPP_INFO(this->get_logger(),
                            "Enable OK  %-10s hold_zero_only=%d fb_raw=%.3f fb_wrap=%.3f",
                            joint_names_[i].c_str(),
                            static_cast<int>(hold_zero_only_[i]),
                            static_cast<double>(p),
                            static_cast<double>(motor_ros2::controller_helpers::wrap_to_pi(p)));
            } catch (const std::exception &e) {
                RCLCPP_ERROR(this->get_logger(),
                             "Enable FAILED: %-10s (%s, ID=0x%02X) — %s",
                             joint_names_[i].c_str(),
                             motors_[i].iface.c_str(),
                             static_cast<unsigned>(motors_[i].motor_id),
                             e.what());
                enable_enabled_[i] = false;
                failed_motors.push_back(joint_names_[i]);
            }

            usleep(1000);
        }

        // 汇总报告
        {
            int ok_count = 0;
            for (std::size_t i = 0; i < enable_enabled_.size(); ++i) {
                if (enable_enabled_[i]) ++ok_count;
            }
            if (failed_motors.empty()) {
                RCLCPP_INFO(this->get_logger(),
                            "电机启动汇总: 全部成功 (%d/%zu)", ok_count, lm::kJointCount);
            } else {
                std::string failed_list;
                for (std::size_t j = 0; j < failed_motors.size(); ++j) {
                    if (j > 0) failed_list += ", ";
                    failed_list += failed_motors[j];
                }
                RCLCPP_ERROR(this->get_logger(),
                             "电机启动汇总: 成功 %d, 失败 %zu [%s]",
                             ok_count, failed_motors.size(), failed_list.c_str());
            }
        }

        RCLCPP_WARN(
            this->get_logger(),
            "Soft-start: GROUPED parallel ramp to hold target...");
        motor_ros2::controller_helpers::ramp_all_to_targets_grouped(
            motors_, enable_enabled_, last_pos_fb_, hold_target_motor_);
        RCLCPP_WARN(this->get_logger(), "Soft-start done.");

        running_ = true;
        worker_thread_ = std::thread(&MotorControlSample::excute_loop, this);

        RCLCPP_INFO(this->get_logger(), "Controller started.");
    }

    ~MotorControlSample()
    {
        running_ = false;
        if (worker_thread_.joinable()) {
            worker_thread_.join();
        }

        for (std::size_t i = 0; i < motors_.size(); ++i)
        {
            if (enable_enabled_[i]) {
                motors_[i].Disenable_Motor(0);
            }
        }
    }

private:
    enum class Mode { HOLD_TARGET, ACTIVE_FOLLOW };

    struct GaitParams {
        float kp;
        float kd;
        float torque;
        float vel;
    };

    float compute_motor_cmd_target(std::size_t idx, float joint_cmd) const
    {
        const float lo = lm::kJointLimits[idx].min_rad;
        const float hi = lm::kJointLimits[idx].max_rad;
        const float clamped_cmd = motor_ros2::controller_helpers::clampf(joint_cmd, lo, hi);
        return clamped_cmd;
    }

    void build_hold_target_motor()
    {
        // Startup hold target: motor-space target = clamp(0) * sign + offset * sign
        // ★ 电机启动后先到达站立姿态（0位 + 偏移），而不是纯0位
        // ★ offset 在 clamp 之后加，避免 calf 的大偏移值被 joint limits 截断
        hold_target_motor_.fill(0.0f);
        for (std::size_t i = 0; i < lm::kJointCount; ++i) {
            hold_target_motor_[i] =
                compute_motor_cmd_target(i, 0.0f) + lm::kStartupOffset[i];
        }
    }


    void gait_params_cb(const std_msgs::msg::String::SharedPtr msg)
    {
        std::lock_guard<std::mutex> lock(gait_params_mutex_);
        const std::string gait_name = msg ? msg->data : std::string();

        if (gait_name == "STAND") {
            current_gait_params_ = {40.0f, 1.0f, 0.0f, 0.0f};    
        } else if (gait_name == "STEPPING") {
            current_gait_params_ = {80.0f, 2.5f, 0.0f, 0.0f};
        } else if (gait_name == "WALK") {
            current_gait_params_ = {80.0f, 2.5f, 0.0f, 0.0f};
        } else if (gait_name == "TROT") {
            current_gait_params_ = {80.0f, 2.0f, 0.0f, 0.0f};   
        } else if (gait_name == "FAST_TROT") {
            current_gait_params_ = {60.0f, 1.5f, 0.0f, 0.0f};
        }
    }

    void joint_cb(const sensor_msgs::msg::JointState::SharedPtr msg)
    {
        if (!msg) return;
        if (msg->name.size() != msg->position.size()) return;

        {
            std::lock_guard<std::mutex> lk(mtx_);
            for (std::size_t i = 0; i < msg->name.size(); ++i) {
                auto it = name_to_index_.find(msg->name[i]);
                if (it == name_to_index_.end()) continue;

                const std::size_t idx = it->second;
                // ★ policy 端发送的是相对偏移（站立时≈0），直接存储
                //   offset 在 execute_loop 中 clamp 之后再加，避免被 joint limits 截断
                joint_cmd_flat_[idx] = static_cast<float>(msg->position[i]);
                joint_cmd_seen_[idx] = true;
            }
        }

        got_first_js_.store(true);
        last_js_ns_.store(this->now().nanoseconds());
    }

    void publish_motor_feedback()
    {
        dog_control::msg::MotorFeedback msg;
        msg.header.stamp = this->now();
        msg.name = joint_names_;
        msg.position.resize(feedback_pos_.size());
        for (std::size_t i = 0; i < feedback_pos_.size(); ++i) {
            const float motor_wrap = motor_ros2::controller_helpers::wrap_to_pi(feedback_pos_[i]);
            // ★ 减去启动偏移：让发布值在"站立时接近0"，方便 policy 端直接使用
            msg.position[i] = motor_ros2::controller_helpers::wrap_to_pi(motor_wrap - lm::kStartupOffset[i]);
            // msg.position[i] = motor_wrap - lm::kStartupOffset[i];
        }
        msg.velocity.assign(feedback_vel_.begin(), feedback_vel_.end());
        msg.torque.assign(feedback_torque_.begin(), feedback_torque_.end());
        msg.temperature.assign(feedback_temp_.begin(), feedback_temp_.end());
        motor_feedback_pub_->publish(msg);
    }

    void excute_loop()
    {
        const double timeout_s = 0.20;
        const auto loop_period = std::chrono::milliseconds(5);
        auto next_tick = std::chrono::steady_clock::now();
        Mode mode = Mode::HOLD_TARGET;

        // RCLCPP_WARN(this->get_logger(), "控制循环已启动，开始运行...");
        // std::cout << "[DEBUG] 控制循环启动" << std::endl;

        while (running_)
        {
            auto sleep_to_next_tick = [&]() {
                next_tick += loop_period;
                std::this_thread::sleep_until(next_tick);
                const auto now = std::chrono::steady_clock::now();
                if (now > next_tick + loop_period) {
                    next_tick = now;
                }
            };

            const bool got = got_first_js_.load();
            const int64_t now_ns  = this->now().nanoseconds();
            const int64_t last_ns = last_js_ns_.load();
            const double dt = (now_ns - last_ns) / 1e9;
            const bool js_ok = got && (dt <= timeout_s);

            if (js_ok && mode != Mode::ACTIVE_FOLLOW)
            {
                mode = Mode::ACTIVE_FOLLOW;
                // RCLCPP_WARN(this->get_logger(), "joint_states OK -> ACTIVE_FOLLOW (kp=%.1f, kd=%.1f)",
                //             current_gait_params_.kp, current_gait_params_.kd);
            }
            if (!js_ok && mode != Mode::HOLD_TARGET)
            {
                mode = Mode::HOLD_TARGET;
                // RCLCPP_WARN(this->get_logger(), "joint_states timeout -> HOLD_TARGET (grouped ramp to configured hold target)");
                motor_ros2::controller_helpers::ramp_all_to_targets_grouped(
                    motors_, enable_enabled_, last_pos_fb_, hold_target_motor_);
            }

            if (mode == Mode::HOLD_TARGET)
            {
                publish_motor_feedback();
                sleep_to_next_tick();
                continue;
            }

            std::array<float, lm::kJointCount> cmd_flat_snapshot{};
            std::array<bool, lm::kJointCount> cmd_seen_snapshot{};
            {
                std::lock_guard<std::mutex> lk(mtx_);
                cmd_flat_snapshot = joint_cmd_flat_;
                cmd_seen_snapshot = joint_cmd_seen_;
            }
            const lm::QuadJoints<float> cmd_quad = lm::unflatten(cmd_flat_snapshot);

            for (std::size_t li = 0; li < lm::kLegCount; ++li)
            {
                const lm::LegId leg = static_cast<lm::LegId>(li);
                for (std::size_t ji = 0; ji < lm::kJointsPerLeg; ++ji)
                {
                    const lm::JointId joint = static_cast<lm::JointId>(ji);
                    const std::size_t idx = lm::flat_index(leg, joint);

                    if (!enable_enabled_[idx]) continue;
                    if (hold_zero_only_[idx]) continue;

                    if (!cmd_seen_snapshot[idx]) {
                        // RCLCPP_WARN_THROTTLE(this->get_logger(), *this->get_clock(), 1000,
                        //     "未找到关节 %s 的缓存数据", lm::kJointNames[idx]);
                        continue;
                    }

                    const float cmd_joint = cmd_quad.at(leg).at(joint);
                    // ★ clamp(偏差) * sign + offset * sign = 完整电机目标
                    //   offset 在 clamp 之后加，避免 calf 的大偏移值被截断
                    const float cmd = compute_motor_cmd_target(idx, cmd_joint)
                                     + lm::kStartupOffset[idx];

                    const float cmd_send = motor_ros2::controller_helpers::nearest_equivalent(cmd, last_pos_fb_[idx]);

                    // ★ calf 关节 (idx%3==2) 有 2:1 减速比：
                    //   电机空间 PD 误差 = 2×关节误差，力矩经减速器放大 2×
                    //   等效关节 kp = 4×kp_motor，所以要除以 4 才能匹配仿真
                    constexpr float kCalfGearRatio = 2.0f;
                    constexpr float kCalfGainScale = 1.0f / (kCalfGearRatio * kCalfGearRatio);  // 0.25
                    const bool is_calf = (joint == lm::JointId::J3);
                    const float kp = current_gait_params_.kp * (is_calf ? kCalfGainScale : 1.0f);
                    const float kd = current_gait_params_.kd * (is_calf ? kCalfGainScale : 1.0f);
                    const float torque = current_gait_params_.torque;
                    const float vel = current_gait_params_.vel;

                    auto [pos_fb, vel_fb, tq, temp] =
                        motors_[idx].send_motion_command(torque, cmd_send, vel, kp, kd);

                    last_pos_fb_[idx] = pos_fb;
                    feedback_pos_[idx] = pos_fb;
                    feedback_vel_[idx] = vel_fb;
                    feedback_torque_[idx] = tq;
                    feedback_temp_[idx] = temp;
                }
            }

            publish_motor_feedback();
            sleep_to_next_tick();
        }
    }

private:
    std::thread worker_thread_;
    std::atomic<bool> running_{false};

    std::array<RobStrideMotor, lm::kJointCount> motors_;
    std::vector<std::string> joint_names_;

    std::array<float, lm::kJointCount> last_pos_fb_{};
    std::array<float, lm::kJointCount> feedback_pos_{};
    std::array<float, lm::kJointCount> feedback_vel_{};
    std::array<float, lm::kJointCount> feedback_torque_{};
    std::array<float, lm::kJointCount> feedback_temp_{};

    std::array<bool, lm::kJointCount> enable_enabled_{};
    std::array<bool, lm::kJointCount> hold_zero_only_{};
    std::array<float, lm::kJointCount> hold_target_motor_{};

    std::array<float, lm::kJointCount> joint_cmd_flat_{};
    std::array<bool, lm::kJointCount> joint_cmd_seen_{};
    std::unordered_map<std::string, std::size_t> name_to_index_;

    rclcpp::Subscription<sensor_msgs::msg::JointState>::SharedPtr joint_sub_;
    rclcpp::Subscription<std_msgs::msg::String>::SharedPtr gait_params_sub_;
    rclcpp::Subscription<std_msgs::msg::Bool>::SharedPtr emergency_stop_sub_;
    rclcpp::Publisher<dog_control::msg::MotorFeedback>::SharedPtr motor_feedback_pub_;

    GaitParams current_gait_params_{40.0f, 1.0f, 0.0f, 0.0f};
    std::mutex gait_params_mutex_;

    std::mutex mtx_;
    std::atomic<bool> got_first_js_{false};
    std::atomic<int64_t> last_js_ns_{0};
};

int main(int argc, char **argv)
{
    rclcpp::init(argc, argv);
    rclcpp::spin(std::make_shared<MotorControlSample>());
    rclcpp::shutdown();
    return 0;
}
