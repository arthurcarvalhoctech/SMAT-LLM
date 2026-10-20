"""The three state-based interference criteria from the article.

The article *Interference and semantic conflicts* (Paulo Borba) presents the
following three concrete conditions:

1. Global divergence: there is a state element ``x`` such that ``B``, ``L`` and
   ``R`` compute pairwise different values for ``x``.
2. Lost parent change: there is a state element ``x`` such that ``L`` (or
   ``R``) computes a value different from both ``B`` and ``Merge``.
3. Unexpected merge effect: there is a state element ``x`` such that ``B``,
   ``L`` and ``R`` compute the same value, but ``Merge`` computes a different
   value.

The article also discusses a fourth formulation in terms of effects ("Merge
has new effects besides the ones in L and R"). It is the same property as
criterion 3 expressed with effects instead of concrete state elements, so it is
documented here as part of criterion 3 rather than as a separate criterion.

Laya does not execute code and cannot compute state values. The questions below
therefore ask Laya for a *hypothesis* over the source versions and the declared
change summaries. The current SMAT execution-based detection remains the
authoritative signal.
"""

from dataclasses import dataclass
from typing import Any, Dict, Optional, Tuple


@dataclass(frozen=True)
class InterferenceCriterion:
    id: str
    number: int
    title: str
    article_definition: str
    laya_instruction: str
    laya_false: str
    laya_true: str


CRITERIA: Tuple[InterferenceCriterion, ...] = (
    InterferenceCriterion(
        id="criterion_1_global_divergence",
        number=1,
        title="Divergência global",
        article_definition=(
            "Existe um state element x tal que B, L e R calculam valores "
            "diferentes entre si para x."
        ),
        laya_instruction=(
            "Criterion 1, global divergence. Separate changes L and R to a base "
            "program B interfere when there is a state element x such that B, L "
            "and R compute pairwise different values for x. Using the base, "
            "left, right and merge versions and the declared change summaries, "
            "is there evidence of pairwise divergence among base, left and "
            "right?"
        ),
        laya_false=(
            "No state element is computed with pairwise different values by "
            "base, left and right."
        ),
        laya_true=(
            "At least one state element is computed with pairwise different "
            "values by base, left and right."
        ),
    ),
    InterferenceCriterion(
        id="criterion_2_parent_change_loss",
        number=2,
        title="Perda de alteração do pai",
        article_definition=(
            "Existe um state element x tal que L (ou R) calcula um valor "
            "diferente de B e de Merge para x."
        ),
        laya_instruction=(
            "Criterion 2, lost parent change. Separate changes L and R to a "
            "base program B interfere when there is a state element x such "
            "that L (or R) computes a value different from both B and Merge "
            "for x, meaning that Merge fails to preserve a change made by a "
            "parent. Using the base, left, right and merge versions and the "
            "declared change summaries, is there evidence of a lost parent "
            "change?"
        ),
        laya_false=(
            "No state element shows a parent value that differs from both "
            "base and merge."
        ),
        laya_true=(
            "At least one state element shows a parent value that differs "
            "from both base and merge."
        ),
    ),
    InterferenceCriterion(
        id="criterion_3_merge_new_effect",
        number=3,
        title="Efeito colateral inesperado do merge",
        article_definition=(
            "Existe um state element x tal que B, L e R calculam o mesmo "
            "valor para x, mas Merge calcula um valor diferente. De forma "
            "equivalente, Merge introduz novos efeitos além dos de L e R."
        ),
        laya_instruction=(
            "Criterion 3, unexpected merge effect. Separate changes L and R to "
            "a base program B interfere when there is a state element x such "
            "that B, L and R compute the same value for x, but Merge computes "
            "a different value. Equivalently, Merge has new effects besides "
            "the ones in L and R. Using the base, left, right and merge "
            "versions and the declared change summaries, is there evidence of "
            "an unexpected merge effect?"
        ),
        laya_false=(
            "No state element is unchanged in base, left and right while "
            "differing in merge."
        ),
        laya_true=(
            "At least one state element is unchanged in base, left and right "
            "while differing in merge."
        ),
    ),
)

CRITERIA_BY_ID: Dict[str, InterferenceCriterion] = {
    criterion.id: criterion for criterion in CRITERIA
}

PRIMARY_CRITERION_QUESTION_ID = "primary_criterion"
AFFECTED_BRANCH_QUESTION_ID = "affected_branch"
CONFIDENCE_QUESTION_ID = "analysis_confidence"

NONE_CRITERION_LABEL = "none"


def build_questions() -> Dict[str, Dict[str, Any]]:
    """Build the typed Laya questions for the three criteria.

    Each criterion gets an independent ``noul`` question so its probability is
    preserved even when another criterion is the primary hypothesis. A
    ``choice`` question selects the strongest criterion, a ``choice`` question
    identifies the affected branch, and a ``score`` question records the
    model's confidence.
    """
    questions: Dict[str, Dict[str, Any]] = {}

    for criterion in CRITERIA:
        questions[criterion.id] = {
            "type": "noul",
            "instructions": criterion.laya_instruction,
            "criteria": {
                "false": criterion.laya_false,
                "true": criterion.laya_true,
            },
        }

    questions[PRIMARY_CRITERION_QUESTION_ID] = {
        "type": "choice",
        "instructions": (
            "Which of the three interference criteria is most strongly "
            "suggested by the state? Choose exactly one. Choose 'none' only "
            "when none of the criteria is supported."
        ),
        "criteria": {
            criterion.id: f"Criterion {criterion.number}: {criterion.title}. "
            f"{criterion.article_definition}"
            for criterion in CRITERIA
        }
        | {
            NONE_CRITERION_LABEL: (
                "No interference criterion is supported by the available "
                "code and change summaries."
            )
        },
    }

    questions[AFFECTED_BRANCH_QUESTION_ID] = {
        "type": "choice",
        "instructions": (
            "Which branch's changed behavior is most likely not preserved by "
            "the merge? Choose 'both' when both parents are affected, or "
            "'unclear' when the state does not distinguish them."
        ),
        "criteria": {
            "left": "The behavior changed by the left branch is not preserved.",
            "right": "The behavior changed by the right branch is not preserved.",
            "both": "Both branches are affected.",
            "unclear": "The state does not identify a single affected branch.",
        },
    }

    questions[CONFIDENCE_QUESTION_ID] = {
        "type": "score",
        "instructions": (
            "How confident is this pre-analysis, given only the source "
            "versions and the declared change summaries?"
        ),
        "criteria": ["very low", "low", "medium", "high", "very high"],
    }

    return questions


def criterion_question_text(criterion: InterferenceCriterion) -> str:
    return criterion.laya_instruction


def _answer_for(raw_result: Any, question_id: str) -> Dict[str, Any]:
    if not isinstance(raw_result, dict):
        return {}
    answers = raw_result.get("answers")
    if not isinstance(answers, dict):
        return {}
    answer = answers.get(question_id)
    return answer if isinstance(answer, dict) else {}


def noul_probability(raw_result: Any, question_id: str) -> Optional[float]:
    answer = _answer_for(raw_result, question_id)
    value = answer.get("noul")
    if value is None:
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def choice_label(raw_result: Any, question_id: str) -> Optional[str]:
    answer = _answer_for(raw_result, question_id)
    value = answer.get("choice")
    return str(value) if value is not None else None


def choice_confidence(raw_result: Any, question_id: str) -> Optional[float]:
    answer = _answer_for(raw_result, question_id)
    value = answer.get("confidence")
    if value is None:
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def score_value(raw_result: Any, question_id: str) -> Optional[float]:
    answer = _answer_for(raw_result, question_id)
    value = answer.get("score")
    if value is None:
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def score_label(raw_result: Any, question_id: str) -> Optional[str]:
    value = score_value(raw_result, question_id)
    if value is None:
        return None
    labels = build_questions()[question_id]["criteria"]
    index = max(0, min(len(labels) - 1, int(round(value))))
    return labels[index]
