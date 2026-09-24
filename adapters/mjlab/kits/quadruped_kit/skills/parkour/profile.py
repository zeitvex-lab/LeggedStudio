"""越障（parkour / PIE）技能的族级配方常量与机型身份。

**技能级常量**（足端槽位序、配方级关节限位上界、PIE 的那几处阈值）保留为默认值 ——
同族机型共享同一套配方；**机型身份**（`task_id` / `experiment_name`）与**相机档位**
（`registry/cameras.json` 的档位 id，见 `camera.py`）由机型侧传入：

* go2：`Unitree-Go2-PIE` / `go2_pie` + 档位 `pie-front-depth-106x60`（本试点）；
* 第二台机型待接：档位要它自己的声明（位姿/内参没标定就不能编，见族文件 gap）。

## 为什么"足端槽位序"是配方常量而不是从契约派生

源配方（PIE）把足端张量按 **FR/FL/RR/RL** 排（对角交织序，IsaacGym 惯例），
而族约定（`binding.foot_geoms` / `contacts.foot_legs`）按契约 `morphology.leg_ids`
（= FL/FR/RL/RR）。两者**不是同一个序**，而"迁移前后逐字段等价"要求保留源序，
故这里显式声明，并在装配时校验"它恰好是本机型腿标记的一个排列"——
换了腿命名的机型在这里**报错退出**，而不是悄悄换序（换序会改变步态相位的时基）。
"""

from dataclasses import dataclass

#: PIE 配方默认的足端槽位序（对角交织；必须是本机型腿标记的一个排列）。
PIE_FOOT_SLOT_ORDER: tuple[str, ...] = ("FR", "FL", "RR", "RL")

#: PIE 配方里大腿（族角色 `hip_pitch`）关节限位的**上界**：出厂上界允许大腿转到
#: "反关节支路"（机械上可达、越障上不可用），此处统一收紧到 2.2 rad 排除该支路；
#: **下界保留 MJCF 真值**（不作弊改物理，只排除不可用支路）。
PIE_THIGH_JOINT_UPPER_LIMIT: float = 2.2

#: 相机 FOV 域随机化的扫幅（度，水平向；源配方 ±1.0°）。
PIE_CAMERA_FOV_SWEEP_DEG: float = 1.0


@dataclass(frozen=True)
class ParkourProfile:
    """一台机型在这个族级越障技能里的身份 + 配方常量。"""

    task_id: str
    experiment_name: str
    #: `registry/cameras.json` 里的**深度相机档位 id**（本技能唯一的相机真值入口）。
    camera_profile: str
    #: 足端槽位序（四足 = 四条腿；见模块 docstring 的说明）。
    foot_slot_order: tuple[str, ...] = PIE_FOOT_SLOT_ORDER
    #: 大腿关节限位上界（rad）；下界取 MJCF。
    thigh_joint_upper_limit: float = PIE_THIGH_JOINT_UPPER_LIMIT
