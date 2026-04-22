import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from brain import BRAIN_REPO_URL, ensure_brain_repo


class TestBrainEntryPoint(unittest.TestCase):
    def test_ensure_brain_repo_uses_existing_clone(self):
        with tempfile.TemporaryDirectory() as tmp_dir:
            root = Path(tmp_dir)
            existing = root / "brain"
            existing.mkdir()
            (existing / ".git").mkdir()

            with patch("brain.subprocess.run") as mock_run:
                result = ensure_brain_repo(project_root=root)

            self.assertEqual(result, existing)
            mock_run.assert_not_called()

    def test_ensure_brain_repo_clones_when_missing(self):
        with tempfile.TemporaryDirectory() as tmp_dir:
            root = Path(tmp_dir)
            expected = root / "brain"

            with patch("brain.subprocess.run") as mock_run:
                result = ensure_brain_repo(project_root=root)

            self.assertEqual(result, expected)
            mock_run.assert_called_once_with(
                ["git", "clone", BRAIN_REPO_URL, str(expected)],
                check=True,
            )

    def test_ensure_brain_repo_raises_for_non_repo_directory(self):
        with tempfile.TemporaryDirectory() as tmp_dir:
            root = Path(tmp_dir)
            bad_dir = root / "brain"
            bad_dir.mkdir()

            with self.assertRaisesRegex(RuntimeError, "not a git repository"):
                ensure_brain_repo(project_root=root)


if __name__ == "__main__":
    unittest.main()
