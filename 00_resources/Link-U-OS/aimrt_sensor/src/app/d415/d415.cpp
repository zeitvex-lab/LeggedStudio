// Copyright (c) 2025, AgiBot Inc.
// All rights reserved.

#include "src/all_in_one/include/aimrte.h"
#include "src/d415/module/d415_module.hpp"

int main(int argc, char **argv) {
    aimrte::Cfg cfg(argc, argv, "d415_usb");
    cfg.WithDefaultLogger().WithDefaultRos();

    return aimrte::Run(cfg, {{"d415", std::make_shared<::aima::sensor::camera::d415::D415Mod>()}});
}