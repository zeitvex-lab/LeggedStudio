---
title: Microduck Sandbox
emoji: 🐤
colorFrom: yellow
colorTo: gray
sdk: docker
app_port: 8080
pinned: false
---

# Microduck Sandbox — flock band fork

Fork of Pollen Robotics' in-browser Microduck playground
([`pollen-robotics/microduck-simulator`](https://huggingface.co/spaces/pollen-robotics/microduck-simulator)).

The original Space is the real robot: MuJoCo WASM, the shipped ONNX
policies, 50 Hz control, gamepad parity. This fork adds a **flock band**
on top of that — not a second physics world.

**Play it:** the official Space is still the place to drive a duck.
This repo is the band mode.

## Flock band

Press **N**, **D-pad left**, or the HUD **Band** chip after the duck
materializes.

The flock plays a 4-bar pentatonic groove (kick, bass, hook) from the
robot's own chirp / wheee voice banks. Three kinematic clones scan in:
echo (you, one bar late), peck (hook), drone (sits and hums).

The five floor columns are the scale. Walk left/right to change note.
The **gold column** is the hook — stand in it to double the melody.
Kick is the snare. Quack is a stab in your current lane. LT wheee is
still the sustained lead, in key.

You stay the only physics + ONNX duck. Clones share `cloneRig` with
the ghost system.

```
N / D-pad left / HUD Band    start / stop the song
walk sideways                play the keys
stand in the glow            hit the hook
Q / E / kick                 snare
RT / quack                   stab
LT                           wheee lead
```

```bash
cd app
npm install
npm run dev          # http://localhost:5173
# or, if file-watchers are exhausted:
npm run build && npx vite preview --port 4173
```

Needs a browser with WebGL + WASM (any recent Chrome/Firefox). First
load fetches MuJoCo and onnxruntime from jsDelivr.

## What this is not

- Not a replacement for the official Space.
- Not a new training env — no PPO, no new ONNX.
- Not Pollen's product. Band mode is a community sketch on their
  sandbox. Policies, MJCF, voices, and the play loop are theirs.

---

# Microduck RL playground (upstream)

Real trained RL policies for the Microduck robot, running fully in the
browser: MuJoCo compiled to WebAssembly steps the physics, onnxruntime-web
runs the policy network at 50 Hz. No server, no backend.

Two locomotion variants of the same robot are included: **legs** (walking,
the default) and **rollers** (the wheeled skating variant). Press `M` (or
hold D-pad up ~1 s on a gamepad) to switch; the roller model, meshes and
policies are lazy-loaded on the first switch.

## Policies

| Mode | Checkpoint | What it does |
|--------|-----------|--------------|
| Run (legs) | `BEST_alpha_walking.onnx` | Velocity-tracking locomotion (arrows / WASD to steer) |
| Sit | `BEST_alpha_sitstand.onnx` | Sits down on its hull, stands back up |
| Roll | `roulade.onnx` | Rolls over and recovers |
| Kick | `ball_kick_left.onnx` / `ball_kick_right.onnx` | Blind one-shot kick (0.5 s window, zeroed commands), left or right leg |
| Drive (rollers) | `BEST_roller.onnx` | Velocity-tracking skating on 4 passive wheels (higher top speed: 0.6 m/s) |
| Crouch (rollers) | `BEST_roller_crouch.onnx` | One-shot crouch-glide: sinks low over ~3.5 s and stands back up (phase-encoded command) |

Policies and MJCF model from
[apirrone/microduck_runtime](https://github.com/apirrone/microduck_runtime)
and [apirrone/mjlab_microduck](https://github.com/apirrone/mjlab_microduck) /
[pollen-robotics/microduck_rl](https://github.com/pollen-robotics/microduck_rl).

## Controls

- Arrows or WASD (ZQSD): forward / back + turn
- M: switch legs <-> rollers
- Q / E (A / E on AZERTY): kick left / right (legs only)
- R: sit (legs) / crouch-glide (rollers)
- G: ground pick
- C: toggle the chase camera (on by default; dragging detaches it)
- Space: reset
- Drag to orbit, scroll to zoom
- Colour dots: repaint the duck (it quacks)

In roller mode the legs-only actions (kicks, sit) are disabled and their
hints fade out; play the ball by driving into it.

### URL parameters

- `?boot=1`: skip the welcome modal and land straight on the BIOS console,
  which then shows the real loading progress live (honest loader) before
  the normal entrance plays. Boot failures (missing asset, policy fetch
  error...) freeze the console on a `SYSTEM HALTED` screen with the error
  detail - handy for debugging.

The ball is local-only: it lives in your tab's physics and is not shared
with the multiplayer ghosts. A square arena (3 x 3 m) fences the play
area so neither the ball nor the duck can wander off.

### Gamepad

Plug in a controller and the same mapping as the real robot runtime applies:

- Left stick: forward / back + turn
- Right stick: orbit the camera (detaches the chase cam)
- R3 (right stick click): toggle the chase cam back on
- X: sit (legs) / crouch-glide (rollers)
- RB / LB: right / left kick (legs only)
- D-pad down: sit / stand toggle (legs only)
- D-pad up: hold ~1 s to switch legs <-> rollers (the real robot uses a 3 s hold)
- D-pad left: flock band
- Right trigger: mouth (analog) + quack
- Left trigger: wheee (pentatonic lead)

## Multiplayer ghosts

Other people visiting the Space at the same time show up as translucent
ducks, live. Peer-to-peer WebRTC via [Trystero](https://github.com/dmotz/trystero)
(serverless signaling over public Nostr relays), so it works from a static
Space with no backend. Each tab broadcasts its duck's pose (trunk + 14
joints + jaw + colour + locomotion variant) at 10 Hz; up to 3 ghosts are
rendered, extra peers stay connected but invisible. The camcorder-style OSD
in the top-right corner shows "N ONLINE" when peers are around.

Ghost limitations in v1: a peer in roller mode renders with the roller rig
only if your tab has already loaded it (otherwise it falls back to the leg
rig), and ghost wheels don't spin (passive wheel joints aren't broadcast).
Old clients simply ignore the new variant flag.

## How it works

The app is a Vite + React + MUI shell around an imperative game core:
React/MUI renders the UI chrome (title menu, BIOS console, HUD, touch
overlay), react-three-fiber owns the canvas/lights/environment, and the
physics/policy/rig loop lives in framework-agnostic modules under
`app/src/game/`. A zustand store bridges the two (game state out,
UI intents in).

- `app/src/game/game.js` fetches the MJCF (`robot_allcollisions.xml`, or
  `robot_allcollisions_rollers.xml` for the roller variant), strips the
  visual geoms, injects a floor, arena walls, a ball, a collision box for
  the arcade cabinet row and a STAND keyframe, and compiles it with the
  official `@mujoco/mujoco` WASM bindings.
- Both variants share the exact same policy interface: 61D observation
  (gyro, projected gravity, 14 joint pos/vel, last action, 13D command)
  and 14 position-targets, matching `mjlab_microduck/scripts/infer_policy.py`.
  The roller variant adds 4 passive wheel hinges that appear in `qpos`
  (zeroed in the keyframe) but not in the observation.
- Rendering is a three.js rig built from `kinematics.json` /
  `kinematics_rollers.json` + decimated STL meshes, driven directly from
  MuJoCo `qpos` (including the passive wheel spin).
- Switching variants swaps the compiled model + data + rig + ONNX sessions
  wholesale; both stay resident after the first load so toggling back and
  forth is instant.
- Flock band lives in `app/src/game/band.js`. Clones are kinematic
  (`cloneRig`); the song is a Web Audio sequencer on the existing voice
  banks; floor columns map to the same pentatonic the LT wheee uses.

## Development

```bash
cd app
npm install
npm run dev     # dev server on http://localhost:5173
npm run build   # production bundle in app/dist/
```

The Space builds with the included `Dockerfile` (Vite build, served by
nginx-unprivileged on port 8080). Static assets (meshes, policies, audio,
images) live in `app/public/` and keep their historical URLs.

## Credit

- [Pollen Robotics](https://pollen-robotics.com/microduck/) / Hugging Face — the robot, the policies, the sandbox
- Official sim: [huggingface.co/spaces/pollen-robotics/microduck-simulator](https://huggingface.co/spaces/pollen-robotics/microduck-simulator)
- Training stack: [pollen-robotics/microduck_rl](https://github.com/pollen-robotics/microduck_rl)
- Runtime: [pollen-robotics/microduck](https://github.com/pollen-robotics/microduck)
