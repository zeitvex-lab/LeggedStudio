/**
 * MotionLoader for imitation-learning policies (LeggedSkillDeploy protocol).
 *
 * Loads a reference-motion CSV with columns
 *   [root_pos(3), root_quat_xyzw(4), dof_pos(N)]
 * (converted internally to MuJoCo's wxyz quaternion order), clips it to
 * [time_start, time_end], and provides time-interpolated joint positions /
 * velocities / root quaternion plus the deployment-specific helpers:
 *
 *  - reset(robotQuat): yaw-only alignment of the reference frame to the
 *    robot's current heading (call once when the policy starts),
 *  - motionAnchorOriB(realQuatW, refQuatW): 6-dim relative orientation
 *    (rotation matrix, first two columns flattened) used by motion
 *    tracking policies.
 *
 * Ported from LeggedSkillDeploy src/scripts/motion_loader.py
 * (upstream project itself carries no LICENSE - internal research use).
 */

export function quatNormalize(q) {
  const n = Math.hypot(q[0], q[1], q[2], q[3]) || 1.0;
  return [q[0] / n, q[1] / n, q[2] / n, q[3] / n];
}

export function quatConjugate(q) {
  return [q[0], -q[1], -q[2], -q[3]];
}

export function quatMultiply(a, b) {
  const [aw, ax, ay, az] = a;
  const [bw, bx, by, bz] = b;
  return [
    aw * bw - ax * bx - ay * by - az * bz,
    aw * bx + ax * bw + ay * bz - az * by,
    aw * by - ax * bz + ay * bw + az * bx,
    aw * bz + ax * by - ay * bx + az * bw,
  ];
}

export function quatYawOnly(q) {
  const yaw = Math.atan2(2 * (q[0] * q[3] + q[1] * q[2]), 1 - 2 * (q[2] * q[2] + q[3] * q[3]));
  const half = yaw / 2;
  return [Math.cos(half), 0, 0, Math.sin(half)];
}

export function quatSlerp(a, b, t) {
  let dot = a[0] * b[0] + a[1] * b[1] + a[2] * b[2] + a[3] * b[3];
  let bb = b;
  if (dot < 0) {
    bb = [-b[0], -b[1], -b[2], -b[3]];
    dot = -dot;
  }
  if (dot > 0.9995) {
    return quatNormalize([
      a[0] + t * (bb[0] - a[0]),
      a[1] + t * (bb[1] - a[1]),
      a[2] + t * (bb[2] - a[2]),
      a[3] + t * (bb[3] - a[3]),
    ]);
  }
  const theta0 = Math.acos(Math.min(1, Math.max(-1, dot)));
  const theta = theta0 * t;
  const sin0 = Math.sin((1 - t) * theta0) / Math.sin(theta0);
  const sin1 = Math.sin(t * theta0) / Math.sin(theta0);
  return quatNormalize([
    a[0] * sin0 + bb[0] * sin1,
    a[1] * sin0 + bb[1] * sin1,
    a[2] * sin0 + bb[2] * sin1,
    a[3] * sin0 + bb[3] * sin1,
  ]);
}

export function quatToRotationMatrix(q) {
  const [w, x, y, z] = quatNormalize(q);
  return [
    1 - 2 * (y * y + z * z), 2 * (x * y - w * z), 2 * (x * z + w * y),
    2 * (x * y + w * z), 1 - 2 * (x * x + z * z), 2 * (y * z - w * x),
    2 * (x * z - w * y), 2 * (y * z + w * x), 1 - 2 * (x * x + y * y),
  ];
}

export function quatFromAxisAngle(axis, angle) {
  const n = Math.hypot(axis[0], axis[1], axis[2]) || 1.0;
  const half = angle / 2;
  const s = Math.sin(half);
  return [Math.cos(half), (axis[0] / n) * s, (axis[1] / n) * s, (axis[2] / n) * s];
}

export class MotionLoader {
  /**
   * @param {string} csvText raw CSV contents
   * @param {{fps?: number, time_start?: number, time_end?: number}} motionParams
   */
  constructor(csvText, motionParams) {
    this.fps = Number(motionParams?.fps ?? 50.0);
    this.dt = 1.0 / this.fps;
    this.timeStart = Number(motionParams?.time_start ?? 0.0);
    this.timeEnd = Number(motionParams?.time_end ?? 0.0);

    const lines = csvText.trim().split(/[\r\n]+/);
    const rowLen = lines[0].split(",").length;
    this.numJoints = rowLen - 7;

    this.rootPositions = [];
    this.rootQuaternions = []; // wxyz (source csv stores xyzw at cols 3..6)
    this.dofPositions = [];
    this.dofVelocities = [];

    const rows = lines.map((line) => line.split(",").map((v) => Number(v) || 0.0));
    const fps = this.fps;
    const startFrame = Math.round(this.timeStart * fps);
    const endFrame = Math.min(rows.length, Math.round(this.timeEnd * fps) || rows.length);
    const clipped = rows.slice(startFrame, Math.max(endFrame, startFrame + 1));
    for (const row of clipped) {
      this.rootPositions.push([row[0], row[1], row[2]]);
      this.rootQuaternions.push([row[6], row[3], row[4], row[5]]);
      this.dofPositions.push(row.slice(7));
    }
    for (let f = 0; f < this.dofPositions.length; f += 1) {
      const next = this.dofPositions[Math.min(f + 1, this.dofPositions.length - 1)];
      const cur = this.dofPositions[f];
      this.dofVelocities.push(cur.map((v, i) => (next[i] - v) / this.dt));
    }
    this.numFrames = this.dofPositions.length;
    this.duration = this.numFrames * this.dt;

    this.index0 = 0;
    this.index1 = 0;
    this.blend = 0.0;
    this.initQuat = [1, 0, 0, 0];
    this.time = 0.0;
    this.finished = false;
  }

  update(timeS) {
    const phase = Math.min(Math.max(timeS / Math.max(this.duration, 1e-8), 0.0), 1.0);
    this.finished = phase >= 1.0;
    const frameFloat = phase * Math.max(this.numFrames - 1, 0);
    this.index0 = Math.floor(frameFloat);
    this.index1 = Math.min(this.index0 + 1, this.numFrames - 1);
    this.blend = frameFloat - this.index0;
  }

  reset(robotQuat, timeS = 0.0) {
    this.update(timeS);
    const refYaw = quatYawOnly(this.rootQuaternion());
    const robotYaw = quatYawOnly(robotQuat);
    this.initQuat = quatMultiply(robotYaw, quatConjugate(refYaw));
  }

  jointPos() {
    const p0 = this.dofPositions[this.index0];
    const p1 = this.dofPositions[this.index1];
    return p0.map((v, i) => v * (1 - this.blend) + p1[i] * this.blend);
  }

  jointVel() {
    const v0 = this.dofVelocities[this.index0];
    const v1 = this.dofVelocities[this.index1];
    return v0.map((v, i) => v * (1 - this.blend) + v1[i] * this.blend);
  }

  rootPosition() {
    const p0 = this.rootPositions[this.index0];
    const p1 = this.rootPositions[this.index1];
    return p0.map((v, i) => v * (1 - this.blend) + p1[i] * this.blend);
  }

  rootQuaternion() {
    return quatSlerp(this.rootQuaternions[this.index0], this.rootQuaternions[this.index1], this.blend);
  }

  motionAnchorOriB(realQuatW, refQuatW) {
    // 上游协议（LeggedSkillDeploy motion_loader.py）：rot = conj(init*ref) * real，
    // 返回旋转矩阵前两列展平（6 维）。
    const rotQuat = quatMultiply(
      quatConjugate(quatMultiply(this.initQuat, refQuatW)),
      realQuatW,
    );
    const rot = quatToRotationMatrix(rotQuat);
    return [rot[0], rot[3], rot[1], rot[4], rot[2], rot[5]];
  }

  /**
   * Torso (waist-compensated) world quaternion: root quat composed with the
   * waist joint rotations applied about the torso frame axes (yaw about z,
   * roll about x, pitch about y), matching upstream torso_quat_w.
   * @param {number[]} rootQuat wxyz world quaternion
   * @param {number[]} waistAngles [yaw, roll, pitch] in radians
   */
  torsoQuatW(rootQuat, waistAngles) {
    const [yaw, roll, pitch] = waistAngles;
    let q = quatMultiply(rootQuat, quatFromAxisAngle([0, 0, 1], yaw));
    q = quatMultiply(q, quatFromAxisAngle([1, 0, 0], roll));
    q = quatMultiply(q, quatFromAxisAngle([0, 1, 0], pitch));
    return quatNormalize(q);
  }

  /**
   * Reference-side torso quaternion: root quaternion of the reference motion
   * composed with the reference waist angles (raw CSV joint columns 12/13/14
   * = waist yaw/roll/pitch in the robot joint order).
   */
  anchorQuatW() {
    const jointPos = this.jointPos();
    return this.torsoQuatW(this.rootQuaternion(), [jointPos[12], jointPos[13], jointPos[14]]);
  }
}
