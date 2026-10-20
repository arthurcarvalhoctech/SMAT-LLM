import json
import tempfile
import unittest
from pathlib import Path

from scripts.prepare_mergedataset_input import prepare

BRANCHES = ("base", "left", "right", "merge")


def scenario(project: str, commit: str) -> dict:
    return {
        "projectName": project,
        "targets": {"pkg.Class": ["method()"]},
        "scenarioJars": {
            branch: f"/path/mergedataset/mergedataset/{project}/{commit}/transformed/{branch}/app.jar"
            for branch in BRANCHES
        },
        "jarType": "transformed",
    }


class PrepareMergedatasetInputTest(unittest.TestCase):
    def setUp(self) -> None:
        self._temp_dir = tempfile.TemporaryDirectory()
        self.root = Path(self._temp_dir.name)
        self.dataset = self.root / "dataset"
        self.artifact = self.root / "input.json"

        commit = "abc123"
        for branch in BRANCHES:
            branch_dir = self.dataset / "project" / commit / "transformed" / branch
            branch_dir.mkdir(parents=True)
            (branch_dir / "app.jar").write_text("")

        self.artifact.write_text(
            json.dumps([scenario("project", commit), scenario("missing", "def456")]),
            encoding="utf-8",
        )

    def tearDown(self) -> None:
        self._temp_dir.cleanup()

    def test_keeps_only_scenarios_with_all_jars_and_rewrites_paths(self) -> None:
        prepared = prepare(str(self.artifact), str(self.dataset), "/data/mergedataset")

        self.assertEqual(len(prepared), 1)
        self.assertEqual(prepared[0]["projectName"], "project")
        self.assertEqual(
            prepared[0]["scenarioJars"]["left"],
            "/data/mergedataset/project/abc123/transformed/left/app.jar",
        )

    def test_can_keep_the_host_path_as_prefix(self) -> None:
        prepared = prepare(str(self.artifact), str(self.dataset), str(self.dataset))

        self.assertEqual(
            prepared[0]["scenarioJars"]["merge"],
            f"{self.dataset}/project/abc123/transformed/merge/app.jar",
        )


if __name__ == "__main__":
    unittest.main()
