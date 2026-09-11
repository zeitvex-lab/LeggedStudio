#!/usr/bin/env python3
# ========================================================================================
# box_detector_pt.py — 物资箱检测器（PyTorch 版，仅用于电脑端测试）
# ========================================================================================
#
# 此文件仅用于电脑端测试，不部署到上位机
# 上位机请使用 box_detector_rknn.py（RKNN 版）
#
# 用法:
#   python3 box_detector_pt.py --mode single
#   python3 box_detector_pt.py --mode scan_all --target-zone 6 --field-side left
#
# 依赖:
#   pip install ultralytics

import argparse
import json
import sys
from pathlib import Path

import cv2
import numpy as np
from ultralytics import YOLO

try:
    import pyrealsense2 as rs
    HAS_REALSENSE = True
except ImportError:
    HAS_REALSENSE = False


def load_config(path):
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)


def letterbox(image, new_shape=640, color=(114, 114, 114)):
    shape = image.shape[:2]
    if isinstance(new_shape, int):
        new_shape = (new_shape, new_shape)
    ratio = min(new_shape[0] / shape[0], new_shape[1] / shape[1])
    new_unpad = (int(round(shape[1] * ratio)), int(round(shape[0] * ratio)))
    dw = new_shape[1] - new_unpad[0]
    dh = new_shape[0] - new_unpad[1]
    dw /= 2
    dh /= 2
    if shape[::-1] != new_unpad:
        image = cv2.resize(image, new_unpad, interpolation=cv2.INTER_LINEAR)
    top, bottom = int(round(dh - 0.1)), int(round(dh + 0.1))
    left, right = int(round(dw - 0.1)), int(round(dw + 0.1))
    image = cv2.copyMakeBorder(image, top, bottom, left, right, cv2.BORDER_CONSTANT, value=color)
    return image, ratio, (left, top)


def nms(boxes, scores, iou_threshold):
    if len(boxes) == 0:
        return []
    x1, y1, x2, y2 = boxes[:, 0], boxes[:, 1], boxes[:, 2], boxes[:, 3]
    areas = np.maximum(0, x2 - x1) * np.maximum(0, y2 - y1)
    order = scores.argsort()[::-1]
    keep = []
    while order.size > 0:
        i = order[0]
        keep.append(i)
        if order.size == 1:
            break
        xx1 = np.maximum(x1[i], x1[order[1:]])
        yy1 = np.maximum(y1[i], y1[order[1:]])
        xx2 = np.minimum(x2[i], x2[order[1:]])
        yy2 = np.minimum(y2[i], y2[order[1:]])
        inter = np.maximum(0, xx2 - xx1) * np.maximum(0, yy2 - yy1)
        union = areas[i] + areas[order[1:]] - inter
        iou = inter / np.maximum(union, 1e-6)
        order = order[1:][iou <= iou_threshold]
    return keep


def pick_single_box(detections, image_shape):
    if not detections:
        return None
    h, w = image_shape[:2]
    cx, cy = w / 2.0, h / 2.0
    ordered = sorted(detections, key=lambda d: (
        (d["center"][0] - cx) ** 2 + (d["center"][1] - cy) ** 2,
        -(d["score"]), d["center"][1], d["center"][0]))
    return ordered[0]


def vote_single_box(frame_results):
    candidates = [r for r in frame_results if r is not None]
    if not candidates:
        return "unknown", None, {}
    stats = {}
    for det in candidates:
        t = det["type"]
        if t not in stats:
            stats[t] = {"count": 0, "score_sum": 0.0, "best": det}
        stats[t]["count"] += 1
        stats[t]["score_sum"] += float(det["score"])
        if det["score"] > stats[t]["best"]["score"]:
            stats[t]["best"] = det
    best_type = sorted(stats.keys(), key=lambda k: (
        -stats[k]["count"],
        -(stats[k]["score_sum"] / max(1, stats[k]["count"])),
        -stats[k]["best"]["score"]))[0]
    return best_type, stats[best_type]["best"], stats


def draw_debug(image, detections, output_path, single_box=None, scan_info=None):
    debug = image.copy()
    for det in detections:
        x1, y1, x2, y2 = [int(v) for v in det["box"]]
        label = f'{det["type"]} {det["score"]:.2f}'
        cv2.rectangle(debug, (x1, y1), (x2, y2), (0, 255, 0), 2)
        cv2.putText(debug, label, (x1, max(20, y1 - 5)), cv2.FONT_HERSHEY_SIMPLEX, 0.6, (0, 255, 0), 2)
    if single_box is not None:
        x1, y1, x2, y2 = [int(v) for v in single_box["box"]]
        cv2.rectangle(debug, (x1, y1), (x2, y2), (0, 0, 255), 3)
        cv2.putText(debug, "selected", (x1, min(debug.shape[0] - 10, y2 + 25)),
                    cv2.FONT_HERSHEY_SIMPLEX, 0.8, (0, 0, 255), 2)
    if scan_info:
        h, w = debug.shape[:2]
        for region in scan_info.get("regions", []):
            xp = int(region["x_min"] * w)
            cv2.line(debug, (xp, 0), (xp, h), (255, 255, 0), 1)
            cv2.putText(debug, f"P{region['point']}", (xp + 5, h - 10),
                       cv2.FONT_HERSHEY_SIMPLEX, 0.5, (255, 255, 0), 1)
        for match in scan_info.get("matches", []):
            if match.get("matched"):
                x1, y1, x2, y2 = [int(v) for v in match["box"]]
                cv2.rectangle(debug, (x1, y1), (x2, y2), (0, 255, 255), 3)
                cv2.putText(debug, f"*P{match['point']}", (x1, max(20, y1 - 25)),
                           cv2.FONT_HERSHEY_SIMPLEX, 0.8, (0, 255, 255), 2)
    cv2.imwrite(str(output_path), debug)


def load_image_or_camera(args, cfg):
    """加载图片或摄像头帧，返回 frames 列表"""
    # 优先使用图片
    if args.image:
        img = cv2.imread(args.image)
        if img is None:
            raise RuntimeError(f"无法读取图片: {args.image}")
        print(f"使用图片: {args.image} ({img.shape[1]}x{img.shape[0]})")
        # 复制 N 帧（模拟多帧投票）
        frame_count = int(args.frames if args.frames else cfg.get("confirm_frames", 5))
        return [img.copy() for _ in range(frame_count)]

    # 摄像头（电脑默认 camera 0，不读取配置文件中的上位机编号）
    camera_id = args.camera if args.camera is not None else 0
    warmup = int(cfg.get("warmup_frames", 10))
    frame_count = int(args.frames if args.frames else cfg.get("confirm_frames", 5))
    interval = int(cfg.get("confirm_frame_interval", 1))
    return capture_frames(camera_id, warmup, frame_count, interval, cfg)


def open_realsense(cfg):
    """打开 RealSense D435i 相机"""
    if not HAS_REALSENSE:
        raise RuntimeError("pyrealsense2 未安装，请运行: pip install pyrealsense2")
    pipeline = rs.pipeline()
    config = rs.config()
    w = int(cfg.get("camera_width", 1920))
    h = int(cfg.get("camera_height", 1080))
    config.enable_stream(rs.stream.color, w, h, rs.format.bgr8, 30)
    profile = pipeline.start(config)
    # 自动曝光
    device = profile.get_device()
    color_sensor = device.first_color_sensor()
    color_sensor.set_option(rs.option.enable_auto_exposure, 1)
    print(f"RealSense D435i 已启动: {w}x{h}")
    return pipeline


def open_camera(camera_id, cfg=None):
    """打开普通摄像头并设置分辨率"""
    cap = cv2.VideoCapture(camera_id)
    if not cap.isOpened():
        raise RuntimeError(f"无法打开相机: {camera_id}")
    if cfg:
        cap.set(cv2.CAP_PROP_FRAME_WIDTH, int(cfg.get("camera_width", 1920)))
        cap.set(cv2.CAP_PROP_FRAME_HEIGHT, int(cfg.get("camera_height", 1080)))
    actual_w = int(cap.get(cv2.CAP_PROP_FRAME_WIDTH))
    actual_h = int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT))
    print(f"摄像头 {camera_id} 分辨率: {actual_w}x{actual_h}")
    return cap


def capture_frames(camera_id, warmup_frames, frame_count, frame_interval, cfg=None):
    """采集帧（优先使用 RealSense）"""
    if cfg and cfg.get("camera_type", "realsense") == "realsense" and HAS_REALSENSE:
        pipeline = open_realsense(cfg)
        try:
            for _ in range(max(1, warmup_frames)):
                pipeline.wait_for_frames()
            frames = []
            for _ in range(max(1, frame_count)):
                f = pipeline.wait_for_frames()
                color = f.get_color_frame()
                if color:
                    frames.append(np.asanyarray(color.get_data()))
                for _ in range(max(0, frame_interval)):
                    pipeline.wait_for_frames()
            if not frames:
                raise RuntimeError("无法读取 RealSense 画面")
            return frames
        finally:
            pipeline.stop()

    # 回退到普通摄像头
    cap = open_camera(camera_id, cfg)
    try:
        for _ in range(max(1, warmup_frames)):
            cap.read()
        frames = []
        for _ in range(max(1, frame_count)):
            ok, frame = cap.read()
            if not ok:
                continue
            frames.append(frame)
            for _ in range(max(0, frame_interval)):
                cap.read()
        if not frames:
            raise RuntimeError("无法读取相机画面")
        return frames
    finally:
        cap.release()


def infer_frame_pt(model, frame_bgr, cfg):
    class_map = {int(k): v for k, v in cfg["classes"].items()}
    class_id_base = int(cfg.get("class_id_base", 1))
    conf_thresh = float(cfg.get("conf_threshold", 0.35))
    input_size = int(cfg.get("input_size", 640))

    results = model.predict(frame_bgr, imgsz=input_size, conf=conf_thresh, verbose=False)
    detections = []
    if results and len(results) > 0:
        r = results[0]
        if r.boxes is not None:
            for box in r.boxes:
                cls_idx = int(box.cls[0])
                class_id = cls_idx + class_id_base
                label = class_map.get(class_id)
                if label is None:
                    continue
                x1, y1, x2, y2 = box.xyxy[0].tolist()
                score = float(box.conf[0])
                detections.append({
                    "box": [x1, y1, x2, y2], "score": score,
                    "class_id": class_id, "type": label,
                    "center": [(x1 + x2) / 2, (y1 + y2) / 2]
                })
    return detections, pick_single_box(detections, frame_bgr.shape)


def compute_iou(box1, box2):
    """计算两个框的 IoU"""
    x1 = max(box1[0], box2[0])
    y1 = max(box1[1], box2[1])
    x2 = min(box1[2], box2[2])
    y2 = min(box1[3], box2[3])
    inter = max(0, x2 - x1) * max(0, y2 - y1)
    area1 = max(0, box1[2] - box1[0]) * max(0, box1[3] - box1[1])
    area2 = max(0, box2[2] - box2[0]) * max(0, box2[3] - box2[1])
    union = area1 + area2 - inter
    return inter / max(union, 1e-6)


def merge_detections(detections, iou_threshold=0.3):
    """合并同一箱子的重复检测（正面/侧面可能同时看到）
    距离相近 + IoU 重叠的检测框合并为一个，取置信度最高的类型"""
    if not detections:
        return []
    # 按距离排序（先添加距离信息）
    merged = []
    used = [False] * len(detections)
    for i in range(len(detections)):
        if used[i]:
            continue
        group = [i]
        used[i] = True
        for j in range(i + 1, len(detections)):
            if used[j]:
                continue
            # 同类型 + IoU 重叠 → 同一个箱子
            if detections[i]["type"] == detections[j]["type"]:
                iou = compute_iou(detections[i]["box"], detections[j]["box"])
                if iou >= iou_threshold:
                    group.append(j)
                    used[j] = True
        # 取置信度最高的作为代表
        best = max(group, key=lambda idx: detections[idx]["score"])
        merged.append(detections[best])
    return merged


def assign_by_depth(detections, depth_frame, image_width, phase_cfg, merge_iou=0.3):
    """通过距离 + x位置分配箱子编号
    phase_cfg 包含:
      first_row_dist/tol, second_row_dist/tol, layout
      可选: visible_boxes — 限制只匹配这些箱子编号
    """
    first_dist = phase_cfg.get("first_row_dist", 2.0)
    first_tol = phase_cfg.get("first_row_tol", 0.8)
    second_dist = phase_cfg.get("second_row_dist", 3.0)
    second_tol = phase_cfg.get("second_row_tol", 0.8)
    visible_boxes = phase_cfg.get("visible_boxes", None)
    layout = phase_cfg.get("layout", {})
    first_row = layout.get("first_row", [9, 10, 11, 12])
    second_row = layout.get("second_row", [5, 6, 7, 8])

    # 获取每个检测的距离
    det_with_dist = []
    for det in detections:
        dist = None
        if depth_frame is not None:
            cx = int((det["box"][0] + det["box"][2]) / 2)
            cy = int((det["box"][1] + det["box"][3]) / 2)
            try:
                dist = depth_frame.get_distance(cx, cy)
            except Exception:
                pass
        det_with_dist.append({**det, "distance": dist})

    # 合并重复检测
    det_with_dist = merge_detections(det_with_dist, merge_iou)

    # 分配箱子编号
    assigned = {}
    n_cols_first = len(first_row)
    n_cols_second = len(second_row)

    for det in det_with_dist:
        dist = det.get("distance")
        if dist is None:
            continue

        row = None
        if abs(dist - first_dist) <= first_tol:
            row = "first_row"
        elif abs(dist - second_dist) <= second_tol:
            row = "second_row"
        else:
            continue

        cx_ratio = det["center"][0] / image_width

        if row == "first_row":
            col = min(int(cx_ratio * n_cols_first), n_cols_first - 1)
            box_num = first_row[col]
        else:
            col = min(int(cx_ratio * n_cols_second), n_cols_second - 1)
            box_num = second_row[col]

        # 如果有 visible_boxes 限制，跳过不在列表中的
        if visible_boxes and box_num not in visible_boxes:
            continue

        if box_num in assigned:
            if det["score"] > assigned[box_num]["score"]:
                assigned[box_num] = det
        else:
            assigned[box_num] = det

    return assigned


def assign_detections_to_points_legacy(detections, image_width, scan_regions):
    """旧版：通过 x 位置区域分配（无深度）"""
    assigned = []
    used_points = set()
    for det in detections:
        cx_ratio = det["center"][0] / image_width
        best_region = None
        for region in scan_regions:
            if region["x_min"] <= cx_ratio < region["x_max"]:
                best_region = region
                break
        if best_region is None:
            best_region = scan_regions[0] if cx_ratio <= 0 else scan_regions[-1]
        point = best_region["point"]
        if point in used_points:
            available = [r for r in scan_regions if r["point"] not in used_points]
            if available:
                best_region = min(available, key=lambda r: abs((r["x_min"] + r["x_max"]) / 2 - cx_ratio))
                point = best_region["point"]
        used_points.add(point)
        assigned.append({"point": point, "type": det["type"], "score": det["score"],
                        "box": det["box"], "center": det["center"], "matched": False})
    return assigned


def vote_all_boxes(frame_results_list):
    """多帧投票：每个箱子编号投票决定类型"""
    point_votes = {}
    for assigned in frame_results_list:
        for box_num, det in assigned.items():
            tp = det["type"]
            point_votes.setdefault(box_num, {}).setdefault(tp, 0)
            point_votes[box_num][tp] += 1
    # 每个箱子取票数最多的类型
    result = {}
    for box_num, votes in point_votes.items():
        result[box_num] = max(votes, key=votes.get)
    return result


def validate_box_types(point_types):
    """验证每种箱子类型必须恰好出现2次（8箱4种，每种2个）
    返回 (ok, errors) """
    type_count = {}
    nulls = []
    for bn in range(5, 13):
        t = point_types.get(bn)
        if t is None:
            nulls.append(bn)
        else:
            type_count[t] = type_count.get(t, 0) + 1

    errors = []
    if nulls:
        errors.append(f"存在未识别的箱子: {['箱%02d' % b for b in nulls]}")
    if len(type_count) != 4:
        errors.append(f"类型种类数={len(type_count)}，期望4种（实际: {list(type_count.keys())}）")
    for t, cnt in sorted(type_count.items()):
        if cnt != 2:
            errors.append(f"类型 {t} 出现 {cnt} 次，期望2次")

    if errors:
        print("\n❌ ★★★ 扫描结果校验失败 ★★★")
        for e in errors:
            print(f"  ❌ {e}")
        print("  建议: 检查摄像头角度/光线，重新扫描")
        return False
    else:
        print("\n✅ 扫描结果校验通过: 每种类型恰好2个")
        return True


def format_box_results(point_types, target_zone, type_zone_map, pickup_map):
    """格式化扫描结果：打印箱05-12类型，NULL=未识别"""
    # 先校验
    validate_box_types(point_types)

    all_boxes = list(range(5, 13))  # 箱05-12

    box_to_pickup = {}
    for pp_str, sides in pickup_map.items():
        pp = int(pp_str)
        for direction, box_num in sides.items():
            box_to_pickup[box_num] = (pp, direction)

    # 打印所有箱子类型
    print("\n★ 场地箱子扫描结果:")
    for bn in all_boxes:
        box_type = point_types.get(bn)
        if box_type:
            zone = type_zone_map.get(box_type, -1)
            pp_dir = ""
            if bn in box_to_pickup:
                pp, d = box_to_pickup[bn]
                pp_dir = f" (← 点{pp}{d}吸盘)"
            print(f"  箱{bn:02d}: {box_type} (→ zone {zone}){pp_dir}")
        else:
            print(f"  箱{bn:02d}: NULL")

    # 输出标准格式
    map_parts = []
    for bn in all_boxes:
        t = point_types.get(bn, "NULL")
        map_parts.append(f"{bn}:{t}")
    print(f"BOX_SCAN_MAP={','.join(map_parts)}")

    # 生成取货计划（只包含目标区的箱子）
    plan = []
    for bn in sorted(point_types.keys()):
        box_type = point_types[bn]
        zone = type_zone_map.get(box_type, -1)
        if zone == target_zone and bn in box_to_pickup:
            pp, direction = box_to_pickup[bn]
            plan.append((pp, direction, bn, box_type))

    if plan:
        plan.sort(key=lambda x: x[0])
        for pp, direction, bn, box_type in plan:
            print(f"  ★ 取货: 点{pp} {direction}吸盘 → 吸箱{bn} ({box_type})")
        plan_parts = [f"{pp}:{direction.upper()[0]}:{bn}" for pp, direction, bn, _ in plan]
        print(f"BOX_SCAN_PLAN={','.join(plan_parts)}")
    else:
        print("  未找到目标箱子")

    # 保存扫描结果到 JSON 文件
    output_dir = Path(__file__).resolve().parent
    result_file = output_dir / "box_scan_result.json"
    save_data = {}
    for bn in all_boxes:
        t = point_types.get(bn, "NULL")
        save_data[f"box_{bn:02d}"] = {"type": t, "zone": type_zone_map.get(t, -1) if t != "NULL" else -1}
    with open(result_file, "w", encoding="utf-8") as f:
        json.dump(save_data, f, ensure_ascii=False, indent=2)
    print(f"  扫描结果已保存到: {result_file}")

    return plan


# ========================================================================================
# scan_all 模式
# ========================================================================================
def run_scan_all(args, cfg, model):
    scan_regions = cfg.get("scan_regions", [])
    type_zone_map = cfg.get("type_zone_map", {})
    pickup_map = cfg.get("pickup_map", {})
    if not type_zone_map:
        raise RuntimeError("配置文件缺少 type_zone_map")

    frames = load_image_or_camera(args, cfg)

    last_frame = frames[-1]
    last_detections = []
    all_assigned = []
    for frame in frames:
        detections, _ = infer_frame_pt(model, frame, cfg)
        last_detections = detections
        # scan_all 无深度，使用旧版区域分配
        assigned = {}
        for item in assign_detections_to_points_legacy(detections, frame.shape[1], scan_regions):
            assigned[item["point"]] = item
        all_assigned.append(assigned)

    point_types = vote_all_boxes(all_assigned)
    target_zone = args.target_zone

    # 使用统一格式输出
    plan = format_box_results(point_types, target_zone, type_zone_map, pickup_map)

    pickup_points = [bn for bn, bt in point_types.items() if type_zone_map.get(bt, -1) == target_zone]

    # Debug 图片
    h, w = last_frame.shape[:2]
    scan_assigned = assign_detections_to_points_legacy(last_detections, w, scan_regions)
    for item in scan_assigned:
        item["matched"] = (type_zone_map.get(item["type"], -1) == target_zone)
    debug_path = Path(__file__).resolve().parent / cfg.get("debug_image", "box_detector_debug.jpg")
    draw_debug(last_frame, last_detections, debug_path, scan_info={"regions": scan_regions, "matches": scan_assigned})

    result = {"success": len(pickup_points) > 0, "target_zone": target_zone,
              "pickup_points": pickup_points, "pickup_count": len(pickup_points),
              "frames": len(frames), "debug_image": str(debug_path)}
    print("BOX_SCAN_JSON=" + json.dumps(result, ensure_ascii=False))


# ========================================================================================
# single 模式
# ========================================================================================
def run_detector(args, cfg, model):
    frames = load_image_or_camera(args, cfg)

    last_frame = frames[-1]
    last_detections, single_results = [], []
    for frame in frames:
        last_detections, single_box = infer_frame_pt(model, frame, cfg)
        single_results.append(single_box)

    voted_type, single_box, vote_stats = vote_single_box(single_results)
    debug_path = Path(__file__).resolve().parent / cfg.get("debug_image", "box_detector_debug.jpg")
    draw_debug(last_frame, last_detections, debug_path, single_box=single_box)

    result = {"type": voted_type, "detection": single_box, "frames": len(frames),
              "votes": {k: {"count": v["count"], "avg_score": v["score_sum"] / max(1, v["count"]),
                            "best_score": v["best"]["score"]} for k, v in vote_stats.items()},
              "debug_image": str(debug_path)}
    print("BOX_TYPE_JSON=" + json.dumps(result, ensure_ascii=False))


# ========================================================================================
# live 模式 — 实时预览，按 y 扫描，按 q 退出
# ========================================================================================
def run_live(args, cfg, model):
    use_realsense = cfg.get("camera_type", "realsense") == "realsense" and HAS_REALSENSE

    # 深度传感器（用于测距）
    depth_scale = 0.0
    align = None
    if use_realsense:
        # live 模式同时启用深度流
        if not HAS_REALSENSE:
            raise RuntimeError("pyrealsense2 未安装")
        pipeline = rs.pipeline()
        config = rs.config()
        w = int(cfg.get("camera_width", 1920))
        h = int(cfg.get("camera_height", 1080))
        config.enable_stream(rs.stream.color, w, h, rs.format.bgr8, 30)
        config.enable_stream(rs.stream.depth, 640, 480, rs.format.z16, 30)
        profile = pipeline.start(config)
        device = profile.get_device()
        color_sensor = device.first_color_sensor()
        color_sensor.set_option(rs.option.enable_auto_exposure, 1)
        align = rs.align(rs.stream.color)
        print(f"RealSense D435i 已启动（彩色+深度）: {w}x{h}")
    else:
        camera_id = args.camera if args.camera is not None else 0
        cap = open_camera(camera_id, cfg)
        print(f"使用普通摄像头 {camera_id}")

    scan_depth_cfg = cfg.get("scan_depth_config", {})
    phase0_cfg = scan_depth_cfg.get("phase0", {})
    phase1_cfg = scan_depth_cfg.get("phase1", {})
    merge_iou = scan_depth_cfg.get("merge_iou_threshold", 0.3)
    scan_regions = cfg.get("scan_regions", [])
    type_zone_map = cfg.get("type_zone_map", {})
    type_colors = cfg.get("type_colors", {})
    pickup_map = cfg.get("pickup_map", {})
    target_zone = args.target_zone
    input_size = int(cfg.get("input_size", 640))
    class_map = {int(k): v for k, v in cfg["classes"].items()}
    class_id_base = int(cfg.get("class_id_base", 1))
    conf_thresh = float(cfg.get("conf_threshold", 0.35))

    # 两步扫描状态
    scan_phase = 0       # 0=在点0(远), 1=在点1(近)
    accumulated = []     # list of assigned dict {box_num: {type, score, ...}}
    max_accum = int(cfg.get("confirm_frames", 5))
    phase0_result = {}   # 点0扫描结果 {box_num: type}
    last_pickup_output = ""

    print("========================================")
    print(" 实时预览模式（两步扫描）")
    print(f" 目标归位区: {target_zone}")
    print(" Phase0(点0远看): 按 'y' 开始")
    print(" Phase1(点1近看): 移动到点1后按 'y'")
    print(" 按 'p' 重置扫描 | 按 'c' 清除累积 | 按 'q' 退出")
    print("========================================")

    cv2.namedWindow("box_detector", cv2.WINDOW_NORMAL)

    try:
        while True:
            # 获取帧
            depth_frame = None
            if use_realsense:
                frameset = pipeline.wait_for_frames()
                # 对齐深度到彩色
                if align is not None:
                    aligned = align.process(frameset)
                    color_frame = aligned.get_color_frame()
                    depth_frame = aligned.get_depth_frame()
                else:
                    color_frame = frameset.get_color_frame()
                    depth_frame = None
                if not color_frame:
                    continue
                frame = np.asanyarray(color_frame.get_data())
            else:
                ok, frame = cap.read()
                if not ok:
                    continue

            # 实时检测（单帧）
            results = model.predict(frame, imgsz=input_size, conf=conf_thresh, verbose=False)
            detections = []
            if results and len(results) > 0 and results[0].boxes is not None:
                for box in results[0].boxes:
                    cls_idx = int(box.cls[0])
                    class_id = cls_idx + class_id_base
                    label = class_map.get(class_id)
                    if label is None:
                        continue
                    x1, y1, x2, y2 = box.xyxy[0].tolist()
                    score = float(box.conf[0])
                    detections.append({
                        "box": [x1, y1, x2, y2], "score": score,
                        "class_id": class_id, "type": label,
                        "center": [(x1 + x2) / 2, (y1 + y2) / 2]
                    })

            # 绘制检测框（类型对应颜色 + 距离）
            display = frame.copy()
            for det in detections:
                x1, y1, x2, y2 = [int(v) for v in det["box"]]
                box_type = det["type"]
                # 类型对应颜色
                color = type_colors.get(box_type, [0, 255, 0])
                color = tuple(int(c) for c in color)

                # 计算距离（使用深度图中心点）
                dist_str = ""
                if depth_frame is not None:
                    cx = (x1 + x2) // 2
                    cy = (y1 + y2) // 2
                    try:
                        dist = depth_frame.get_distance(cx, cy)
                        dist_str = f" {dist:.2f}m"
                    except Exception:
                        pass

                label = f'{box_type} {det["score"]:.2f}{dist_str}'
                cv2.rectangle(display, (x1, y1), (x2, y2), color, 2)
                cv2.putText(display, label, (x1, max(20, y1 - 5)),
                           cv2.FONT_HERSHEY_SIMPLEX, 0.6, color, 2)

            # 绘制扫描区域分割线
            h, w = display.shape[:2]
            for region in scan_regions:
                xp = int(region["x_min"] * w)
                cv2.line(display, (xp, 0), (xp, h), (255, 255, 0), 1)
                cv2.putText(display, f"P{region['point']}", (xp + 5, h - 10),
                           cv2.FONT_HERSHEY_SIMPLEX, 0.4, (255, 255, 0), 1)

            # 状态信息
            phase_str = "P0(点0远)" if scan_phase == 0 else "P1(点1近)"
            status = f"Phase:{phase_str} Acc:{len(accumulated)}/{max_accum} Zone:{target_zone}"
            if last_pickup_output:
                status += f" Last:{last_pickup_output}"
            cv2.putText(display, status, (10, 25),
                       cv2.FONT_HERSHEY_SIMPLEX, 0.6, (0, 255, 255), 2)
            phase_hint = "Y=scan(点0远)" if scan_phase == 0 else "Y=scan(点1近)"
            if scan_phase == 1 and phase0_result:
                phase_hint += " ★合并点0结果"
            cv2.putText(display, f"{phase_hint}  P=reset  C=clear  Q=quit", (10, 50),
                       cv2.FONT_HERSHEY_SIMPLEX, 0.5, (200, 200, 200), 1)

            cv2.imshow("box_detector", display)
            key = cv2.waitKey(1) & 0xFF

            if key == ord('q') or key == ord('Q'):
                break

            elif key == ord('y') or key == ord('Y'):
                # 根据当前 phase 选择配置
                if scan_phase == 0:
                    phase_cfg = phase0_cfg
                else:
                    phase_cfg = phase1_cfg

                # 使用深度+位置分配箱子编号
                if use_realsense and phase_cfg and depth_frame is not None:
                    assigned = assign_by_depth(detections, depth_frame, w, phase_cfg, merge_iou)
                else:
                    # 回退到旧版（无深度）
                    assigned = {}
                    for item in assign_detections_to_points_legacy(detections, w, scan_regions):
                        assigned[item["point"]] = item

                if assigned:
                    accumulated.append(assigned)

                if len(accumulated) >= max_accum:
                    # 多帧投票
                    point_types = vote_all_boxes(accumulated)

                    if scan_phase == 0:
                        # Phase 0 完成：保存结果，提示移动到点1
                        phase0_result = dict(point_types)
                        print(f"\n★ Phase0 完成（点0远看）:")
                        for bn in range(5, 13):
                            t = phase0_result.get(bn, "NULL")
                            print(f"  箱{bn:02d}: {t}")
                        nulls = [bn for bn in range(5, 13) if bn not in phase0_result]
                        print(f"\n→ 移动到点1后按 'y' 扫描（补充: {nulls}）")
                        scan_phase = 1
                        accumulated.clear()
                    else:
                        # Phase 1 完成：合并两步结果 + 验证
                        phase1_result = dict(point_types)
                        merged = dict(phase0_result)  # 以 phase0 为基础

                        # 用 phase1 补充 NULL 和验证
                        print(f"\n★ Phase1 完成（点1近看）:")
                        for bn in phase1_result:
                            t = phase1_result[bn]
                            old_t = merged.get(bn)
                            if old_t is None:
                                # 补充 NULL
                                merged[bn] = t
                                print(f"  箱{bn:02d}: {t} (补充)")
                            elif old_t == t:
                                # 验证一致
                                print(f"  箱{bn:02d}: {t} (✓验证一致)")
                            else:
                                # 不一致：用 phase1 的（近距离更准确）
                                merged[bn] = t
                                print(f"  箱{bn:02d}: {t} (覆盖，旧={old_t})")

                        # 输出最终合并结果
                        plan = format_box_results(merged, target_zone, type_zone_map, pickup_map)

                        last_pickup_output = f"PLAN={len(plan)}箱"
                        scan_phase = 0
                        phase0_result = {}
                        accumulated.clear()
                else:
                    print(f"  累积帧 {len(accumulated)}/{max_accum}，继续按 y...")

            elif key == ord('p') or key == ord('P'):
                # 重置全部扫描状态
                accumulated.clear()
                scan_phase = 0
                phase0_result = {}
                last_pickup_output = ""
                print("\n  ★ 已重置扫描（按 y 重新开始 Phase0）")

            elif key == ord('c') or key == ord('C'):
                accumulated.clear()
                print("  已清除累积帧")

    finally:
        if use_realsense:
            pipeline.stop()
        else:
            cap.release()
        cv2.destroyAllWindows()


def main():
    base_dir = Path(__file__).resolve().parent

    parser = argparse.ArgumentParser(description="Box detector (PyTorch, PC testing only)")
    parser.add_argument("--model", default=str(base_dir / "model" / "best.pt"))
    parser.add_argument("--config", default=str(base_dir / "box_detector_config.json"))
    parser.add_argument("--camera", type=int, default=None,
                        help="摄像头 ID（默认 0）")
    parser.add_argument("--image", default=None,
                        help="测试图片路径（不需要摄像头，优先于摄像头）")
    parser.add_argument("--mode", choices=["single", "scan_all", "live"], default="live",
                        help="检测模式: single/scan_all/live（默认 live 实时预览）")
    parser.add_argument("--frames", type=int, default=None)
    parser.add_argument("--target-zone", type=int, default=0)
    parser.add_argument("--field-side", choices=["left", "right"], default="left")
    args = parser.parse_args()

    cfg = load_config(args.config)

    model = YOLO(args.model)

    if args.mode == "scan_all":
        run_scan_all(args, cfg, model)
    elif args.mode == "live":
        run_live(args, cfg, model)
    else:
        run_detector(args, cfg, model)


if __name__ == "__main__":
    main()