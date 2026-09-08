Trained policies (.onnx exports) land here and are registered in
`simulation/config.json` under `policies`. The package ships with an empty
policy list; the observation/action contract to satisfy is documented in
`simulation/config.json` -> `policy_contract` (330-dim input = 33 single obs
x 10 history, action 8, LimX joint order).
