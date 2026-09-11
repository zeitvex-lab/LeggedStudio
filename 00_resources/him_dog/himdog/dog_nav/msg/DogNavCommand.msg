# dog_nav 自定义导航命令消息
# 由导航节点发布，dog_policy_test 订阅

std_msgs/Header header

# ===== 运动控制 =====
float32 vx           # 前后速度 (m/s)，正值=前进，负值=后退
float32 vy           # 左右速度 (m/s)，正值=左移，负值=右移
float32 wz           # 偏航角速度 (rad/s)，正值=左转，负值=右转

# ===== 体高控制 =====
float32 height       # 体高命令 (m)，默认 0.25

# ===== 模型切换 =====
string model_path    # ONNX 模型路径，空字符串=不切换

# 信号量