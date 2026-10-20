import tempfile
import unittest
from pathlib import Path

from nimrod.source_code import extract_java_class_info


JAVA_SOURCE = """
package example;

import java.util.List;

public class Calculator {
    private int total;
    private final List<String> history;

    public Calculator() {
        this.total = 0;
    }

    public int sum(int a, int b) {
        int result = a + b;
        total = result;
        return result;
    }
}
"""


class SourceCodeExtractionTest(unittest.TestCase):
    def setUp(self) -> None:
        self._temp_dir = tempfile.TemporaryDirectory()
        self.source = Path(self._temp_dir.name) / "Calculator.java"
        self.source.write_text(JAVA_SOURCE)

    def tearDown(self) -> None:
        self._temp_dir.cleanup()

    def test_extracts_fields_constructor_and_method_body(self) -> None:
        fields, constructors, method = extract_java_class_info(
            str(self.source),
            "sum(int, int)",
            "example.Calculator",
        )

        self.assertEqual(len(fields), 2)
        self.assertTrue(any("private int total" in field for field in fields))
        self.assertTrue(any("private final List<String> history" in field for field in fields))
        self.assertTrue(any("public Calculator()" in constructor for constructor in constructors))
        self.assertIn("public int sum(int a, int b)", method)
        self.assertIn("int result = a + b;", method)


if __name__ == "__main__":
    unittest.main()
