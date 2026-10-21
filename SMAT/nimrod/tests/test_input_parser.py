import json
import os
import tempfile
from unittest import TestCase
from unittest.mock import patch

from nimrod.input_parsing.input_parser import JsonInputParser, expand_env_vars


def _scenario_with_jars(base_jar: str) -> dict:
    return {
        "projectName": "antlr4",
        "runAnalysis": True,
        "scenarioCommits": {"base": "", "left": "", "right": "", "merge": ""},
        "targets": {},
        "scenarioJars": {
            "base": base_jar,
            "left": "/fixed/left.jar",
            "right": "/fixed/right.jar",
            "merge": "/fixed/merge.jar",
        },
        "jarType": "transformed",
    }


class ExpandEnvVarsTest(TestCase):
    def test_replaces_defined_variable(self):
        with patch.dict(os.environ, {"PATH_DATASET": "/data/mergedataset"}, clear=True):
            self.assertEqual(
                expand_env_vars("${PATH_DATASET}/antlr4/x.jar"),
                "/data/mergedataset/antlr4/x.jar",
            )

    def test_leaves_plain_paths_unchanged(self):
        self.assertEqual(expand_env_vars("/abs/path/x.jar"), "/abs/path/x.jar")

    def test_undefined_variable_raises_clear_error(self):
        with patch.dict(os.environ, {}, clear=True):
            with self.assertRaises(ValueError) as context:
                expand_env_vars("${PATH_DATASET}/antlr4/x.jar")
        self.assertIn("PATH_DATASET", str(context.exception))


class JsonInputParserEnvVarsTest(TestCase):
    def test_parses_jar_paths_with_environment_variables(self):
        scenario = _scenario_with_jars("${PATH_DATASET}/antlr4/base.jar")
        with tempfile.NamedTemporaryFile("w", suffix=".json", delete=False) as file:
            json.dump([scenario], file)
            input_path = file.name
        try:
            with patch.dict(os.environ, {"PATH_DATASET": "/data/mergedataset"}, clear=True):
                scenarios = JsonInputParser().parse_input(input_path)
        finally:
            os.remove(input_path)

        self.assertEqual(
            scenarios[0].scenario_jars.base,
            "/data/mergedataset/antlr4/base.jar",
        )
        self.assertEqual(scenarios[0].scenario_jars.left, "/fixed/left.jar")
