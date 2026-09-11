代码介绍：

pick_and_place.py				Final_code中第一个平台抓取的代码
pick_and_place1.py			Final_code中转平台抓取的代码
arm_sr-control.py				机械臂 7 关节角度直接控制（命令行下发角度）（使用看”临时.txt“找到这个代码的运行示例代码就可以，或者直接打开代码看上面的注解）
arm_ik_control.py				第一个平台 机械臂 XYZ 坐标控制（IK 求解，零点 [-90,10,55,0,-61,0,60]）
arm_ik_control1.py			同上，中转平台，零点不同（[68.7,10,55,-2,-61,1,60]）		（注：宇树科技每个D1机械臂都有差别，							我的代码零点不一定适合你的机械臂，都需要你们自己去调整，而且我们机械臂运行代码也很卡，在赛场上							面看别人机械臂运行的很快，你们可以想帮法解除限制让机械臂飞起）

d1_ik_solver.py				D1 机械臂逆运动学求解器（阻尼最小二乘），被 arm_ik_control import
d1_forward_kinematics.py		D1 正运动学（URDF 参数），被 d1_ik_solver import
color_object_detector.py		RealSense 颜色物体检测 + 深度测距，被 pick_and_place import
depth_camera.py	RealSense 	D435i 封装，被 color_object_detector/pick_and_place import
中转放置.py					中转放置动作序列（夹爪松到 40°），被主程序 import
夹着走.py					机械臂摆出 "夹住走" 单姿态