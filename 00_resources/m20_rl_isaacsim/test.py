# test_isaac.py
from omni.isaac.lab.app import AppLauncher

# 初始化启动器，配置为无头单卡模式
app_launcher = AppLauncher(headless=True, device="cuda:0")
simulation_app = app_launcher.app

print("\n" + "="*50)
print("--- [SUCCESS] Isaac Sim 核心渲染引擎成功拉起！ ---")
print("="*50 + "\n")

# 模拟运行 20 步
for _ in range(20):
    simulation_app.update()

simulation_app.close()
print("正常关闭。")