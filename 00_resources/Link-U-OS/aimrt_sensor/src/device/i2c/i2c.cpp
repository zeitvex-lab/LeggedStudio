// Copyright (c) 2025, AgiBot Inc.
// All rights reserved.

#include "i2c.hpp"
#include <cstdint>

namespace aima {
namespace sensors {
namespace device {

int i2c_read(std::string dev, uint8_t addr, uint16_t reg, uint8_t *data,
             int len) {
  // 打开I2C总线设备
  int file = open(dev.c_str(), O_RDWR);
  if (file < 0) {
    return 1;
  }

  // 准备写入数据（两个0x00）
  uint8_t write_buffer[2] = {static_cast<uint8_t>((reg >> 8) & 0xFF),
                             static_cast<uint8_t>(reg & 0xFF)};

  // 构建复合I2C消息（先写后读）
  struct i2c_msg messages[2] = {{// 写消息
                                 .addr = addr,
                                 .flags = 0, // 写操作
                                 .len = sizeof(write_buffer),
                                 .buf = write_buffer},
                                {// 读消息
                                 .addr = addr,
                                 .flags = I2C_M_RD, // 读操作
                                 .len = (uint16_t)len,
                                 .buf = data}};

  struct i2c_rdwr_ioctl_data ioctl_data = {.msgs = messages, .nmsgs = 2};

  // 执行I2C事务
  if (ioctl(file, I2C_RDWR, &ioctl_data) < 0) {
    close(file);
    return 2;
  }

  close(file);
  return 0;
}

int i2c_write(std::string dev, uint8_t addr, uint16_t reg, uint8_t value) {
  // 打开I2C总线设备
  int file = open(dev.c_str(), O_RDWR);
  if (file < 0) {
    return 1;
  }

  // 准备写入数据（3个字节）
  uint8_t write_buffer[3] = {static_cast<uint8_t>((reg >> 8) & 0xFF),
                             static_cast<uint8_t>(reg & 0xFF), value};

  // 构建I2C写消息
  struct i2c_msg message = {.addr = addr, // 设备地址
                            .flags = 0,   // 写操作标志
                            .len = sizeof(write_buffer),
                            .buf = write_buffer};

  struct i2c_rdwr_ioctl_data ioctl_data = {
      .msgs = &message, // 消息数组指针
      .nmsgs = 1        // 消息数量
  };

  // 执行I2C写操作
  if (ioctl(file, I2C_RDWR, &ioctl_data) < 0) {
    close(file);
    return 2;
  }

  close(file);
  return 0;
}

} // namespace device
} // namespace sensors
} // namespace aima