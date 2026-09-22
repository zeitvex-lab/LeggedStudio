// Copyright (c) 2025, AgiBot Inc.
// All rights reserved.

#include "src/all_in_one/include/aimrte.h"
#include "src/dcw2/module/dcw2_module.hpp"

int main(int argc, char **argv) {
    aimrte::Cfg cfg(argc, argv, "dcw2_usb");
    cfg.WithDefaultLogger().WithDefaultRos();

    return aimrte::Run(cfg, {{"dcw2", std::make_shared<::aima::sensor::camera::dcw2::Dcw2Mod>()}});
}