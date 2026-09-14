import json
import unittest
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[1]


class WorkspaceConfigTests(unittest.TestCase):
    def test_root_package_exposes_documented_workspace_commands(self) -> None:
        package = json.loads((REPO_ROOT / "package.json").read_text(encoding="utf-8"))

        self.assertEqual(package["name"], "badminton-analysis-workspace")
        self.assertTrue(package["private"])
        self.assertEqual(package["workspaces"], ["apps/web", "apps/mini"])
        self.assertEqual(package["scripts"]["web:dev"], "npm run dev -w @badminton-analysis/web")
        self.assertEqual(package["scripts"]["web:build"], "npm run build -w @badminton-analysis/web")
        self.assertEqual(
            package["scripts"]["mini:build"],
            "npm run build:weapp -w @badminton-analysis/mini",
        )


if __name__ == "__main__":
    unittest.main()
