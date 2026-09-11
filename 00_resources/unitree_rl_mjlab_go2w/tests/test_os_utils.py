from __future__ import annotations

import sys
import tempfile
import unittest
from pathlib import Path

_REPO_ROOT = Path(__file__).resolve().parents[1]
if str(_REPO_ROOT) not in sys.path:
  sys.path.insert(0, str(_REPO_ROOT))

from mjlab.utils.os import resolve_local_checkpoint_path


class OsUtilsTest(unittest.TestCase):
  def test_resolve_local_checkpoint_path_preserves_explicit_file(self) -> None:
    with tempfile.TemporaryDirectory() as tmpdir:
      checkpoint = Path(tmpdir) / "model_1000.pt"
      checkpoint.touch()

      resolved = resolve_local_checkpoint_path(checkpoint)

      self.assertEqual(resolved, checkpoint.resolve())

  def test_resolve_local_checkpoint_path_picks_highest_iteration_in_run_dir(self) -> None:
    with tempfile.TemporaryDirectory() as tmpdir:
      run_dir = Path(tmpdir)
      (run_dir / "events.out.tfevents").touch()
      (run_dir / "model_1000.pt").touch()
      (run_dir / "model_5000.pt").touch()
      (run_dir / "model_15000.pt").touch()

      resolved = resolve_local_checkpoint_path(run_dir)

      self.assertEqual(resolved, (run_dir / "model_15000.pt").resolve())

  def test_resolve_local_checkpoint_path_errors_when_run_dir_has_no_models(self) -> None:
    with tempfile.TemporaryDirectory() as tmpdir:
      run_dir = Path(tmpdir)
      (run_dir / "events.out.tfevents").touch()

      with self.assertRaisesRegex(
        ValueError,
        "No checkpoints matching 'model_<iter>.pt' found in run directory",
      ):
        resolve_local_checkpoint_path(run_dir)


if __name__ == "__main__":
  unittest.main()
