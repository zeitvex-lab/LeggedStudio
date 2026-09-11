#!/usr/bin/env python3
"""
test_ocr.py — D435i OCR + 物资箱检测全流程测试（相机持续开着）

和真实比赛流程一致:
  1. 启动 D435i + Foxglove 推流（相机一直开，全程推画面）
  2. OCR 识别算术题 → mod4 → 语音播报
  3. 物资箱检测 scan_all → 8 箱类型映射
  4. 两项做完后，相机保持开、继续推流，直到 Ctrl+C
     （方便你在 Foxglove 持续观察画面、调相机角度）

用法:
  python3 test/test_ocr.py                      # 默认推流 ws://0.0.0.0:8765
  python3 test/test_ocr.py --port 8765
  python3 test/test_ocr.py --no-stream          # 不推流（离线验证）
  python3 test/test_ocr.py --field-side right   # 右赛场
  python3 test/test_ocr.py --warmup 20          # OCR 拍照前丢帧数

电脑端:
  Foxglove Studio 连 ws://<上位机IP>:8765，订阅 /d435i/color
"""

import argparse
import json
import os
import re
import subprocess
import sys
import threading
import time
from pathlib import Path

import cv2
import numpy as np

# 项目路径
DOG_NAV_DIR = Path(__file__).resolve().parent.parent
VISION_DIR = DOG_NAV_DIR / "resource" / "vision"
AUDIO_DIR = VISION_DIR / "audio"
BOX_DETECTOR = VISION_DIR / "box_detector_rknn.py"


# ========================================================================================
# 持续运行的 D435i + 推流
# ========================================================================================
class FoxgloveServer:
    """Foxglove WebSocket 服务（单例，全程只开一次，避免端口冲突）。

    foxglove SDK 的 server 没有 stop 接口，重启会 'Address already in use'。
    所以把 server 和相机解耦: server 全程开一次，相机可以反复开关。
    """

    _instance = None

    @classmethod
    def get(cls, port, stream_enabled):
        if cls._instance is None:
            cls._instance = cls(port, stream_enabled)
        return cls._instance

    def __init__(self, port, stream_enabled):
        self.stream_enabled = stream_enabled
        self._foxglove = None
        self._CompressedImage = None
        self._Timestamp = None
        if stream_enabled:
            import foxglove
            from foxglove.messages import CompressedImage, Timestamp
            self._foxglove = foxglove
            self._CompressedImage = CompressedImage
            self._Timestamp = Timestamp
            foxglove.start_server(host="0.0.0.0", port=port, name="ocr-test")
            print(f"  🟢 Foxglove 推流服务: ws://0.0.0.0:{port}")
            print(f"     电脑端订阅 /d435i/color")
        else:
            print("  （推流已禁用 --no-stream）")

    def push(self, topic, image_bgr, quality=85):
        if not self.stream_enabled or self._foxglove is None:
            return
        ok, buf = cv2.imencode(".jpg", image_bgr, [cv2.IMWRITE_JPEG_QUALITY, quality])
        if not ok:
            return
        self._foxglove.log(
            topic,
            self._CompressedImage(
                timestamp=self._Timestamp.now(),
                frame_id="d435i_color",
                format="jpeg",
                data=buf.tobytes(),
            ),
        )


class D435iLive:
    """D435i 持续开，每帧推到 Foxglove；按需抓单帧给 OCR / 检测用。

    和 navigation_dog 的 d435i_stream.py 行为一致:
      - color 1920x1080 bgr8 30fps
      - 全程推 /d435i/color 到 Foxglove
      - 抓帧给下游用（OCR 取 1 张，物资箱检测调 box_detector）
    """

    def __init__(self, fg_server):
        import pyrealsense2 as rs
        self.rs = rs
        self.fg = fg_server
        self.pipeline = None

    def start(self):
        """打开 D435i"""
        rs = self.rs
        self.pipeline = rs.pipeline()
        config = rs.config()
        config.enable_stream(rs.stream.color, 1920, 1080, rs.format.bgr8, 30)
        profile = self.pipeline.start(config)
        device = profile.get_device()
        color_sensor = device.first_color_sensor()
        color_sensor.set_option(rs.option.enable_auto_exposure, 1)
        print("  🟢 D435i 已启动")

    def grab_color(self, warmup=0):
        """抓一张 color 帧（warmup>0 时先丢几帧等曝光）"""
        rs = self.rs
        for _ in range(max(0, warmup)):
            self.pipeline.wait_for_frames()
        frameset = self.pipeline.wait_for_frames()
        color_frame = frameset.get_color_frame()
        if not color_frame:
            return None
        return np.asanyarray(color_frame.get_data())

    def push_loop(self, stop_event):
        """持续推流循环，直到 stop_event 被设置"""
        rs = self.rs
        try:
            while not stop_event.is_set():
                frameset = self.pipeline.wait_for_frames()
                color_frame = frameset.get_color_frame()
                if not color_frame:
                    continue
                img = np.asanyarray(color_frame.get_data())
                self.fg.push("/d435i/color", img, quality=85)
        except Exception as e:
            print(f"  ⚠️ 推流循环异常: {e}")

    def stop(self):
        if self.pipeline is not None:
            try:
                self.pipeline.stop()
            except Exception:
                pass
            self.pipeline = None
        print("  🔴 D435i 已关闭")


# ========================================================================================
# OCR（自动适配 PaddleOCR 新旧版 API）
# ========================================================================================
def _build_ocr():
    """构造 PaddleOCR 实例，兼容新旧版参数名。"""
    from paddleocr import PaddleOCR
    import inspect

    sig_params = set(inspect.signature(PaddleOCR.__init__).parameters.keys())
    kwargs = {}
    if "use_textline_orientation" in sig_params:   # 新版（3.0+）
        kwargs["use_textline_orientation"] = False
    elif "use_angle_cls" in sig_params:            # 老版
        kwargs["use_angle_cls"] = False
    if "lang" in sig_params:
        kwargs["lang"] = "ch"
    if "show_log" in sig_params:                   # 只有老版支持
        kwargs["show_log"] = False
    return PaddleOCR(**kwargs)


def _run_ocr(ocr, image):
    """调用 OCR 推理，兼容新版 predict() 和老版 ocr()。"""
    if hasattr(ocr, "predict"):   # 新版
        return _extract_text_new(ocr.predict(image))
    return _extract_text_old(ocr.ocr(image, cls=False))   # 老版


def _extract_text_old(result):
    if not result or not result[0]:
        return ""
    return "".join(str(line[1][0]) for line in result[0])


def _extract_text_new(result):
    if not result:
        return ""
    first = result[0]
    if hasattr(first, "rec_texts") and first.rec_texts:
        return "".join(str(t) for t in first.rec_texts)
    if isinstance(first, dict):
        texts = first.get("rec_texts") or first.get("texts")
        if texts:
            return "".join(str(t) for t in texts)
    try:
        return _extract_text_old(result)
    except Exception:
        return ""


def ocr_step(live, warmup):
    """OCR 步骤: 抓一张 → 预处理 → 识别 → 算 mod4 → 播报。返回 mod4 或 None。"""
    print("\n" + "=" * 60)
    print("  ★ Step 1: OCR 识别算术题")
    print("=" * 60)

    # 抓一张
    frame = live.grab_color(warmup=warmup)
    if frame is None:
        print("  ❌ 抓帧失败")
        return None
    save_path = str(VISION_DIR / "test_ocr_capture.jpg")
    cv2.imwrite(save_path, frame)
    print(f"  ✅ 拍照: {save_path} ({frame.shape[1]}x{frame.shape[0]})")

    # 预处理
    gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
    blurred = cv2.GaussianBlur(gray, (3, 3), 0)
    binary = cv2.adaptiveThreshold(
        blurred, 255, cv2.ADAPTIVE_THRESH_GAUSSIAN_C, cv2.THRESH_BINARY, 21, 10)
    pre_path = str(VISION_DIR / "test_ocr_preprocessed.jpg")
    cv2.imwrite(pre_path, binary)
    print(f"  ✅ 预处理: {pre_path}")

    # OCR
    try:
        ocr = _build_ocr()
        text = _run_ocr(ocr, pre_path)
    except Exception as e:
        print(f"  ❌ OCR 失败: {e}")
        return None

    if not text:
        print("  ❌ OCR 未识别到文本")
        return None
    print(f"  ✅ OCR 结果: '{text}'")

    # 算 mod4
    clean = ""
    for ch in text:
        code = ord(ch)
        if 0xFF01 <= code <= 0xFF5E:
            clean += chr(code - 0xFEE0)
        else:
            clean += ch
    clean = clean.replace("×", "*").replace("x", "*").replace("X", "*")
    clean = clean.replace("÷", "/").replace("=", "").strip()
    match = re.search(r"([\d\+\-\*\/\.\(\) ]+)", clean)
    if not match:
        print(f"  ❌ 无法从 '{text}' 提取表达式")
        return None
    exp = match.group(1).replace(" ", "")
    raw = int(eval(exp))
    mod4 = raw % 4
    print(f"  表达式: {exp}")
    print(f"  计算结果: {raw}")
    print(f"  ★ mod4 = {mod4}")

    # 播报
    mp3 = AUDIO_DIR / f"{mod4}.mp3"
    if mp3.exists():
        os.system(f"sg audio -c 'mpg123 -o alsa -a plughw:2,0 {mp3}' > /dev/null 2>&1")
        print(f"  ✅ 播报: {mp3.name}")

    return mod4


# ========================================================================================
# 物资箱检测（调 box_detector_rknn.py）
# ========================================================================================
def box_detect_step(field_side, target_zone):
    """物资箱检测步骤: 调 box_detector_rknn.py scan_all，解析 8 箱类型。"""
    print("\n" + "=" * 60)
    print("  ★ Step 2: 物资箱检测 scan_all")
    print("=" * 60)

    if not BOX_DETECTOR.exists():
        print(f"  ❌ 找不到 {BOX_DETECTOR}")
        return None

    cmd = [
        sys.executable, str(BOX_DETECTOR),
        "--mode", "scan_all",
        "--target-zone", str(target_zone),
        "--field-side", field_side,
    ]
    print(f"  执行: {' '.join(cmd)}")

    try:
        # stderr 也合并到 stdout，确保看到 box_detector 的错误信息
        result = subprocess.run(cmd, capture_output=True, text=True, timeout=60)
    except subprocess.TimeoutExpired:
        print("  ❌ box_detector 超时（60s）")
        return None
    except Exception as e:
        print(f"  ❌ 执行失败: {e}")
        return None

    output = result.stdout or ""
    stderr = result.stderr or ""
    # box_detector 的 print 可能去 stderr，合并显示
    combined = output + ("\n--- stderr ---\n" + stderr if stderr.strip() else "")
    print("  --- box_detector 输出 ---")
    print(combined if combined.strip() else "(无输出)")
    print("  --- 输出结束 ---")

    if result.returncode != 0:
        print(f"  ❌ box_detector 退出码 {result.returncode}")

    # 解析 BOX_SCAN_MAP=11:food,12:tool,...
    box_map = {}
    pos = combined.find("BOX_SCAN_MAP=")
    if pos == -1:
        print("  ❌ 未输出 BOX_SCAN_MAP（看上面的输出排查 box_detector 问题）")
        return None
    map_str = combined[pos + 13:].split("\n")[0].strip()
    for entry in map_str.split(","):
        if ":" in entry:
            try:
                k, v = entry.split(":", 1)
                box_map[int(k.strip())] = v.strip()
            except Exception:
                pass

    print(f"\n  ★ 识别到 {len(box_map)} 个箱子:")
    for box_num in sorted(box_map.keys()):
        print(f"    箱{box_num:02d} → {box_map[box_num]}")
    return box_map


# ========================================================================================
# 主流程
# ========================================================================================
def main():
    parser = argparse.ArgumentParser(description="D435i OCR + 物资箱检测（相机持续开）")
    parser.add_argument("--port", type=int, default=8765, help="Foxglove WebSocket 端口")
    parser.add_argument("--no-stream", action="store_true", help="不推流")
    parser.add_argument("--field-side", choices=["left", "right"], default="left",
                        help="赛场方向")
    parser.add_argument("--warmup", type=int, default=20, help="OCR 拍照前丢帧数")
    parser.add_argument("--target-zone", type=int, default=0,
                        help="物资箱检测 target-zone（OCR 失败时用 0）")
    args = parser.parse_args()

    print("=" * 60)
    print("  ★ D435i OCR + 物资箱检测全流程测试")
    print("  相机持续开 → OCR → 物资箱检测 → 保持推流（Ctrl+C 退出）")
    print("=" * 60)

    stream_enabled = not args.no_stream

    # 检查依赖
    try:
        import pyrealsense2  # noqa: F401
    except ImportError:
        print("❌ pyrealsense2 未安装"); return 1
    try:
        from paddleocr import PaddleOCR  # noqa: F401
    except ImportError:
        print("❌ paddleocr 未安装"); return 1
    if stream_enabled:
        try:
            import foxglove  # noqa: F401
            from foxglove.messages import CompressedImage, Timestamp  # noqa: F401
        except ImportError:
            print("❌ foxglove 未安装（或用 --no-stream）"); return 1

    # 启动 Foxglove server（全程只开一次，避免端口冲突）
    fg_server = FoxgloveServer.get(args.port, stream_enabled)

    # D435i 可以反复开关（box_detector 用时停，用完重开）
    live = D435iLive(fg_server)
    stop_event = threading.Event()
    stream_thread = threading.Thread(target=_stream_worker, args=(live, stop_event), daemon=True)

    try:
        live.start()
        stream_thread.start()

        # Step 1: OCR（推流同时进行）
        mod4 = ocr_step(live, args.warmup)

        # Step 2: 物资箱检测（调独立脚本）
        # box_detector_rknn.py 会自己开 D435i，先停 live 避免冲突
        print("\n  ★ 短暂停 D435i，让 box_detector 使用相机...")
        stop_event.set()
        stream_thread.join(timeout=2.0)
        live.stop()

        box_map = box_detect_step(args.field_side, args.target_zone)

        # 重新开 D435i + 推流（foxglove server 复用，不重开）
        print("\n  ★ 重新开 D435i，保持推流（Ctrl+C 退出）...")
        live = D435iLive(fg_server)
        stop_event = threading.Event()
        live.start()
        stream_thread = threading.Thread(target=_stream_worker, args=(live, stop_event), daemon=True)
        stream_thread.start()

        # 总结
        print("\n" + "=" * 60)
        print("  ★ 全流程完成 ★")
        print("=" * 60)
        print(f"  OCR mod4: {mod4 if mod4 is not None else '失败'}")
        print(f"  物资箱: {len(box_map) if box_map else 0} 个识别")
        if box_map:
            for n in sorted(box_map):
                print(f"    箱{n:02d} → {box_map[n]}")

        # 保持推流，等 Ctrl+C
        print("\n  相机保持开 + 推流中，按 Ctrl+C 退出...")
        while True:
            time.sleep(1.0)

    except KeyboardInterrupt:
        print("\n  🔴 收到 Ctrl+C，退出...")
    except Exception as e:
        print(f"\n❌ 异常: {e}")
        import traceback
        traceback.print_exc()
    finally:
        stop_event.set()
        live.stop()

    return 0


def _stream_worker(live, stop_event):
    """推流后台线程"""
    live.push_loop(stop_event)


if __name__ == "__main__":
    sys.exit(main())
