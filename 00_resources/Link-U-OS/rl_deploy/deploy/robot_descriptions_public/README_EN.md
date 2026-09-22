# robot_descriptions_public

## Project Overview
This project provides robot description files (URDF) and related resources for visualizing robot models in a ROS2 environment. The project includes two main models: a basic model (model.urdf) and a model with fingers (model_with_finger.urdf).

## Directory Structure
- **urdf/**: Contains robot description files, including the basic model and the model with fingers.
- **mesh/**: Contains mesh resource files (.stl files) for various parts of the robot.
- **launch/**: Contains launch files for starting the visualization of the robot model in ROS2.
- **rviz/**: Contains RViz configuration files for visualizing the robot model.
- **convex/**: Contains convex hull files for collision detection.
- **build.sh**: Build script for building this package.
- **display_model.sh**: Script to launch the basic model.
- **display_model_with_finger.sh**: Script to launch the model with fingers.

## Dependencies
- ROS2
- ament_cmake

## Build Instructions
Use the following command to build this package:
```bash
./build.sh
```

## Usage
### Launching the Basic Model
Use the following command to launch the basic model:
```bash
./display_model.sh
```

### Launching the Model with Fingers
Use the following command to launch the model with fingers:
```bash
./display_model_with_finger.sh
```

## Maintainers
- Author: Yin Fulong
- Email: yinfulong@zhiyuan-robot.com

## License
This project is licensed under the BSD License. 