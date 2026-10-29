import os
from unittest import TestCase
from unittest.mock import patch

from nimrod.test_suite_generation.generators.context_filter import (
    CONTEXT_FILTER_ENV_VAR,
    changed_identifiers,
    context_filter_enabled,
    declared_field_names,
    filter_class_fields,
    filter_context,
)


BASE = """class Calc {
    int used = 1;
    int changed = 2;
    int unrelated = 3;
    int calc() { return used; }
}
"""

BRANCH = """class Calc {
    int used = 1;
    int changed = 5;
    int unrelated = 3;
    int calc() { return used; }
}
"""


class ContextFilterFlagTest(TestCase):
    def test_disabled_by_default(self):
        with patch.dict(os.environ, {}, clear=True):
            self.assertFalse(context_filter_enabled())

    def test_enabled_with_true(self):
        with patch.dict(os.environ, {CONTEXT_FILTER_ENV_VAR: "true"}, clear=True):
            self.assertTrue(context_filter_enabled())


class DeclaredFieldNamesTest(TestCase):
    def test_simple_and_initialized_fields(self):
        self.assertEqual(declared_field_names("int count;"), ["count"])
        self.assertEqual(declared_field_names('private final String name = "x";'), ["name"])

    def test_generic_and_multiple_declarators(self):
        self.assertEqual(declared_field_names("Map<String, Integer> cache = new HashMap<>();"), ["cache"])
        self.assertEqual(declared_field_names("int a, b;"), ["a", "b"])


class ChangedIdentifiersTest(TestCase):
    def test_only_identifiers_on_changed_lines(self):
        changed = changed_identifiers(BASE, BRANCH)
        self.assertIn("changed", changed)
        self.assertNotIn("unrelated", changed)
        self.assertNotIn("calc", changed)


class FilterClassFieldsTest(TestCase):
    FIELDS = ["int used;", "int changed;", "int unrelated;"]

    def test_keeps_fields_used_by_method(self):
        kept = filter_class_fields(self.FIELDS, "int calc() { return used; }", set())
        self.assertEqual(kept, ["int used;"])

    def test_keeps_fields_touched_by_change(self):
        kept = filter_class_fields(self.FIELDS, "int calc() { return used; }", {"changed"})
        self.assertEqual(kept, ["int used;", "int changed;"])

    def test_keeps_field_it_cannot_read(self):
        kept = filter_class_fields(["???"], "int calc() { return 1; }", set())
        self.assertEqual(kept, ["???"])


class FilterContextTest(TestCase):
    def test_end_to_end_on_changed_class(self):
        fields = ["int used;", "int changed;", "int unrelated;"]
        kept = filter_context(fields, "int calc() { return used; }", BASE, BRANCH)
        self.assertEqual(kept, ["int used;", "int changed;"])
