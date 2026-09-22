// Copyright (c) 2025, AgiBot Inc.
// All rights reserved.

#include "std_msgs/msg/bool.hpp"
#include "std_msgs/msg/byte.hpp"
#include "std_msgs/msg/byte_multi_array.hpp"
#include "std_msgs/msg/char.hpp"
#include "std_msgs/msg/color_rgba.hpp"
#include "std_msgs/msg/empty.hpp"
#include "std_msgs/msg/float32.hpp"
#include "std_msgs/msg/float32_multi_array.hpp"
#include "std_msgs/msg/float64.hpp"
#include "std_msgs/msg/float64_multi_array.hpp"
#include "std_msgs/msg/header.hpp"
#include "std_msgs/msg/int16.hpp"
#include "std_msgs/msg/int16_multi_array.hpp"
#include "std_msgs/msg/int32.hpp"
#include "std_msgs/msg/int32_multi_array.hpp"
#include "std_msgs/msg/int64.hpp"
#include "std_msgs/msg/int64_multi_array.hpp"
#include "std_msgs/msg/int8.hpp"
#include "std_msgs/msg/int8_multi_array.hpp"
#include "std_msgs/msg/multi_array_dimension.hpp"
#include "std_msgs/msg/multi_array_layout.hpp"
#include "std_msgs/msg/string.hpp"
#include "std_msgs/msg/u_int16.hpp"
#include "std_msgs/msg/u_int16_multi_array.hpp"
#include "std_msgs/msg/u_int32.hpp"
#include "std_msgs/msg/u_int32_multi_array.hpp"
#include "std_msgs/msg/u_int64.hpp"
#include "std_msgs/msg/u_int64_multi_array.hpp"
#include "std_msgs/msg/u_int8.hpp"
#include "std_msgs/msg/u_int8_multi_array.hpp"

// sensor_msgs includes
#include "sensor_msgs/msg/battery_state.hpp"
#include "sensor_msgs/msg/camera_info.hpp"
#include "sensor_msgs/msg/channel_float32.hpp"
#include "sensor_msgs/msg/compressed_image.hpp"
#include "sensor_msgs/msg/fluid_pressure.hpp"
#include "sensor_msgs/msg/illuminance.hpp"
#include "sensor_msgs/msg/image.hpp"
#include "sensor_msgs/msg/imu.hpp"
#include "sensor_msgs/msg/joint_state.hpp"
#include "sensor_msgs/msg/joy_feedback_array.hpp"
#include "sensor_msgs/msg/joy_feedback.hpp"
#include "sensor_msgs/msg/joy.hpp"
#include "sensor_msgs/msg/laser_echo.hpp"
#include "sensor_msgs/msg/laser_scan.hpp"
#include "sensor_msgs/msg/magnetic_field.hpp"
#include "sensor_msgs/msg/multi_dof_joint_state.hpp"
#include "sensor_msgs/msg/multi_echo_laser_scan.hpp"
#include "sensor_msgs/msg/nav_sat_fix.hpp"
#include "sensor_msgs/msg/nav_sat_status.hpp"
#include "sensor_msgs/msg/point_cloud2.hpp"
#include "sensor_msgs/msg/point_cloud.hpp"
#include "sensor_msgs/msg/point_field.hpp"
#include "sensor_msgs/msg/range.hpp"
#include "sensor_msgs/msg/region_of_interest.hpp"
#include "sensor_msgs/msg/relative_humidity.hpp"
#include "sensor_msgs/msg/temperature.hpp"
#include "sensor_msgs/msg/time_reference.hpp"

// nav_msgs includes
#include "nav_msgs/msg/grid_cells.hpp"
#include "nav_msgs/msg/map_meta_data.hpp"
#include "nav_msgs/msg/occupancy_grid.hpp"
#include "nav_msgs/msg/odometry.hpp"
#include "nav_msgs/msg/path.hpp"

//geometry_msgs includes
#include "geometry_msgs/msg/accel.hpp"
#include "geometry_msgs/msg/accel_stamped.hpp"
#include "geometry_msgs/msg/accel_with_covariance.hpp"
#include "geometry_msgs/msg/accel_with_covariance_stamped.hpp"
#include "geometry_msgs/msg/inertia.hpp"
#include "geometry_msgs/msg/inertia_stamped.hpp"
#include "geometry_msgs/msg/point32.hpp"
#include "geometry_msgs/msg/point.hpp"
#include "geometry_msgs/msg/point_stamped.hpp"
#include "geometry_msgs/msg/polygon.hpp"
#include "geometry_msgs/msg/polygon_stamped.hpp"
#include "geometry_msgs/msg/pose2_d.hpp"
#include "geometry_msgs/msg/pose_array.hpp"
#include "geometry_msgs/msg/pose.hpp"
#include "geometry_msgs/msg/pose_stamped.hpp"
#include "geometry_msgs/msg/pose_with_covariance.hpp"
#include "geometry_msgs/msg/pose_with_covariance_stamped.hpp"
#include "geometry_msgs/msg/quaternion.hpp"
#include "geometry_msgs/msg/quaternion_stamped.hpp"
#include "geometry_msgs/msg/transform.hpp"
#include "geometry_msgs/msg/transform_stamped.hpp"
#include "geometry_msgs/msg/twist.hpp"
#include "geometry_msgs/msg/twist_stamped.hpp"
#include "geometry_msgs/msg/twist_with_covariance.hpp"
#include "geometry_msgs/msg/twist_with_covariance_stamped.hpp"
#include "geometry_msgs/msg/vector3.hpp"
#include "geometry_msgs/msg/vector3_stamped.hpp"
#include "geometry_msgs/msg/wrench.hpp"
#include "geometry_msgs/msg/wrench_stamped.hpp"

// tf2_msgs includes
#include "tf2_msgs/msg/tf_message.hpp"
#include "tf2_msgs/msg/tf2_error.hpp"


// visualization_msgs
#include <visualization_msgs/msg/image_marker.hpp>
#include <visualization_msgs/msg/interactive_marker_control.hpp>
#include <visualization_msgs/msg/interactive_marker_feedback.hpp>
#include <visualization_msgs/msg/interactive_marker.hpp>
#include <visualization_msgs/msg/interactive_marker_init.hpp>
#include <visualization_msgs/msg/interactive_marker_pose.hpp>
#include <visualization_msgs/msg/interactive_marker_update.hpp>
#include <visualization_msgs/msg/marker_array.hpp>
#include <visualization_msgs/msg/marker.hpp>
#include <visualization_msgs/msg/menu_entry.hpp>
#include <visualization_msgs/msg/mesh_file.hpp>
#include <visualization_msgs/msg/uv_coordinate.hpp>

// map msgs
#include <map_msgs/msg/occupancy_grid_update.hpp>
#include <map_msgs/msg/point_cloud2_update.hpp>
#include <map_msgs/msg/projected_map.hpp>
#include <map_msgs/msg/projected_map_info.hpp>

// other msgs
#include "src/protocols/plugins/topic_logger_plugin/topic_logger.pb.h"
#include "aimrt_type_support_pkg_c_interface/type_support_pkg_main.h"
#include "src/interface/aimrt_module_ros2_interface/util/ros2_type_support.h"
#include "src/interface/aimrt_module_protobuf_interface/util/protobuf_type_support.h"


static const aimrt_type_support_base_t* type_support_array[]{
  // std_msgs
  aimrt::GetRos2MessageTypeSupport<std_msgs::msg::String>(),
  aimrt::GetRos2MessageTypeSupport<std_msgs::msg::Bool>(),
  aimrt::GetRos2MessageTypeSupport<std_msgs::msg::Byte>(),
  aimrt::GetRos2MessageTypeSupport<std_msgs::msg::ByteMultiArray>(),
  aimrt::GetRos2MessageTypeSupport<std_msgs::msg::Char>(),
  aimrt::GetRos2MessageTypeSupport<std_msgs::msg::ColorRGBA>(),
  aimrt::GetRos2MessageTypeSupport<std_msgs::msg::Empty>(),
  aimrt::GetRos2MessageTypeSupport<std_msgs::msg::Float32>(),
  aimrt::GetRos2MessageTypeSupport<std_msgs::msg::Float32MultiArray>(),
  aimrt::GetRos2MessageTypeSupport<std_msgs::msg::Float64>(),
  aimrt::GetRos2MessageTypeSupport<std_msgs::msg::Float64MultiArray>(),
  aimrt::GetRos2MessageTypeSupport<std_msgs::msg::Header>(),
  aimrt::GetRos2MessageTypeSupport<std_msgs::msg::Int16>(),
  aimrt::GetRos2MessageTypeSupport<std_msgs::msg::Int16MultiArray>(),
  aimrt::GetRos2MessageTypeSupport<std_msgs::msg::Int32>(),
  aimrt::GetRos2MessageTypeSupport<std_msgs::msg::Int32MultiArray>(),
  aimrt::GetRos2MessageTypeSupport<std_msgs::msg::Int64>(),
  aimrt::GetRos2MessageTypeSupport<std_msgs::msg::Int64MultiArray>(),
  aimrt::GetRos2MessageTypeSupport<std_msgs::msg::Int8>(),
  aimrt::GetRos2MessageTypeSupport<std_msgs::msg::Int8MultiArray>(),
  aimrt::GetRos2MessageTypeSupport<std_msgs::msg::MultiArrayDimension>(),
  aimrt::GetRos2MessageTypeSupport<std_msgs::msg::MultiArrayLayout>(),
  aimrt::GetRos2MessageTypeSupport<std_msgs::msg::UInt16>(),
  aimrt::GetRos2MessageTypeSupport<std_msgs::msg::UInt16MultiArray>(),
  aimrt::GetRos2MessageTypeSupport<std_msgs::msg::UInt32>(),
  aimrt::GetRos2MessageTypeSupport<std_msgs::msg::UInt32MultiArray>(),
  aimrt::GetRos2MessageTypeSupport<std_msgs::msg::UInt64>(),
  aimrt::GetRos2MessageTypeSupport<std_msgs::msg::UInt64MultiArray>(),
  aimrt::GetRos2MessageTypeSupport<std_msgs::msg::UInt8>(),
  aimrt::GetRos2MessageTypeSupport<std_msgs::msg::UInt8MultiArray>(),

  // sensor_msgs
  aimrt::GetRos2MessageTypeSupport<sensor_msgs::msg::BatteryState>(),
  aimrt::GetRos2MessageTypeSupport<sensor_msgs::msg::CameraInfo>(),
  aimrt::GetRos2MessageTypeSupport<sensor_msgs::msg::ChannelFloat32>(),
  aimrt::GetRos2MessageTypeSupport<sensor_msgs::msg::CompressedImage>(),
  aimrt::GetRos2MessageTypeSupport<sensor_msgs::msg::FluidPressure>(),
  aimrt::GetRos2MessageTypeSupport<sensor_msgs::msg::Illuminance>(),
  aimrt::GetRos2MessageTypeSupport<sensor_msgs::msg::Image>(),
  aimrt::GetRos2MessageTypeSupport<sensor_msgs::msg::Imu>(),
  aimrt::GetRos2MessageTypeSupport<sensor_msgs::msg::JointState>(),
  aimrt::GetRos2MessageTypeSupport<sensor_msgs::msg::JoyFeedbackArray>(),
  aimrt::GetRos2MessageTypeSupport<sensor_msgs::msg::JoyFeedback>(),
  aimrt::GetRos2MessageTypeSupport<sensor_msgs::msg::Joy>(),
  aimrt::GetRos2MessageTypeSupport<sensor_msgs::msg::LaserEcho>(),
  aimrt::GetRos2MessageTypeSupport<sensor_msgs::msg::LaserScan>(),
  aimrt::GetRos2MessageTypeSupport<sensor_msgs::msg::MagneticField>(),
  aimrt::GetRos2MessageTypeSupport<sensor_msgs::msg::MultiDOFJointState>(),
  aimrt::GetRos2MessageTypeSupport<sensor_msgs::msg::MultiEchoLaserScan>(),
  aimrt::GetRos2MessageTypeSupport<sensor_msgs::msg::NavSatFix>(),
  aimrt::GetRos2MessageTypeSupport<sensor_msgs::msg::NavSatStatus>(),
  aimrt::GetRos2MessageTypeSupport<sensor_msgs::msg::PointCloud2>(),
  aimrt::GetRos2MessageTypeSupport<sensor_msgs::msg::PointCloud>(),
  aimrt::GetRos2MessageTypeSupport<sensor_msgs::msg::PointField>(),
  aimrt::GetRos2MessageTypeSupport<sensor_msgs::msg::Range>(),
  aimrt::GetRos2MessageTypeSupport<sensor_msgs::msg::RegionOfInterest>(),
  aimrt::GetRos2MessageTypeSupport<sensor_msgs::msg::RelativeHumidity>(),
  aimrt::GetRos2MessageTypeSupport<sensor_msgs::msg::Temperature>(),
  aimrt::GetRos2MessageTypeSupport<sensor_msgs::msg::TimeReference>(),

  // nav_msgs
  aimrt::GetRos2MessageTypeSupport<nav_msgs::msg::GridCells>(),
  aimrt::GetRos2MessageTypeSupport<nav_msgs::msg::MapMetaData>(),
  aimrt::GetRos2MessageTypeSupport<nav_msgs::msg::OccupancyGrid>(),
  aimrt::GetRos2MessageTypeSupport<nav_msgs::msg::Odometry>(),
  aimrt::GetRos2MessageTypeSupport<nav_msgs::msg::Path>(),

  //geometry_msgs
  aimrt::GetRos2MessageTypeSupport<geometry_msgs::msg::Accel>(),
  aimrt::GetRos2MessageTypeSupport<geometry_msgs::msg::AccelStamped>(),
  aimrt::GetRos2MessageTypeSupport<geometry_msgs::msg::AccelWithCovariance>(),
  aimrt::GetRos2MessageTypeSupport<geometry_msgs::msg::AccelWithCovarianceStamped>(),
  aimrt::GetRos2MessageTypeSupport<geometry_msgs::msg::Inertia>(),
  aimrt::GetRos2MessageTypeSupport<geometry_msgs::msg::InertiaStamped>(),
  aimrt::GetRos2MessageTypeSupport<geometry_msgs::msg::Point32>(),
  aimrt::GetRos2MessageTypeSupport<geometry_msgs::msg::Point>(),
  aimrt::GetRos2MessageTypeSupport<geometry_msgs::msg::PointStamped>(),
  aimrt::GetRos2MessageTypeSupport<geometry_msgs::msg::Polygon>(),
  aimrt::GetRos2MessageTypeSupport<geometry_msgs::msg::PolygonStamped>(),
  aimrt::GetRos2MessageTypeSupport<geometry_msgs::msg::Pose2D>(),
  aimrt::GetRos2MessageTypeSupport<geometry_msgs::msg::PoseArray>(),
  aimrt::GetRos2MessageTypeSupport<geometry_msgs::msg::Pose>(),
  aimrt::GetRos2MessageTypeSupport<geometry_msgs::msg::PoseStamped>(),
  aimrt::GetRos2MessageTypeSupport<geometry_msgs::msg::PoseWithCovariance>(),
  aimrt::GetRos2MessageTypeSupport<geometry_msgs::msg::PoseWithCovarianceStamped>(),
  aimrt::GetRos2MessageTypeSupport<geometry_msgs::msg::Quaternion>(),
  aimrt::GetRos2MessageTypeSupport<geometry_msgs::msg::QuaternionStamped>(),
  aimrt::GetRos2MessageTypeSupport<geometry_msgs::msg::Transform>(),
  aimrt::GetRos2MessageTypeSupport<geometry_msgs::msg::TransformStamped>(),
  aimrt::GetRos2MessageTypeSupport<geometry_msgs::msg::Twist>(),
  aimrt::GetRos2MessageTypeSupport<geometry_msgs::msg::TwistStamped>(),
  aimrt::GetRos2MessageTypeSupport<geometry_msgs::msg::TwistWithCovariance>(),
  aimrt::GetRos2MessageTypeSupport<geometry_msgs::msg::TwistWithCovarianceStamped>(),
  aimrt::GetRos2MessageTypeSupport<geometry_msgs::msg::Vector3>(),
  aimrt::GetRos2MessageTypeSupport<geometry_msgs::msg::Vector3Stamped>(),
  // 不同版本ros2的接口有所不同，暂时注释掉
  // aimrt::GetRos2MessageTypeSupport<geometry_msgs::msg::VelocityStamped>(),
  aimrt::GetRos2MessageTypeSupport<geometry_msgs::msg::Wrench>(),
  aimrt::GetRos2MessageTypeSupport<geometry_msgs::msg::WrenchStamped>(),

  // tf2_msgs
  aimrt::GetRos2MessageTypeSupport<tf2_msgs::msg::TFMessage>(),
  aimrt::GetRos2MessageTypeSupport<tf2_msgs::msg::TF2Error>(),

  // visualization_msgs
  aimrt::GetRos2MessageTypeSupport<visualization_msgs::msg::ImageMarker>(),
  aimrt::GetRos2MessageTypeSupport<visualization_msgs::msg::InteractiveMarkerControl>(),
  aimrt::GetRos2MessageTypeSupport<visualization_msgs::msg::InteractiveMarkerFeedback>(),
  aimrt::GetRos2MessageTypeSupport<visualization_msgs::msg::InteractiveMarker>(),
  aimrt::GetRos2MessageTypeSupport<visualization_msgs::msg::InteractiveMarkerInit>(),
  aimrt::GetRos2MessageTypeSupport<visualization_msgs::msg::InteractiveMarkerPose>(),
  aimrt::GetRos2MessageTypeSupport<visualization_msgs::msg::InteractiveMarkerUpdate>(),
  aimrt::GetRos2MessageTypeSupport<visualization_msgs::msg::MarkerArray>(),
  aimrt::GetRos2MessageTypeSupport<visualization_msgs::msg::Marker>(),
  aimrt::GetRos2MessageTypeSupport<visualization_msgs::msg::MenuEntry>(),
  aimrt::GetRos2MessageTypeSupport<visualization_msgs::msg::MeshFile>(),
  aimrt::GetRos2MessageTypeSupport<visualization_msgs::msg::UVCoordinate>(),
  // map msgs
  aimrt::GetRos2MessageTypeSupport<map_msgs::msg::OccupancyGridUpdate>(),
  aimrt::GetRos2MessageTypeSupport<map_msgs::msg::PointCloud2Update>(),
  aimrt::GetRos2MessageTypeSupport<map_msgs::msg::ProjectedMapInfo>(),
  aimrt::GetRos2MessageTypeSupport<map_msgs::msg::ProjectedMap>(),
  // other msgs
  aimrt::GetProtobufMessageTypeSupport<aimrt::protocols::topic_logger::LogData>(),
};

extern "C" {

  size_t AimRTDynlibGetTypeSupportArrayLength() {
    return sizeof(type_support_array) / sizeof(type_support_array[0]);
  }

  const aimrt_type_support_base_t** AimRTDynlibGetTypeSupportArray() {
    return type_support_array;
  }
}
