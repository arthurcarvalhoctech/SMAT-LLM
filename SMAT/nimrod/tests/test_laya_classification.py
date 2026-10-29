from unittest import TestCase

from nimrod.laya_interference.flow import (
    CLASSIFICATION_ERROR,
    CLASSIFICATION_NO_SIGNAL,
    CLASSIFICATION_POSSIBLE_INTERFERENCE,
    CriterionAssessment,
    LayaAssessment,
)
from nimrod.laya_interference.criteria import CRITERIA


def _assessment(triggered: bool, error: str = None) -> LayaAssessment:
    criteria = {
        criterion.id: CriterionAssessment(
            criterion_id=criterion.id,
            number=criterion.number,
            title=criterion.title,
            article_definition=criterion.article_definition,
            probability=0.9 if triggered and criterion.number == 1 else 0.1,
            threshold=0.5,
            triggered=triggered and criterion.number == 1,
        )
        for criterion in CRITERIA
    }
    return LayaAssessment(
        timestamp="2026-10-21T00:00:00",
        project_name="p",
        class_name="example.Foo",
        method_name="value",
        method_signature="value()",
        jar_type="transformed",
        model="english",
        threshold=0.5,
        max_len=512,
        state_digest="x",
        source_paths={},
        missing_branches=[],
        criteria=criteria,
        error=error,
    )


class LayaClassificationLabelsTest(TestCase):
    def test_triggered_criterion_is_possible_interference(self):
        self.assertEqual(_assessment(triggered=True).classification, CLASSIFICATION_POSSIBLE_INTERFERENCE)

    def test_no_triggered_criterion_is_no_signal_not_absence(self):
        self.assertEqual(_assessment(triggered=False).classification, CLASSIFICATION_NO_SIGNAL)

    def test_error_is_error(self):
        self.assertEqual(_assessment(triggered=False, error="boom").classification, CLASSIFICATION_ERROR)
