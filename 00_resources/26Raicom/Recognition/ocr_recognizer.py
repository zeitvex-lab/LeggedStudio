"""
模板匹配标志识别模块
====================
使用 OpenCV 模板匹配识别比赛场地中的各类标志和标识。
(从 PaddleOCR 迁移至模板匹配)

支持的识别类型:
  - 抓取平台编号: "1号平台" / "2号平台" (模板: 1号标识.jpg / 2号标识.jpg)
  - 警示标志: "打招呼" / "伸懒腰" / "闪烁前灯3次" (对应同名模板)
  - 物资类型: 球体/正方体/三角锥/圆柱体 (需对应模板图片)

使用方式:
    # 1. 从摄像头捕获并识别
    recognizer = OCRRecognizer()
    recognizer.init_camera(camera_index=0)
    markers = recognizer.recognize_from_camera()

    # 2. 从图片文件识别
    results = recognizer.recognize_image("marker.jpg")

    # 3. 从 numpy 数组识别
    results = recognizer.recognize_frame(frame)

    # 4. 初始化 (Go2 DDS 摄像头优先)
    recognizer.init(network_interface="eth0")
"""

# === Jetson 平台修复 (必须最早执行) ===
# 问题: CPU torch 的 libgomp 需要大量静态 TLS 空间，cv2/numpy 等模块先加载
#       会抢占 TLS 导致 "cannot allocate memory in static TLS block"
# 修复: 在所有重型模块之前，预加载 torch 自带的 libgomp
import sys
import os
import ctypes
try:
    _dlopen_flags = sys.getdlopenflags()
    sys.setdlopenflags(_dlopen_flags | ctypes.RTLD_GLOBAL)
    _loaded = False
    for _base in sys.path:
        _libgomp_dir = os.path.join(_base, "torch.libs")
        if os.path.isdir(_libgomp_dir):
            for _f in os.listdir(_libgomp_dir):
                if _f.startswith("libgomp"):
                    ctypes.CDLL(os.path.join(_libgomp_dir, _f))
                    _loaded = True
                    break
        if _loaded:
            break
    if not _loaded:
        ctypes.CDLL("libgomp.so.1")
    sys.setdlopenflags(_dlopen_flags)
except (OSError, AttributeError):
    pass

# === Go2 DDS 摄像头修复 (必须在 cyclonedds 导入前) ===
# 问题: cyclonedds Python 绑定 0.10.2 需要新版 libddsc，但 ROS2 Foxy 自带
#       旧版 libddsc.so.0.7.0，链接器优先找到旧版导致 undefined symbol
# 修复: 预加载 /usr/local/lib 的新版 libddsc
try:
    sys.setdlopenflags(sys.getdlopenflags() | ctypes.RTLD_GLOBAL)
    ctypes.CDLL("/usr/local/lib/libddsc.so.0")
    sys.setdlopenflags(_dlopen_flags)
except (OSError, AttributeError):
    pass

import time
import json
import cv2
import numpy as np
from dataclasses import dataclass, field
from typing import List, Tuple, Dict, Optional
from enum import Enum

# 导入标志识别器 (YOLO 分类 + ORB 特征匹配)
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from sign_recognizer import SignRecognizer, MatchResult, imread_unicode, imwrite_unicode


# ============================================================
# 标志类型枚举
# ============================================================

class MarkerType(Enum):
    """标志类型分类"""
    PLATFORM = "platform"          # 抓取/放置平台编号
    WARNING = "warning"            # 警示标志 (动作触发)
    MATERIAL = "material"          # 物资类型
    UNKNOWN = "unknown"            # 未识别


# ============================================================
# 数据类定义
# ============================================================

@dataclass
class OCRResult:
    """单次识别结果 (兼容旧 OCR 接口)"""
    text: str                  # 识别到的文本/模板名称
    confidence: float          # 置信度 (0-1)
    box: np.ndarray            # 文本框坐标 (4x2) — 模板匹配时为矩形四点
    center: Tuple[float, float] = (0.0, 0.0)  # 文本框中心点 (x, y)
    marker_type: MarkerType = MarkerType.UNKNOWN  # 标志类型

    def __post_init__(self):
        if isinstance(self.center, tuple) or isinstance(self.center, list):
            self.center = tuple(self.center)


@dataclass
class MarkerInfo:
    """标志的语义信息"""
    marker_type: MarkerType
    category: str              # 具体类别, 如 "1号平台", "打招呼"
    sub_category: str = ""     # 子类, 如 "球体", "正方体"
    confidence: float = 0.0
    image_center: Tuple[float, float] = (0.0, 0.0)  # 标志在图像中的位置
    raw_text: str = ""         # 原始识别文本/模板名称

    def to_dict(self) -> dict:
        return {
            "type": self.marker_type.value,
            "category": self.category,
            "sub_category": self.sub_category,
            "confidence": self.confidence,
            "image_center": self.image_center,
            "raw_text": self.raw_text,
        }


# ============================================================
# 模板 → 标志映射
# ============================================================

# 模板文件名 → (MarkerType, 分类名)
TEMPLATE_MARKER_MAP = {
    "1号标识": (MarkerType.PLATFORM, "1号平台"),
    "2号标识": (MarkerType.PLATFORM, "2号平台"),
    "打招呼": (MarkerType.WARNING, "打招呼"),
    "伸懒腰": (MarkerType.WARNING, "伸懒腰"),
    "闪烁前灯三次": (MarkerType.WARNING, "闪烁前灯3次"),
    # 物资类型 (需提供对应模板图片)
    # "球体":   (MarkerType.MATERIAL, "球体"),
    # "正方体": (MarkerType.MATERIAL, "正方体"),
    # "三角锥": (MarkerType.MATERIAL, "三角锥"),
    # "圆柱体": (MarkerType.MATERIAL, "圆柱体"),
}

# 标志词典 — 用于关键词匹配 (保留兼容)
MARKER_DICTIONARY = {
    "platform": {
        "keywords": ["1号平台", "2号平台", "1号标识", "2号标识"],
        "type": MarkerType.PLATFORM,
    },
    "warning": {
        "keywords": ["打招呼", "伸懒腰", "闪烁前灯", "闪烁前灯3次", "闪烁前灯三次"],
        "type": MarkerType.WARNING,
    },
    "material": {
        "keywords": ["球体", "正方体", "三角锥", "圆柱体"],
        "type": MarkerType.MATERIAL,
    },
}

# 标志图片路径映射 (兼容旧代码)
MARKER_IMAGE_MAP = {
    "打招呼.jpg": MarkerInfo(
        marker_type=MarkerType.WARNING,
        category="打招呼",
        confidence=1.0,
        raw_text="打招呼",
    ),
    "伸懒腰.jpg": MarkerInfo(
        marker_type=MarkerType.WARNING,
        category="伸懒腰",
        confidence=1.0,
        raw_text="伸懒腰",
    ),
    "闪烁前灯三次.jpg": MarkerInfo(
        marker_type=MarkerType.WARNING,
        category="闪烁前灯3次",
        confidence=1.0,
        raw_text="闪烁前灯3次",
    ),
}


# ============================================================
# 模板匹配识别器 (替换 PaddleOCR)
# ============================================================

class OCRRecognizer:
    """基于模板匹配的标志识别器 (替换 PaddleOCR)

    负责:
    1. 从摄像头/图片中执行模板匹配识别
    2. 将匹配结果映射到已知标志类型
    3. 返回标志的语义信息和空间位置
    4. 缓存识别结果供后续步骤使用
    """

    # 默认匹配参数 (与 camera_ocr_realtime.py 保持一致)
    DEFAULT_THRESHOLD = 0.50
    DEFAULT_SCALES = [0.25, 0.45, 0.7, 1.0, 1.5]
    DEFAULT_DOWNSCALE_TARGET = 480  # 480p — 兼顾精度与速度
    DEFAULT_COARSE_TARGET = 200
    DEFAULT_FINE_TARGET = 480

    def __init__(self, lang: str = "ch", use_angle_cls: bool = True,
                 network_interface: str = None):
        """
        Args:
            lang: 识别语言 (保留兼容, 模板匹配不需要)
            use_angle_cls: 保留兼容参数
            network_interface: DDS 网络接口 (如 eth0), 用于 Go2 摄像头
        """
        self.lang = lang
        self.use_angle_cls = use_angle_cls
        self.network_interface = network_interface
        self.recognizer = None
        self._camera = None
        self._video_client = None  # Go2 DDS 摄像头
        self._use_go2_camera = False
        self._initialized = False

        # 识别历史记录
        self._history: List[OCRResult] = []
        self._marker_cache: Dict[str, MarkerInfo] = {}

        # 图像保存路径
        self._save_dir = os.path.join(os.path.dirname(os.path.abspath(__file__)), "ocr_results")
        os.makedirs(self._save_dir, exist_ok=True)

        # 匹配参数
        self.threshold = self.DEFAULT_THRESHOLD
        self.scales = list(self.DEFAULT_SCALES)

        # 多帧投票参数
        self._vote_enabled = True
        self._vote_window: List[Dict[str, float]] = []
        self._vote_size = 10          # 滑动窗口帧数
        self._vote_min_frames = 3     # 最少共识帧数
        self._vote_consensus: Dict[str, int] = {}  # 类别 → 连续帧计数

    # ============================================================
    # 初始化
    # ============================================================

    def init(self, network_interface: str = None):
        """初始化模板匹配器

        Args:
            network_interface: Go2 网络接口 (可选, 用于摄像头初始化)
        """
        if self._initialized:
            return

        if network_interface:
            self.network_interface = network_interface

        try:
            # 构建模板列表
            template_list = self._build_template_list()

            if not template_list:
                print("[TM] [ERROR] 没有找到任何模板图片")
                self._initialized = False
                return

            # 检查标注数据目录
            labeled_dirs = {}
            base_dir = os.path.dirname(os.path.abspath(__file__))
            labeled_base = os.path.join(base_dir, "photo", "labeled")
            if os.path.isdir(labeled_base):
                for name in os.listdir(labeled_base):
                    dirpath = os.path.join(labeled_base, name)
                    if os.path.isdir(dirpath):
                        labeled_dirs[name] = dirpath

            # 构建模型路径 (优先 PyTorch .pt 用于 GPU, 其次 .engine, 最后 .onnx)
            model_dir = os.path.join(base_dir, "models", "sign_classifier")
            model_path = None
            for ext in [".pt", ".engine", ".onnx"]:
                candidate = os.path.join(model_dir, f"best{ext}")
                if os.path.exists(candidate):
                    model_path = candidate
                    break

            # 检测设备
            device = "cpu"
            try:
                import torch
                if torch.cuda.is_available():
                    device = "cuda:0"
            except ImportError:
                pass

            self.recognizer = SignRecognizer(
                model_path=model_path,
                templates=template_list,
                device=device,
                threshold=self.threshold,
                use_orb=True,
                preprocess_mode="clahe",
                cls_weight=0.8,
                orb_weight=0.2,
                sliding_window=False,
            )

            self._initialized = True
            print(f"[TM] 标志识别器初始化成功, 共 {self.recognizer.get_match_count()} 个模板, "
                  f"阈值={self.threshold}")
        except Exception as e:
            print(f"[TM] [ERROR] 标志识别器初始化失败: {e}")
            self._initialized = False

    def _build_template_list(self) -> List[Tuple[str, str]]:
        """构建模板列表 [(名称, 路径), ...]"""
        base_dir = os.path.dirname(os.path.abspath(__file__))
        templates = []

        for name in TEMPLATE_MARKER_MAP:
            path = os.path.join(base_dir, f"{name}.jpg")
            if os.path.exists(path):
                templates.append((name, path))
            else:
                print(f"[TM] [WARN] 模板文件不存在: {path}")

        return templates

    def init_camera(self, camera_index: int = 0, width: int = 640, height: int = 480):
        """初始化摄像头 (Go2 DDS 优先, 回退到本地 USB)

        Args:
            camera_index: 摄像头索引 (仅本地 USB 模式使用)
            width: 分辨率宽度
            height: 分辨率高度
        """
        self.init()
        if not self._initialized:
            return False

        # 优先尝试 Go2 DDS 摄像头
        try:
            SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
            SDK_PATH = os.path.join(SCRIPT_DIR, "unitree_sdk2_python")
            if SDK_PATH not in sys.path:
                sys.path.insert(0, SDK_PATH)

            from unitree_sdk2py.core.channel import ChannelFactoryInitialize
            from unitree_sdk2py.go2.video.video_client import VideoClient

            ChannelFactoryInitialize(0, self.network_interface)
            self._video_client = VideoClient()
            self._video_client.SetTimeout(3.0)
            self._video_client.Init()

            # 预取一帧确认可用
            code, _ = self._video_client.GetImageSample()
            if code == 0:
                self._use_go2_camera = True
                print(f"[TM] 已连接 Go2 前置摄像头 (DDS)")
                return True
            else:
                print(f"[TM] Go2 摄像头返回错误码: {code}")
        except Exception as e:
            print(f"[TM] Go2 摄像头不可用: {e}")

        # 回退到本地 USB 摄像头
        self._camera = cv2.VideoCapture(camera_index)
        self._camera.set(cv2.CAP_PROP_FRAME_WIDTH, width)
        self._camera.set(cv2.CAP_PROP_FRAME_HEIGHT, height)

        if not self._camera.isOpened():
            print(f"[TM] [ERROR] 无法打开摄像头 {camera_index}")
            return False

        print(f"[TM] 本地摄像头已打开 (index={camera_index}, {width}x{height})")
        return True

    def release_camera(self):
        """释放摄像头"""
        if self._camera is not None:
            self._camera.release()
            self._camera = None
        self._video_client = None
        self._use_go2_camera = False
        print("[TM] 摄像头已释放")

    # ============================================================
    # 识别接口
    # ============================================================

    def recognize_from_camera(self, timeout: float = 5.0, save_frame: bool = True) -> List[MarkerInfo]:
        """从摄像头实时识别标志 (Go2 DDS 优先)

        Args:
            timeout: 超时时间 (秒)
            save_frame: 是否保存识别帧

        Returns:
            识别到的标志信息列表
        """
        if self._use_go2_camera:
            return self._recognize_from_go2(timeout, save_frame)

        if not self._camera or not self._camera.isOpened():
            print("[TM] [ERROR] 摄像头未打开, 请先调用 init_camera()")
            return []

        print(f"[TM] 开始识别 (超时 {timeout}s)...")
        start_time = time.time()

        while time.time() - start_time < timeout:
            ret, frame = self._camera.read()
            if not ret:
                print("[TM] [WARN] 读取帧失败")
                continue

            results = self.recognize_frame(frame, save=save_frame)

            if results:
                print(f"[TM] 识别到 {len(results)} 个标志:")
                for r in results:
                    print(f"  - [{r.marker_type.value}] {r.category} "
                          f"(置信度: {r.confidence:.2f}, 位置: {r.image_center})")
                return results

            time.sleep(0.1)

        print("[TM] 超时, 未识别到标志")
        return []

    def _recognize_from_go2(self, timeout: float = 5.0, save_frame: bool = True) -> List[MarkerInfo]:
        """通过 Go2 DDS 视频流识别"""
        print(f"[TM] Go2 摄像头识别中 (超时 {timeout}s)...")
        start_time = time.time()

        while time.time() - start_time < timeout:
            code, data = self._video_client.GetImageSample()
            if code != 0:
                time.sleep(0.1)
                continue

            # Go2 返回 JPEG 编码的图像
            image_data = np.frombuffer(bytes(data), dtype=np.uint8)
            frame = cv2.imdecode(image_data, cv2.IMREAD_COLOR)
            if frame is None:
                continue

            results = self.recognize_frame(frame, save=save_frame)
            if results:
                print(f"[TM] 识别到 {len(results)} 个标志:")
                for r in results:
                    print(f"  - [{r.marker_type.value}] {r.category} "
                          f"(置信度: {r.confidence:.2f}, 位置: {r.image_center})")
                return results

            time.sleep(0.1)

        print("[TM] 超时, 未识别到标志")
        return []

    def recognize_image(self, image_path: str, save_result: bool = True) -> List[MarkerInfo]:
        """从图片文件识别标志

        Args:
            image_path: 图片路径
            save_result: 是否保存标注结果图

        Returns:
            识别到的标志信息列表
        """
        self.init()
        if not self._initialized:
            return []

        if not os.path.exists(image_path):
            print(f"[TM] [ERROR] 图片不存在: {image_path}")
            return []

        frame = imread_unicode(image_path, cv2.IMREAD_COLOR)
        if frame is None:
            print(f"[TM] [ERROR] 无法读取图片: {image_path}")
            return []

        results = self.recognize_frame(frame, save=save_result, save_path=image_path)
        return results

    def _recognize_multi_region(self, frame: np.ndarray) -> List:
        """
        多区域识别 — 全帧 + 中心裁剪 + 滑动窗口，
        取置信度最高的结果。
        """
        h, w = frame.shape[:2]
        all_results = []

        # 1. 全帧
        results = self.recognizer.match(frame)
        all_results.extend(results)

        # 2. 中心正方形裁剪 (覆盖画面中央)
        s = min(h, w)
        cx, cy = w // 2, h // 2
        for scale in [1.0, 0.75, 0.5]:
            ss = int(s * scale)
            x1 = max(0, cx - ss // 2)
            y1 = max(0, cy - ss // 2)
            x2 = min(w, x1 + ss)
            y2 = min(h, y1 + ss)
            if x2 - x1 > 100 and y2 - y1 > 100:
                crop = frame[y1:y2, x1:x2]
                crop_results = self.recognizer.match(crop)
                for r in crop_results:
                    # 偏移坐标回原图
                    new_r = type(r)(
                        template_name=r.template_name,
                        confidence=r.confidence,
                        position=(r.position[0] + x1, r.position[1] + y1),
                        size=r.size,
                        cls_confidence=r.cls_confidence,
                        orb_confidence=r.orb_confidence,
                        num_inliers=r.num_inliers,
                    )
                    all_results.append(new_r)

        # 3. 四角滑动窗口 (处理标志不在中央的情况)
        stride = min(w, h) // 3
        win_size = int(min(w, h) * 0.6)
        for y in range(0, h - win_size + 1, stride):
            for x in range(0, w - win_size + 1, stride):
                roi = frame[y:y + win_size, x:x + win_size]
                roi_results = self.recognizer.match(roi)
                for r in roi_results:
                    new_r = type(r)(
                        template_name=r.template_name,
                        confidence=r.confidence,
                        position=(r.position[0] + x, r.position[1] + y),
                        size=r.size,
                        cls_confidence=r.cls_confidence,
                        orb_confidence=r.orb_confidence,
                        num_inliers=r.num_inliers,
                    )
                    all_results.append(new_r)

        # NMS: 按模板名去重，保留最高置信度
        if not all_results:
            return []

        best = {}
        for r in all_results:
            key = r.template_name
            if key not in best or r.confidence > best[key].confidence:
                best[key] = r
        return list(best.values())

    def recognize_frame(self, frame: np.ndarray, save: bool = True,
                        save_path: str = None) -> List[MarkerInfo]:
        """
        从图像帧执行模板匹配并映射到标志类型

        Args:
            frame: BGR 格式图像 (numpy array)
            save: 是否保存标注结果
            save_path: 原图路径 (用于命名输出文件)

        Returns:
            识别到的 MarkerInfo 列表
        """
        if frame is None or frame.size == 0:
            return []

        if not self._initialized:
            self.init()
        if not self._initialized or self.recognizer is None:
            return []

        # 中心正方形裁剪 — 训练数据是这样准备的
        h, w = frame.shape[:2]
        s = min(h, w)
        cx, cy = w // 2, h // 2
        cropped = frame[cy - s // 2:cy + s // 2, cx - s // 2:cx + s // 2]

        # 执行标志识别
        match_results = self.recognizer.match(cropped)

        if not match_results:
            if save:
                self._save_frame(frame, "no_match_found")
            return []

        # 转换为 MarkerInfo
        marker_infos = []
        for mr in match_results:
            # 构建 OCRResult (兼容旧接口)
            x, y = mr.position
            w, h = mr.size
            box = np.array([
                [x, y],
                [x + w, y],
                [x + w, y + h],
                [x, y + h],
            ], dtype=np.float32)
            center_x = float(x + w / 2)
            center_y = float(y + h / 2)
            center = (center_x, center_y)

            ocr_result = OCRResult(
                text=mr.template_name,
                confidence=mr.confidence,
                box=box,
                center=center,
            )
            self._history.append(ocr_result)

            # 映射到已知标志类型
            marker = self._classify_marker(ocr_result, center)
            if marker:
                marker_infos.append(marker)

        # NMS: 按模板名去重 (同模板只保留最高置信度)
        marker_infos = self._deduplicate_by_category(marker_infos)

        # 保存标注结果
        if save and marker_infos:
            label = os.path.basename(save_path).split(".")[0] if save_path else "frame"
            timestamp = int(time.time() * 1000)
            # 绘制标注
            vis = frame.copy()
            for mr in match_results:
                x, y = mr.position
                w, h = mr.size
                cv2.rectangle(vis, (x, y), (x + w, y + h), (0, 255, 0), 2)
                label_text = f"{mr.template_name} {mr.confidence:.2f}"
                cv2.putText(vis, label_text, (x, y - 5),
                             cv2.FONT_HERSHEY_SIMPLEX, 0.5, (0, 255, 0), 1)
            self._save_frame(vis, f"{label}_{timestamp}")

        return marker_infos

    def _classify_marker(self, result: OCRResult,
                         image_center: Tuple[float, float]) -> Optional[MarkerInfo]:
        """将模板匹配结果分类为已知标志类型"""
        name = result.text.strip()
        conf = result.confidence

        if conf < self.threshold:
            return None

        # 查找模板映射
        for tmpl_name, (mtype, category) in TEMPLATE_MARKER_MAP.items():
            if tmpl_name == name or name in tmpl_name or tmpl_name in name:
                return MarkerInfo(
                    marker_type=mtype,
                    category=category,
                    confidence=conf,
                    image_center=image_center,
                    raw_text=name,
                )

        # 模糊匹配: 遍历词典关键词
        for cat_key, config in MARKER_DICTIONARY.items():
            for keyword in config["keywords"]:
                if keyword in name or name in keyword:
                    return MarkerInfo(
                        marker_type=config["type"],
                        category=keyword,
                        sub_category=name,
                        confidence=conf * 0.9,  # 模糊匹配略微降权
                        image_center=image_center,
                        raw_text=name,
                    )

        # 未匹配到已知类型
        if conf > self.threshold:
            result.marker_type = MarkerType.UNKNOWN
        return None

    @staticmethod
    def _deduplicate_by_category(markers: List[MarkerInfo]) -> List[MarkerInfo]:
        """按类别去重 — 同 category 只保留最高置信度"""
        best = {}
        for m in markers:
            key = m.category
            if key not in best or m.confidence > best[key].confidence:
                best[key] = m
        return list(best.values())

    # ============================================================
    # 多帧投票
    # ============================================================

    def _vote_and_filter(self, markers: List[MarkerInfo]) -> List[MarkerInfo]:
        """
        多帧投票过滤 — 减少单帧误识别。

        策略:
          - 维护最近 N 帧的滑动窗口
          - 每帧记录识别到的类别及置信度
          - 只有连续出现 >= vote_min_frames 帧的类别才输出
          - 输出时取窗口内平均置信度
        """
        if not self._vote_enabled:
            return markers

        # 更新滑动窗口
        frame_vote = {m.category: m.confidence for m in markers}
        self._vote_window.append(frame_vote)
        if len(self._vote_window) > self._vote_size:
            self._vote_window.pop(0)

        # 更新连续帧计数
        current_categories = set(frame_vote.keys())
        for cat in list(self._vote_consensus.keys()):
            if cat in current_categories:
                self._vote_consensus[cat] += 1
            else:
                if self._vote_consensus[cat] <= 1:
                    del self._vote_consensus[cat]
                else:
                    self._vote_consensus[cat] -= 1

        for cat in current_categories:
            if cat not in self._vote_consensus:
                self._vote_consensus[cat] = 1

        # 筛选：至少连续出现 vote_min_frames 帧
        filtered = []
        for m in markers:
            consensus_count = self._vote_consensus.get(m.category, 0)
            if consensus_count >= self._vote_min_frames:
                # 计算窗口内平均置信度
                window_confs = [
                    fv.get(m.category, 0.0) for fv in self._vote_window
                    if m.category in fv
                ]
                avg_conf = sum(window_confs) / len(window_confs) if window_confs else m.confidence
                m.confidence = avg_conf
                filtered.append(m)

        return filtered

    def scan_all_markers(self) -> List[MarkerInfo]:
        """扫描所有已知标志 (预加载模板对应的标志信息)"""
        all_markers = []

        for tmpl_name, (mtype, category) in TEMPLATE_MARKER_MAP.items():
            info = MarkerInfo(
                marker_type=mtype,
                category=category,
                confidence=1.0,
                raw_text=tmpl_name,
            )
            all_markers.append(info)
            print(f"[TM] 预加载: {tmpl_name} -> {category}")

        # 也保留 MARKER_IMAGE_MAP 中的条目
        for filename, info in MARKER_IMAGE_MAP.items():
            if info.category not in [m.category for m in all_markers]:
                all_markers.append(info)

        self._marker_cache = {m.category: m for m in all_markers}
        print(f"[TM] 扫描完成, 共 {len(all_markers)} 个标志")
        return all_markers

    # ============================================================
    # 查询接口 (兼容旧 OCR API)
    # ============================================================

    def get_platform_info(self) -> Optional[MarkerInfo]:
        """获取最近识别的平台信息"""
        for result in reversed(self._history):
            for tmpl_name, (mtype, category) in TEMPLATE_MARKER_MAP.items():
                if mtype == MarkerType.PLATFORM and tmpl_name == result.text:
                    return MarkerInfo(
                        marker_type=MarkerType.PLATFORM,
                        category=category,
                        confidence=result.confidence,
                        image_center=result.center,
                        raw_text=result.text,
                    )
        return None

    def get_warning_info(self) -> Optional[MarkerInfo]:
        """获取最近识别的警示标志"""
        for result in reversed(self._history):
            for tmpl_name, (mtype, category) in TEMPLATE_MARKER_MAP.items():
                if mtype == MarkerType.WARNING and tmpl_name == result.text:
                    return MarkerInfo(
                        marker_type=MarkerType.WARNING,
                        category=category,
                        confidence=result.confidence,
                        image_center=result.center,
                        raw_text=result.text,
                    )
        return None

    def get_material_info(self) -> Optional[MarkerInfo]:
        """获取最近识别的物资类型"""
        for result in reversed(self._history):
            for tmpl_name, (mtype, category) in TEMPLATE_MARKER_MAP.items():
                if mtype == MarkerType.MATERIAL and tmpl_name == result.text:
                    return MarkerInfo(
                        marker_type=MarkerType.MATERIAL,
                        category=category,
                        confidence=result.confidence,
                        image_center=result.center,
                        raw_text=result.text,
                    )
        return None

    def get_latest_results(self, marker_type: MarkerType = None,
                           limit: int = 1) -> List[OCRResult]:
        """获取最新的识别结果"""
        results = list(reversed(self._history))
        if marker_type:
            results = [r for r in results if r.marker_type == marker_type]
        return results[:limit]

    def clear_history(self):
        """清空识别历史和投票状态"""
        self._history.clear()
        self._vote_window.clear()
        self._vote_consensus.clear()
        print("[TM] 识别历史已清空")

    # ============================================================
    # 保存
    # ============================================================

    def _save_frame(self, frame: np.ndarray, label: str):
        """保存标注帧"""
        timestamp = time.strftime("%Y%m%d_%H%M%S")
        filename = f"{label}_{timestamp}.jpg"
        filepath = os.path.join(self._save_dir, filename)
        imwrite_unicode(filepath, frame)
        print(f"[TM] 结果已保存: {filepath}")

    def save_results_json(self, filepath: str = None):
        """将所有识别结果保存为 JSON"""
        if filepath is None:
            timestamp = time.strftime("%Y%m%d_%H%M%S")
            filepath = os.path.join(self._save_dir, f"results_{timestamp}.json")

        data = {
            "timestamp": time.time(),
            "total_results": len(self._history),
            "markers": [],
            "ocr_history": [
                {"text": r.text, "confidence": r.confidence,
                 "center": r.center, "type": r.marker_type.value}
                for r in self._history
            ],
        }

        with open(filepath, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=2)
        print(f"[TM] 结果已保存到: {filepath}")

        return filepath


# ============================================================
# 便捷函数
# ============================================================

def quick_ocr(image_path: str) -> List[Dict]:
    """快速模板匹配识别 (单行代码调用)"""
    rec = OCRRecognizer()
    results = rec.recognize_image(image_path)
    return [r.to_dict() for r in results]


def quick_camera_ocr(timeout: float = 3.0, camera_index: int = 0) -> List[Dict]:
    """快速摄像头识别"""
    rec = OCRRecognizer()
    rec.init_camera(camera_index=camera_index)
    results = rec.recognize_from_camera(timeout=timeout)
    rec.release_camera()
    return [r.to_dict() for r in results]


# ============================================================
# 测试入口
# ============================================================

if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(description="模板匹配标志识别工具")
    parser.add_argument("--image", type=str, help="识别图片文件")
    parser.add_argument("--camera", type=int, default=0, help="摄像头索引 (仅本地 USB)")
    parser.add_argument("--interface", type=str, default=None, help="Go2 DDS 网络接口 (如 eth0)")
    parser.add_argument("--timeout", type=float, default=5.0, help="摄像头识别超时时间 (秒)")
    parser.add_argument("--scan", action="store_true", help="扫描所有已知标志")
    parser.add_argument("--threshold", type=float, default=None, help="匹配阈值 (默认 0.55)")
    args = parser.parse_args()

    recognizer = OCRRecognizer(network_interface=args.interface)
    if args.threshold is not None:
        recognizer.threshold = args.threshold

    if args.scan:
        recognizer.init()
        markers = recognizer.scan_all_markers()
        recognizer.save_results_json()

    elif args.image:
        results = recognizer.recognize_image(args.image)
        print(f"\n识别到 {len(results)} 个标志:")
        for r in results:
            print(f"  类型: {r.marker_type.value}")
            print(f"  内容: {r.category}")
            print(f"  置信度: {r.confidence:.2f}")
            print(f"  位置: {r.image_center}")
            print()

    else:
        # 摄像头实时识别 (Go2 DDS 优先)
        if recognizer.init_camera(args.camera):
            try:
                results = recognizer.recognize_from_camera(timeout=args.timeout)
                print(f"\n识别到 {len(results)} 个标志:")
                for r in results:
                    print(f"  {r.to_dict()}")
            finally:
                recognizer.release_camera()
