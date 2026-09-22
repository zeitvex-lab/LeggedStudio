#pragma once

#include "Types.h"

#include "std_msgs/msg/float64_multi_array.hpp"

namespace legged {

std_msgs::msg::Float64MultiArray createFloat64MultiArrayFromVector(const vector_t& data);

}