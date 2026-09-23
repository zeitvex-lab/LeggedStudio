import argparse
import pickle
from mpi4py import MPI
from motion_imitation.envs import env_builder as env_builder
import os
import numpy as np
from tqdm import tqdm

from motion_imitation.robots import robot_config
# python3 -m motion_imitation.examples.test_env_gui --robot_type=A1 --motor_control_mode=Position --on_rack=True
# python3 -m motion_imitation.examples.test_env_gui --robot_type=Laikago --motor_control_mode=Position --on_rack=True
# python3 -m motion_imitation.examples.test_env_gui --robot_type=A1 --motor_control_mode=Torque --on_rack=True
# python3 -m motion_imitation.examples.test_env_gui --robot_type=Laikago --motor_control_mode=Torque --on_rack=True
ENABLE_ENV_RANDOMIZER = True

arg_parser = argparse.ArgumentParser()
arg_parser.add_argument("--seed", dest="seed", type=int, default=None)
arg_parser.add_argument("--mode", dest="mode", type=str, default="test")
arg_parser.add_argument("--motion_file", dest="motion_file", type=str, default="motion_imitation/data/motions/dog_pace.txt")
arg_parser.add_argument("--visualize", dest="visualize", action="store_true", default=True)
arg_parser.add_argument("--output_dir", dest="output_dir", type=str, default="output")
arg_parser.add_argument("--num_test_episodes", dest="num_test_episodes", type=int, default=None)
arg_parser.add_argument("--model_file", dest="model_file", type=str, default="")
arg_parser.add_argument("--total_timesteps", dest="total_timesteps", type=int, default=2e8)
arg_parser.add_argument("--int_save_freq", dest="int_save_freq", type=int, default=0) # save intermediate model every n policy steps

args = arg_parser.parse_args()

num_procs = MPI.COMM_WORLD.Get_size()
os.environ["CUDA_VISIBLE_DEVICES"] = '-1'

enable_env_rand = ENABLE_ENV_RANDOMIZER and (args.mode != "test")

with open('weight_data.pkl', 'rb') as f:  
    allresult = pickle.load(f) 
    
PNtoKCweight = allresult['PNtoKCweight']
activate_KC_dims = allresult['activate_KC_dims']
KCtoMBONweight = allresult['KCtoMBONweight']

env = env_builder.build_laikago_env( motor_control_mode = robot_config.MotorControlMode.POSITION, enable_rendering=args.visualize)
o = env.reset()
env.render(mode='rgb_array')

# print('o[\'IMU\']:',o['IMU'],o['LastAction'],o['MotorAngle'])
# o_PN = np.append(o[:4], o[12:24])
PN = np.append(o['IMU'],o['MotorAngle'])

def cal_action(PN, PNtoKCweight, activate_KC_dims, KCtoMBONweight):
    KC = PN @ PNtoKCweight
    sorted_indices = np.argsort(KC)[::-1]  
    inactivate_indices = sorted_indices[activate_KC_dims:]  
    KC[inactivate_indices] = 0
    action = KC @ KCtoMBONweight
    return action

action = cal_action(PN, PNtoKCweight, activate_KC_dims, KCtoMBONweight)
# action *= 0
i = 0
# while i:
while True:
    # action = env.action_space.sample()
    
    o, r, d, _ = env.step(action)
    PN = np.append(o['IMU'],o['MotorAngle'])
    PN *= 0.001
    action = cal_action(PN, PNtoKCweight, activate_KC_dims, KCtoMBONweight)
    action *= 1e-10
    env.render(mode='rgb_array')
    # if i%100==0:
        # env.reset()
    print(r,d)
        # break
    i += 1
env.close()
