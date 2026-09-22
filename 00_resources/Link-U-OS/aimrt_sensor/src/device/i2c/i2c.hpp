// Copyright (c) 2025, AgiBot Inc.
// All rights reserved.

# pragma once

#include <fcntl.h>
#include <unistd.h>
#include <sys/ioctl.h>
#include <linux/i2c-dev.h>
#include <linux/i2c.h>
#include <cstdint>
#include <iostream>
#include <cerrno>
#include <cstring>

namespace aima {
namespace sensors {
namespace device {

int i2c_read(std::string dev, uint8_t addr, uint16_t reg, uint8_t *data, int len);
int i2c_write(std::string dev, uint8_t addr, uint16_t reg, uint8_t value);

}
}
}