# RoboLab MJLab patches

RoboLab keeps framework-specific behavior changes in the corresponding backend
bundle. The A1 velocity binding requires the action manager to honor an explicit
joint order for actuated joints; the bundled MJLab implementation now forwards
`BaseActionCfg.preserve_order` through `find_joints_by_actuator_names`.

This is a backward-compatible change: existing configurations retain their
natural MJCF joint order because `preserve_order` defaults to `False`.
