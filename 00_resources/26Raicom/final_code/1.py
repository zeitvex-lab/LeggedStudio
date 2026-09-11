#!/usr/bin/env python3
"""同时读取所有 TinyF 红外测距传感器并实时刷新显示。

基于 TOF_test.py 的解析逻辑扩展为多路并发 + 动态端口检测：
- 每个传感器一个后台读线程（in_waiting + read 轮询，跨 chunk 行缓冲拆帧）；
- 线程安全共享最新读数；主线程持续刷新显示（每 0.2s）；
- **动态检测**：每 1s 扫描一次 /dev/ttyUSB*，新插上的端口自动加入读取、
  掉线的自动移除 —— 启动时没插的，后面插上也会被检测到，无需重启；
- **无数据看门狗**：打开成功但超 STALE_RECONNECT 无有效帧时强制断开重连 ——
  防"启动瞬间设备未就绪 → 整个会话卡 ----"；启动时错开各串口打开时刻，避免同时上电；
- **别名防御**：/dev/tinyf_* 别名指向 bus/usb 原始节点时自动回退 /dev/ttyUSB*；
- 解析与阈值遵循 TOF_test.py（距离 > MAX_DISTANCE 视为无效）。

用法:
  python3 TOF_read3.py [port0 port1 port2 ...]   # 指定端口（不指定则动态扫描）
  Ctrl-C 退出
"""

import glob
import os
import serial
import sys
import threading
import time

# 遵循厂商参考阈值（TOF_test.py 同款）；规格书 4500，如需放宽改这里
MAX_DISTANCE = 4000
SCAN_INTERVAL = 1.0    # 端口扫描周期 (s)
REFRESH_INTERVAL = 0.2  # 显示刷新周期 (s)
STALE_RECONNECT = 0.6  # 打开后超过此时长仍无有效帧 → 强制重连唤醒（防“启动即失联”）

# sensor_id → 方向标签。稳定别名 /dev/tinyf_{方向} 映射：
#   left→0、right→1、front→2（与 tinyf_maze.py 的 SENSOR_ID 一致）
# 实测确认（2026-08-07）：ttyUSB0=左、ttyUSB1=右、ttyUSB2=前
SENSOR_LABELS = {0: "左", 1: "右", 2: "前"}


class TinyFSensor:
    """单个 TinyF 传感器：后台线程读取 + 解析 + 线程安全最新值。"""

    def __init__(self, sensor_id: int, port: str, baud_rate: int = 115200):
        self.sensor_id = sensor_id
        self.port = port
        self.baud_rate = baud_rate
        self._ser = None
        self._stop = threading.Event()
        self._thread = None
        self._linebuf = b""
        self._lock = threading.Lock()
        self._latest = None  # (distance_mm, confidence)
        self._open_fail = False

    # ---------------- 解析（沿用 TOF_test.py 规则） ----------------

    def parse_data_format(self, data_bytes: bytes):
        """解析一帧 ASCII 数据，非法或超范围返回 (None, None)。

        帧格式: <空格><距离>, <置信度>\n  (如 " 327, 61\n")
        """
        # 查找逗号分隔符位置 (0x2C)
        comma_index = -1
        for i, b in enumerate(data_bytes):
            if b == 0x2C:
                comma_index = i
                break
        if comma_index == -1:
            return None, None

        # 提取距离部分（逗号前），跳过开头空格
        start_index = 0
        while start_index < comma_index and data_bytes[start_index] == 0x20:
            start_index += 1
        distance_bytes = data_bytes[start_index:comma_index]

        # 提取置信度部分（逗号后），跳过逗号后空格，去尾部换行
        conf_start = comma_index + 1
        while conf_start < len(data_bytes) and data_bytes[conf_start] == 0x20:
            conf_start += 1
        confidence_bytes = data_bytes[conf_start:].strip()  # 去 \n / \r

        try:
            distance = int(distance_bytes.decode("ascii"))
            confidence = int(confidence_bytes.decode("ascii"))
        except ValueError:
            return None, None

        if distance > MAX_DISTANCE:
            return None, None
        return distance, confidence

    # ---------------- 生命周期 ----------------

    def start(self) -> None:
        if self._thread and self._thread.is_alive():
            return
        self._stop.clear()
        self._thread = threading.Thread(
            target=self._reader_loop, daemon=True, name=f"tinyf-s{self.sensor_id}"
        )
        self._thread.start()

    def stop(self) -> None:
        self._stop.set()
        if self._ser is not None:
            try:
                self._ser.close()
            except Exception:
                pass
        if self._thread and self._thread.is_alive():
            self._thread.join(timeout=1.0)
        self._thread = None

    # ---------------- 读线程核心 ----------------

    def _reader_loop(self) -> None:
        # 无数据看门狗：打开成功但一直收不到有效帧时，强制断开重连唤醒设备。
        # 避免"启动瞬间设备未就绪 → 打开成功却沉默 → 整个会话卡在 ----"。
        stale_since: float | None = None
        while not self._stop.is_set():
            if self._ser is None:
                try:
                    # 与厂商示例 TOF_test.py 一致：普通打开，不额外操作 DTR/RTS
                    ser = serial.Serial(
                        port=self.port, baudrate=self.baud_rate, timeout=0.3
                    )
                    ser.reset_input_buffer()
                    self._ser = ser
                    self._linebuf = b""
                    self._open_fail = False
                    stale_since = time.time()
                except (serial.SerialException, OSError) as e:
                    self._open_fail = True
                    stale_since = None
                    self._stop.wait(2.0)  # 打不开则重试，期间可响应 stop
                    continue

            try:
                got_frame = False
                n = self._ser.in_waiting
                if n:
                    chunk = self._ser.read(n)
                    self._linebuf += chunk
                    while b"\n" in self._linebuf:
                        line, self._linebuf = self._linebuf.split(b"\n", 1)
                        d, c = self.parse_data_format(line)
                        if d is not None and c is not None:
                            with self._lock:
                                self._latest = (d, c)
                            got_frame = True

                if got_frame:
                    stale_since = time.time()  # 有有效帧就刷新
                elif stale_since is not None and time.time() - stale_since > STALE_RECONNECT:
                    # 打开后一直无数据：设备可能卡在未初始化状态，强制重连一次
                    print(
                        f"\n[{self.port}] 打开 {STALE_RECONNECT:.0f}s 无数据，强制重连",
                        file=sys.stderr, flush=True,
                    )
                    self._drop_serial()
                    stale_since = None
                    self._stop.wait(0.2)  # 给设备一点恢复时间再重开，期间可响应 stop
                    continue
                else:
                    time.sleep(0.005)  # 无数据短暂让出，避免空转
            except (serial.SerialException, OSError):
                self._drop_serial()
                stale_since = None

    def _drop_serial(self) -> None:
        if self._ser is not None:
            try:
                self._ser.close()
            except Exception:
                pass
            self._ser = None

    # ---------------- 对外接口 ----------------

    def get_reading(self):
        """返回 (distance_mm, confidence) 或 None。"""
        with self._lock:
            return self._latest

    @property
    def ok(self) -> bool:
        return not self._open_fail and self.get_reading() is not None

    @property
    def state(self) -> str:
        """显示用状态：有读数→空；已打开但暂无有效帧→同步中（看门狗自动重连）；打开失败→掉线。"""
        if self.get_reading() is not None:
            return ""
        return "掉线" if self._open_fail else "同步中"


def sensor_id_from_port(port: str) -> int:
    """从端口名解析 sensor_id。

    优先按稳定别名 /dev/tinyf_{方向}：left→0、right→1、front→2（对应 SENSOR_LABELS）。
    否则按 ttyUSB 编号（ttyUSB{N}→N）回退。
    """
    name = port.rsplit("/", 1)[-1]
    for direction, sid in (("left", 0), ("right", 1), ("front", 2)):
        if name == f"tinyf_{direction}":
            return sid
    digits = "".join(c for c in name if c.isdigit())
    return int(digits) if digits else 0


def scan_ports() -> list:
    """优先扫描稳定别名 /dev/tinyf_{方向}；别名缺失或指向错误节点时回退 /dev/ttyUSB*。

    别名按方向排序（left→0, right→1, front→2），保证 sensor_id 稳定。
    仅当三个别名都解析到真实 ttyUSB* 串口时才采用；若 udev 规则装错导致别名指向
    /dev/bus/usb/0xx 原始 USB 节点，pyserial 打开后读不到数据（显示 ----），
    此时回退到 /dev/ttyUSB* 保证全部能读到。
    """
    aliases = [f"/dev/tinyf_{d}" for d in ("left", "right", "front")]
    if all(os.path.islink(a) and "ttyUSB" in os.readlink(a) for a in aliases):
        return aliases
    return sorted(glob.glob("/dev/ttyUSB*"))


def main() -> int:
    fixed = sys.argv[1:]
    sensors: dict = {}  # port -> TinyFSensor
    last_scan = 0.0
    print("Ctrl-C 退出", flush=True)
    try:
        while True:
            now = time.time()

            # 周期扫描端口，动态增删传感器
            if now - last_scan >= SCAN_INTERVAL:
                last_scan = now
                current = list(fixed) if fixed else scan_ports()
                # 移除已消失的端口
                for port in list(sensors):
                    if port not in current:
                        sensors[port].stop()
                        del sensors[port]
                # 加入新出现的端口（sensor_id 由端口号决定：ttyUSB0→0→前）
                for port in current:
                    if port not in sensors:
                        sid = sensor_id_from_port(port)
                        s = TinyFSensor(sensor_id=sid, port=port)
                        s.start()
                        sensors[port] = s
                        time.sleep(0.25)  # 错开各串口打开时刻，避免同时上电导致个别设备静默
                print("\n[扫描] 在线端口: %s" % (", ".join(sensors) or "无"), flush=True)

            # 实时刷新显示（按 sensor_id 排序，用方向标签）
            if sensors:
                parts = []
                for s in sorted(sensors.values(), key=lambda x: x.sensor_id):
                    label = SENSOR_LABELS.get(s.sensor_id, f"S{s.sensor_id}")
                    r = s.get_reading()
                    if r is None:
                        parts.append(f"{label}: {s.state}")
                    else:
                        parts.append(f"{label}: {r[0]}mm c={r[1]}")
                print("\r" + "  |  ".join(parts) + " " * 24, end="", flush=True)
            time.sleep(REFRESH_INTERVAL)
    except KeyboardInterrupt:
        print("\n退出", flush=True)
    finally:
        for s in sensors.values():
            s.stop()
    return 0


if __name__ == "__main__":
    sys.exit(main())
