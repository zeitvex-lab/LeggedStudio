#!/usr/bin/env python3
# ========================================================================================
# box_detector_rknn.py — 物资箱检测器（RKNN 版，上位机 RK3588 专用）
# ========================================================================================
#
# 电脑端测试请使用 box_detector_pt.py（PyTorch 版）
#
# 模式:
#   single   — 检测最近的单个箱子类型
#   scan_all — 扫描所有箱子，输出每个箱子的类型和场地点位
#
# 用法:
#   python3 box_detector_rknn.py --mode single
#   python3 box_detector_rknn.py --mode scan_all --target-zone 6
#
# 输出:
#   single   → BOX_TYPE_JSON={...}
#   scan_all → BOX_SCAN_JSON={...}
#              BOX_SCAN_PICKUP=12,16
#              BOX_SCAN_MAP=11:food,12:tool,...

import argparse
import json
from pathlib import Path

import cv2
import numpy as np

from rknnlite.api import RKNNLite

try:
    import pyrealsense2 as rs
    HAS_REALSENSE = True
except ImportError:
    HAS_REALSENSE = False

try:
    # d435i_stream.py 独占 D435i 时，通过共享内存取帧；读不到则回退直接开相机
    from d435i_client import FrameClient, ShmUnavailable
    HAS_SHM_CLIENT = True
except ImportError:
    HAS_SHM_CLIENT = False


# ========================================================================================
# 通用工具函数
# ========================================================================================

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


def xywh_to_xyxy(boxes):
    out = np.zeros_like(boxes)
    out[:, 0] = boxes[:, 0] - boxes[:, 2] / 2
    out[:, 1] = boxes[:, 1] - boxes[:, 3] / 2
    out[:, 2] = boxes[:, 0] + boxes[:, 2] / 2
    out[:, 3] = boxes[:, 1] + boxes[:, 3] / 2
    return out


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


def flatten_outputs(outputs):
    rows = []
    for out in outputs:
        arr = np.asarray(out)
        arr = np.squeeze(arr)
        if arr.ndim == 1:
            continue
        if arr.ndim == 3:
            arr = arr.reshape(arr.shape[0], -1).T
        elif arr.ndim == 2:
            if arr.shape[0] < arr.shape[1] and arr.shape[0] <= 128:
                arr = arr.T
        else:
            arr = arr.reshape(-1, arr.shape[-1])
        rows.append(arr)
    if not rows:
        return np.empty((0, 0), dtype=np.float32)
    return np.concatenate(rows, axis=0).astype(np.float32)


def decode_detections(outputs, cfg, ratio, pad, image_shape):
    pred = flatten_outputs(outputs)
    if pred.size == 0 or pred.shape[1] < 8:
        return []
    class_map = {int(k): v for k, v in cfg["classes"].items()}
    class_count = len(class_map)
    class_id_base = int(cfg.get("class_id_base", 1))
    dims = pred.shape[1]
    if dims >= 5 + class_count:
        boxes_xywh = pred[:, :4]
        obj = pred[:, 4]
        class_scores = pred[:, 5:5 + class_count]
        class_indices = np.argmax(class_scores, axis=1)
        scores = obj * class_scores[np.arange(len(pred)), class_indices]
    elif dims >= 4 + class_count:
        boxes_xywh = pred[:, :4]
        class_scores = pred[:, 4:4 + class_count]
        class_indices = np.argmax(class_scores, axis=1)
        scores = class_scores[np.arange(len(pred)), class_indices]
    else:
        return []
    keep = scores >= float(cfg.get("conf_threshold", 0.35))
    boxes_xywh, scores, class_indices = boxes_xywh[keep], scores[keep], class_indices[keep]
    if len(boxes_xywh) == 0:
        return []
    boxes = xywh_to_xyxy(boxes_xywh)
    boxes[:, [0, 2]] -= pad[0]
    boxes[:, [1, 3]] -= pad[1]
    boxes /= ratio
    h, w = image_shape[:2]
    boxes[:, [0, 2]] = np.clip(boxes[:, [0, 2]], 0, w - 1)
    boxes[:, [1, 3]] = np.clip(boxes[:, [1, 3]], 0, h - 1)
    keep_indices = nms(boxes, scores, float(cfg.get("iou_threshold", 0.45)))
    detections = []
    for idx in keep_indices:
        class_id = int(class_indices[idx]) + class_id_base
        label = class_map.get(class_id)
        if label is None:
            continue
        x1, y1, x2, y2 = boxes[idx].tolist()
        detections.append({
            "box": [float(x1), float(y1), float(x2), float(y2)],
            "score": float(scores[idx]),
            "class_id": class_id,
            "type": label,
            "center": [float((x1 + x2) / 2), float((y1 + y2) / 2)]
        })
    return detections


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


def draw_debug(image, detections, output_path, single_box=None, scan_info=None, type_colors=None):
    if type_colors is None:
        type_colors = {}
    debug = image.copy()
    for det in detections:
        x1, y1, x2, y2 = [int(v) for v in det["box"]]
        box_type = det["type"]
        color = tuple(int(c) for c in type_colors.get(box_type, [0, 255, 0]))
        label = f'{box_type} {det["score"]:.2f}'
        cv2.rectangle(debug, (x1, y1), (x2, y2), color, 2)
        cv2.putText(debug, label, (x1, max(20, y1 - 5)), cv2.FONT_HERSHEY_SIMPLEX, 0.6, color, 2)
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


def capture_frames(camera_id, warmup_frames, frame_count, frame_interval, cfg=None):
    """采集帧（优先使用 RealSense D435i，带回深度图）"""
    use_rs = cfg and cfg.get("camera_type", "realsense") == "realsense" and HAS_REALSENSE

    if use_rs:
        return capture_frames_realsense(warmup_frames, frame_count, frame_interval, cfg)

    # 回退到普通摄像头
    cap = cv2.VideoCapture(camera_id)
    if not cap.isOpened():
        raise RuntimeError(f"无法打开相机: {camera_id}")
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
        return frames, [None] * len(frames)
    finally:
        cap.release()


def capture_frames_realsense(warmup_frames, frame_count, frame_interval, cfg):
    """使用 RealSense D435i 采集帧+深度。

    优先走 d435i_stream 共享内存（D435i 被 streamer 独占时不抢相机）；
    读不到则回退直接打开 D435i（原 rs.pipeline 逻辑，代码保留）。
    """
    # 优先: 共享内存取帧（d435i_stream 在跑）
    if HAS_SHM_CLIENT:
        try:
            client = FrameClient()
            interval_s = frame_interval / 30.0  # 原帧间隔按 30fps 折算成秒
            print("[相机] 通过共享内存取帧（d435i_stream）...")
            total = max(1, warmup_frames) + max(1, frame_count)
            pairs = client.grab_burst(total, interval_s)
            if len(pairs) < max(1, frame_count):
                raise ShmUnavailable(f"仅取到 {len(pairs)} 帧，不足 {frame_count}")
            # 丢掉 warmup 帧
            pairs = pairs[max(1, warmup_frames):]
            frames = [c for c, _ in pairs]
            depth_frames = []
            for _, d in pairs:
                # 把 numpy depth 数组包装成有 get_distance 的对象（assign_by_depth_rknn 需要）
                depth_frames.append(_DepthArrayWrapper(d) if d is not None else None)
            print(f"[相机] shm 取帧成功: {len(frames)} 帧")
            return frames, depth_frames
        except ShmUnavailable as e:
            print(f"[相机] shm 不可用({e})，回退直接打开 D435i...")

    # 回退: 直接打开 D435i（原逻辑，代码原样保留）
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

    try:
        for _ in range(max(1, warmup_frames)):
            pipeline.wait_for_frames()

        frames = []
        depth_frames = []
        for _ in range(max(1, frame_count)):
            frameset = pipeline.wait_for_frames()
            aligned = align.process(frameset)
            color_frame = aligned.get_color_frame()
            depth_frame = aligned.get_depth_frame()
            if not color_frame:
                continue
            frames.append(np.asanyarray(color_frame.get_data()))
            depth_frames.append(depth_frame)
            for _ in range(max(0, frame_interval)):
                pipeline.wait_for_frames()

        if not frames:
            raise RuntimeError("无法读取 RealSense 画面")
        return frames, depth_frames
    finally:
        pipeline.stop()


class _DepthArrayWrapper:
    """把 numpy depth 数组包装成带 get_distance 的对象，
    让 assign_by_depth_rknn 能像 rs.depth_frame 一样用（shm 路径用）。"""
    def __init__(self, depth_arr):
        self._arr = depth_arr

    def get_distance(self, x, y):
        try:
            v = float(self._arr[int(y), int(x)])
            # z16 深度单位是毫米，转米（与 rs.depth_frame.get_distance 一致）
            return v / 1000.0
        except Exception:
            return 0.0


# ========================================================================================
# RKNN 推理
# ========================================================================================

def infer_frame(rknn, frame_bgr, cfg):
    frame_rgb = cv2.cvtColor(frame_bgr, cv2.COLOR_BGR2RGB)
    input_size = int(cfg.get("input_size", 640))
    image, ratio, pad = letterbox(frame_rgb, input_size)
    input_data = np.expand_dims(image, axis=0).astype(np.uint8)
    outputs = rknn.inference(inputs=[input_data])
    detections = decode_detections(outputs, cfg, ratio, pad, frame_bgr.shape)
    return detections, pick_single_box(detections, frame_bgr.shape)




# ========================================================================================
# scan_all 模式
# ========================================================================================

def compute_iou(box1, box2):
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
    """合并同一箱子的重复检测（正面/侧面）"""
    if not detections:
        return []
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
            if detections[i]["type"] == detections[j]["type"]:
                iou = compute_iou(detections[i]["box"], detections[j]["box"])
                if iou >= iou_threshold:
                    group.append(j)
                    used[j] = True
        best = max(group, key=lambda idx: detections[idx]["score"])
        merged.append(detections[best])
    return merged


def assign_detections_to_points(detections, image_width, scan_regions):
    """通过 x 位置区域分配箱子编号（合并重复后）"""
    # 先合并重复检测
    detections = merge_detections(detections, 0.3)
    assigned = {}
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
        if point in assigned:
            if det["score"] > assigned[point]["score"]:
                assigned[point] = det
        else:
            assigned[point] = det
    return assigned


def vote_all_boxes(frame_results_list):
    """多帧投票：每个箱子编号投票决定类型"""
    point_votes = {}
    for assigned in frame_results_list:
        for box_num, det in assigned.items():
            tp = det["type"]
            point_votes.setdefault(box_num, {}).setdefault(tp, 0)
            point_votes[box_num][tp] += 1
    return {box_num: max(votes, key=votes.get) for box_num, votes in point_votes.items()}


def validate_box_types(point_types):
    """验证每种箱子类型必须恰好出现2次（8箱4种，每种2个）"""
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
    """格式化扫描结果：箱05-12全打印，NULL=未识别"""
    # 先校验
    validate_box_types(point_types)

    all_boxes = list(range(5, 13))
    box_to_pickup = {}
    for pp_str, sides in pickup_map.items():
        pp = int(pp_str)
        for direction, box_num in sides.items():
            box_to_pickup[box_num] = (pp, direction)

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

    map_parts = []
    for bn in all_boxes:
        t = point_types.get(bn, "NULL")
        map_parts.append(f"{bn}:{t}")
    print(f"BOX_SCAN_MAP={','.join(map_parts)}")

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


def run_scan_all(args):
    cfg = load_config(args.config)
    scan_regions = cfg.get("scan_regions", [])
    scan_depth_cfg = cfg.get("scan_depth_config", {})
    phase0_cfg = scan_depth_cfg.get("phase0", {})
    type_zone_map = cfg.get("type_zone_map", {})
    pickup_map = cfg.get("pickup_map", {})
    if not type_zone_map:
        raise RuntimeError("配置文件缺少 type_zone_map")

    frame_count = int(args.frames if args.frames is not None else cfg.get("confirm_frames", 5))
    frame_interval = int(cfg.get("confirm_frame_interval", 1))
    frames, depth_frames = capture_frames(
        args.camera, int(cfg.get("warmup_frames", 10)), frame_count, frame_interval, cfg)

    rknn = RKNNLite()
    ret = rknn.load_rknn(args.model)
    if ret != 0:
        raise RuntimeError(f"加载 RKNN 模型失败: {args.model}")
    ret = rknn.init_runtime(core_mask=RKNNLite.NPU_CORE_0_1_2)
    if ret != 0:
        raise RuntimeError("初始化 RKNN runtime 失败")

    use_depth = phase0_cfg and depth_frames[0] is not None

    last_frame = frames[-1]
    last_detections = []
    all_assigned = []
    try:
        for i, frame in enumerate(frames):
            detections, _ = infer_frame(rknn, frame, cfg)
            last_detections = detections
            if use_depth:
                # 用深度+距离分配（与PT版一致）
                assigned = assign_by_depth_rknn(
                    detections, depth_frames[i], frame.shape[1], phase0_cfg)
            else:
                assigned = assign_detections_to_points(detections, frame.shape[1], scan_regions)
            all_assigned.append(assigned)
    finally:
        rknn.release()

    point_types = vote_all_boxes(all_assigned)
    target_zone = args.target_zone
    plan = format_box_results(point_types, target_zone, type_zone_map, pickup_map)

    pickup_points = [bn for bn, bt in point_types.items() if type_zone_map.get(bt, -1) == target_zone]

    h, w = last_frame.shape[:2]
    type_colors = cfg.get("type_colors", {})
    debug_path = Path(args.config).parent / cfg.get("debug_image", "box_detector_debug.jpg")
    draw_debug(last_frame, last_detections, debug_path, type_colors=type_colors)

    result = {"success": len(pickup_points) > 0, "target_zone": target_zone,
              "pickup_points": pickup_points, "pickup_count": len(pickup_points),
              "frames": len(frames), "debug_image": str(debug_path)}
    print("BOX_SCAN_JSON=" + json.dumps(result, ensure_ascii=False))
    return result


def assign_by_depth_rknn(detections, depth_frame, image_width, phase_cfg):
    """RKNN版：通过距离+x位置分配箱子编号"""
    first_dist = phase_cfg.get("first_row_dist", 2.0)
    first_tol = phase_cfg.get("first_row_tol", 0.8)
    second_dist = phase_cfg.get("second_row_dist", 3.0)
    second_tol = phase_cfg.get("second_row_tol", 0.8)
    layout = phase_cfg.get("layout", {})
    first_row = layout.get("first_row", [9, 10, 11, 12])
    second_row = layout.get("second_row", [5, 6, 7, 8])

    # 合并重复
    det_list = merge_detections(detections, 0.3)

    assigned = {}
    n_cols_first = len(first_row)
    n_cols_second = len(second_row)

    for det in det_list:
        # 获取距离
        dist = None
        if depth_frame is not None:
            cx = int((det["box"][0] + det["box"][2]) / 2)
            cy = int((det["box"][1] + det["box"][3]) / 2)
            try:
                dist = depth_frame.get_distance(cx, cy)
            except Exception:
                pass
        if dist is None:
            continue

        # 判断排数
        row = None
        if abs(dist - first_dist) <= first_tol:
            row = "first_row"
        elif abs(dist - second_dist) <= second_tol:
            row = "second_row"
        else:
            continue

        # 判断列数
        cx_ratio = det["center"][0] / image_width
        if row == "first_row":
            col = min(int(cx_ratio * n_cols_first), n_cols_first - 1)
            box_num = first_row[col]
        else:
            col = min(int(cx_ratio * n_cols_second), n_cols_second - 1)
            box_num = second_row[col]

        if box_num in assigned:
            if det["score"] > assigned[box_num]["score"]:
                assigned[box_num] = det
        else:
            assigned[box_num] = det

    return assigned


# ========================================================================================
# single 模式
# ========================================================================================

def run_detector(args):
    cfg = load_config(args.config)
    frame_count = int(args.frames if args.frames is not None else cfg.get("confirm_frames", 5))
    frame_interval = int(cfg.get("confirm_frame_interval", 1))
    frames, _ = capture_frames(args.camera, int(cfg.get("warmup_frames", 10)), frame_count, frame_interval, cfg)

    rknn = RKNNLite()
    ret = rknn.load_rknn(args.model)
    if ret != 0:
        raise RuntimeError(f"加载 RKNN 模型失败: {args.model}")
    ret = rknn.init_runtime(core_mask=RKNNLite.NPU_CORE_0_1_2)
    if ret != 0:
        raise RuntimeError("初始化 RKNN runtime 失败")

    last_frame = frames[-1]
    last_detections, single_results = [], []
    try:
        for frame in frames:
            last_detections, single_box = infer_frame(rknn, frame, cfg)
            single_results.append(single_box)
    finally:
        rknn.release()

    voted_type, single_box, vote_stats = vote_single_box(single_results)
    type_colors = cfg.get("type_colors", {})
    debug_path = Path(args.save_debug) if args.save_debug else Path(args.config).parent / cfg.get("debug_image", "box_detector_debug.jpg")
    draw_debug(last_frame, last_detections, debug_path, single_box=single_box, type_colors=type_colors)

    result = {"type": voted_type, "detection": single_box, "frames": len(frames),
              "votes": {k: {"count": v["count"], "avg_score": v["score_sum"] / max(1, v["count"]),
                            "best_score": v["best"]["score"]} for k, v in vote_stats.items()},
              "debug_image": str(debug_path)}
    print("BOX_TYPE_JSON=" + json.dumps(result, ensure_ascii=False))


# ========================================================================================
# main
# ========================================================================================

def main():
    base_dir = Path(__file__).resolve().parent

    parser = argparse.ArgumentParser(description="Material box detector (RKNN, RK3588)")
    parser.add_argument("--model", default=str(base_dir / "model" / "best.rknn"),
                        help="RKNN 模型路径")
    parser.add_argument("--config", default=str(base_dir / "box_detector_config.json"))
    parser.add_argument("--camera", type=int, default=None)
    parser.add_argument("--save-debug", default="")
    parser.add_argument("--mode", choices=["single", "scan_all"], default="single")
    parser.add_argument("--frames", type=int, default=None)
    parser.add_argument("--target-zone", type=int, default=0)
    parser.add_argument("--field-side", choices=["left", "right"], default="left")
    args = parser.parse_args()

    cfg = load_config(args.config)
    if args.camera is None:
        args.camera = int(cfg.get("camera_id", 0))

    if args.mode == "scan_all":
        run_scan_all(args)
    else:
        run_detector(args)


if __name__ == "__main__":
    main()