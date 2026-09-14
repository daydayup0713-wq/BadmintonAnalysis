from __future__ import annotations

import unittest
import subprocess
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]

FORBIDDEN_PATHS = (
    "src",
    "ShuttleSet",
    "videos",
    "res",
    "main.py",
    "requirements-windows-nvidia.txt",
    "WINDOWS_NVIDIA_部署运行说明.md",
    "services/api/courtvision/training",
    "scripts/audit_shuttleset.py",
    "scripts/evaluate_shuttleset.py",
    "scripts/train_shuttleset.py",
    "docs/ALGORITHM_AUDIT.md",
    "docs/MODEL_MANIFEST.md",
    "docs/SHUTTLESET_TRAINING.md",
)


class RepositoryBoundaryTests(unittest.TestCase):
    def test_release_tree_excludes_bundled_model_and_dataset_paths(self) -> None:
        tracked = set(
            subprocess.run(
                ["git", "ls-files"],
                cwd=ROOT,
                check=True,
                capture_output=True,
                text=True,
                encoding="utf-8",
            ).stdout.splitlines()
        )
        present = [
            relative
            for relative in FORBIDDEN_PATHS
            if relative in tracked
            or any(path.startswith(f"{relative}/") for path in tracked)
        ]

        self.assertEqual(present, [])


if __name__ == "__main__":
    unittest.main()
