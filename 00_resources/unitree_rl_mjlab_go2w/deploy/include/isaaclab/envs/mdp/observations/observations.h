// Copyright (c) 2025, Unitree Robotics Co., Ltd.
// All rights reserved.

#pragma once

#include <algorithm>
#include <chrono>
#include <cmath>
#include <stdexcept>
#include <string>
#include <vector>

#include "FSM/FSMState.h"
#include "isaaclab/envs/manager_based_rl_env.h"

namespace isaaclab
{
namespace mdp
{

REGISTER_OBSERVATION(base_ang_vel)
{
    auto & asset = env->robot;
    auto & data = asset->data.root_ang_vel_b;
    return std::vector<float>(data.data(), data.data() + data.size());
}

REGISTER_OBSERVATION(projected_gravity)
{
    auto & asset = env->robot;
    auto & data = asset->data.projected_gravity_b;
    return std::vector<float>(data.data(), data.data() + data.size());
}

REGISTER_OBSERVATION(joint_pos)
{
    auto & asset = env->robot;
    std::vector<float> data;

    std::vector<int> joint_ids;
    try {
        joint_ids = params["asset_cfg"]["joint_ids"].as<std::vector<int>>();
    } catch(const std::exception& e) {
    }

    if(joint_ids.empty())
    {
        data.resize(asset->data.joint_pos.size());
        for(size_t i = 0; i < asset->data.joint_pos.size(); ++i)
        {
            data[i] = asset->data.joint_pos[i];
        }
    }
    else
    {
        data.resize(joint_ids.size());
        for(size_t i = 0; i < joint_ids.size(); ++i)
        {
            data[i] = asset->data.joint_pos[joint_ids[i]];
        }
    }

    return data;
}

REGISTER_OBSERVATION(joint_pos_rel)
{
    auto & asset = env->robot;
    std::vector<float> data;

    data.resize(asset->data.joint_pos.size());
    for(size_t i = 0; i < asset->data.joint_pos.size(); ++i) {
        data[i] = asset->data.joint_pos[i] - asset->data.default_joint_pos[i];
    }

    try {
        std::vector<int> joint_ids;
        joint_ids = params["asset_cfg"]["joint_ids"].as<std::vector<int>>();
        if(!joint_ids.empty()) {
            std::vector<float> tmp_data;
            tmp_data.resize(joint_ids.size());
            for(size_t i = 0; i < joint_ids.size(); ++i){
                tmp_data[i] = data[joint_ids[i]];
            }
            data = tmp_data;
        }
    } catch(const std::exception& e) {
    
    }

    return data;
}

REGISTER_OBSERVATION(joint_vel_rel)
{
    auto & asset = env->robot;
    auto data = asset->data.joint_vel;

    try {
        const std::vector<int> joint_ids = params["asset_cfg"]["joint_ids"].as<std::vector<int>>();

        if(!joint_ids.empty()) {
            data.resize(joint_ids.size());
            for(size_t i = 0; i < joint_ids.size(); ++i) {
                data[i] = asset->data.joint_vel[joint_ids[i]];
            }
        }
    } catch(const std::exception& e) {
    }
    return std::vector<float>(data.data(), data.data() + data.size());
}

REGISTER_OBSERVATION(wheel_joint_pos_rel)
{
    return joint_pos_rel(env, params);
}

REGISTER_OBSERVATION(wheel_joint_vel_rel)
{
    return joint_vel_rel(env, params);
}

REGISTER_OBSERVATION(last_action)
{
    auto data = env->action_manager->action();
    return std::vector<float>(data.data(), data.data() + data.size());
};

REGISTER_OBSERVATION(velocity_commands)
{
    std::vector<float> obs(3);
    const std::string command_name = params["command_name"] ? params["command_name"].as<std::string>() : "base_velocity";
    const auto command_cfg = env->cfg["commands"][command_name];
    if (!command_cfg)
    {
        throw std::runtime_error("Command config not found for '" + command_name + "'");
    }

    const auto ranges = command_cfg["ranges"];
    if (!ranges)
    {
        throw std::runtime_error("Command ranges missing for '" + command_name + "'");
    }

    const std::string input_source = command_cfg["input_source"].as<std::string>("joystick");

    // CLI override: --command takes priority over deploy.yaml
    if (param::command_mode == "patrol")
    {
        static auto patrol_start = std::chrono::steady_clock::now();
        const float speed = 0.5f;
        const float distance = 2.0f;
        const float half_period = distance / speed;

        float elapsed = std::chrono::duration<float>(
            std::chrono::steady_clock::now() - patrol_start).count();
        float phase = std::fmod(elapsed, 2.0f * half_period);
        obs[0] = (phase < half_period) ? speed : -speed;
        obs[1] = 0.0f;
        obs[2] = 0.0f;
    }
    else if (param::command_mode == "fixed")
    {
        obs[0] = param::command_override[0];
        obs[1] = param::command_override[1];
        obs[2] = param::command_override[2];
    }
    else if (input_source == "fixed")
    {
        if (!command_cfg["fixed_command"] || command_cfg["fixed_command"].size() != 3)
        {
            throw std::runtime_error(
                "commands." + command_name + ".fixed_command must be a 3-element list [vx, vy, wz]"
            );
        }
        const auto fixed = command_cfg["fixed_command"].as<std::vector<float>>();
        obs[0] = fixed[0];
        obs[1] = fixed[1];
        obs[2] = fixed[2];
    }
    else if (input_source == "joystick")
    {
        auto & joystick = env->robot->data.joystick;
        obs[0] = joystick->ly();
        obs[1] = -joystick->lx();
        obs[2] = -joystick->rx();
    }
    else if (input_source == "keyboard")
    {
        if (!FSMState::keyboard)
        {
            throw std::runtime_error(
                "Keyboard command source requested but FSMState::keyboard is null."
            );
        }

        const auto keyboard_cfg = command_cfg["keyboard"];
        const float key_lin_x = keyboard_cfg && keyboard_cfg["lin_vel_x"]
                                    ? keyboard_cfg["lin_vel_x"].as<float>()
                                    : ranges["lin_vel_x"][1].as<float>();
        const float key_lin_y = keyboard_cfg && keyboard_cfg["lin_vel_y"]
                                    ? keyboard_cfg["lin_vel_y"].as<float>()
                                    : std::max(
                                        std::abs(ranges["lin_vel_y"][0].as<float>()),
                                        std::abs(ranges["lin_vel_y"][1].as<float>())
                                    );
        const float key_ang_z = keyboard_cfg && keyboard_cfg["ang_vel_z"]
                                    ? keyboard_cfg["ang_vel_z"].as<float>()
                                    : std::max(
                                        std::abs(ranges["ang_vel_z"][0].as<float>()),
                                        std::abs(ranges["ang_vel_z"][1].as<float>())
                                    );

        const std::string key = FSMState::keyboard->key();
        if (key == "w" || key == "up")
        {
            obs[0] = key_lin_x;
        }
        else if (key == "s" || key == "down")
        {
            obs[0] = -key_lin_x;
        }
        else if (key == "a")
        {
            obs[1] = key_lin_y;
        }
        else if (key == "d")
        {
            obs[1] = -key_lin_y;
        }
        else if (key == "q" || key == "left")
        {
            obs[2] = key_ang_z;
        }
        else if (key == "e" || key == "right")
        {
            obs[2] = -key_ang_z;
        }
    }
    else
    {
        throw std::runtime_error(
            "Unsupported input_source='" + input_source + "' for commands." + command_name +
            ". Expected 'joystick', 'fixed', or 'keyboard'."
        );
    }

    obs[0] = std::clamp(obs[0], ranges["lin_vel_x"][0].as<float>(), ranges["lin_vel_x"][1].as<float>());
    obs[1] = std::clamp(obs[1], ranges["lin_vel_y"][0].as<float>(), ranges["lin_vel_y"][1].as<float>());
    obs[2] = std::clamp(obs[2], ranges["ang_vel_z"][0].as<float>(), ranges["ang_vel_z"][1].as<float>());

    return obs;
}

REGISTER_OBSERVATION(gait_phase)
{
    float period = params["period"].as<float>();
    float delta_phase = env->step_dt * (1.0f / period);

    env->global_phase += delta_phase;
    env->global_phase = std::fmod(env->global_phase, 1.0f);

    std::vector<float> obs(2);
    obs[0] = std::sin(env->global_phase * 2 * M_PI);
    obs[1] = std::cos(env->global_phase * 2 * M_PI);
    return obs;
}

}
}
