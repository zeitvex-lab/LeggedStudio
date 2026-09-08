Trained policies (.onnx exports) land here and are registered in
`simulation/config.json` under `policies`. The package ships with an empty
policy list; the observation/action contract to satisfy is documented in
`simulation/config.json` -> `policy_contract` (135-dim input = 27 single obs
x 5 history, action 6, LimX joint order).
