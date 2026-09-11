import numpy as np

# ── Go2 EDU front camera (1920×1080 fisheye) ──────────────────────────────────
# Lens model: fisheye (equidistant / kannala-brandt)
# Calibration matrix K
DOG_K_FISHEYE = np.array([
    [1248.95099, 0.0,        957.862066],
    [0.0,        1247.94633, 530.821641],
    [0.0,        0.0,        1.0       ]
], dtype=np.float64)

# Distortion coefficients [k1, k2, k3, k4]
DOG_D_FISHEYE = np.array(
    [-0.04634571, -0.21551315, 0.45541731, -0.37792435],
    dtype=np.float64
)

DOG_IMG_W = 1920
DOG_IMG_H = 1080
