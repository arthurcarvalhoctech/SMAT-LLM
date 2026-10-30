"""Prompts and response parsing for the LLM interference analysis.

The three criteria are the state-based conditions from the article
*Interference and semantic conflicts* (Paulo Borba). The LLM is a triage
hypothesis generator: it reads the base/left/right/merge snippets and the
declared change summaries, but it does not execute code.
"""

import json
import re
from typing import Any, Dict, List, Optional

from nimrod.laya_interference.criteria import CRITERIA


class LlmResponseError(ValueError):
    """Raised when the model response does not contain a valid analysis."""


def _criteria_description() -> str:
    return "\n".join(
        f"{criterion.number}. {criterion.id} — {criterion.title}\n"
        f"   {criterion.article_definition}"
        for criterion in CRITERIA
    )


def build_messages(state: Any, max_input_chars: int) -> List[Dict[str, str]]:
    """Build the system/user messages sent to the configured LLM."""
    payload = state.to_payload()
    state_text = json.dumps(
        payload,
        ensure_ascii=False,
        indent=2,
        sort_keys=True,
    )
    if len(state_text) > max_input_chars:
        state_text = (
            state_text[:max_input_chars]
            + "\n... [source state truncated by SMAT due to input limit]\n"
        )

    schema = """{
  "criteria": {
    "criterion_1_global_divergence": {
      "probability": 0.0,
      "triggered": false,
      "evidence": "short source-based justification"
    },
    "criterion_2_parent_change_loss": {
      "probability": 0.0,
      "triggered": false,
      "evidence": "short source-based justification"
    },
    "criterion_3_merge_new_effect": {
      "probability": 0.0,
      "triggered": false,
      "evidence": "short source-based justification"
    }
  },
  "primary_criterion": "criterion_1_global_divergence | criterion_2_parent_change_loss | criterion_3_merge_new_effect | none",
  "affected_branch": "left | right | both | unclear",
  "confidence": "very low | low | medium | high | very high",
  "summary": "one paragraph summary",
  "reasoning": "concise explanation grounded in the supplied code and summaries"
}"""

    system = (
        "You are a senior software engineering researcher analyzing whether "
        "two independent changes to a base program interfere after a merge. "
        "Use only the supplied Java snippets and declared change summaries. "
        "Do not execute code and do not invent behavior. This analysis is a "
        "triage hypothesis, not a confirmed execution result. "
        "Return exactly one JSON object with no markdown fences, comments or "
        "extra text."
    )

    user = f"""Analyze the merge scenario for the three interference criteria.

Criteria:
{_criteria_description()}

Scenario state:
{state_text}

Instructions:
- Evaluate each criterion independently. A criterion is triggered only when
  the supplied code/summaries provide concrete evidence for it.
- `probability` must be a number from 0 to 1 representing evidence strength,
  not a claim of statistical certainty.
- `triggered` must be true when the evidence supports the criterion.
- `primary_criterion` must be one of the three criterion ids, or "none" when
  no criterion is supported.
- `affected_branch` must be "left", "right", "both" or "unclear".
- `confidence` must be one of the listed labels.
- Keep evidence tied to the source. If the state was truncated, say so in the
  reasoning and avoid unsupported claims.

Return this JSON schema:
{schema}
"""
    return [
        {"role": "system", "content": system},
        {"role": "user", "content": user},
    ]


def _first_json_object(text: str) -> str:
    """Return the first complete JSON object, ignoring trailing text.

    Some reasoning models return a valid object followed by a second object or
    an explanatory suffix. Using the first-to-last brace would merge both and
    produce ``Extra data`` even though the first object is valid.
    """
    start = text.find("{")
    if start < 0:
        raise LlmResponseError("The LLM response does not contain a JSON object.")

    depth = 0
    in_string = False
    escaped = False

    for index in range(start, len(text)):
        character = text[index]
        if in_string:
            if escaped:
                escaped = False
            elif character == "\\":
                escaped = True
            elif character == '"':
                in_string = False
            continue

        if character == '"':
            in_string = True
        elif character == "{":
            depth += 1
        elif character == "}":
            depth -= 1
            if depth == 0:
                return text[start : index + 1]

    raise LlmResponseError("The LLM response contains an incomplete JSON object.")


def _extract_json(text: str) -> Dict[str, Any]:
    if not isinstance(text, str) or not text.strip():
        raise LlmResponseError("The LLM returned an empty response.")

    cleaned = text.strip()
    if cleaned.startswith("```"):
        cleaned = re.sub(r"^```(?:json)?\s*", "", cleaned, flags=re.IGNORECASE)
        cleaned = re.sub(r"\s*```$", "", cleaned)

    candidate = _first_json_object(cleaned)

    try:
        parsed = json.loads(candidate)
    except json.JSONDecodeError as error:
        raise LlmResponseError(f"Invalid JSON from LLM: {error}") from error

    if not isinstance(parsed, dict):
        raise LlmResponseError("The LLM response JSON is not an object.")
    return parsed


def _parse_bool(value: Any) -> Optional[bool]:
    if isinstance(value, bool):
        return value
    if isinstance(value, (int, float)):
        return bool(value)
    if isinstance(value, str):
        normalized = value.strip().lower()
        if normalized in {"true", "yes", "1", "sim"}:
            return True
        if normalized in {"false", "no", "0", "nao", "não"}:
            return False
    return None


def _parse_probability(value: Any) -> Optional[float]:
    if value is None or isinstance(value, bool):
        return None
    try:
        parsed = float(value)
    except (TypeError, ValueError):
        return None
    return max(0.0, min(1.0, parsed))


def _criterion_id(value: Any) -> Optional[str]:
    if not isinstance(value, str):
        return None
    normalized = value.strip()
    for criterion in CRITERIA:
        if normalized == criterion.id:
            return criterion.id
        if normalized.lower() in {
            f"c{criterion.number}",
            str(criterion.number),
        }:
            return criterion.id
    return None


def parse_llm_analysis(text: str, threshold: float) -> Dict[str, Any]:
    """Parse and validate the structured model response."""
    payload = _extract_json(text)
    raw_criteria = payload.get("criteria")
    if not isinstance(raw_criteria, dict):
        raise LlmResponseError("The LLM response has no criteria object.")

    criteria: Dict[str, Dict[str, Any]] = {}
    for criterion in CRITERIA:
        raw = raw_criteria.get(criterion.id)
        if not isinstance(raw, dict):
            raise LlmResponseError(
                f"The LLM response is missing criterion {criterion.id}."
            )

        probability = _parse_probability(raw.get("probability"))
        triggered = _parse_bool(raw.get("triggered"))

        if probability is None and triggered is None:
            raise LlmResponseError(
                f"Criterion {criterion.id} has neither probability nor triggered."
            )

        if probability is None:
            probability = 1.0 if triggered else 0.0
        if triggered is None:
            triggered = probability >= threshold

        criteria[criterion.id] = {
            "probability": probability,
            "triggered": bool(triggered),
            "evidence": str(raw.get("evidence", "") or "").strip(),
        }

    primary = _criterion_id(payload.get("primary_criterion"))
    if payload.get("primary_criterion") in {"none", "None", None}:
        primary = "none"

    affected_branch = payload.get("affected_branch")
    if not isinstance(affected_branch, str):
        affected_branch = None
    elif affected_branch.strip().lower() not in {
        "left",
        "right",
        "both",
        "unclear",
    }:
        affected_branch = None
    else:
        affected_branch = affected_branch.strip().lower()

    confidence = payload.get("confidence")
    if confidence is not None:
        confidence = str(confidence).strip() or None

    return {
        "criteria": criteria,
        "primary_criterion": primary,
        "affected_branch": affected_branch,
        "confidence": confidence,
        "summary": str(payload.get("summary", "") or "").strip(),
        "reasoning": str(payload.get("reasoning", "") or "").strip(),
    }
