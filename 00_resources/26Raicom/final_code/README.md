代码介绍：

Final_code.py	 			全流程主程序 v3（Phase1–8，存在一些小问题，我们还没有完美解决，需要你们接着完善。我们比赛出现的问题就是动作识别不好，导致扣了20分。）
迷宫.py					迷宫定序运动控制（经典步态开环动作序列），被测距模块 import
dds_lib_fix.py				DDS 库版本冲突修复（预加载正确 libddsc），几乎所有脚本顶部都 import 它
usb_blue_detect.py		USB 摄像头蓝色区域检测（Phase8 蓝色驱动前进用，含下半画面占比）
camera_preview.py		USB 摄像头 OpenCV 预览（可设手动曝光，调参用）
set_camera_exposure.sh	开机自动设置 USB 摄像头曝光 / 亮度（rc.local 调用）

赛前快速测试设备代码：
0.sh					一行命令：cd 视觉抓取 + 执行 arm_sr-control 设夹住走姿态
1.py					多路 TinyF TOF 传感器读取，与测距模块 / TOF_read.py 完全相同
2.py					RealSense D435i 深度摄像头模块，与视觉抓取 /depth_camera.py 完全相同
3.sh					USB 摄像头预览脚本（修白屏），与机身姿态 /camera_preview.sh 完全相同