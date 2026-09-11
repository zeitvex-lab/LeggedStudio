"""
基于 YOLO 分类 + ORB 特征匹配的标志识别模块
===========================================
替换缺失的 template_matcher.py，提供兼容接口。

识别管线:
  1. CLAHE 预处理 → 光照归一化
  2. YOLOv8/v11-cls 分类 → 识别标志类别
  3. ORB 特征匹配 → 空间定位 + 验证
  4. 合并置信度 → 加权融合

兼容旧 TemplateMatchResult 接口:
  - template_name: str
  - confidence: float
  - position: (x, y)
  - size: (w, h)
"""

import os
import sys
import time
import logging
from dataclasses import dataclass
from typing import List, Tuple, Dict, Optional

import cv2
import numpy as np

logger = logging.getLogger(__name__)


# ============================================================
# 工具函数
# ============================================================

def imread_unicode(path: str, flags: int = cv2.IMREAD_COLOR) -> Optional[np.ndarray]:
    """
    跨平台图片读取 (支持中文路径)。

    cv2.imread 在 Windows 上无法处理非 ASCII 路径，
    使用 np.fromfile + cv2.imdecode 替代。
    """
    try:
        data = np.fromfile(path, dtype=np.uint8)
        img = cv2.imdecode(data, flags)
        return img
    except Exception as e:
        logger.warning(f"无法读取图片: {path} ({e})")
        return None


def imwrite_unicode(path: str, img: np.ndarray,
                    params: list = None) -> bool:
    """
    跨平台图片写入 (支持中文路径)。

    cv2.imwrite 在 Windows 上无法处理非 ASCII 路径，
    使用 cv2.imencode + tofile 替代。
    """
    try:
        ext = os.path.splitext(path)[1]
        if not ext:
            ext = '.jpg'
        success, buf = cv2.imencode(ext, img, params or [])
        if success:
            buf.tofile(path)
            return True
        return False
    except Exception as e:
        logger.warning(f"无法写入图片: {path} ({e})")
        return False


# ============================================================
# 数据类 — 兼容旧 TemplateMatchResult 接口
# ============================================================

@dataclass
class MatchResult:
    """模板匹配结果 (兼容旧接口)"""
    template_name: str           # 匹配到的模板名称
    confidence: float            # 综合置信度 (0-1)
    position: Tuple[int, int]    # 边界框左上角 (x, y)
    size: Tuple[int, int]        # 边界框大小 (w, h)
    cls_confidence: float = 0.0  # 分类置信度
    orb_confidence: float = 0.0  # ORB 匹配置信度
    num_inliers: int = 0         # ORB 内点数 (调试用)


# ============================================================
# ORB 特征存储
# ============================================================

class ORBFeatureStore:
    """预计算并存储每个模板的 ORB 特征"""

    def __init__(self, n_features: int = 2000):
        self.orb = cv2.ORB_create(nfeatures=n_features)
        self._features: Dict[str, dict] = {}  # name -> {img, kp, des}

        # FLANN 参数 (LSH 用于 binary descriptors)
        index_params = dict(
            algorithm=6,        # FLANN_INDEX_LSH
            table_number=6,
            key_size=12,
            multi_probe_level=1,
        )
        search_params = dict(checks=50)
        self.flann = cv2.FlannBasedMatcher(index_params, search_params)

    def add_template(self, name: str, image_path: str):
        """添加一个模板并预计算 ORB 特征"""
        img = imread_unicode(image_path, cv2.IMREAD_GRAYSCALE)
        if img is None:
            logger.warning(f"无法读取模板图片: {image_path}")
            return
        kp, des = self.orb.detectAndCompute(img, None)
        if des is None or len(kp) < 10:
            logger.warning(f"模板 {name} 特征点不足 ({len(kp) if kp else 0})")
            return
        self._features[name] = {"img": img, "kp": kp, "des": des}
        logger.info(f"[ORB] 模板 {name}: {len(kp)} 个特征点")

    def add_template_from_array(self, name: str, img: np.ndarray):
        """从 numpy 数组添加模板"""
        if len(img.shape) == 3:
            img = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)
        kp, des = self.orb.detectAndCompute(img, None)
        if des is None or len(kp) < 10:
            logger.warning(f"模板 {name} 特征点不足")
            return
        self._features[name] = {"img": img, "kp": kp, "des": des}

    def get_template_names(self) -> List[str]:
        return list(self._features.keys())

    def match(self, frame: np.ndarray, target_class: str = None,
              lowe_ratio: float = 0.75, min_inliers: int = 12
              ) -> Optional[Tuple[str, float, np.ndarray, int]]:
        """
        对帧执行 ORB 匹配。

        Args:
            frame: BGR 或灰度图像
            target_class: 若指定，只匹配该模板 (加速)
            lowe_ratio: Lowe's ratio test 阈值
            min_inliers: 最小内点数

        Returns:
            (template_name, confidence, homography_box, num_inliers) 或 None
        """
        if len(frame.shape) == 3:
            gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
        else:
            gray = frame

        kp_frame, des_frame = self.orb.detectAndCompute(gray, None)
        if des_frame is None or len(kp_frame) < 10:
            return None

        candidates = (
            [target_class] if target_class and target_class in self._features
            else list(self._features.keys())
        )

        best_result = None
        best_inliers = 0

        for name in candidates:
            tmpl = self._features[name]
            try:
                raw_matches = self.flann.knnMatch(tmpl["des"], des_frame, k=2)
            except Exception:
                continue

            # Lowe's ratio test — 处理只有 1 个邻居的情况
            good = []
            for pair in raw_matches:
                if len(pair) == 2:
                    m, n = pair
                    if m.distance < lowe_ratio * n.distance:
                        good.append(m)
                elif len(pair) == 1:
                    good.append(pair[0])  # 唯一匹配，直接保留

            if len(good) < min_inliers:
                continue

            # 计算单应性矩阵
            src_pts = np.float32([tmpl["kp"][m.queryIdx].pt for m in good]).reshape(-1, 1, 2)
            dst_pts = np.float32([kp_frame[m.trainIdx].pt for m in good]).reshape(-1, 1, 2)

            H, mask = cv2.findHomography(src_pts, dst_pts, cv2.RANSAC, 5.0)
            if H is None:
                continue

            inliers = int(mask.sum())
            if inliers < min_inliers:
                continue

            # 将模板四角投影到帧坐标
            h, w = tmpl["img"].shape
            corners = np.float32([[0, 0], [w, 0], [w, h], [0, h]]).reshape(-1, 1, 2)
            projected = cv2.perspectiveTransform(corners, H)

            # 置信度 = 内点比例 × 匹配质量
            confidence = (inliers / len(good)) * min(1.0, inliers / 30.0)

            if inliers > best_inliers:
                best_inliers = inliers
                best_result = (name, confidence, projected, inliers)

        return best_result


# ============================================================
# 分类模型封装
# ============================================================

class YOLOClassifier:
    """YOLOv8/v11 分类模型封装，支持 PyTorch / ONNX / TensorRT"""

    def __init__(self, model_path: str = None, device: str = "cpu",
                 imgsz: int = 224, conf_threshold: float = 0.3):
        self.model_path = model_path
        self.device = device
        self.imgsz = imgsz
        self.conf_threshold = conf_threshold
        self._model = None
        self._model_type = None  # 'ultralytics' | 'onnx' | None
        self._class_names: List[str] = []
        self._loaded = False

    @property
    def class_names(self) -> List[str]:
        return self._class_names

    def load(self):
        """加载模型 (优先 ultralytics PyTorch，回退 ONNX)"""
        if self._loaded:
            return

        if self.model_path and os.path.exists(self.model_path):
            # 尝试 ultralytics
            try:
                from ultralytics import YOLO
                self._model = YOLO(self.model_path)
                # 分类模型的 names 在 predictor 中
                if hasattr(self._model, 'names') and self._model.names:
                    self._class_names = list(self._model.names.values())
                self._model_type = 'ultralytics'
                self._loaded = True
                logger.info(f"[CLS] YOLO 模型已加载: {self.model_path} "
                            f"({len(self._class_names)} 类, device={self.device})")
                return
            except Exception as e:
                logger.warning(f"[CLS] ultralytics 加载失败: {e}")

            # 尝试 ONNX Runtime
            try:
                import onnxruntime as ort
                providers = ['CUDAExecutionProvider', 'CPUExecutionProvider'] if self.device.startswith('cuda') else ['CPUExecutionProvider']
                self._model = ort.InferenceSession(self.model_path, providers=providers)
                self._model_type = 'onnx'
                self._loaded = True
                logger.info(f"[CLS] ONNX 模型已加载: {self.model_path}")
                return
            except Exception as e:
                logger.warning(f"[CLS] ONNX 加载失败: {e}")

        # 模型不存在或加载失败 → 降级为纯 ORB 模式
        logger.warning("[CLS] 无可用的分类模型，将在纯 ORB 模式下运行")
        self._loaded = True
        self._model = None
        self._model_type = None

    def classify(self, frame: np.ndarray) -> Tuple[Optional[str], float]:
        """
        分类单帧。

        Returns:
            (class_name, confidence) — 若低于阈值则 class_name 为 None
        """
        if self._model is None:
            return None, 0.0

        if self._model_type == 'ultralytics':
            return self._classify_ultralytics(frame)
        elif self._model_type == 'onnx':
            return self._classify_onnx(frame)
        return None, 0.0

    def _classify_ultralytics(self, frame: np.ndarray) -> Tuple[Optional[str], float]:
        try:
            results = self._model.predict(
                frame, imgsz=self.imgsz, device=self.device,
                verbose=False
            )
            if results and len(results) > 0:
                probs = getattr(results[0], 'probs', None)
                if probs is not None:
                    top1_idx = int(probs.top1)
                    top1_conf = float(probs.top1conf)
                    if top1_conf >= self.conf_threshold and top1_idx < len(self._class_names):
                        return self._class_names[top1_idx], top1_conf
        except Exception as e:
            logger.error(f"[CLS] 推理错误: {e}")
        return None, 0.0

    def _classify_onnx(self, frame: np.ndarray) -> Tuple[Optional[str], float]:
        try:
            import onnxruntime as ort
            # 预处理
            if len(frame.shape) == 3:
                img = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
            else:
                img = cv2.cvtColor(frame, cv2.COLOR_GRAY2RGB)
            img = cv2.resize(img, (self.imgsz, self.imgsz))
            img = img.astype(np.float32) / 255.0
            img = (img - np.array([0.485, 0.456, 0.406])) / np.array([0.229, 0.224, 0.225])
            img = np.transpose(img, (2, 0, 1))[np.newaxis, ...]

            input_name = self._model.get_inputs()[0].name
            output = self._model.run(None, {input_name: img.astype(np.float32)})
            logits = output[0][0]
            # softmax
            exp = np.exp(logits - np.max(logits))
            probs = exp / exp.sum()
            top1_idx = int(np.argmax(probs))
            top1_conf = float(probs[top1_idx])

            if top1_conf >= self.conf_threshold and top1_idx < len(self._class_names):
                return self._class_names[top1_idx], top1_conf
        except Exception as e:
            logger.error(f"[CLS] ONNX 推理错误: {e}")
        return None, 0.0


# ============================================================
# 预处理
# ============================================================

def apply_preprocessing(frame: np.ndarray, mode: str = "clahe") -> np.ndarray:
    """
    图像预处理。

    Args:
        frame: BGR 图像
        mode: "clahe" | "histeq" | "none"

    Returns:
        预处理后的 BGR 图像
    """
    if mode == "none":
        return frame
    if mode == "clahe":
        lab = cv2.cvtColor(frame, cv2.COLOR_BGR2LAB)
        l, a, b = cv2.split(lab)
        clahe = cv2.createCLAHE(clipLimit=2.0, tileGridSize=(8, 8))
        l = clahe.apply(l)
        lab = cv2.merge([l, a, b])
        return cv2.cvtColor(lab, cv2.COLOR_LAB2BGR)
    if mode == "histeq":
        ycrcb = cv2.cvtColor(frame, cv2.COLOR_BGR2YCrCb)
        y, cr, cb = cv2.split(ycrcb)
        y = cv2.equalizeHist(y)
        ycrcb = cv2.merge([y, cr, cb])
        return cv2.cvtColor(ycrcb, cv2.COLOR_YCrCb2BGR)
    return frame


# ============================================================
# 主识别器
# ============================================================

class SignRecognizer:
    """标志识别器 — YOLO 分类 + ORB 特征匹配

    替换缺失的 EnhancedTemplateMatcher，提供兼容的 match() 接口。
    """

    def __init__(
        self,
        model_path: str = None,
        template_dir: str = None,
        templates: List[Tuple[str, str]] = None,
        device: str = "cpu",
        threshold: float = 0.50,
        use_orb: bool = True,
        preprocess_mode: str = "clahe",
        cls_weight: float = 0.6,
        orb_weight: float = 0.4,
        sliding_window: bool = False,
        window_scales: List[float] = None,
    ):
        """
        Args:
            model_path: YOLO 分类模型路径 (.pt / .onnx / .engine)
            template_dir: 模板图片目录 (可选)
            templates: [(名称, 路径), ...] 模板列表 (兼容旧接口)
            device: "cpu" | "cuda:0"
            threshold: 综合置信度阈值
            use_orb: 是否启用 ORB 特征匹配
            preprocess_mode: 预处理模式 "clahe" | "histeq" | "none"
            cls_weight: 分类权重 (0-1)
            orb_weight: ORB 权重 (0-1)
            sliding_window: 是否使用滑动窗口搜索
            window_scales: 滑动窗口多尺度 (如 [0.5, 0.75, 1.0])
        """
        self.threshold = threshold
        self.use_orb = use_orb
        self.preprocess_mode = preprocess_mode
        self.cls_weight = cls_weight
        self.orb_weight = orb_weight
        self.sliding_window = sliding_window
        self.window_scales = window_scales or [0.5, 0.75, 1.0]

        # 分类器
        self.classifier = YOLOClassifier(
            model_path=model_path,
            device=device,
            conf_threshold=0.25,  # 分类用较低阈值，后续综合判断
        )
        self.classifier.load()

        # ORB 特征存储
        self.orb_store = ORBFeatureStore() if use_orb else None

        # 加载模板
        self._template_list: List[Tuple[str, str]] = []
        if templates:
            self._template_list = list(templates)
        elif template_dir and os.path.isdir(template_dir):
            for fname in os.listdir(template_dir):
                if fname.lower().endswith(('.jpg', '.jpeg', '.png')):
                    name = os.path.splitext(fname)[0]
                    path = os.path.join(template_dir, fname)
                    self._template_list.append((name, path))

        # 预加载 ORB 特征
        if self.orb_store and self._template_list:
            for name, path in self._template_list:
                self.orb_store.add_template(name, path)

    def get_match_count(self) -> int:
        """返回模板数量 (兼容旧接口)"""
        return len(self._template_list)

    def get_template_names(self) -> List[str]:
        return [name for name, _ in self._template_list]

    def match(self, frame: np.ndarray, target_class: str = None) -> List[MatchResult]:
        """
        主识别接口 — 兼容旧 EnhancedTemplateMatcher.match()

        Args:
            frame: BGR 格式图像
            target_class: 若指定，只匹配该类别

        Returns:
            MatchResult 列表 (按置信度降序)
        """
        if frame is None or frame.size == 0:
            return []

        # 预处理
        processed = apply_preprocessing(frame, self.preprocess_mode)

        # 分类
        cls_name, cls_conf = self.classifier.classify(processed)

        # ORB 匹配
        orb_name, orb_conf, orb_box, orb_inliers = None, 0.0, None, 0
        if self.use_orb and self.orb_store:
            orb_result = self.orb_store.match(
                processed,
                target_class=target_class or cls_name,
                min_inliers=10,
            )
            if orb_result:
                orb_name, orb_conf, orb_box, orb_inliers = orb_result

        # --- 决策：合并分类 + ORB ---
        results = []

        # 情况 1：分类和 ORB 都给出结果且一致
        if cls_name and orb_name and cls_name == orb_name:
            combined_conf = self.cls_weight * cls_conf + self.orb_weight * orb_conf
            if combined_conf >= self.threshold:
                x, y, w, h = self._box_to_rect(orb_box)
                results.append(MatchResult(
                    template_name=cls_name,
                    confidence=combined_conf,
                    position=(x, y),
                    size=(w, h),
                    cls_confidence=cls_conf,
                    orb_confidence=orb_conf,
                    num_inliers=orb_inliers,
                ))

        # 情况 2：分类给出结果，ORB 不同或无结果
        elif cls_name and cls_conf >= self.threshold:
            # 只用分类，位置估计在图像中心
            h, w = frame.shape[:2]
            results.append(MatchResult(
                template_name=cls_name,
                confidence=cls_conf * self.cls_weight,  # 降权（无 ORB 验证）
                position=(w // 4, h // 4),
                size=(w // 2, h // 2),
                cls_confidence=cls_conf,
                orb_confidence=0.0,
                num_inliers=0,
            ))

        # 情况 3：分类失败但 ORB 匹配成功
        elif orb_name and orb_conf >= self.threshold:
            x, y, w, h = self._box_to_rect(orb_box)
            results.append(MatchResult(
                template_name=orb_name,
                confidence=orb_conf * self.orb_weight,  # 降权（无分类验证）
                position=(x, y),
                size=(w, h),
                cls_confidence=0.0,
                orb_confidence=orb_conf,
                num_inliers=orb_inliers,
            ))

        # 情况 4：滑动窗口搜索（如果启用且上述都失败）
        if not results and self.sliding_window:
            results = self._sliding_window_match(processed)

        return results

    def _box_to_rect(self, box: np.ndarray) -> Tuple[int, int, int, int]:
        """将四点 box 转为 (x, y, w, h)"""
        if box is None:
            return 0, 0, 100, 100
        pts = box.reshape(-1, 2)
        x = int(pts[:, 0].min())
        y = int(pts[:, 1].min())
        w = int(pts[:, 0].max() - x)
        h = int(pts[:, 1].max() - y)
        return x, y, max(w, 1), max(h, 1)

    def _sliding_window_match(self, frame: np.ndarray) -> List[MatchResult]:
        """
        滑动窗口 + 多尺度搜索 (当单帧分类/ORB 不确定时使用)
        """
        if not self.use_orb or self.orb_store is None:
            return []

        h, w = frame.shape[:2]
        best_result = None

        for scale in self.window_scales:
            win_w = int(w * scale)
            win_h = int(h * scale)
            if win_w < 100 or win_h < 100:
                continue

            # 步长 = 窗口大小的 50%
            step_x = max(win_w // 2, 50)
            step_y = max(win_h // 2, 50)

            for y in range(0, h - win_h + 1, step_y):
                for x in range(0, w - win_w + 1, step_x):
                    roi = frame[y:y + win_h, x:x + win_w]
                    orb_result = self.orb_store.match(roi, min_inliers=8)
                    if orb_result:
                        name, conf, box, inliers = orb_result
                        if best_result is None or conf > best_result.confidence:
                            # 将 ROI 坐标转为全局坐标
                            bx, by, bw, bh = self._box_to_rect(box)
                            best_result = MatchResult(
                                template_name=name,
                                confidence=conf,
                                position=(x + bx, y + by),
                                size=(bw, bh),
                                orb_confidence=conf,
                                num_inliers=inliers,
                            )

        return [best_result] if best_result else []
