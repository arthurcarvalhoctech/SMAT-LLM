"""State-based interference hypotheses, never execution-based proof.

The three conditions follow *Interference and semantic conflicts* (Paulo Borba).
They apply to the same observable and input across source versions. Observation
scope is part of the task, not an implicit model decision.
"""

import math
from dataclasses import dataclass
from typing import Any, Dict, Optional, Tuple

PROMPT_VERSION = "state-observables-v2"
QUESTION_FORMATS = ("noul", "noul_ab", "choice_ab")
OBSERVATION_POLICY = (
    "Use the same external inputs, operation sequence and corresponding observation "
    "point across versions, respecting each version's initialization. Compare the same "
    "observable x. If observations are supplied, use only those expressions. Otherwise "
    "compare individual fields, collection entries, return values or exception outcomes; "
    "do not aggregate independent entries into a whole-object difference. "
    "Source behavior is evidence; change summaries are context, not proof. "
    "Missing code or unresolved dependencies do not establish absence of interference."
)


@dataclass(frozen=True)
class InterferenceCriterion:
    id: str
    number: int
    title: str
    article_definition: str
    laya_instruction: str
    laya_false: str
    laya_true: str

    @property
    def required_branches(self) -> Tuple[str, ...]:
        if self.number == 1:
            return ("base", "left", "right")
        return ("base", "left", "right", "merge")


CRITERIA: Tuple[InterferenceCriterion, ...] = (
    InterferenceCriterion(
        id="criterion_1_global_divergence", number=1, title="Divergência global",
        article_definition="Existe um elemento de estado x para o qual B, L e R calculam valores dois a dois diferentes.",
        laya_instruction=(
            "Follow observation_policy. B=base, L=left, R=right. For the same "
            "observable x and input, does the source support B(x) != L(x), "
            "B(x) != R(x), and L(x) != R(x)? Merge is irrelevant to this criterion."
        ),
        laya_false="The source does not support pairwise distinct B, L and R values for a common observable.",
        laya_true="A common observable has pairwise distinct values in B, L and R.",
    ),
    InterferenceCriterion(
        id="criterion_2_parent_change_loss", number=2, title="Perda de alteração do pai",
        article_definition="Existe um elemento de estado x para o qual L (ou R) difere tanto de B quanto de Merge.",
        laya_instruction=(
            "Follow observation_policy. B=base, L=left, R=right, M=merge. "
            "For the same observable x and input, does the source support "
            "(L(x) != B(x) and L(x) != M(x)) or "
            "(R(x) != B(x) and R(x) != M(x))?"
        ),
        laya_false="The source does not support a parent value differing from both B and M for a common observable.",
        laya_true="A common observable has a parent value differing from both B and M.",
    ),
    InterferenceCriterion(
        id="criterion_3_merge_new_effect", number=3, title="Efeito colateral inesperado do merge",
        article_definition="Existe um elemento de estado x para o qual B, L e R são iguais, mas Merge difere.",
        laya_instruction=(
            "Follow observation_policy. B=base, L=left, R=right, M=merge. "
            "For the same observable x and input, does the source support "
            "B(x) = L(x) = R(x) and M(x) != B(x)?"
        ),
        laya_false="The source does not support equal B, L and R values differing from M for a common observable.",
        laya_true="A common observable has equal values in B, L and R and a different value in M.",
    ),
)
CRITERIA_BY_ID = {criterion.id: criterion for criterion in CRITERIA}
PRIMARY_CRITERION_QUESTION_ID = "primary_criterion"
AFFECTED_BRANCH_QUESTION_ID = "affected_branch"
CONFIDENCE_QUESTION_ID = "analysis_confidence"
NONE_CRITERION_LABEL = "none"
CONFIDENCE_LABELS = ["very low", "low", "medium", "high", "very high"]


def build_questions(question_format: str = "noul") -> Dict[str, Dict[str, Any]]:
    """Independent scores and diagnostic questions; alternate formats need validation."""
    if question_format not in QUESTION_FORMATS:
        raise ValueError(f"Unsupported Laya question format: {question_format}")
    questions: Dict[str, Dict[str, Any]] = {}
    for criterion in CRITERIA:
        question = {
            "type": "noul", "instructions": criterion.laya_instruction,
            "criteria": {"false": criterion.laya_false, "true": criterion.laya_true},
        }
        if question_format == "noul_ab":
            question["labels"] = {"false": "B", "true": "A"}
        elif question_format == "choice_ab":
            question.update(type="choice", criteria={"A": criterion.laya_true, "B": criterion.laya_false})
        questions[criterion.id] = question
    questions[PRIMARY_CRITERION_QUESTION_ID] = {
        "type": "choice",
        "instructions": (
            "Follow observation_policy. Which criterion has the strongest source evidence? "
            "Criteria may overlap. Choose none if none is supported, or "
            "insufficient_context if required source behavior cannot be established."
        ),
        "criteria": {c.id: c.laya_true for c in CRITERIA} | {
            "none": "No criterion is supported by the source evidence.",
            "insufficient_context": "Required source behavior cannot be established.",
        },
    }
    questions[AFFECTED_BRANCH_QUESTION_ID] = {
        "type": "choice",
        "instructions": (
            "Follow observation_policy. Which parent's changed behavior is not preserved "
            "by merge? Choose not_applicable if neither parent has a supported lost "
            "change, or unclear if the evidence cannot distinguish the parents."
        ),
        "criteria": {
            "left": "Only the left parent's change is lost.",
            "right": "Only the right parent's change is lost.",
            "both": "Both parents have lost changes.",
            "unclear": "The evidence cannot distinguish the parents.",
            "not_applicable": "Neither parent has a supported lost change.",
        },
    }
    questions[CONFIDENCE_QUESTION_ID] = {
        "type": "score",
        "instructions": (
            "Rate completeness of source evidence for the comparisons. "
            "This diagnostic rubric is not a probability of correctness."
        ),
        "criteria": [
            "very low: required versions or target bodies are missing",
            "low: relevant dependencies or observations are unresolved",
            "medium: versions are present but behavior requires assumptions",
            "high: comparable observations and relevant source behavior are explicit",
            "very high: a concrete common input and comparable outcomes are supported",
        ],
    }
    return questions


def criterion_question_text(criterion: InterferenceCriterion) -> str:
    return criterion.laya_instruction


def _answer_for(raw_result: Any, question_id: str) -> Dict[str, Any]:
    answers = raw_result.get("answers") if isinstance(raw_result, dict) else None
    answer = answers.get(question_id) if isinstance(answers, dict) else None
    return answer if isinstance(answer, dict) else {}


def _bounded_number(value: Any, minimum: float, maximum: float) -> Optional[float]:
    if value is None or isinstance(value, bool):
        return None
    try:
        number = float(value)
        return number if math.isfinite(number) and minimum <= number <= maximum else None
    except (TypeError, ValueError, OverflowError):
        return None


def noul_probability(raw_result: Any, question_id: str) -> Optional[float]:
    return _bounded_number(_answer_for(raw_result, question_id).get("noul"), 0.0, 1.0)


def criterion_probability(raw_result: Any, question_id: str, question_format: str = "noul") -> Optional[float]:
    if question_format != "choice_ab":
        return noul_probability(raw_result, question_id)
    probabilities = _answer_for(raw_result, question_id).get("probabilities")
    if not isinstance(probabilities, dict):
        return None
    positive = _bounded_number(probabilities.get("A"), 0.0, 1.0)
    negative = _bounded_number(probabilities.get("B"), 0.0, 1.0)
    if positive is None or negative is None or not math.isclose(positive + negative, 1.0, abs_tol=1e-4):
        return None
    return positive


def choice_label(raw_result: Any, question_id: str) -> Optional[str]:
    value = _answer_for(raw_result, question_id).get("choice")
    options = build_questions().get(question_id, {}).get("criteria", {})
    return value if isinstance(value, str) and isinstance(options, dict) and value in options else None


def choice_confidence(raw_result: Any, question_id: str) -> Optional[float]:
    return _bounded_number(_answer_for(raw_result, question_id).get("confidence"), 0.0, 1.0)


def score_value(raw_result: Any, question_id: str) -> Optional[float]:
    return _bounded_number(_answer_for(raw_result, question_id).get("score"), 0.0, 4.0)


def score_label(raw_result: Any, question_id: str) -> Optional[str]:
    value = score_value(raw_result, question_id)
    return CONFIDENCE_LABELS[int(round(value))] if value is not None else None
