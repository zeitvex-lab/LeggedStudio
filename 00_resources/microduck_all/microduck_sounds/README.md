# microduck_sounds

Tiny seedable synth for [microduck](https://github.com/apirrone/microduck_runtime)
robot pet vocalisations. Pure numpy, no models, no assets — every sound is
synthesized from a recipe plus a per-robot `Personality`.

## How it works

A single integer seed deterministically derives a `Personality`: pitch
register, harmonic tilt, nasality, vibrato, quackiness, tempo, etc. Two
seeds sound like two different creatures; the same seed always sounds the
same. Each sound **tag** has several **variants** (small re-rolls within
the same voice) so the duck doesn't sound like a stuck recording.

Tags: `alarm`, `greet`, `inquire`, `peck`, `chirp`, `coo`, `wheee`.
`wheee` is segmented (`start` / `loop` / `end`) so the runtime can stream
it for as long as the ride lasts.

## Usage

```bash
# print the personality traits behind a seed
uv run microduck-sounds show --seed 100

# play one sound / listen to the whole repertoire
uv run microduck-sounds play chirp --seed 100 --variant 2
uv run microduck-sounds audition --seed 100

# write wavs (22.05 kHz mono)
uv run microduck-sounds render greet out.wav --seed 100
uv run microduck-sounds render-all bank/ --seed 100
```

`render-all` writes the layout the runtime plays from:
`<out_dir>/<tag>/<tag>_<letter>.wav`, with segmented tags as
`<tag>_start_<letter>.wav` / `_loop_` / `_end_`.

From Python:

```python
from microduck_sounds import api

buf = api.render("coo", seed=100, variant=1)   # float32 mono
api.play("chirp", seed=100)                    # synthesize + play now
api.render_all(seed=100, out_dir="bank/")
```

## Use in microduck_runtime

`install.sh` runs `scripts/generate_sounds.sh`, which hashes the SoC's
efuse serial into a seed — so every robot gets its own stable voice,
surviving reboots and reflashes — then runs `render-all` and resamples the
bank to 48 kHz into `~/microduck/sounds/`. The runtime picks a random
variant per play: `greet` on startup, `chirp` for quacks, `coo` when
petted, `peck` on shutdown, `wheee` while held.
