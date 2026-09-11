import torch
import torch.nn as nn
from torch.distributions import Normal
def mlp(inp,hidden,out):
    layers=[]
    for width in hidden: layers += [nn.Linear(inp,width),nn.ELU()]; inp=width
    layers.append(nn.Linear(inp,out)); return nn.Sequential(*layers)
class ActorCriticTS(nn.Module):
    is_recurrent=False
    def __init__(self,num_actions=12,actor_obs=45,teacher_obs=99,history_dim=900,latent_dim=99,critic_obs=480, actor_hidden_dims=(256,256), critic_hidden_dims=(1024,256,128), privilege_encoder_hidden_dims=(256,128), history_encoder_hidden_dims=(256,128), history_encoder_type="MLP", **kwargs):
        super().__init__(); self.history_encoder_type=history_encoder_type; self.privilege_encoder=mlp(teacher_obs,privilege_encoder_hidden_dims,latent_dim); self.history_encoder=mlp(history_dim,history_encoder_hidden_dims,latent_dim); self.actor=mlp(actor_obs+latent_dim,actor_hidden_dims,num_actions); self.critic=mlp(critic_obs,critic_hidden_dims,1); self.std=nn.Parameter(torch.ones(num_actions)); self.distribution=None
    def act(self,obs,teacher): self.distribution=Normal(self.actor(torch.cat((obs,self.privilege_encoder(teacher)),-1)),self.std.abs()+1e-4); return self.distribution.sample()
    def act_student(self,obs,history): return self.actor(torch.cat((obs,self.history_encoder(history)),-1))
    def evaluate(self,critic): return self.critic(critic)
    def get_actions_log_prob(self,a): return self.distribution.log_prob(a).sum(-1)
    @property
    def action_mean(self): return self.distribution.mean
    @property
    def action_std(self): return self.distribution.stddev
    @property
    def entropy(self): return self.distribution.entropy().sum(-1)
    def reset(self,dones=None): pass
