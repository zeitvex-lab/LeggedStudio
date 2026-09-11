# RoboLab Agent Skills

For a request that matches one of the following workflows, read the referenced
`SKILL.md` before acting. The Skill documents are operational guidance only;
execute work through `robolab workflow` and the existing backend runtime.

| Request | Skill |
|---|---|
| Train or resume a policy | `skills/train/SKILL.md` |
| Reproduce a method recipe or paper run | `skills/reproduce/SKILL.md` |
| Independently evaluate a checkpoint | `skills/evaluate/SKILL.md` |
| Create a PolicyArtifact manifest | `skills/export/SKILL.md` |
| Adapt or add a robot asset for Isaac Gym and MJLab | `skills/robot-dual-backend-adapt/SKILL.md` |

Do not load an unrelated Skill. New executable workflows live under
`src/robolab/workflows/`; there is no Python `src/robolab/skills/` package.
