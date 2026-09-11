from legged_gym.utils.helpers import class_to_dict
from .environment import register_task
from .runner import TeacherStudentRunner
class TeacherStudentPlugin:
    method_id="teacher_student"
    def register_task(self,task_registry,requested_task):
        if requested_task not in ("a1","a1_teacher_student"): raise ValueError("teacher_student currently supports only Unitree A1")
        return register_task(task_registry)
    def make_runner(self,task_registry,env,task,runtime_args,*,log_dir,checkpoint):
        _,cfg=task_registry.get_cfgs(task); r=TeacherStudentRunner(env,class_to_dict(cfg),log_dir=log_dir,device=env.device)
        if checkpoint is not None:r.load(str(checkpoint))
        return r,cfg
PLUGIN=TeacherStudentPlugin()
