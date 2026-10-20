import tempfile
import unittest
from pathlib import Path

from nimrod.test_suite_generation.generators.codellama_test_suite_generator import (
    CodellamaTestSuiteGenerator,
)


class SourceCodePathsTest(unittest.TestCase):
    def setUp(self) -> None:
        self._temp_dir = tempfile.TemporaryDirectory()
        self.root = Path(self._temp_dir.name)
        self.scenario = self.root / "dataset" / "Project" / "abc123"
        self.source = self.scenario / "source"

        for branch in ("base", "left", "right", "merge"):
            branch_dir = self.scenario / "transformed" / branch
            branch_dir.mkdir(parents=True)
            (branch_dir / "app.jar").write_text("")

        self.source.mkdir()
        self.generator = CodellamaTestSuiteGenerator(object(), "gemini", {})

    def tearDown(self) -> None:
        self._temp_dir.cleanup()

    def _jar(self, branch: str) -> str:
        return str(self.scenario / "transformed" / branch / "app.jar")

    def test_finds_class_prefixed_sources(self) -> None:
        for branch in ("base", "left", "right", "merge"):
            (self.source / f"Foo_{branch}.java").write_text(f"class Foo {{}} // {branch}")

        paths = self.generator.find_source_code_paths(
            self._jar("left"), "transformed", "Foo", "Project"
        )

        self.assertEqual(paths["left"], str(self.source / "Foo_left.java"))
        self.assertEqual(paths["right"], str(self.source / "Foo_right.java"))
        self.assertEqual(paths["base"], str(self.source / "Foo_base.java"))
        self.assertEqual(paths["merge"], str(self.source / "Foo_merge.java"))

    def test_finds_sources_in_class_folder(self) -> None:
        class_dir = self.source / "Foo"
        class_dir.mkdir()
        for branch in ("base", "left", "right", "merge"):
            (class_dir / f"{branch}.java").write_text(f"class Foo {{}} // {branch}")

        paths = self.generator.find_source_code_paths(
            self._jar("right"), "transformed", "Foo", "Project"
        )

        self.assertEqual(paths["left"], str(class_dir / "left.java"))
        self.assertEqual(paths["right"], str(class_dir / "right.java"))

    def test_falls_back_to_single_source_version(self) -> None:
        (self.source / "Foo.java").write_text("class Foo {}")

        paths = self.generator.find_source_code_paths(
            self._jar("left"), "transformed", "Foo", "Project"
        )

        self.assertEqual(paths["left"], str(self.source / "Foo.java"))
        self.assertEqual(paths["right"], str(self.source / "Foo.java"))

    def test_raises_when_left_or_right_source_is_missing(self) -> None:
        (self.source / "Foo_right.java").write_text("class Foo {}")

        with self.assertRaises(FileNotFoundError):
            self.generator.find_source_code_paths(
                self._jar("left"), "transformed", "Foo", "Project"
            )

    def test_fetch_branch_uses_parent_directory(self) -> None:
        for branch in ("base", "left", "right", "merge"):
            (self.source / f"Foo_{branch}.java").write_text(f"class Foo {{}} // {branch}")

        source_path, branch, all_paths = self.generator.fetch_source_code_branch(
            self._jar("left"), "transformed", "Foo", "Project"
        )

        self.assertEqual(branch, "left")
        self.assertEqual(source_path, str(self.source / "Foo_left.java"))
        self.assertEqual(all_paths["right"], str(self.source / "Foo_right.java"))

    def test_accepts_multiple_jars_per_branch(self) -> None:
        for branch in ("base", "left", "right", "merge"):
            (self.source / f"Foo_{branch}.java").write_text(f"class Foo {{}} // {branch}")

        second_jar = self.scenario / "transformed" / "left" / "extra.jar"
        second_jar.write_text("")

        paths = self.generator.find_source_code_paths(
            f"{self._jar('left')}:{second_jar}", "transformed", "Foo", "Project"
        )

        self.assertEqual(paths["left"], str(self.source / "Foo_left.java"))


if __name__ == "__main__":
    unittest.main()
