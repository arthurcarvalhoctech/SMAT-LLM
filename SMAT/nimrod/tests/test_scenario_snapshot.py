import json
import tempfile
import unittest
from pathlib import Path

from nimrod.core.merge_scenario_under_analysis import (
    MergeScenarioUnderAnalysis,
    ScenarioInformation,
)
from nimrod.scenario_snapshot import (
    BRANCHES,
    dataset_name_from_input,
    persist_merge_scenarios,
    scenario_folder_name,
)


class ScenarioSnapshotTest(unittest.TestCase):
    def setUp(self):
        self._temp_dir = tempfile.TemporaryDirectory()
        self.temp = Path(self._temp_dir.name)
        self.dataset = self.temp / "dataset"
        self.scenario_root = self.dataset / "Project" / "abc123"
        for branch in BRANCHES:
            branch_dir = self.scenario_root / "transformed" / branch
            branch_dir.mkdir(parents=True)
            (branch_dir / "app.jar").write_text("")

        source_dir = self.scenario_root / "source"
        source_dir.mkdir()
        for class_name in ("Foo", "Bar"):
            for branch in BRANCHES:
                (source_dir / f"{class_name}_{branch}.java").write_text(
                    "package example;\n"
                    f"public class {class_name} {{\n"
                    f'    public String value() {{ return "{branch}"; }}\n'
                    "}\n"
                )

        self.scenario = MergeScenarioUnderAnalysis(
            project_name="Project",
            run_analysis=True,
            scenario_commits=ScenarioInformation("base-sha", "left-sha", "right-sha", "merge-sha"),
            targets={
                "example.Foo": [{"method": "value()"}],
                "example.Bar": [{"method": "value()"}],
            },
            scenario_jars=ScenarioInformation(
                str(self.scenario_root / "transformed" / "base" / "app.jar"),
                str(self.scenario_root / "transformed" / "left" / "app.jar"),
                str(self.scenario_root / "transformed" / "right" / "app.jar"),
                str(self.scenario_root / "transformed" / "merge" / "app.jar"),
            ),
            jar_type="transformed",
        )
        self.output_root = self.temp / "output"

    def tearDown(self):
        self._temp_dir.cleanup()

    def _persist(self, scenarios, input_path="/tmp/input-smat-test.json"):
        return persist_merge_scenarios(
            scenarios,
            input_path=input_path,
            output_root=str(self.output_root),
            timestamp="20261028_190000_000000",
        )

    def test_creates_dataset_timestamp_and_scenario_folders(self):
        root = Path(self._persist([self.scenario]))

        self.assertEqual(
            root,
            self.output_root / "input-smat-test_20261028_190000_000000",
        )
        scenario_dir = root / "001_Project"
        self.assertTrue(scenario_dir.is_dir())
        for branch in BRANCHES:
            self.assertTrue((scenario_dir / branch).is_file())

    def test_branch_files_contain_all_target_sources(self):
        root = Path(self._persist([self.scenario]))
        scenario_dir = root / "001_Project"

        for branch in BRANCHES:
            content = (scenario_dir / branch).read_text(encoding="utf-8")
            self.assertIn(f"// branch: {branch}", content)
            self.assertIn("// target classes: example.Foo", content)
            self.assertIn("// target classes: example.Bar", content)
            self.assertIn("public class Foo {", content)
            self.assertIn("public class Bar {", content)
            self.assertIn(f'return "{branch}";', content)

    def test_manifest_records_input_dataset_and_scenarios(self):
        root = Path(self._persist([self.scenario]))
        manifest = json.loads((root / "manifest.json").read_text(encoding="utf-8"))

        self.assertEqual(manifest["dataset"], "input-smat-test")
        self.assertEqual(manifest["run_id"], "20261028_190000_000000")
        self.assertEqual(len(manifest["scenarios"]), 1)
        self.assertEqual(manifest["scenarios"][0]["folder"], "001_Project")
        self.assertEqual(manifest["scenarios"][0]["project"], "Project")
        self.assertEqual(manifest["scenarios"][0]["missing_sources"], [])

    def test_same_project_gets_distinct_indexed_folders(self):
        root = Path(self._persist([self.scenario, self.scenario]))

        self.assertTrue((root / "001_Project").is_dir())
        self.assertTrue((root / "002_Project").is_dir())

    def test_missing_sources_still_create_branch_files(self):
        self.scenario.targets = {"example.Missing": [{"method": "value()"}]}
        root = Path(self._persist([self.scenario]))

        scenario_dir = root / "001_Project"
        for branch in BRANCHES:
            content = (scenario_dir / branch).read_text(encoding="utf-8")
            self.assertIn(
                f"No source files found for branch '{branch}'", content
            )
            self.assertIn("// Missing sources:", content)

    def test_no_scenarios_does_not_create_output(self):
        root = self._persist([])

        self.assertEqual(root, "")
        self.assertFalse(self.output_root.exists())

    def test_dataset_name_comes_from_input_file_stem(self):
        self.assertEqual(
            dataset_name_from_input("/tmp/input-smat-mergedataset.json"),
            "input-smat-mergedataset",
        )
        self.assertEqual(dataset_name_from_input(""), "dataset")

    def test_scenario_folder_name_is_sanitized_and_indexed(self):
        self.assertEqual(scenario_folder_name(1, "antlr4"), "001_antlr4")
        self.assertEqual(
            scenario_folder_name(12, "spring boot/loader"), "012_spring_boot_loader"
        )


if __name__ == "__main__":
    unittest.main()
