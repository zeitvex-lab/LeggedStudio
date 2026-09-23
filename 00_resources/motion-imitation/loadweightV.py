import pickle  
import numpy as np
  
# 使用pickle从文件加载数组  
with open('weight_dataV.pkl', 'rb') as f:  
    allresult = pickle.load(f)  
PN = allresult['PN']
weights_PN2KC_bool = allresult['weights_PN2KC_bool']
num_dim_KC_activated = allresult['num_dim_KC_activated']
KCtoMBONweight = allresult['KCtoMBONweight']
# goal = allresult["goal"]
joint_angle = PN[:, 4:]
goal_joint_angle = np.vstack((PN[1:, 4:] ,PN[:1, 4:]))
goal_joint_velocity = ((goal_joint_angle - joint_angle) / 0.01667)
KC = (weights_PN2KC_bool @ PN.T).T

print(goal_joint_velocity[0])

sorted_indices = np.argsort(KC)
inactivate_indices = sorted_indices[:, num_dim_KC_activated:,]  
KC[np.arange(KC.shape[0])[:, None], inactivate_indices] = 0
MBON = (KCtoMBONweight@KC.T).T

# sorted_indices = np.argsort(KC, axis=1)[:, ::-1]  
# inactivate_indices = sorted_indices[:, activate_KC_dims:]  
# KC[np.arange(KC.shape[0])[:, None], inactivate_indices] = 0
# MBON = KC @ KCtoMBONweight
# print(goal)
print(MBON[0])

