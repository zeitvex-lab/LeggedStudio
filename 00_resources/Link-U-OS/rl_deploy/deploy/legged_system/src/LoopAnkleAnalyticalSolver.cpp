#include "LoopAnkleAnalyticalSolver.h"

using namespace zy;

double LoopAnkleAnalyticalSolver::CalculateTxML(const Eigen::Vector2d& mc) {
  double tML = mc[0];
  double tMR = mc[1];

  if (std::abs(tML) > 1.52) {
    tML = (tML / std::abs(tML)) * 1.52;
  }

  if (std::abs(tMR) > 1.52) {
    tMR = (tMR / std::abs(tMR)) * 1.52;
  }

  static double pre_result = 0;

  double b_t19_tmp;
  double t12;
  double t14;
  double t15;
  double t17;
  double t19;
  double t19_tmp;
  double t5;
  double tXtML_tmp;

  t5 = 1.0 / d;
  t12 = 1.0 / (h1 + h2);
  t14 = tML / 2.0 + tMR / 2.0;
  t15 = std::cos(t14);
  t14 = std::sin(t14);
  t17 = 1.0 / (t15 * t15);
  t19_tmp = l1 * (h1 - h2);
  b_t19_tmp = l1 * h1;
  t19 = (l1 * h2 * std::sin(tMR) - b_t19_tmp * std::sin(tML)) + t19_tmp * t14;
  tXtML_tmp = t5 * t12;

  double result = -1.0 / std::sqrt(-(t5 * t5) * (t12 * t12) * t17 * (t19 * t19) + 1.0) *
                  (tXtML_tmp * (t19_tmp * t15 / 2.0 - b_t19_tmp * std::cos(tML)) / t15 + tXtML_tmp * t14 * t17 * t19 / 2.0);
  if (std::isnan(result)) {
    result = pre_result;
  } else {
    pre_result = result;
  }
  return result;
}

double LoopAnkleAnalyticalSolver::CalculateTxMR(const Eigen::Vector2d& mc) {
  double tML = mc[0];
  double tMR = mc[1];

  if (std::abs(tML) > 1.52) {
    tML = (tML / std::abs(tML)) * 1.52;
  }

  if (std::abs(tMR) > 1.52) {
    tMR = (tMR / std::abs(tMR)) * 1.52;
  }

  static double pre_result = 0;

  double b_t19_tmp;
  double t12;
  double t14;
  double t15;
  double t17;
  double t19;
  double t19_tmp;
  double t5;
  double tXtMR_tmp;

  t5 = 1.0 / d;
  t12 = 1.0 / (h1 + h2);
  t14 = tML / 2.0 + tMR / 2.0;
  t15 = std::cos(t14);
  t14 = std::sin(t14);
  t17 = 1.0 / (t15 * t15);
  t19_tmp = l1 * (h1 - h2);
  b_t19_tmp = l1 * h2;
  t19 = (b_t19_tmp * std::sin(tMR) - l1 * h1 * std::sin(tML)) + t19_tmp * t14;
  tXtMR_tmp = t5 * t12;

  double result = -1.0 / std::sqrt(-(t5 * t5) * (t12 * t12) * t17 * (t19 * t19) + 1.0) *
                  (tXtMR_tmp * (t19_tmp * t15 / 2.0 + b_t19_tmp * std::cos(tMR)) / t15 + tXtMR_tmp * t14 * t17 * t19 / 2.0);
  if (std::isnan(result)) {
    result = pre_result;
  } else {
    pre_result = result;
  }
  return result;
}

LoopAnkleAnalyticalSolver::LoopAnkleAnalyticalSolver() {
  j1 = Eigen::Matrix2d::Identity();

  d = 0.0315;
  l1 = 0.062992;
  h1 = 0.145;
  h2 = 0.239;
}

Eigen::Vector2d LoopAnkleAnalyticalSolver::IK(const Eigen::Vector2d& pr) {
  double tx = pr[1];
  double ty = pr[0];

  double cx = cos(tx);
  double sx = sin(tx);
  double cy = cos(ty);
  double sy = sin(ty);

  double AL = -l1 * l1 * cy + l1 * d * sx * sy;
  double BL = -l1 * l1 * sy + l1 * h1 - l1 * d * sx * cy;
  double CL = -(l1 * l1 + d * d - d * d * cx - l1 * h1 * sy - d * h1 * sx * cy);
  double LenL = sqrt(AL * AL + BL * BL);

  double AR = -l1 * l1 * cy - l1 * d * sx * sy;
  double BR = -l1 * l1 * sy + l1 * h2 + l1 * d * sx * cy;
  double CR = -(l1 * l1 + d * d - d * d * cx - l1 * h2 * sy + d * h2 * sx * cy);
  double LenR = sqrt(AR * AR + BR * BR);

  if (LenL <= abs(CL) || LenR <= abs(CR)) {
    return {0.0, 0.0};
  } else {
    double tL_1 = asin(CL / LenL) - asin(AL / LenL);
    double tR_1 = asin(CR / LenR) - asin(AR / LenR);
    return {tL_1, tR_1};
  }
}

Eigen::Vector2d LoopAnkleAnalyticalSolver::FK(const Eigen::Vector2d& mc) {
  double mL = mc[0];
  double mR = mc[1];

  double halfSumAngles = (mL / 2.0) + (mR / 2.0);
  double sinHalfSum = std::sin(halfSumAngles);
  double cosHalfSum = std::cos(halfSumAngles);

  double numerator = l1 * (h2 - h1) * sinHalfSum + l1 * h1 * std::sin(mL) - l1 * h2 * std::sin(mR);

  double denominator = d * (h1 + h2) * cosHalfSum;

  if (std::abs(denominator) <= 1e-3) {
    denominator = 1e-3;
  }

  // Calculate the arcsine value and return it
  double sinTx = numerator / denominator;
  // Clamp the value to the range [-1, 1] to avoid domain errors in asin due to numerical precision issues
  if (sinTx < -1.0) sinTx = -1.0;
  if (sinTx > 1.0) sinTx = 1.0;

  return {0.5 * (mL + mR), asin(sinTx)};
}

void LoopAnkleAnalyticalSolver::UpdateJ1(const Eigen::Vector2d& mc) {
  j1(0, 0) = 0.5;
  j1(0, 1) = 0.5;

  j1(1, 0) = CalculateTxML(mc);
  j1(1, 1) = CalculateTxMR(mc);
}