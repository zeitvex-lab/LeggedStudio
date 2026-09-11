// ========================================================================================
// delivery_planner.hpp — 取放计划模块
// ========================================================================================
//
// 职责:
//   1. 维护静态映射表 (pickup_map, type_zone_map, zone_place_map)
//   2. 从扫描结果生成多轮取放计划 (GenerateDeliveryPlan)
//   3. 自动计算放置转身角度 (CalcPlaceTurnAngle)
//   4. 管理归位区坐标
//
// 不依赖 ROS，方便单元测试

#ifndef DOG_NAV_DELIVERY_PLANNER_HPP_
#define DOG_NAV_DELIVERY_PLANNER_HPP_

#include <cmath>
#include <string>
#include <vector>
#include <map>
#include "dog_nav/field_path_planner.hpp"

namespace dog_nav
{

// Point3D 定义在 field_path_planner.hpp 中，此处不再重复定义

// ========================================================================================
// 箱子信息
// ========================================================================================
struct BoxInfo
{
  int box_num{0};          // 箱子编号 (5-12)
  std::string type;        // 箱子类型: food/tool/instrument/medicine
  int zone{0};             // 归位区编号 (1-4)
  int place_point{0};      // 放置站位 (10/11/12)
  std::string direction;   // 吸盘侧: "left"/"right"（放货转身/绕行判断用）
  bool valid{false};       // 是否有效（扫描到了）
};

// ========================================================================================
// 一轮取放（成对取货点：左吸盘从 pickup_point_left 取，右吸盘从 pickup_point_right 取）
// ========================================================================================
//
// 新布局每个取货点旁边只有一个箱，一轮里跑两个点凑齐左右吸盘:
//   第1轮: pickup_point_left=点2(吸09), pickup_point_right=点3(吸10)
//   第2轮: pickup_point_left=点4(吸11), pickup_point_right=点5(吸12)
//   第3轮: pickup_point_left=点6(吸05), pickup_point_right=点7(吸06)
//   第4轮: pickup_point_left=点8(吸07), pickup_point_right=点9(吸08)
//
struct PickupRound
{
  int pickup_point_left{0};    // 左吸盘取货站位 (2/4/6/8)
  int pickup_point_right{0};   // 右吸盘取货站位 (3/5/7/9)
  BoxInfo left;                // 左吸盘箱子
  BoxInfo right;               // 右吸盘箱子
};

// ========================================================================================
// DeliveryPlanner — 取放计划器
// ========================================================================================
class DeliveryPlanner
{
public:
  DeliveryPlanner() = default;

  // ========================================================================================
  // LoadStaticMaps — 加载静态映射表
  // ========================================================================================
  //
  // pickup_pair_map: 成对取货点 (left_point, right_point, left_box, right_box)
  //   {点2, 点3, 09, 10}  第一排左
  //   {点4, 点5, 11, 12}  第一排右
  //   {点6, 点7, 05, 06}  第二排左
  //   {点8, 点9, 07, 08}  第二排右
  //
  // type_zone_map: 箱子类型 → zone 编号
  //   food→1, tool→2, instrument→3, medicine→4
  //
  // place_zone_map: 放货站位 × 吸盘侧 → 归位区编号
  //   点10: left→1, right→2
  //   点11: left→2, right→3
  //   点12: left→3, right→4
  //   → 反查: 左吸盘的箱 food→点10, tool→点11, instrument→点12, medicine→点12(转圈)
  //           右吸盘的箱 food→点10(转圈), tool→点10, instrument→点11, medicine→点12
  //
  void LoadStaticMaps()
  {
    pickup_pair_map_ = {
      {2, 3, 9,  10},   // 第1轮: 左点2吸09, 右点3吸10
      {4, 5, 11, 12},   // 第2轮: 左点4吸11, 右点5吸12
      {6, 7, 5,  6},    // 第3轮: 左点6吸05, 右点7吸06
      {8, 9, 7,  8},    // 第4轮: 左点8吸07, 右点9吸08
    };

    type_zone_map_ = {
      {"food", 1}, {"tool", 2}, {"instrument", 3}, {"medicine", 4}
    };

    // 放货站位 × 吸盘侧 → 归位区
    place_zone_map_ = {
      {10, {{"left", 1},  {"right", 2}}},
      {11, {{"left", 2},  {"right", 3}}},
      {12, {{"left", 3},  {"right", 4}}},
    };
  }

  // ========================================================================================
  // SetZoneCoord — 设置归位区坐标
  // ========================================================================================
  void SetZoneCoord(int zone_id, double x, double y, double theta = 0.0)
  {
    zone_coords_[zone_id] = {x, y, theta};
  }

  // ========================================================================================
  // SetPlaceCoord — 设置放置点坐标（用于 CalcPlaceTurnAngle）
  // ========================================================================================
  void SetPlaceCoord(int point, double x, double y, double theta = 0.0)
  {
    place_coords_[point] = {x, y, theta};
  }

  // ========================================================================================
  // GenerateDeliveryPlan — 从扫描结果生成多轮取放计划
  // ========================================================================================
  //
  // 输入: box_type_map (箱子编号 → 类型，来自扫描)
  // 输出: delivery_plan (每轮 = 一对取货点，左吸盘从 left 点取，右吸盘从 right 点取)
  //
  // 注意: 放货站位由吸盘侧决定（place_zone_map_ 反查），复杂逻辑在 navigation_dog
  //       内置实现；此处只填 BoxInfo.zone，place_point 留 0（待上层根据吸盘侧解析）
  //
  const std::vector<PickupRound> & GenerateDeliveryPlan(
    const std::map<int, std::string> & box_type_map)
  {
    delivery_plan_.clear();

    for (const auto & [lp, rp, lb, rb] : pickup_pair_map_) {
      PickupRound round;
      round.pickup_point_left = lp;
      round.pickup_point_right = rp;

      // 左吸盘的箱
      {
        auto type_it = box_type_map.find(lb);
        if (type_it != box_type_map.end()) {
          round.left.box_num = lb;
          round.left.type = type_it->second;
          round.left.valid = true;
          auto zone_it = type_zone_map_.find(round.left.type);
          if (zone_it != type_zone_map_.end()) round.left.zone = zone_it->second;
        }
      }
      // 右吸盘的箱
      {
        auto type_it = box_type_map.find(rb);
        if (type_it != box_type_map.end()) {
          round.right.box_num = rb;
          round.right.type = type_it->second;
          round.right.valid = true;
          auto zone_it = type_zone_map_.find(round.right.type);
          if (zone_it != type_zone_map_.end()) round.right.zone = zone_it->second;
        }
      }

      if (round.left.valid || round.right.valid) {
        delivery_plan_.push_back(round);
      }
    }

    return delivery_plan_;
  }

  // ========================================================================================
  // CalcPlaceTurnAngle — 自动计算放置时的转身角度
  // ========================================================================================
  //
  // 原理:
  //   1. 获取放置点坐标 (px, py) 和归位区坐标 (zx, zy)
  //   2. zone_angle = atan2(zy-py, zx-px)
  //   3. 左吸盘方向 = cur_yaw + π/2, 右吸盘 = cur_yaw - π/2
  //   4. turn = zone_angle - sucker_angle（让吸盘对准归位区）
  //
  // 参数 direction: "left"/"right" 吸盘侧，决定 sucker_angle 和归位区（place_zone_map_）
  //
  // ★ 转圈倒车: 当吸盘侧与归位区位置矛盾时（如右吸盘放 zone1，归位区在站位左侧），
  //   turn 会接近 ±π，表示要转半圈倒进去。上层根据 |turn| 大小判断是否需要倒车。
  //
  double CalcPlaceTurnAngle(int place_point, const std::string & direction,
    double cur_yaw) const
  {
    auto pit = place_coords_.find(place_point);
    if (pit == place_coords_.end()) {
      return (direction == "left") ? (-M_PI / 2.0) : (M_PI / 2.0);
    }
    double px = pit->second.x;
    double py = pit->second.y;

    // 由 放货点 × 吸盘侧 反查归位区
    auto pzm = place_zone_map_.find(place_point);
    if (pzm == place_zone_map_.end()) {
      return (direction == "left") ? (-M_PI / 2.0) : (M_PI / 2.0);
    }
    auto dit = pzm->second.find(direction);
    if (dit == pzm->second.end()) {
      return (direction == "left") ? (-M_PI / 2.0) : (M_PI / 2.0);
    }
    int zone_id = dit->second;

    auto zit = zone_coords_.find(zone_id);
    if (zit == zone_coords_.end()) {
      return (direction == "left") ? (-M_PI / 2.0) : (M_PI / 2.0);
    }
    double zx = zit->second.x;
    double zy = zit->second.y;

    double zone_angle = std::atan2(zy - py, zx - px);

    double sucker_angle = (direction == "left")
      ? (cur_yaw + M_PI / 2.0)
      : (cur_yaw - M_PI / 2.0);

    return NormalizeAngle(zone_angle - sucker_angle);
  }

  // ========================================================================================
  // GetDeliveryPlan — 获取当前计划
  // ========================================================================================
  const std::vector<PickupRound> & GetDeliveryPlan() const { return delivery_plan_; }

  // ========================================================================================
  // 辅助: 查询箱子类型 → zone
  // ========================================================================================
  int TypeToZone(const std::string & type) const
  {
    auto it = type_zone_map_.find(type);
    return (it != type_zone_map_.end()) ? it->second : 0;
  }

  // ========================================================================================
  // 辅助: 按 吸盘侧 + 目标zone 反查放货站位
  // ========================================================================================
  // 例: 左吸盘要放 zone1 → 点10; 右吸盘要放 zone1 → 点10(需转圈)
  //
  int ZoneSideToPlacePoint(int zone, const std::string & direction) const
  {
    for (const auto & [pp, side_map] : place_zone_map_) {
      auto it = side_map.find(direction);
      if (it != side_map.end() && it->second == zone) {
        return pp;
      }
    }
    return 0;
  }

private:
  static double NormalizeAngle(double a)
  {
    while (a > M_PI) a -= 2.0 * M_PI;
    while (a < -M_PI) a += 2.0 * M_PI;
    return a;
  }

  // 静态映射表
  std::vector<std::tuple<int, int, int, int>> pickup_pair_map_;  // (left_pt, right_pt, left_box, right_box)
  std::map<std::string, int> type_zone_map_;
  std::map<int, std::map<std::string, int>> place_zone_map_;     // 站位 × 吸盘侧 → zone

  // 坐标
  std::map<int, Point3D> zone_coords_;
  std::map<int, Point3D> place_coords_;

  // 生成的计划
  std::vector<PickupRound> delivery_plan_;
};

}  // namespace dog_nav

#endif  // DOG_NAV_DELIVERY_PLANNER_HPP_