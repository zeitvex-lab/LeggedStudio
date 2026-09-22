#pragma once

#include <Eigen/Dense>
#include <cmath>

namespace zy {
/*
 * refer to https://github.com/HuNingHe/closed_loop_ankle/tree/main
 */
class LoopAnkleAnalyticalSolver {
 public:
  EIGEN_MAKE_ALIGNED_OPERATOR_NEW
  LoopAnkleAnalyticalSolver();

  ~LoopAnkleAnalyticalSolver() = default;

  void SetLinkLength(double dd, double ll1, double hh1, double hh2) {
    d = dd;
    l1 = ll1;
    h1 = hh1;
    h2 = hh2;
  }

  /*!
   * by hhn
   * @param pr pitch and roll of ankle
   * @return motor configuration
   */
  Eigen::Vector2d IK(const Eigen::Vector2d& pr);

  /*!
   * by hhn
   * @param mc motor configuration
   * @return pitch and roll of ankle
   */
  Eigen::Vector2d FK(const Eigen::Vector2d& mc);

  /*!
   * by hhn
   * @param mc motor configuration
   * update j1
   */
  void UpdateJ1(const Eigen::Vector2d& mc);

  /*!
   * by hhn
   * call before UpdateJ1
   * @param vel_pr velocity of ankle pitch roll
   * @return velocity of motors
   */
  Eigen::Vector2d DIK(const Eigen::Vector2d& vel_pr) { return j1.inverse() * vel_pr; }

  /*!
   * by hhn
   * call before UpdateJ1
   * @param vel_m velocity of motors
   * @return velocity of ankle pitch roll
   */
  Eigen::Vector2d DFK(const Eigen::Vector2d& vel_m) { return j1 * vel_m; }

  /*!
   * by hhn
   * call before UpdateJ1
   * @param tau_m torque of motors
   * @return torque of ankle pitch roll
   */
  Eigen::Vector2d FDyn(const Eigen::Vector2d& tau_m) {
    auto j2 = j1.inverse();
    return j2.transpose() * tau_m;
  }

  /*!
   * by hhn
   * call before UpdateJ1
   * @param tau_m torque of ankle pitch and roll joint
   * @return torque of motors
   */
  Eigen::Vector2d IDyn(const Eigen::Vector2d& tau_pr) { return j1.transpose() * tau_pr; }

 private:
  double CalculateTxML(const Eigen::Vector2d& mc);

  double CalculateTxMR(const Eigen::Vector2d& mc);

  Eigen::Matrix2d j1;

  double d = 0.0315;
  double l1 = 0.062992;
  double h1 = 0.145;
  double h2 = 0.239;
};
}  // namespace zy