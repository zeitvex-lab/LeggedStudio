import pickle

import numpy as np
pn = [0.5,0.5,0.5,.5,0.11549135,  0.72885522, -1.17123964,  0.02767567,  0.57620288 ,-1.3708175,  0.06587868 , 0.65840279 ,-1.23590205, -0.05726506 , 0.70591571 ,-1.30014827]
# pn = np.array([0.49491, 0.53393, 0.49912, 0.46997, -0.12721, 0.07675, -0.95545, -0.25301, 0.18682, -1.14403, -0.19362, 0.14030, -0.77823, -0.09528, 0.05437, -0.97596])

# 使用pickle从文件加载数组  
with open('weight_dataV.pkl', 'rb') as f:  
    allresult = pickle.load(f)  


PNtoKCweight = allresult['PNtoKCweight']
activate_KC_dims = allresult['activate_KC_dims']
KCtoMBONweight = allresult['KCtoMBONweight']
def cal_action(PN, PNtoKCweight, activate_KC_dims, KCtoMBONweight):
    KC = PN @ PNtoKCweight
    sorted_indices = np.argsort(KC)[::-1]  
    inactivate_indices = sorted_indices[activate_KC_dims:]  
    KC[inactivate_indices] = 0
    action = KC @ KCtoMBONweight
    return action

a = cal_action(pn,PNtoKCweight,activate_KC_dims,KCtoMBONweight)
print(a * 0.0167)