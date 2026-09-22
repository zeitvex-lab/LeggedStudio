#pragma once

namespace zy {
struct ClosedAnkleWristParam {
  int ankle_motor1_direction = 1;  // 1: forward, -1: reverse
  int ankle_motor2_direction = 1;  // 1: forward, -1: reverse

  int ankle_pitch_direction = 1;  // 1: forward, -1: reverse
  int ankle_roll_direction = 1;   // 1: forward, -1: reverse

  double ankle_d = 0.0315;              // m
  double ankle_l = 0.063;               // m
  double ankle_h1 = 0.239;              // m
  double ankle_h2 = 0.145;              // m
  double ankle_actuator_pos_limit = 1;  // unit: rad
  double ankle_pitch_limit = 1;         // unit: rad
  double ankle_roll_limit = 0.5;        // unit: rad
};
}  // namespace zy