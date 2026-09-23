---
pipeline_tag: robotics
tags:
- leggedrobot
---

🐾 Quadruped Locomotion Policies

This repository contains learned locomotion policies for quadruped robots, trained and deployed in the Isaac Lab simulation environment.

🚀 Overview

Each locomotion policy takes as input an observation vector and outputs joint torques to control the robot.

    Flat Terrain Policy

        Observation: 48-dimensional vector

        Action: 12-dimensional torque command

    Rough Terrain Policy

        Observation: 48-dimensional base observation + 187-dimensional height map
        (Total: 235 dimensions)

        Action: 12-dimensional torque command

These policies are suitable for deployment in simulation or transfer to real hardware, and were trained to ensure robustness and agility on both flat and uneven terrains.
🤖 Supported Robots

Each policy is associated with a specific quadruped robot. You can find more information about each robot and its associated policy below:

    Hound-1 – https://dynamicrobot.kaist.ac.kr/hound1.html
    
    Hound-2 - https://dynamicrobot.kaist.ac.kr/hound2.html


📂 Structure

policies/
├── hound1/
│   ├── flat.pt
│   └── ...
├── hound2/
│   ├── flat.pt
│   └── ...

📎 Notes

    Policies are exported in PyTorch format (.pt) and ONNX format (.onnx).

    They are compatible with the Isaac Lab environment and can be loaded into simulation scripts directly.

    Contact torque-level control is used across all policies.

🛠️ Usage

Example code snippets or instructions for loading the policy into Isaac Lab can be provided here.