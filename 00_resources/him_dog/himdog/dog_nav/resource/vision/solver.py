#!/usr/bin/env python3
# ========================================================================================
# solver.py — 任务赛算术题 OCR 识别 + mod4 计算 + 语音播报
# ========================================================================================
#
# 主流程（每步一行精简输出，方便 navigation_dog 解析 + 人看）:
#   [1] OCR 启动
#   [2] 拍照完成
#   [3] 识别式子为: 3+5=
#   [4] 结果为: 8 (mod4 = 0)
#   [5] 播报中: 0.wav
#   [PROBLEM_RESULT_JSON=...]  ← 供 navigation_dog 解析（必输出）
#
# 相机: 优先 d435i_stream 共享内存（比赛时相机被 streamer 独占），读不到回退直接开 D435i
# 音频: sudo aplay -D plughw:2,0（板载声卡，plughw 自动重采样）
# OCR:  PaddleOCR（自适应新旧版 API）

import os
import re
import json

import cv2
import numpy as np

try:
    import pyrealsense2 as rs
    HAS_REALSENSE = True
except ImportError:
    HAS_REALSENSE = False

try:
    from d435i_client import FrameClient, ShmUnavailable
    HAS_SHM_CLIENT = True
except ImportError:
    HAS_SHM_CLIENT = False


def _build_ocr():
    """PaddleOCR 自适应构造（兼容新旧版 API）。"""
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


class MathSolver:
    def __init__(self):
        # 板载声卡（plughw 自动重采样，sudo 取权限）
        self.alsa_device = "plughw:2,0"
        self.audio_files = {
            0: "./audio/0.wav",
            1: "./audio/1.wav",
            2: "./audio/2.wav",
            3: "./audio/3.wav",
        }
        print("[1] OCR 启动")
        self.ocr = _build_ocr()

    # --------------------------------------------------
    # 拍照（优先 shm，回退直接开 D435i）
    # --------------------------------------------------
    def capture_image(self, save_path="./math_question.jpg", skip_frames=20):
        if HAS_SHM_CLIENT:
            try:
                client = FrameClient()
                for _ in range(max(1, skip_frames)):
                    client.grab_color()
                frame = client.grab_color()
                cv2.imwrite(save_path, frame)
                print(f"[2] 拍照完成（shm）: {save_path}")
                return save_path
            except ShmUnavailable:
                pass

        if not HAS_REALSENSE:
            raise Exception("未安装 pyrealsense2，且 shm 不可用")

        pipeline = rs.pipeline()
        config = rs.config()
        config.enable_stream(rs.stream.color, 1920, 1080, rs.format.bgr8, 30)
        try:
            pipeline.start(config)
            for _ in range(max(1, skip_frames)):
                pipeline.wait_for_frames()
            color_frame = pipeline.wait_for_frames().get_color_frame()
            if not color_frame:
                raise Exception("D435i 未读到 color 帧")
            frame = np.asanyarray(color_frame.get_data())
            cv2.imwrite(save_path, frame)
            print(f"[2] 拍照完成（D435i）: {save_path}")
            return save_path
        finally:
            try:
                pipeline.stop()
            except Exception:
                pass

    # --------------------------------------------------
    # 预处理 + OCR + 计算
    # --------------------------------------------------
    def solve(self, image_path):
        # 预处理
        src = cv2.imread(image_path)
        if src is None:
            raise Exception(f"无法读取 {image_path}")
        gray = cv2.cvtColor(src, cv2.COLOR_BGR2GRAY)
        blurred = cv2.GaussianBlur(gray, (3, 3), 0)
        binary = cv2.adaptiveThreshold(
            blurred, 255, cv2.ADAPTIVE_THRESH_GAUSSIAN_C, cv2.THRESH_BINARY, 21, 10)
        pre_path = "./preprocessed.jpg"
        cv2.imwrite(pre_path, binary)

        # OCR
        if hasattr(self.ocr, "predict"):
            out = self.ocr.predict(pre_path)
            text = self._extract_new(out)
        else:
            out = self.ocr.ocr(pre_path, cls=False)
            text = self._extract_old(out)

        if not text:
            raise Exception("OCR 未识别到文本")

        print(f"[3] 识别式子为: {text}")

        # 计算
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
            raise Exception(f"无法从 '{text}' 提取表达式")

        exp = match.group(1).replace(" ", "")
        raw = int(eval(exp))
        mod4 = raw % 4
        print(f"[4] 结果为: {raw} (mod4 = {mod4})")
        return text, exp, raw, mod4

    @staticmethod
    def _extract_old(result):
        if not result or not result[0]:
            return ""
        return "".join(str(line[1][0]) for line in result[0])

    @staticmethod
    def _extract_new(result):
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
            return MathSolver._extract_old(result)
        except Exception:
            return ""

    # --------------------------------------------------
    # 播报
    # --------------------------------------------------
    def play_audio(self, mod4):
        wav = self.audio_files.get(mod4)
        if not wav or not os.path.exists(wav):
            print(f"[5] 播报跳过: {wav} 不存在")
            return
        print(f"[5] 播报中: {wav}")
        os.system(f"sudo aplay -D {self.alsa_device} {wav} > /dev/null 2>&1")

    # --------------------------------------------------
    # 完整流程
    # --------------------------------------------------
    def run(self):
        try:
            img_path = self.capture_image()
            text, exp, raw, mod4 = self.solve(img_path)

            result = {
                "success": True,
                "expression": exp,
                "raw_result": raw,
                "mod4": mod4,
                "ocr_text": text,
            }
            print("PROBLEM_RESULT_JSON=" + json.dumps(result, ensure_ascii=False))

            self.play_audio(mod4)

        except Exception as e:
            print(f"[异常] {e}")
            result = {"success": False, "error": str(e)}
            print("PROBLEM_RESULT_JSON=" + json.dumps(result, ensure_ascii=False))


if __name__ == "__main__":
    MathSolver().run()
