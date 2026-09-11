# DreamWaQ Isaac Gym method extension

DreamWaQ is loaded only when `--method dreamwaq` is supplied. The ordinary
`a1` task and default PPO runner are untouched. This implementation uses the
A1 45-dimensional proprioceptive observation, a five-frame history, a VAE
latent/explicit velocity estimator, and a privileged critic during training.
The plugin keeps PPO rollout/storage, GAE and VAE encoder optimization
isolated from the default rsl_rl package. The VAE uses the reference shared
encoder plus four independent distribution heads, and policy/VAE dimensions
are supplied from the method configuration. Link-contact labels follow the
reference order (thigh, calf, foot, base, hip). Checkpoints use the explicit
v5 architecture contract; older checkpoints are intentionally rejected.
This remains an engineering port and does not claim paper-level reproduction
numbers.
