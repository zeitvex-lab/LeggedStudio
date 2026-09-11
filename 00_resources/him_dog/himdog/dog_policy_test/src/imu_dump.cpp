// 简单节点：订阅 /imu/data，打印四元数、角速度、重力投影向量
#include <rclcpp/rclcpp.hpp>
#include <sensor_msgs/msg/imu.hpp>
#include <cmath>
#include <iomanip>
#include <sstream>

class ImuDump : public rclcpp::Node
{
public:
  ImuDump()
  : Node("imu_dump")
  {
    sub_ = this->create_subscription<sensor_msgs::msg::Imu>(
      "/imu/data", 10,
      std::bind(&ImuDump::callback, this, std::placeholders::_1));

    RCLCPP_INFO(this->get_logger(), "imu_dump started — listening to /imu/data");
  }

private:
  // 将世界坐标系向量旋转到机体坐标系（quat_rotate_inverse）
  std::array<double, 3> RotateWorldToBody(
    const std::array<double, 4> & q,  // [w, x, y, z]
    const std::array<double, 3> & v)
  {
    const double w = q[0], x = q[1], y = q[2], z = q[3];
    const double r00 = 1.0 - 2.0 * (y * y + z * z);
    const double r01 = 2.0 * (x * y - z * w);
    const double r02 = 2.0 * (x * z + y * w);
    const double r10 = 2.0 * (x * y + z * w);
    const double r11 = 1.0 - 2.0 * (x * x + z * z);
    const double r12 = 2.0 * (y * z - x * w);
    const double r20 = 2.0 * (x * z - y * w);
    const double r21 = 2.0 * (y * z + x * w);
    const double r22 = 1.0 - 2.0 * (x * x + y * y);
    return {
      r00 * v[0] + r01 * v[1] + r02 * v[2],
      r10 * v[0] + r11 * v[1] + r12 * v[2],
      r20 * v[0] + r21 * v[1] + r22 * v[2]
    };
  }

  void callback(const sensor_msgs::msg::Imu::SharedPtr msg)
  {
    // 四元数 [w, x, y, z]
    const double qw = msg->orientation.w;
    const double qx = msg->orientation.x;
    const double qy = msg->orientation.y;
    const double qz = msg->orientation.z;

    // 角速度 [wx, wy, wz] rad/s
    const double wx = msg->angular_velocity.x;
    const double wy = msg->angular_velocity.y;
    const double wz = msg->angular_velocity.z;

    // 重力投影向量：世界系 [0, 0, -1] 旋转到机体系
    auto grav = RotateWorldToBody({qw, qx, qy, qz}, {0.0, 0.0, -1.0});

    // 四元数模长（应该接近1.0）
    double q_norm = std::sqrt(qw * qw + qx * qx + qy * qy + qz * qz);

    std::ostringstream oss;
    oss << std::fixed << std::setprecision(6);

    oss << "\n======== /imu/data (count=" << ++count_ << ") ========\n";

    oss << "  quaternion (w,x,y,z): ["
        << std::setw(9) << qw << ", "
        << std::setw(9) << qx << ", "
        << std::setw(9) << qy << ", "
        << std::setw(9) << qz << "]  norm=" << std::setprecision(4) << q_norm << "\n";

    oss << "  angular_vel  (x,y,z): ["
        << std::setw(9) << wx << ", "
        << std::setw(9) << wy << ", "
        << std::setw(9) << wz << "]\n";

    oss << "  projected_gravity     : ["
        << std::setw(9) << grav[0] << ", "
        << std::setw(9) << grav[1] << ", "
        << std::setw(9) << grav[2] << "]\n";

    oss << "=================================================";
    RCLCPP_INFO(this->get_logger(), "%s", oss.str().c_str());
  }

  rclcpp::Subscription<sensor_msgs::msg::Imu>::SharedPtr sub_;
  std::size_t count_{0};
};

int main(int argc, char ** argv)
{
  rclcpp::init(argc, argv);
  rclcpp::spin(std::make_shared<ImuDump>());
  rclcpp::shutdown();
  return 0;
}