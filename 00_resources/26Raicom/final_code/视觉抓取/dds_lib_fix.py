# dds_lib_fix.py — 在任何 `import cyclonedds` 之前先导入本模块，
# 预加载匹配版本的 CycloneDDS 核心库，解决：
#
#   ImportError: _clayer...so: undefined symbol: ddsi_sertype_v0
#
# 原因：ROS 2 (Foxy) 的 LD_LIBRARY_PATH 把旧版 libddsc.so.0
# (/opt/ros/foxy/lib/aarch64-linux-gnu, CycloneDDS 0.7.0) 排在了匹配版本
# /usr/local/lib/libddsc.so.0 (CycloneDDS 0.10.x) 之前。cyclonedds 0.10.2
# 的 _clayer.so 按 NEEDED libddsc.so.0 解析时命中了旧库，缺少 0.10.2
# 才引入的 ddsi_sertype_v0 符号。
#
# 修复：用 RTLD_GLOBAL 把正确版本先载入进程。动态加载器在解析 _clayer.so
# 的 NEEDED libddsc.so.0 时，会优先复用已按同名 SONAME 载入的库，从而跳过
# LD_LIBRARY_PATH 的搜索。
#
# 用法（脚本顶部、cyclonedds 导入之前）：
#   import dds_lib_fix
import ctypes

ctypes.CDLL("/usr/local/lib/libddsc.so.0", mode=ctypes.RTLD_GLOBAL)
