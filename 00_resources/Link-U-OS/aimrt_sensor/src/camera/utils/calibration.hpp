// Copyright (c) 2025, AgiBot Inc.
// All rights reserved.

#pragma once

#include "src/device/i2c/i2c.hpp"

#include <string>
#include <cstdint>

using namespace aima::sensors::device;

namespace aima {
namespace sensors {
namespace camera {

typedef struct {
    std::string sn;
    uint32_t width;
    uint32_t height;
    uint8_t model;
    double fx;
    double fy;
    double cx;
    double cy;
    double k1;
    double k2;
    double p1;
    double p2;
    double k3;
    double k4;
    double k5;
    double k6;
} isx031c_calibration_data;

int get_isx031c_raw(std::string dev, uint8_t addr, uint32_t flash_addr, uint8_t* data, int len);
int get_isx031c_calibration(std::string dev, uint8_t addr, isx031c_calibration_data* data);

}
}
}