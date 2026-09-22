// Copyright (c) 2025, AgiBot Inc.
// All rights reserved.

#include "calibration.hpp"

namespace aima {
namespace sensors {
namespace camera {

int get_isx031c_calibration(std::string dev, uint8_t addr,
                            isx031c_calibration_data *data) {
  // get first 256bytes
  uint8_t data_buffer[256];
  int ret = get_isx031c_raw(dev, addr, 0x00080000, data_buffer, 256);
  if (ret < 0) {
    return ret;
  }
  // parse data
  uint16_t *width_ptr = (uint16_t *)&data_buffer[2];
  uint16_t *height_ptr = (uint16_t *)&data_buffer[4];
  uint8_t model = data_buffer[0x64];
  double *fx_ptr = (double *)&data_buffer[0x65];
  double *fy_ptr = (double *)&data_buffer[0x6D];
  double *cx_ptr = (double *)&data_buffer[0x75];
  double *cy_ptr = (double *)&data_buffer[0x7D];
  uint32_t k1_base = 0x85;
  if (model == 2) {
    k1_base = 0xC5;
  } else if (model == 3) {
    k1_base = 0xE5;
  }
  double *k1_ptr = (double *)&data_buffer[k1_base];
  double *k2_ptr = (double *)&data_buffer[k1_base + 0x8];

  data->width = *width_ptr;
  data->height = *height_ptr;
  data->model = model;
  data->fx = *fx_ptr;
  data->fy = *fy_ptr;
  data->cx = *cx_ptr;
  data->cy = *cy_ptr;
  data->k1 = *k1_ptr;
  data->k2 = *k2_ptr;

  if (model == 1) {
    data->p1 = *((double *)&data_buffer[k1_base + 0x10]);
    data->p2 = *((double *)&data_buffer[k1_base + 0x18]);
    data->k3 = *((double *)&data_buffer[k1_base + 0x20]);
    data->k4 = *((double *)&data_buffer[k1_base + 0x28]);
    data->k5 = *((double *)&data_buffer[k1_base + 0x30]);
    data->k6 = *((double *)&data_buffer[k1_base + 0x38]);
  } else if (model == 2) {
    data->k3 = *((double *)&data_buffer[k1_base + 0x10]);
    data->k4 = *((double *)&data_buffer[k1_base + 0x18]);
  } else if (model == 3) {
    // TODO: CMei type
  }

  // get second 256bytes
  ret = get_isx031c_raw(dev, addr, 0x00080100, data_buffer, 256);
  if (ret < 0) {
    return ret;
  }
  // Convert bytes from 0x20 to 0x40 into a string
  size_t max_length = 0x20;
  size_t actual_length = 0;
  for (size_t i = 0; i < max_length; ++i) {
    if (data_buffer[0x20 + i] == 0xFF) {
      data_buffer[0x20 + i] = 0x0;
      break;
    }
    ++actual_length;
  }
  std::string sn(reinterpret_cast<char *>(&data_buffer[0x20]), actual_length);

  data->sn = sn;

  return 0;
}

int get_isx031c_raw(std::string dev, uint8_t addr, uint32_t flash_addr,
                    uint8_t *data, int len) {
  // i2ctransfer -f -y 10 w3@0x1A 0xFF 0xFF 0xF4
  if (i2c_write(dev, addr, 0xFFFF, 0xF4) < 0) {
    return -1;
  }
  usleep(100 * 1000);
  // i2ctransfer -f -y 10 w3@0x1A 0xFF 0xFF 0xF7
  if (i2c_write(dev, addr, 0xFFFF, 0xF7) < 0) {
    return -2;
  }
  usleep(100 * 1000);
  // i2ctransfer -f -y 10 w3@0x1A 0x80 0x00 0x01
  if (i2c_write(dev, addr, 0x8000, 0x01) < 0) {
    return -3;
  }
  uint8_t flash_addr_bytes[4] = {
      static_cast<uint8_t>((flash_addr >> 24) & 0xFF),
      static_cast<uint8_t>((flash_addr >> 16) & 0xFF),
      static_cast<uint8_t>((flash_addr >> 8) & 0xFF),
      static_cast<uint8_t>(flash_addr & 0xFF)};
  if (i2c_write(dev, addr, 0x8001, flash_addr_bytes[0]) < 0) {
    return -4;
  }
  if (i2c_write(dev, addr, 0x8002, flash_addr_bytes[1]) < 0) {
    return -5;
  }
  if (i2c_write(dev, addr, 0x8003, flash_addr_bytes[2]) < 0) {
    return -6;
  }
  if (i2c_write(dev, addr, 0x8004, 0x00) < 0) {
    return -7;
  }
  if (i2c_write(dev, addr, 0x8005, 0x5A) < 0) {
    return -8;
  }
  usleep(100 * 1000);
  // i2ctransfer -f -y 10 w2@0x1A 0x00 0x00 r256
  if (i2c_read(dev, addr, (uint16_t)flash_addr_bytes[3], data, len) < 0) {
    return -9;
  }
  // i2ctransfer -f -y 10 w3@0x1A 0xFF 0xFF 0xF5
  if (i2c_write(dev, addr, 0xFFFF, 0xF5) < 0) {
    return -10;
  }

  // i2ctransfer -f -y 10 w3@0x1A 0xFF 0xFF 0x00
  if (i2c_write(dev, addr, 0xFFFF, 0x00) < 0) {
    return -11;
  }

  return 0;
}

} // namespace camera
} // namespace sensors
} // namespace aima