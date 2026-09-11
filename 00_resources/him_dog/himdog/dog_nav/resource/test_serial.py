#!/usr/bin/env python3
"""
香橙派串口通信程序 - 发送舵机角度到STM32
"""
# sudo chmod 666 /dev/ttyUSB0

import serial
import time
import sys

def main():
    port = '/dev/ttyUSB0'
    baudrate = 115200
    
    try:
        print(f"正在打开串口 {port}...")
        ser = serial.Serial(port, baudrate, timeout=1)
        print(f"串口打开成功！\n")
        
        print("输入三个数值（左角度,右角度,编号），按回车发送")
        print("格式: 角度范围0~270，用英文逗号分隔")
        print("注意: 左舵机会自动转换为 270-Angle_left（对称处理）")
        print("示例: 90,120,1")
        print("输入 'q' 退出\n")
        
        while True:
            user_input = input("请输入: ").strip()
            
            if user_input.lower() == 'q':
                print("退出程序")
                break
            
            try:
                vals = [int(x) for x in user_input.split(',')]
                if len(vals) != 3:
                    print("请输入3个数值，用逗号分隔")
                    continue
                
                angle_left, angle_right, num = vals
                angle_left = 270 - angle_left
                
                cmd = f"{angle_left},{angle_right},{num}\n"
                print(f"发送: 左{angle_left}° 右{angle_right}° 编号{num}")
                ser.write(cmd.encode('ascii'))
                
            except ValueError:
                print("请输入有效的整数")
                continue
            
            time.sleep(0.2)
            
            if ser.in_waiting > 0:
                response = ser.read(ser.in_waiting)
                print(f"收到: {response.decode('utf-8', errors='ignore')}")
        
        ser.close()
        print("串口已关闭")
        
    except FileNotFoundError:
        print(f"错误：找不到串口设备 {port}")
        print("  请检查USB数据线是否连接，执行 ls /dev/ttyUSB* 查看")
        sys.exit(1)
    except PermissionError:
        print(f"错误：没有权限访问 {port}")
        print("  请执行：sudo chmod 666 /dev/ttyUSB0")
        sys.exit(1)
    except Exception as e:
        print(f"错误：{e}")
        sys.exit(1)

if __name__ == "__main__":
    main()

