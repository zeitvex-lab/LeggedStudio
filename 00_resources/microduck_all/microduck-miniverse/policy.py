"""Microduck 61D observation controller shared by every published policy bundle."""

JOINT_NAMES = (
    "left_hip_yaw", "left_hip_roll", "left_hip_pitch", "left_knee", "left_ankle",
    "neck_pitch", "head_pitch", "head_yaw", "head_roll",
    "right_hip_yaw", "right_hip_roll", "right_hip_pitch", "right_knee", "right_ankle",
)
DEFAULT_POSE = np.asarray((
    0.0, -0.08726646259971647, -0.457924, -0.004940, 0.452984,
    0.3490658503988659, 0.3490658503988659, 0.0, 0.0,
    0.0, 0.08726646259971647, 0.457924, 0.004940, -0.452984,
), dtype=np.float32)


def quat_to_matrix(q):
    x, y, z, w = (float(value) for value in q)
    norm = max((x * x + y * y + z * z + w * w) ** 0.5, 1e-12)
    x, y, z, w = x / norm, y / norm, z / norm, w / norm
    return np.asarray((
        (1 - 2 * (y * y + z * z), 2 * (x * y - z * w), 2 * (x * z + y * w)),
        (2 * (x * y + z * w), 1 - 2 * (x * x + z * z), 2 * (y * z - x * w)),
        (2 * (x * z - y * w), 2 * (y * z + x * w), 1 - 2 * (x * x + y * y)),
    ), dtype=np.float32)


def scalar_command(commands, command_id, default=0.0):
    value = np.asarray(commands.get(command_id, default), dtype=np.float32).reshape(-1)
    return float(value[0]) if value.size else float(default)


class MicroduckPolicy:
    physics_hz = 200
    policy_hz = 50
    publish_hz = 50
    control_loop = "policy-then-decimation"

    def initial_state(self):
        return ControllerInitialState(
            root_body_id="trunk_base",
            root_position=(0.0, 0.0, 0.12),
            root_rotation=(0.0, 0.0, 0.0, 1.0),
            joint_positions={
                      "left_hip_yaw": 0.0, "left_hip_roll": -0.08726646259971647,
                      "left_hip_pitch": -0.457924, "left_knee": -0.004940, "left_ankle": 0.452984,
                      "neck_pitch": 0.3490658503988659, "head_pitch": 0.3490658503988659,
                      "head_yaw": 0.0, "head_roll": 0.0, "right_hip_yaw": 0.0,
                      "right_hip_roll": 0.08726646259971647, "right_hip_pitch": 0.457924,
                      "right_knee": 0.004940, "right_ankle": -0.452984,
                  },
        )

    def initialize(self, context):
        self.model = context.models["policy"]
        metadata = context.manifest.get("metadata", {})
        self.mode = metadata["mode"]
        self.run_seconds = float(metadata.get("runSeconds", 0.0))
        self.phase_period = float(metadata.get("phasePeriodSeconds", 0.0))
        self.phase_end = float(metadata.get("phaseEnd", 1.0))
        self.active_steps = None
        self.previous_trigger = False
        self.last_action = np.zeros(14, dtype=np.float32)

    def joint_values(self, data, velocity=False):
        model = data.model
        values = np.asarray(data.joint_velocities if velocity else data.joint_positions, dtype=np.float32).reshape(-1)
        result = []
        for joint_id in JOINT_NAMES:
            if joint_id not in model.joint_ids:
                raise ValueError(f"Microduck joint is missing from the embodiment: {joint_id}")
            selected = values[model.joint_slice(joint_id, velocity=velocity)]
            if selected.size != 1:
                raise ValueError(f"Microduck joint is not scalar: {joint_id}")
            result.append(float(selected[0]))
        return np.asarray(result, dtype=np.float32)

    def command_block(self, step):
        command = np.zeros(13, dtype=np.float32)
        if self.mode in {"walking", "roller"}:
            command[0] = scalar_command(step.commands, "forward-speed")
            command[2] = scalar_command(step.commands, "yaw-rate")
        elif self.mode == "sitstand":
            command[0] = scalar_command(step.commands, "sit")
        elif self.mode in {"ground-pick", "roller-crouch"} and self.active_steps is not None:
            phase = self.active_steps / (self.policy_hz * self.phase_period)
            angle = 2.0 * math.pi * phase
            command[0], command[1] = math.cos(angle), math.sin(angle)
        return command

    def update_trigger(self, step):
        if self.mode not in {"ground-pick", "roller-crouch", "kick", "roulade"}:
            return
        trigger = scalar_command(step.commands, "trigger") >= 0.5
        if trigger and not self.previous_trigger:
            self.active_steps = 0
            self.last_action.fill(0)
        self.previous_trigger = trigger

    def is_active(self):
        if self.mode not in {"ground-pick", "roller-crouch", "kick", "roulade"}:
            return True
        return self.active_steps is not None

    def advance_one_shot(self):
        if self.active_steps is None:
            return
        self.active_steps += 1
        if self.mode in {"ground-pick", "roller-crouch"}:
            if self.active_steps >= self.policy_hz * self.phase_period * self.phase_end:
                self.active_steps = None
        elif self.active_steps >= self.policy_hz * self.run_seconds:
            self.active_steps = None

    def step(self, step):
        data = step.sim_data
        if data is None:
            raise ValueError("Microduck policies require canonical SimData")
        self.update_trigger(step)
        if not self.is_active():
            self.last_action.fill(0)
            return StepResult(actuation=DEFAULT_POSE.copy())

        model = data.model
        if "trunk_base" not in model.body_ids:
            raise ValueError("Microduck embodiment is missing trunk_base")
        root_index = model.body_ids.index("trunk_base")
        transforms = np.asarray(data.body_transforms, dtype=np.float32).reshape(len(model.body_ids), 7)
        velocities = np.asarray(data.body_velocities, dtype=np.float32).reshape(len(model.body_ids), 6)
        rotation = quat_to_matrix(transforms[root_index, 3:7])
        angular_velocity = rotation.T @ velocities[root_index, 3:6]
        projected_gravity = rotation.T @ np.asarray((0.0, 0.0, -1.0), dtype=np.float32)
        joint_position = self.joint_values(data) - DEFAULT_POSE
        joint_velocity = self.joint_values(data, velocity=True)
        observation = np.concatenate((
            angular_velocity, projected_gravity, joint_position, joint_velocity,
            self.last_action, self.command_block(step),
        )).astype(np.float32).reshape(1, 61)
        output = self.model.run({"obs": observation})
        action = np.asarray(output["actions"], dtype=np.float32).reshape(14)
        if not np.isfinite(action).all():
            raise ValueError("Microduck policy returned a non-finite action")
        self.last_action = action.copy()
        self.advance_one_shot()
        return StepResult(actuation=DEFAULT_POSE + action)
