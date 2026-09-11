# CTS Isaac Gym method extension

Loaded only with `--method cts`. In each rollout the first three quarters of
A1 environments train with privileged teacher observations, while the final
quarter train with the history-conditioned student policy. The shared actor is
optimized from both partitions; the history encoder is supervised from the
student partition only. Inference always uses the deterministic student path.

This is an A1 engineering port of the LeggedGym-Ex CTS structure, not a
strict Go2 paper reproduction.
