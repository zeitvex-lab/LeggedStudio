#include "rl_controllers/Utilities.h"

namespace legged {

std_msgs::msg::Float64MultiArray createFloat64MultiArrayFromVector(const vector_t& data) {
  std_msgs::msg::Float64MultiArray msg;
  msg.data.resize(data.size());
  // copy data from eigen vector to std vector
  vector_t::Map(&msg.data[0], data.size()) = data;
  return msg;
}

}  // namespace legged