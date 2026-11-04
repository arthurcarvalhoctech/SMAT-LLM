"""Regression cases for abstention, evidence scope and decision consistency."""

import math
import json
import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from nimrod.laya_interference.config import LayaFlowConfig
from nimrod.laya_interference.criteria import CRITERIA, build_questions, criterion_probability, score_label
from nimrod.laya_interference.flow import LayaInterferenceFlow
from nimrod.source_code import extract_java_class_info
from nimrod.tests.test_laya_interference import FakeLayaClient, make_result, make_state

C1, C2, C3 = (c.id for c in CRITERIA)


class LayaQualityTest(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.flow = LayaInterferenceFlow(LayaFlowConfig(), client=FakeLayaClient(), log_dir=self.temp.name)

    def test_invalid_probability_cannot_become_no_signal_or_positive(self):
        for value in (None, "NaN", math.inf, -0.1, 1.1, True, {}, "bad"):
            with self.subTest(value=value):
                result = self.flow._assessment_from_result(make_state(), make_result(c1=value, c2=.1, c3=.1))
                self.assertEqual(result.classification, "insufficient_context")
                self.assertEqual(result.criteria[C1].status, "invalid_response")
                self.assertFalse(result.criteria[C1].triggered)
                json.dumps(result.to_dict(), allow_nan=False)
        self.assertIsNone(score_label(make_result(confidence=math.nan), "analysis_confidence"))

    def test_empty_response_is_not_no_signal(self):
        for payload in ({}, None, [], {"answers": []}):
            self.assertEqual(self.flow._assessment_from_result(make_state(), payload).classification,
                             "insufficient_context")

    def test_missing_merge_still_allows_c1_but_not_c2_or_c3(self):
        state = make_state()
        del state.branches["merge"]
        client = FakeLayaClient(make_result(c1=.8, c2=.9, c3=.9))
        self.flow.client = client
        with patch("nimrod.laya_interference.flow.build_method_state", return_value=state):
            result = self.flow._analyze_method(None, "example.Foo", "value()")
        self.assertEqual(set(client.calls[0][1]), {C1})
        self.assertEqual(result.triggered_criteria, [C1])
        self.assertFalse(result.assessment_complete)
        self.assertEqual(result.classification, "possible_interference")
        result = self.flow._assessment_from_result(state, make_result(c1=.1))
        self.assertEqual(result.classification, "insufficient_context")

    def test_missing_target_body_skips_inference(self):
        state = make_state()
        state.branches["base"].method_code = " "
        with patch("nimrod.laya_interference.flow.build_method_state", return_value=state):
            result = self.flow._analyze_method(None, "example.Foo", "value()")
        self.assertEqual(self.flow.client.calls, [])
        self.assertEqual(result.classification, "insufficient_context")

    def test_truncation_only_invalidates_affected_questions(self):
        raw = make_result(c1=.1, c2=.9, c3=.1)
        raw["usage"].update(truncated=True, truncated_questions=[C2], state_tokens_dropped=32)
        result = self.flow._assessment_from_result(make_state(), raw)
        self.assertEqual(result.classification, "insufficient_context")
        self.assertEqual(result.criteria[C1].status, "assessed")
        self.assertEqual(result.criteria[C2].reasons, ["truncated_state"])
        self.assertEqual(result.criteria[C2].probability, .9)  # raw score retained for audit
        del raw["usage"]["truncated_questions"]
        self.assertFalse(self.flow._assessment_from_result(make_state(), raw).assessment_complete)

    def test_diagnostic_truncation_does_not_discard_valid_criteria(self):
        raw = make_result(c1=.1, c2=.2, c3=.1)
        raw["usage"].update(truncated=True, truncated_questions=["analysis_confidence"])
        result = self.flow._assessment_from_result(make_state(), raw)
        self.assertEqual(result.classification, "no_signal")
        self.assertIsNone(result.confidence_score)

    def test_primary_is_derived_and_contradictions_are_logged(self):
        result = self.flow._assessment_from_result(make_state(), make_result(c1=.8, c2=.7, c3=.1, primary="none"))
        self.assertEqual(result.primary_criterion, C1)
        self.assertIn("primary_choice_disagrees_with_criterion_scores", result.warnings)
        self.assertIn("c1_probability_exceeds_c2_despite_logical_implication", result.warnings)
        self.assertIsNone(result.primary_criterion_confidence)

    def test_per_criterion_threshold_applies_to_decision_and_reports(self):
        self.flow.config = LayaFlowConfig(criterion_thresholds={C1: .9, C2: .3})
        result = self.flow._assessment_from_result(make_state(), make_result(c1=.8, c2=.4, c3=.1))
        self.assertEqual(result.triggered_criteria, [C2])
        self.assertEqual(result.primary_criterion, C2)
        self.assertEqual(result.classification_dict("test")["criterion_thresholds"][C2], .3)
        self.assertIn("threshold=0.30", "\n".join(result.readable_lines()))

    def test_alternate_question_formats_preserve_positive_semantics(self):
        self.assertEqual(build_questions("noul_ab")[C1]["labels"], {"false": "B", "true": "A"})
        self.assertEqual(build_questions("choice_ab")[C1]["type"], "choice")
        raw = {"answers": {C1: {"probabilities": {"A": .8, "B": .2}, "confidence": .2}}}
        self.assertEqual(criterion_probability(raw, C1, "choice_ab"), .8)
        raw["answers"][C1]["probabilities"]["B"] = .8
        self.assertIsNone(criterion_probability(raw, C1, "choice_ab"))

    def test_env_rejects_nonfinite_threshold_and_reads_overrides(self):
        with patch.dict(os.environ, {"SMAT_LAYA_THRESHOLD": "nan", "SMAT_LAYA_THRESHOLD_C2": ".7",
                                     "SMAT_LAYA_QUESTION_FORMAT": "choice_ab"}, clear=True):
            with self.assertLogs(level="WARNING"):
                config = LayaFlowConfig.from_env(self.temp.name)
        self.assertEqual(config.threshold_for(C1), .5)
        self.assertEqual(config.threshold_for(C2), .7)
        self.assertEqual(config.question_format, "choice_ab")

    def test_payload_excludes_paths_and_carries_observation_contract(self):
        state = make_state()
        state.observations = ['types.get("a")']
        state.observation_context = "new Foo(); init(); inspect each key"
        payload = state.to_payload()
        self.assertNotIn("project", payload)
        self.assertNotIn("path", payload["versions"]["base"])
        self.assertEqual(payload["observations"], state.observations)
        digest = state.digest()
        state.observations = ['types.get("b")']
        self.assertNotEqual(digest, state.digest())


class StrictExtractionTest(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.path = Path(self.temp.name) / "Foo.java"
        self.path.write_text('''class Foo {
            int x = 1;
            int value(int n) { return helper(n); }
            int value(String n) { return 20; }
            int helper(int n) { return nested(n) + x; }
            int nested(int n) { return n * 2; }
            int array(String[] names, int... numbers) { return numbers.length; }
            int generic(java.util.Map<String, Integer> values) { return values.size(); }
            int foreign(a.Value value) { return 1; }
            int foreign(b.Value value) { return 2; }
            class Inner { int value(int n) { return 999; } }
        }''', encoding="utf-8")

    def extract(self, signature, cls="example.Foo"):
        return extract_java_class_info(str(self.path), signature, cls, strict=True)[2]

    def test_correct_overload_and_transitive_helpers(self):
        code = self.extract("value(int)")
        self.assertIn("return helper(n)", code)
        self.assertIn("return nested(n) + x", code)
        self.assertIn("return n * 2", code)
        self.assertNotIn("return 20", code)
        self.assertNotIn("999", code)
        self.assertIn("999", self.extract("value(int)", "example.Foo$Inner"))

    def test_arrays_varargs_and_generic_commas(self):
        self.assertIn("numbers.length", self.extract("array(java.lang.String[], int[])"))
        self.assertIn("values.size()", self.extract("generic(java.util.Map<String, Integer>)"))

    def test_ambiguity_and_missing_targets_are_rejected(self):
        for signature in ("value", "value(double)", "foreign(Value)", "foreign(c.Value)", "missing()"):
            with self.subTest(signature=signature), self.assertRaises(ValueError):
                self.extract(signature)
        self.assertIn("return 2", self.extract("foreign(b.Value)"))
        with self.assertRaises(ValueError):
            self.extract("value(int)", "example.Absent")


if __name__ == "__main__":
    unittest.main()
