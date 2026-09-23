import argparse
from mpi4py import MPI
from motion_imitation.envs import env_builder as env_builder
import os
import numpy as np
from tqdm import tqdm
import pickle  
# python3 -m motion_imitation.examples.test_env_gui --robot_type=A1 --motor_control_mode=Position --on_rack=True
# python3 -m motion_imitation.examples.test_env_gui --robot_type=Laikago --motor_control_mode=Position --on_rack=True
# python3 -m motion_imitation.examples.test_env_gui --robot_type=A1 --motor_control_mode=Torque --on_rack=True
# python3 -m motion_imitation.examples.test_env_gui --robot_type=Laikago --motor_control_mode=Torque --on_rack=True

# print(env.observation_space, env.action_space)  # Box(160,) Box(12,)
def cal_action(PN, PNtoKCweight, activate_KC_dims, KCtoMBONweight):
    KC =  PNtoKCweight @ PN.T
    sorted_indices = np.argsort(KC)[::-1]
    inactivate_indices = sorted_indices[activate_KC_dims:]
    KC[inactivate_indices] = 0
    action = KCtoMBONweight @ KC.T
    return action

if __name__=="__main__":
    DEFAULT_JOINT_POSE = np.array([0, 0.67, -1.25, 0, 0.67, -1.25, 0, 0.67, -1.25, 0, 0.67, -1.25])
    UPPER_LEG_JOINT_OFFSET = -0.6
    KNEE_JOINT_OFFSET = 0.66
    SIM_TOE_JOINT_IDS = [
        7,  # left hand
        15,  # left foot
        3,  # right hand
        11  # right foot
    ]
    SIM_HIP_JOINT_IDS = [4, 12, 0, 8]
    SIM_ROOT_OFFSET = np.array([0, 0, 0])
    SIM_TOE_OFFSET_LOCAL = [
        np.array([-0.02, 0.0, 0.0]),
        np.array([-0.02, 0.0, 0.01]),
        np.array([-0.02, 0.0, 0.0]),
        np.array([-0.02, 0.0, 0.01])
    ]

    dt = 0.1/60
    ENABLE_ENV_RANDOMIZER = True

    arg_parser = argparse.ArgumentParser()
    arg_parser.add_argument("--seed", dest="seed", type=int, default=None)
    arg_parser.add_argument("--mode", dest="mode", type=str, default="test")
    arg_parser.add_argument("--motion_file", dest="motion_file", type=str,
                            default="motion_imitation/data/motions/dog_pace.txt")
    arg_parser.add_argument("--visualize", dest="visualize", action="store_true", default=True)
    arg_parser.add_argument("--output_dir", dest="output_dir", type=str, default="output")
    arg_parser.add_argument("--num_test_episodes", dest="num_test_episodes", type=int, default=None)
    arg_parser.add_argument("--model_file", dest="model_file", type=str, default="")
    arg_parser.add_argument("--total_timesteps", dest="total_timesteps", type=int, default=2e8)
    arg_parser.add_argument("--int_save_freq", dest="int_save_freq", type=int,
                            default=0)  # save intermediate model every n policy steps

    args = arg_parser.parse_args()

    num_procs = MPI.COMM_WORLD.Get_size()
    os.environ["CUDA_VISIBLE_DEVICES"] = '-1'

    # 使用pickle从文件加载数组
    with open('weight_dataV.pkl', 'rb') as f:
        allresult = pickle.load(f)

        # PNtoKCweight = allresult['PNtoKCweight']
    # activate_KC_dims = allresult['activate_KC_dims']
    # KCtoMBONweight = allresult['KCtoMBONweight']
    #     allresult = {'weights_PN2KC_bool': weights_PN2KC,
    #                  'PN': pace[:, 3:],
    #                  'num_dim_KC_activated': num_dim_KC_activated, 'KCtoMBONweight': KCtoMBONweight}

    PNtoKCweight = allresult['weights_PN2KC_bool']
    activate_KC_dims = allresult['num_dim_KC_activated']
    KCtoMBONweight = allresult['KCtoMBONweight']

    enable_env_rand = ENABLE_ENV_RANDOMIZER and (args.mode != "test")
    env = env_builder.build_imitation_env(motion_files=[args.motion_file],
                                          num_parallel_envs=num_procs,
                                          mode=args.mode,
                                          enable_randomizer=enable_env_rand,
                                          enable_rendering=args.visualize)

    o = env.reset()
    env.render(mode='rgb_array')

    imu_quat=env._gym_env._gym_env._gym_env.robot.GetTrueBaseOrientation()
    # imu_quat = [-imu_quat[0],-imu_quat[1],-imu_quat[2],imu_quat[3]]
    observed_joints = o[48:60]
    observed_joints[np.array([1, 4, 7, 10])] -= 0.66
    observed_joints[np.array([2, 5, 8, 11])] += 0.9

    PN = np.append(imu_quat,observed_joints)

    # IMU+MotorAngle
    # PN = np.append(o[:4],o[48:60])
    # goal
    # PN = o[87:103]



    action = cal_action(PN, PNtoKCweight, activate_KC_dims, KCtoMBONweight)
    # action *= 1e-5
    i = 0
    #
    action0 = np.array([0, 0.67, -1.25, 0, 0.67, -1.25, 0, 0.67, -1.25, 0, 0.67, -1.25])
    # action0[np.array([0, 3, 6, 9])]-= 0.66
    action0[np.array([1, 4, 7, 10])] -= 0.66
    action0[np.array([2, 5, 8, 11])] += 0.9
    while True:
        # action =action0
        action = observed_joints + action * dt
        # action[np.array([1, 4, 7, 10])] += 0.66
        # action[np.array([2, 5, 8, 11])] -= 0.9

        o, r, d, _ = env.step(action)
        # print(o[:12],o[12:24],o[48:60])
        new_imu_quat = env._gym_env._gym_env._gym_env.robot.GetTrueBaseOrientation()
        # print(f'o:\n{o[84:84+19]}\nimu_quat:\n{imu_quat}')
        # print(d)

        imu_quat = env._gym_env._gym_env._gym_env.robot.GetTrueBaseOrientation()
        # imu_quat = [-imu_quat[0],-imu_quat[1],-imu_quat[2],imu_quat[3]]
        observed_joints = o[48:60]
        observed_joints[np.array([1, 4, 7, 10])] -= 0.66
        observed_joints[np.array([2, 5, 8, 11])] += 0.9
        # observed_joints = np.array([-0.12721, 0.07675, -0.95545, -0.25301, 0.18682, -1.14403, -0.19362, 0.14030, -0.77823, -0.09528, 0.05437, -0.97596])
        PN = np.append(imu_quat, observed_joints)
        # # imu_quat = [-imu_quat[0],-imu_quat[1],-imu_quat[2],imu_quat[3]]
        # delta_imu_quat = np.array(new_imu_quat) - np.array(imu_quat)
        # PN = np.append(delta_imu_quat*30,o[48:60])
        # print(imu_quat,new_imu_quat,delta_imu_quat)
        # imu_quat = new_imu_quat
        # PN = o[87:103]
        # print(f'i:{i}\naction:\n{action}\no:\n{PN}')
        # PN *= 0.01

        action = cal_action(PN, PNtoKCweight, activate_KC_dims, KCtoMBONweight)
        # action *= 0
        env.render(mode='rgb_array')
        if d:
            env.reset()
        i += 1
    env.close()
