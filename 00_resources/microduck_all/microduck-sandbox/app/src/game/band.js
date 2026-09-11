// Flock band: a real 4-bar song, and the arena floor is the instrument.
//
// You stay the only physics + ONNX duck. Three kinematic clones scan in
// (echo / peck / drone). A Web Audio sequencer plays a pentatonic groove
// (kick + bass + hook) from the robot's own chirp / wheee banks.
//
// The five section-columns of the 3 m arena ARE the scale. Walk left /
// right to change note; the glowing column is the hook you're doubling.
// Kick is the snare. Echo repeats your notes one bar later.

import { signed } from "./signed.js";
import { cloneRig, setJoint, setJawOpen, SITTING_POSE } from "./duck.js";
import { applyVariant } from "./variants.js";
import {
  JOINT_NAMES, NUM_JOINTS, DEFAULT_POSE, SPAWN_X, SPAWN_Y,
  ARENA_HALF, GRID_SECTION,
} from "./constants.js";

const BPM = 108;
const BEAT_S = 60 / BPM;
const EIGHTH_S = BEAT_S / 2;
const BAR_EIGHTHS = 8;
const LOOP_EIGHTHS = 32; // 4 bars
const BAR_S = BEAT_S * 4;
const RING = 320;
const CAPTURE_MS = 20;
const ECHO_LATERAL = 0.38;
const VOICE_BANK = { classic: "duck1", charcoal: "duck2", purple: "duck3", blue: "duck4" };
const CHIRP_TAKES = "abcdefghijkl";
const WHEEE_TAKES = "ab";
// Same pentatonic as the LT wheee, minus the unison octave — 5 columns.
const SCALE_ST = [-12, -10, -8, -5, -3];
const RATE = (st) => 2 ** (st / 12);

const ROLES = [
  { id: "echo", variant: "blue", delayS: BAR_S },
  { id: "peck", variant: "charcoal", plant: [-1.15, -1.15] },
  { id: "drone", variant: "purple", plant: [-1.15, 1.15], sit: true },
];

// 4-bar hook, eighths, scale degree 0..4, -1 = rest.
const HOOK = [
  0, -1, 2, -1, 4, -1, 2,  0,
  2, -1, 4,  4, 3, -1, 2, -1,
  0, -1, 2, -1, 4,  2, 0, -1,
  4,  2, 0, -1,-1, -1,-1, -1,
];
// Bass on every quarter (even eighths); -1 skips.
const BASS = [
  0, -1, 0, -1, 3, -1, 0, -1,
  2, -1, 2, -1, 0, -1, 3, -1,
  0, -1, 0, -1, 3, -1, 2, -1,
  0, -1, 0, -1, 0, -1,-1, -1,
];

const yawOf = (p) =>
  Math.atan2(2 * (p[3] * p[6] + p[4] * p[5]), 1 - 2 * (p[5] * p[5] + p[6] * p[6]));

const leftOf = (p, dist) => {
  const yaw = yawOf(p);
  return [dist * Math.cos(yaw + Math.PI / 2), dist * Math.sin(yaw + Math.PI / 2)];
};

export function columnOfY(y) {
  const i = Math.floor((y + ARENA_HALF) / GRID_SECTION);
  return Math.max(0, Math.min(4, i));
}

export function createBand(env) {
  const {
    THREE, scene, camera, renderer, fxModule, gridMat,
    getLeadRig, getAudioContext, onChange, onPulse,
  } = env;

  const ring = Array.from({ length: RING }, () => ({
    at: 0,
    p: new Float32Array(7),
    j: new Float32Array(NUM_JOINTS),
    w: 0,
    ev: 0,
    col: 2,
  }));
  let ringI = 0;
  let ringN = 0;
  let lastCap = 0;
  let pendingEv = 0;
  let leadCol = 2;

  let active = false;
  let members = [];
  let leaving = [];
  let startedAt = 0;
  let lastEchoW = 0;
  let lastAnimEighth = -1;

  let droneGain = null;
  let droneSrc = null;
  const bufCache = new Map();
  const chirpByVariant = {};
  let bassLoop = null;

  let songStart = 0; // audioContext time
  let nextSched = 0; // eighth index to schedule
  let lastPulse = -1;
  let lastSoundedCol = -1;

  const getCtx = () => {
    const ctx = getAudioContext();
    if (ctx.state === "suspended") ctx.resume().catch(() => {});
    return ctx;
  };

  const loadBuf = (url) => {
    let p = bufCache.get(url);
    if (!p) {
      p = fetch(url)
        .then((r) => r.arrayBuffer())
        .then((ab) => getCtx().decodeAudioData(ab));
      bufCache.set(url, p);
    }
    return p;
  };

  const playAt = (buf, when, { rate = 1, gain = 0.45, dur = 0 } = {}) => {
    if (!buf) return;
    const ctx = getCtx();
    const t = Math.max(when, ctx.currentTime);
    const src = ctx.createBufferSource();
    src.buffer = buf;
    src.playbackRate.value = rate;
    const g = ctx.createGain();
    g.gain.setValueAtTime(Math.max(gain, 0.001), t);
    if (dur > 0) {
      g.gain.setValueAtTime(gain, t + Math.max(0.012, dur - 0.05));
      g.gain.exponentialRampToValueAtTime(0.0001, t + dur);
    }
    src.connect(g).connect(ctx.destination);
    src.start(t);
    if (dur > 0) src.stop(t + dur + 0.02);
  };

  const randomChirpUrl = (variant) => {
    const bank = VOICE_BANK[variant] ?? "duck1";
    const take = CHIRP_TAKES[(Math.random() * CHIRP_TAKES.length) | 0];
    return signed(`./assets/voices/${bank}/chirp_${take}.wav`);
  };

  async function warm() {
    const variants = ["classic", "charcoal", "purple", "blue"];
    await Promise.all(variants.map(async (v) => {
      chirpByVariant[v] = await loadBuf(randomChirpUrl(v));
    }));
    const bank = VOICE_BANK.purple;
    const take = WHEEE_TAKES[(Math.random() * WHEEE_TAKES.length) | 0];
    bassLoop = await loadBuf(signed(`./assets/voices/${bank}/wheee_loop_${take}.wav`));
  }

  async function startDrone() {
    stopDrone({ silent: true });
    if (!bassLoop) return;
    const ctx = getCtx();
    const gain = ctx.createGain();
    gain.connect(ctx.destination);
    const t0 = ctx.currentTime;
    gain.gain.setValueAtTime(0, t0);
    gain.gain.linearRampToValueAtTime(0.1, t0 + 0.5);
    const src = ctx.createBufferSource();
    src.buffer = bassLoop;
    src.loop = true;
    src.playbackRate.value = RATE(SCALE_ST[0]);
    src.connect(gain);
    src.start(t0);
    droneGain = gain;
    droneSrc = src;
  }

  function stopDrone({ silent = false } = {}) {
    const gain = droneGain;
    const src = droneSrc;
    droneGain = null;
    droneSrc = null;
    if (!gain) {
      try { src?.stop(); } catch { /* already ended */ }
      return;
    }
    const ctx = getCtx();
    const t = ctx.currentTime;
    if (silent) {
      try { src?.stop(); } catch { /* already ended */ }
      gain.disconnect();
      return;
    }
    gain.gain.setTargetAtTime(0, t, 0.08);
    try { src?.stop(t + 0.4); } catch { /* already ended */ }
    setTimeout(() => gain.disconnect(), 500);
  }

  const eighthTime = (i) => songStart + i * EIGHTH_S;

  function scheduleEighth(i) {
    const t = eighthTime(i);
    const step = ((i % LOOP_EIGHTHS) + LOOP_EIGHTHS) % LOOP_EIGHTHS;
    const inBar = step % BAR_EIGHTHS;
    const chirp = (v) => chirpByVariant[v];

    // Kick on 1 and 3.
    if (inBar === 0 || inBar === 4) {
      playAt(chirp("classic"), t, { rate: 0.36, gain: 0.7, dur: 0.18 });
    }
    // Ghost snare on 2 and 4 — the player can punch this with a kick.
    if (inBar === 2 || inBar === 6) {
      playAt(chirp("charcoal"), t, { rate: 1.25, gain: 0.18, dur: 0.12 });
    }
    const bassDeg = BASS[step];
    if (bassDeg >= 0 && bassLoop) {
      playAt(bassLoop, t, {
        rate: RATE(SCALE_ST[bassDeg]),
        gain: 0.28,
        dur: EIGHTH_S * 1.6,
      });
    }
    const hookDeg = HOOK[step];
    if (hookDeg >= 0) {
      playAt(chirp("charcoal"), t, {
        rate: RATE(SCALE_ST[hookDeg]) * 2, // an octave up from the pad
        gain: 0.42,
        dur: EIGHTH_S * 1.1,
      });
    }
  }

  function scheduler() {
    if (!active || songStart === 0) return;
    const ctx = getCtx();
    const horizon = ctx.currentTime + 0.18;
    while (eighthTime(nextSched) < horizon) {
      scheduleEighth(nextSched);
      nextSched++;
    }
  }

  function cueDegree(eighth) {
    const step = ((eighth % LOOP_EIGHTHS) + LOOP_EIGHTHS) % LOOP_EIGHTHS;
    return HOOK[step];
  }

  const snapAt = (agoMs) => {
    if (ringN === 0) return null;
    const t = performance.now() - agoMs;
    for (let k = 0; k < ringN; k++) {
      const s = ring[(ringI - 1 - k + RING) % RING];
      if (s.at <= t) return s;
    }
    return ring[(ringI - ringN + RING) % RING];
  };

  function groundTrunk(rig, trunk) {
    rig.placer.updateWorldMatrix(true, true);
    const box = new THREE.Box3().setFromObject(rig.placer);
    if (!Number.isFinite(box.min.y)) return;
    trunk.position.z += -box.min.y;
  }

  function applyJoints(rig, pose) {
    for (let i = 0; i < NUM_JOINTS; i++) setJoint(rig, JOINT_NAMES[i], pose[i]);
  }

  function plantMember(m) {
    const [x, y] = m.plant;
    m.trunk.position.set(x, y, m.sit ? 0.07 : 0.12);
    m.trunk.quaternion.set(0, 0, 0, 1);
    if (m.sit) {
      for (const name of JOINT_NAMES) {
        setJoint(m.rig, name, SITTING_POSE[name] ?? 0);
      }
    } else {
      applyJoints(m.rig, DEFAULT_POSE);
    }
    setJawOpen(m.rig, 0);
    groundTrunk(m.rig, m.trunk);
    m.plantZ = m.trunk.position.z;
  }

  function spawnMembers() {
    const leadRig = getLeadRig();
    const spawn = [];
    for (const role of ROLES) {
      const rig = cloneRig(leadRig);
      applyVariant(rig, role.variant);
      const trunk = rig.bodies.get("trunk_base");
      const propFx = fxModule.createWireframeFx();
      propFx.init({
        THREE, scene, root: rig.placer, camera, renderer, hidden: true,
      });
      scene.add(rig.placer);
      const m = {
        id: role.id,
        rig,
        trunk,
        fx: propFx,
        variant: role.variant,
        delayS: role.delayS ?? 0,
        plant: role.plant ?? null,
        sit: !!role.sit,
        plantZ: 0.12,
      };
      if (m.plant) plantMember(m);
      else {
        m.trunk.position.set(SPAWN_X, SPAWN_Y + ECHO_LATERAL, 0.12);
        m.trunk.quaternion.set(0, 0, 0, 1);
        applyJoints(m.rig, DEFAULT_POSE);
      }
      spawn.push(m);
    }
    members = spawn;
    spawn.forEach((m, i) => {
      setTimeout(() => { if (active && members.includes(m)) m.fx.start(); }, i * 160);
    });
  }

  function peelMembers(list) {
    for (const m of list) {
      if (m.fx.playing && m.fx.reversing) continue;
      m.fx.startReverse();
    }
    leaving.push(...list);
  }

  function disposeMember(m) {
    m.fx.dispose();
    scene.remove(m.rig.placer);
  }

  function sweepLeaving() {
    if (!leaving.length) return;
    leaving = leaving.filter((m) => {
      if (!m.fx.isDone()) return true;
      disposeMember(m);
      return false;
    });
  }

  function driveEcho() {
    const echo = members.find((m) => m.id === "echo");
    if (!echo) return;
    const snap = snapAt(echo.delayS * 1000);
    if (!snap) return;
    const [dx, dy] = leftOf(snap.p, ECHO_LATERAL);
    echo.trunk.position.set(snap.p[0] + dx, snap.p[1] + dy, snap.p[2]);
    echo.trunk.quaternion.set(snap.p[4], snap.p[5], snap.p[6], snap.p[3]);
    applyJoints(echo.rig, snap.j);
    setJawOpen(echo.rig, snap.w);
    if (lastEchoW < 0.35 && snap.w > 0.5) {
      const buf = chirpByVariant.blue;
      if (buf) playAt(buf, getCtx().currentTime, { rate: 1.05, gain: 0.35, dur: 0.15 });
    }
    lastEchoW = snap.w;
  }

  function drivePlanted(eighth) {
    const t = eighth * EIGHTH_S;
    const peck = members.find((m) => m.id === "peck");
    const drone = members.find((m) => m.id === "drone");
    const cue = cueDegree(eighth);
    if (peck) {
      const bob = cue >= 0 ? 0.22 : 0.08 * Math.sin(t * Math.PI * 2 / BEAT_S);
      for (let i = 0; i < NUM_JOINTS; i++) {
        const name = JOINT_NAMES[i];
        let a = DEFAULT_POSE[i];
        if (name === "neck_pitch") a += bob;
        if (name === "head_pitch") a += bob * 0.5;
        if (name === "head_yaw" && cue >= 0) a += (cue - 2) * 0.18;
        setJoint(peck.rig, name, a);
      }
      setJawOpen(peck.rig, cue >= 0 ? 0.9 : 0.05);
      peck.trunk.position.z = peck.plantZ + (cue >= 0 ? 0.01 : 0);
    }
    if (drone) {
      const sway = 0.28 * Math.sin(t * 0.55);
      for (const name of JOINT_NAMES) {
        let a = SITTING_POSE[name] ?? 0;
        if (name === "head_yaw") a += sway;
        if (name === "neck_pitch") a += 0.05 * Math.sin(t * 1.05);
        setJoint(drone.rig, name, a);
      }
    }
  }

  function paintGrid(eighth) {
    if (!gridMat?.uniforms) return;
    const u = gridMat.uniforms;
    if (!u.uBandOn) return;
    const ctx = getCtx();
    const phase = ((ctx.currentTime - songStart) / BEAT_S) % 1;
    const pulse = Math.max(0, 1 - phase * 3.2);
    u.uBandOn.value = active ? 1 : 0;
    u.uBeat.value = active ? pulse : 0;
    u.uPlayCol.value = active ? leadCol : -1;
    u.uCueCol.value = active ? cueDegree(eighth) : -1;
  }

  function firePlayerEighth(eighth) {
    const ctx = getCtx();
    const t = ctx.currentTime;
    const col = leadCol;
    const cue = cueDegree(eighth);
    const moved = col !== lastSoundedCol;
    lastSoundedCol = col;
    // Walking changes the note; standing on the glowing column doubles
    // the hook. Standing elsewhere lets the song play without a drone.
    if (moved || cue === col) {
      const buf = chirpByVariant.classic;
      if (buf) {
        playAt(buf, t, {
          rate: RATE(SCALE_ST[col]) * 2,
          gain: cue === col ? 0.7 : 0.48,
          dur: EIGHTH_S * 0.95,
        });
      }
    }
    const delayed = snapAt(BAR_S * 1000);
    if (delayed && chirpByVariant.blue && delayed.col !== columnOfY(0)) {
      // Echo only if the delayed pose had the player off-center (they
      // were actually walking the keys). Always echo on a delayed hit.
      const delayedCue = cueDegree(Math.max(0, eighth - BAR_EIGHTHS));
      if (delayed.col === delayedCue || delayed.col !== 2) {
        playAt(chirpByVariant.blue, t, {
          rate: RATE(SCALE_ST[delayed.col]) * 2,
          gain: 0.28,
          dur: EIGHTH_S * 0.95,
        });
      }
    }
    onPulse?.({
      beat: Math.floor(eighth / 2) % 4,
      cue,
      col,
      hit: cue === col,
    });
  }

  async function setActive(on) {
    on = !!on;
    if (on === active) return;
    if (on) {
      active = true;
      startedAt = performance.now();
      lastEchoW = 0;
      lastAnimEighth = -1;
      lastPulse = -1;
      lastSoundedCol = -1;
      songStart = 0;
      ringN = 0;
      ringI = 0;
      spawnMembers();
      onChange?.(true);
      try {
        await warm();
      } catch {
        /* samples optional — groove still tries */
      }
      if (!active) return;
      const ctx = getCtx();
      songStart = ctx.currentTime + 0.12;
      nextSched = 0;
      startDrone();
    } else {
      active = false;
      songStart = 0;
      stopDrone();
      peelMembers(members);
      members = [];
      if (gridMat?.uniforms?.uBandOn) {
        gridMat.uniforms.uBandOn.value = 0;
        gridMat.uniforms.uBeat.value = 0;
        gridMat.uniforms.uPlayCol.value = -1;
        gridMat.uniforms.uCueCol.value = -1;
      }
      onChange?.(false);
    }
  }

  function toggle() {
    setActive(!active);
  }

  function capture({ qpos, qposAdr, jaw }) {
    if (!active) return;
    const now = performance.now();
    if (now - lastCap < CAPTURE_MS) return;
    lastCap = now;
    const s = ring[ringI];
    s.at = now;
    for (let i = 0; i < 7; i++) s.p[i] = qpos[i];
    for (let i = 0; i < NUM_JOINTS; i++) s.j[i] = qpos[qposAdr[i]];
    s.w = jaw;
    s.ev = pendingEv;
    s.col = columnOfY(qpos[1]);
    leadCol = s.col;
    pendingEv = 0;
    ringI = (ringI + 1) % RING;
    if (ringN < RING) ringN++;
  }

  function accent(kind) {
    if (!active) return;
    pendingEv = kind === "kick" || kind === "roll" ? 1 : 0;
    if (kind === "kick") {
      const buf = chirpByVariant.classic;
      if (buf) playAt(buf, getCtx().currentTime, { rate: 0.34, gain: 0.85, dur: 0.2 });
    }
    if (kind === "quack") {
      const buf = chirpByVariant.classic;
      if (buf) {
        playAt(buf, getCtx().currentTime, {
          rate: RATE(SCALE_ST[leadCol]) * 2.5,
          gain: 0.6,
          dur: 0.18,
        });
      }
    }
  }

  function update(dt) {
    sweepLeaving();
    if (!active) {
      for (const m of leaving) m.fx.update(dt);
      return;
    }
    scheduler();
    if (songStart === 0) {
      for (const m of members) m.fx.update(dt);
      for (const m of leaving) m.fx.update(dt);
      return;
    }
    const ctx = getCtx();
    const eighth = Math.max(0, Math.floor((ctx.currentTime - songStart) / EIGHTH_S));
    if (eighth !== lastAnimEighth && ctx.currentTime >= songStart) {
      lastAnimEighth = eighth;
      firePlayerEighth(eighth);
      drivePlanted(eighth);
    }
    driveEcho();
    paintGrid(eighth);
    for (const m of members) m.fx.update(dt);
    for (const m of leaving) m.fx.update(dt);
  }

  function dispose() {
    setActive(false);
    for (const m of [...members, ...leaving]) disposeMember(m);
    members = [];
    leaving = [];
    stopDrone({ silent: true });
  }

  return {
    toggle,
    setActive,
    capture,
    accent,
    update,
    dispose,
    get active() { return active; },
    get col() { return leadCol; },
  };
}
