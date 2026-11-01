"""Decision policies for the Laya-only interference classifier.

The Laya model returns probabilities, not a calibrated decision. This module
keeps the decision rule explicit and testable so the baseline can be compared
with conservative variants without changing the model integration.
"""

from typing import Dict, Optional, Tuple

POSSIBLE_INTERFERENCE = "possible_interference"
NO_SIGNAL = "no_signal"
UNCERTAIN = "uncertain"

BASELINE = "baseline"
CONSISTENT = "consistent"
CONSERVATIVE = "conservative"

DEFAULT_NONE_THRESHOLD = 0.90


def _triggered(
    probabilities: Dict[str, Optional[float]],
    thresholds: Dict[str, float],
) -> Dict[str, bool]:
    return {
        criterion_id: (
            probability is not None
            and probability >= thresholds.get(criterion_id, 1.0)
        )
        for criterion_id, probability in probabilities.items()
    }


def decide(
    rule: str,
    probabilities: Dict[str, Optional[float]],
    thresholds: Dict[str, float],
    primary_criterion: Optional[str],
    none_probability: Optional[float],
    none_threshold: float = DEFAULT_NONE_THRESHOLD,
    witness: Optional[str] = None,
) -> Tuple[str, str]:
    """Return ``(classification, reason)`` for one Laya assessment.

    ``baseline`` reproduces the historical behavior. ``consistent`` and
    ``conservative`` use the primary-choice answer, the explicit ``none``
    probability, and (when available) the witness choice to avoid treating
    three correlated high probabilities as independent evidence.
    """
    triggered = _triggered(probabilities, thresholds)
    any_triggered = any(triggered.values())

    if rule == BASELINE:
        if any_triggered:
            return POSSIBLE_INTERFERENCE, "any criterion reached its threshold"
        return NO_SIGNAL, "no criterion reached its threshold"

    if rule == CONSISTENT:
        if witness == "none":
            return UNCERTAIN, "the witness choice is none"
        if primary_criterion == "none":
            if any_triggered:
                return (
                    UNCERTAIN,
                    "criteria triggered but the primary choice is none",
                )
            return NO_SIGNAL, "no criterion triggered and the primary choice is none"
        if primary_criterion and triggered.get(primary_criterion, False):
            return (
                POSSIBLE_INTERFERENCE,
                f"primary criterion {primary_criterion} reached its threshold",
            )
        return (
            UNCERTAIN,
            "the primary choice and the criterion probabilities disagree",
        )

    if rule == CONSERVATIVE:
        if witness == "none":
            return UNCERTAIN, "the witness choice is none"
        if primary_criterion == "none":
            return UNCERTAIN, "the primary choice is none"
        if none_probability is not None and none_probability >= none_threshold:
            return (
                UNCERTAIN,
                f"P(none)={none_probability:.3f} is above {none_threshold:.2f}",
            )
        if primary_criterion and triggered.get(primary_criterion, False):
            return (
                POSSIBLE_INTERFERENCE,
                f"primary criterion {primary_criterion} reached its threshold",
            )
        if any_triggered:
            return (
                UNCERTAIN,
                "a criterion triggered without a consistent primary choice",
            )
        return NO_SIGNAL, "no criterion reached its threshold"

    # Unknown rules fall back to the historical behavior.
    if any_triggered:
        return POSSIBLE_INTERFERENCE, "unknown rule; baseline decision"
    return NO_SIGNAL, "unknown rule; baseline decision"
