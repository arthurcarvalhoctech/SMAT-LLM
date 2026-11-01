"""Laya pre-analysis flow for the three interference criteria.

This flow runs before SMAT's execution-based detection. It builds a compact
source state for each target method, asks Laya three independent ``noul``
questions plus one ``choice`` and one ``score`` question, and writes a readable
log and a JSONL file for analysis.

Laya is a hypothesis generator here, not an oracle: it does not execute code and
cannot compute state values. The execution-based SMAT pipeline remains the
authoritative detector.
"""

import gc
import json
import logging
import os
import re
import traceback
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, Dict, List, Optional, Tuple, Union

from nimrod.core.merge_scenario_under_analysis import MergeScenarioUnderAnalysis
from nimrod.laya_interference.client import (
    LayaClient,
    LayaUnavailableError,
    RouterLayaClient,
)
from nimrod.laya_interference.config import LayaFlowConfig
from nimrod.laya_interference.decision import decide
from nimrod.laya_interference.criteria import (
    AFFECTED_BRANCH_QUESTION_ID,
    CONFIDENCE_QUESTION_ID,
    CRITERIA,
    PRIMARY_CRITERION_QUESTION_ID,
    WITNESS_QUESTION_ID,
    build_questions,
    choice_confidence,
    choice_label,
    choice_probability,
    noul_probability,
    score_label,
    score_value,
)
from nimrod.laya_interference.source_context import (
    LayaMethodState,
    build_method_state,
    parse_method_item,
)


def _default_log_dir() -> str:
    from nimrod.tests.utils import get_base_output_path

    return os.path.join(os.path.dirname(get_base_output_path()), "reports", "laya")


CLASSIFICATION_POSSIBLE_INTERFERENCE = "possible_interference"
CLASSIFICATION_NO_SIGNAL = "no_signal"
CLASSIFICATION_UNCERTAIN = "uncertain"
CLASSIFICATION_ERROR = "error"

CLASSIFICATION_NOTE = (
    "Laya triage only. possible_interference is a hypothesis, not a confirmed "
    "conflict. no_signal does not prove the absence of interference. "
    "Execution-based detection remains the reference."
)


def _safe_file_part(value: str) -> str:
    return re.sub(r"[^A-Za-z0-9_.-]+", "_", value).strip("_") or "unnamed"


@dataclass
class CriterionAssessment:
    criterion_id: str
    number: int
    title: str
    article_definition: str
    probability: Optional[float]
    threshold: float
    triggered: bool

    def to_dict(self) -> Dict[str, Any]:
        return {
            "number": self.number,
            "title": self.title,
            "article_definition": self.article_definition,
            "probability": self.probability,
            "threshold": self.threshold,
            "triggered": self.triggered,
        }


@dataclass
class LayaAssessment:
    timestamp: str
    project_name: str
    class_name: str
    method_name: str
    method_signature: str
    jar_type: str
    model: str
    threshold: float
    max_len: int
    state_digest: str
    source_paths: Dict[str, str]
    missing_branches: List[str]
    criteria: Dict[str, CriterionAssessment] = field(default_factory=dict)
    state_format: str = "json"
    none_probability: Optional[float] = None
    witness: Optional[str] = None
    witness_confidence: Optional[float] = None
    witness_two_stage: bool = False
    allow_baseline_with_witness: bool = False
    negative_instructions: bool = True
    diagnostic_questions: bool = False
    criterion_thresholds: Tuple[float, float, float] = ()
    decision_rule: str = "baseline"
    decision_reason: str = ""
    classification_override: Optional[str] = None
    primary_criterion: Optional[str] = None
    primary_criterion_confidence: Optional[float] = None
    affected_branch: Optional[str] = None
    affected_branch_confidence: Optional[float] = None
    confidence_score: Optional[float] = None
    confidence_label: Optional[str] = None
    routing: Dict[str, Any] = field(default_factory=dict)
    usage: Dict[str, Any] = field(default_factory=dict)
    answers: Dict[str, Any] = field(default_factory=dict)
    error: Optional[str] = None
    error_traceback: Optional[str] = None

    @property
    def triggered_criteria(self) -> List[str]:
        return [
            criterion_id
            for criterion_id, assessment in self.criteria.items()
            if assessment.triggered
        ]

    @property
    def classification(self) -> str:
        if self.error:
            return CLASSIFICATION_ERROR
        if self.classification_override is not None:
            return self.classification_override
        if self.triggered_criteria:
            return CLASSIFICATION_POSSIBLE_INTERFERENCE
        return CLASSIFICATION_NO_SIGNAL

    def classification_dict(self, run_id: str) -> Dict[str, Any]:
        return {
            "run_id": run_id,
            "timestamp": self.timestamp,
            "project": self.project_name,
            "class": self.class_name,
            "method": self.method_name,
            "method_signature": self.method_signature,
            "jar_type": self.jar_type,
            "model": self.model,
            "max_len": self.max_len,
            "threshold": self.threshold,
            "state_format": self.state_format,
            "witness_two_stage": self.witness_two_stage,
            "allow_baseline_with_witness": self.allow_baseline_with_witness,
            "negative_instructions": self.negative_instructions,
            "diagnostic_questions": self.diagnostic_questions,
            "criterion_thresholds": list(self.criterion_thresholds),
            "none_probability": self.none_probability,
            "witness": self.witness,
            "witness_confidence": self.witness_confidence,
            "decision_rule": self.decision_rule,
            "decision_reason": self.decision_reason,
            "classification": self.classification,
            "triggered_criteria": self.triggered_criteria,
            "primary_criterion": self.primary_criterion,
            "affected_branch": self.affected_branch,
            "confidence": self.confidence_label,
            "probabilities": {
                criterion_id: assessment.probability
                for criterion_id, assessment in self.criteria.items()
            },
            "error": self.error,
            "note": CLASSIFICATION_NOTE,
        }

    def to_dict(self) -> Dict[str, Any]:
        return {
            "timestamp": self.timestamp,
            "project": self.project_name,
            "class": self.class_name,
            "method": self.method_name,
            "method_signature": self.method_signature,
            "jar_type": self.jar_type,
            "model": self.model,
            "threshold": self.threshold,
            "max_len": self.max_len,
            "state_format": self.state_format,
            "state_digest": self.state_digest,
            "witness_two_stage": self.witness_two_stage,
            "allow_baseline_with_witness": self.allow_baseline_with_witness,
            "negative_instructions": self.negative_instructions,
            "diagnostic_questions": self.diagnostic_questions,
            "criterion_thresholds": list(self.criterion_thresholds),
            "none_probability": self.none_probability,
            "witness": self.witness,
            "witness_confidence": self.witness_confidence,
            "decision_rule": self.decision_rule,
            "decision_reason": self.decision_reason,
            "source_paths": self.source_paths,
            "missing_branches": self.missing_branches,
            "criteria": {
                criterion_id: assessment.to_dict()
                for criterion_id, assessment in self.criteria.items()
            },
            "triggered_criteria": self.triggered_criteria,
            "primary_criterion": self.primary_criterion,
            "primary_criterion_confidence": self.primary_criterion_confidence,
            "affected_branch": self.affected_branch,
            "affected_branch_confidence": self.affected_branch_confidence,
            "confidence_score": self.confidence_score,
            "confidence_label": self.confidence_label,
            "routing": self.routing,
            "usage": self.usage,
            "answers": self.answers,
            "error": self.error,
            "error_traceback": self.error_traceback,
        }

    def readable_lines(self) -> List[str]:
        sources = " ".join(
            f"{branch}={self.source_paths.get(branch, '') or '-'}"
            for branch in ("base", "left", "right", "merge")
        )
        lines = [
            "",
            f"[{self.timestamp}] {self.project_name} :: {self.class_name}.{self.method_name}",
            f"  jar_type={self.jar_type} method_signature={self.method_signature!r}",
            f"  state_digest={self.state_digest}",
            f"  state_format={self.state_format}",
            f"  decision_rule={self.decision_rule}",
            f"  witness_two_stage={self.witness_two_stage}",
            f"  criterion_thresholds={self.criterion_thresholds}",
            f"  decision={self.classification} ({self.decision_reason or '-'})",
            f"  none_probability={self.none_probability}",
            f"  witness={self.witness}",
            f"  witness_confidence={self.witness_confidence}",
            f"  sources: {sources}",
            f"  missing_branches={self.missing_branches or '-'}",
        ]

        for criterion in CRITERIA:
            assessment = self.criteria.get(criterion.id)
            probability = (
                "n/a"
                if assessment is None or assessment.probability is None
                else f"{assessment.probability:.4f}"
            )
            triggered = (
                "TRIGGERED"
                if assessment is not None and assessment.triggered
                else "not-triggered"
            )
            lines.append(
                f"  {criterion.id}: p={probability} "
                f"threshold={assessment.threshold if assessment else self.threshold:.2f} "
                f"-> {triggered}"
            )
            lines.append(f"    definition: {criterion.article_definition}")

        def format_choice(label: Optional[str], confidence: Optional[float]) -> str:
            if label is None:
                return "n/a"
            if confidence is None:
                return label
            return f"{label} (confidence={confidence:.4f})"

        lines.append(
            "  primary_criterion: "
            + format_choice(
                self.primary_criterion, self.primary_criterion_confidence
            )
        )
        lines.append(
            "  affected_branch: "
            + format_choice(self.affected_branch, self.affected_branch_confidence)
        )
        lines.append(
            "  analysis_confidence: "
            + (
                "n/a"
                if self.confidence_score is None
                else f"{self.confidence_score:.4f} ({self.confidence_label or 'n/a'})"
            )
        )
        lines.append(
            "  triggered_criteria: "
            + (", ".join(self.triggered_criteria) if self.triggered_criteria else "none")
        )
        lines.append(f"  routing: {json.dumps(self.routing, ensure_ascii=False, sort_keys=True, default=str)}")
        lines.append(f"  usage: {json.dumps(self.usage, ensure_ascii=False, sort_keys=True, default=str)}")
        if self.error:
            lines.append(f"  error: {self.error}")
        if self.error_traceback:
            lines.append("  traceback:")
            lines.extend(
                "    " + line
                for line in self.error_traceback.rstrip().splitlines()
            )

        return lines


class LayaInterferenceFlow:
    """Run the Laya pre-analysis for every target method in a scenario."""

    def __init__(
        self,
        config: LayaFlowConfig,
        client: Optional[LayaClient] = None,
        log_dir: Optional[str] = None,
    ) -> None:
        self.config = config
        self.client = client if client is not None else RouterLayaClient(
            model=config.model, max_len=config.max_len
        )
        self.log_dir = log_dir or config.log_dir or _default_log_dir()
        run_id = datetime.now().strftime("%Y%m%d_%H%M%S_%f")
        self.log_path = os.path.join(
            self.log_dir, f"laya_interference_{run_id}.log"
        )
        self.jsonl_path = os.path.join(
            self.log_dir, f"laya_interference_{run_id}.jsonl"
        )
        self.run_id = run_id
        self.classification_dir = os.path.join(
            self.log_dir, "classification", f"run_{run_id}"
        )
        self._classification_count = 0
        self._initialized = False
        self._unavailable_reason: Optional[str] = None
        self._logged_errors: set[str] = set()

    def _ensure_initialized(self) -> None:
        if self._initialized:
            return

        try:
            os.makedirs(self.log_dir, exist_ok=True)
            client_description = {}
            describe = getattr(self.client, "describe", None)
            if callable(describe):
                try:
                    client_description = describe()
                except Exception:
                    client_description = {}
            with open(self.log_path, "a", encoding="utf-8") as log_file:
                log_file.write("=" * 80 + "\n")
                log_file.write("Laya interference pre-analysis\n")
                log_file.write(
                    "role=hypothesis-only; execution-based SMAT remains authoritative\n"
                )
                log_file.write(f"model={self.config.model}\n")
                log_file.write(f"max_len={self.config.max_len}\n")
                log_file.write(f"threshold={self.config.threshold:.2f}\n")
                log_file.write(
                    "criterion_thresholds="
                    + ",".join(f"{value:.2f}" for value in self.config.criterion_thresholds)
                    + "\n"
                )
                log_file.write(f"decision_rule={self.config.decision_rule}\n")
                log_file.write(f"state_format={self.config.state_format}\n")
                log_file.write(f"witness={self.config.witness}\n")
                log_file.write(f"witness_two_stage={self.config.witness_two_stage}\n")
                log_file.write(
                    "allow_baseline_with_witness="
                    f"{self.config.allow_baseline_with_witness}\n"
                )
                log_file.write(
                    "negative_instructions="
                    f"{self.config.negative_instructions}\n"
                )
                log_file.write(
                    "diagnostic_questions="
                    f"{self.config.diagnostic_questions}\n"
                )
                log_file.write(
                    "client="
                    + json.dumps(
                        client_description,
                        ensure_ascii=False,
                        sort_keys=True,
                        default=str,
                    )
                    + "\n"
                )
                log_file.write("=" * 80 + "\n")
            self._initialized = True
        except OSError as error:
            logging.error("Could not create the Laya log files in %s: %s", self.log_dir, error)
            self._initialized = True

    def run_for_scenario(
        self, scenario: MergeScenarioUnderAnalysis
    ) -> List[LayaAssessment]:
        logging.info(
            "Starting Laya interference pre-analysis for project %s",
            scenario.project_name,
        )
        assessments: List[LayaAssessment] = []

        for class_name, methods in (scenario.targets or {}).items():
            if not isinstance(methods, (list, tuple)):
                methods = [methods]
            for method_item in methods:
                assessment = self._analyze_method(
                    scenario, class_name, method_item
                )
                if assessment is not None:
                    assessments.append(assessment)
                    self._write_assessment(assessment)
                    self._write_classification(assessment)
                    # The Laya runtime can retain large tensors between calls.
                    gc.collect()

        logging.info(
            "Finished Laya interference pre-analysis for project %s (%d method(s))",
            scenario.project_name,
            len(assessments),
        )
        return assessments

    def _traceback_once(self, error: Exception) -> Optional[str]:
        message = str(error)
        if message in self._logged_errors:
            return None
        self._logged_errors.add(message)
        return traceback.format_exc()

    def _questions_for(self, witness_candidates=None):
        """Return only the questions used by the configured decision rule.

        baseline uses C1/C2/C3 only. consistent/conservative additionally need
        witness and primary. affected_branch/analysis_confidence are diagnostic
        and only requested when explicitly enabled.
        """
        questions = build_questions(
            witness_candidates,
            negative_instructions=self.config.negative_instructions,
        )
        allowed = {criterion.id for criterion in CRITERIA}
        if self.config.decision_rule != "baseline":
            allowed.add(PRIMARY_CRITERION_QUESTION_ID)
            if witness_candidates:
                allowed.add(WITNESS_QUESTION_ID)
        if self.config.diagnostic_questions:
            allowed.update({AFFECTED_BRANCH_QUESTION_ID, CONFIDENCE_QUESTION_ID})
        return {key: value for key, value in questions.items() if key in allowed}

    def _analyze_method(
        self,
        scenario: MergeScenarioUnderAnalysis,
        class_name: str,
        method_item: Union[str, Dict[str, str]],
    ) -> LayaAssessment:
        try:
            state = build_method_state(scenario, class_name, method_item)
        except Exception as error:
            logging.error(
                "Laya pre-analysis could not build the source state for %s: %s",
                class_name,
                error,
            )
            return self._error_assessment(
                scenario,
                class_name,
                method_item,
                error,
                error_traceback=self._traceback_once(error),
            )

        if self._unavailable_reason is not None:
            return self._error_assessment(
                scenario,
                class_name,
                method_item,
                LayaUnavailableError(self._unavailable_reason),
                state=state,
            )

        try:
            state_payload = (
                state.to_compact_payload()
                if self.config.state_format == "compact"
                else state.to_payload()
            )
            use_witness = self.config.witness and (
                self.config.decision_rule != "baseline"
                or self.config.witness_two_stage
            )
            witness_candidates = (
                state.witness_candidates() if use_witness else None
            )
            witness_override = None
            witness_confidence_override = None
            if witness_candidates and self.config.witness_two_stage:
                witness_result = self.client.predict(
                    state_payload,
                    build_questions(
                        witness_candidates,
                        include_criteria=False,
                        negative_instructions=self.config.negative_instructions,
                    ),
                )
                witness_override = choice_label(
                    witness_result, WITNESS_QUESTION_ID
                )
                witness_confidence_override = choice_confidence(
                    witness_result, WITNESS_QUESTION_ID
                )
                if witness_override in (None, "none"):
                    raw_result = witness_result
                else:
                    focused_payload = self._with_witness(
                        state_payload, witness_override
                    )
                    raw_result = self.client.predict(
                        focused_payload,
                        self._questions_for(),
                    )
            else:
                raw_result = self.client.predict(
                    state_payload,
                    self._questions_for(witness_candidates),
                )
        except LayaUnavailableError as error:
            self._unavailable_reason = str(error)
            logging.error("Laya pre-analysis is unavailable: %s", error)
            return self._error_assessment(
                scenario,
                class_name,
                method_item,
                error,
                state=state,
                error_traceback=self._traceback_once(error),
            )
        except Exception as error:
            logging.error(
                "Laya pre-analysis failed for %s.%s: %s",
                class_name,
                state.method_name,
                error,
            )
            return self._error_assessment(
                scenario,
                class_name,
                method_item,
                error,
                state=state,
                error_traceback=self._traceback_once(error),
            )

        return self._assessment_from_result(
            state,
            raw_result,
            state_payload,
            witness_candidates,
            witness_override=witness_override,
            witness_confidence_override=witness_confidence_override,
        )

    def _with_witness(self, payload: Any, witness: str) -> Any:
        if isinstance(payload, str):
            return payload + f"\nTestemunha: {witness}"
        if isinstance(payload, dict):
            focused = dict(payload)
            focused["witness"] = witness
            return focused
        return payload

    def _assessment_from_result(
        self,
        state: LayaMethodState,
        raw_result: Dict[str, Any],
        state_payload: Any = None,
        witness_candidates: Optional[Dict[str, str]] = None,
        witness_override: Optional[str] = None,
        witness_confidence_override: Optional[float] = None,
    ) -> LayaAssessment:
        thresholds = {
            criterion.id: self.config.criterion_thresholds[index]
            for index, criterion in enumerate(CRITERIA)
        }
        criteria: Dict[str, CriterionAssessment] = {}
        probabilities: Dict[str, Optional[float]] = {}
        for criterion in CRITERIA:
            probability = noul_probability(raw_result, criterion.id)
            probabilities[criterion.id] = probability
            criteria[criterion.id] = CriterionAssessment(
                criterion_id=criterion.id,
                number=criterion.number,
                title=criterion.title,
                article_definition=criterion.article_definition,
                probability=probability,
                threshold=thresholds[criterion.id],
                triggered=(
                    probability is not None
                    and probability >= thresholds[criterion.id]
                ),
            )

        routing = raw_result.get("routing", {}) if isinstance(raw_result, dict) else {}
        usage = raw_result.get("usage", {}) if isinstance(raw_result, dict) else {}
        answers = raw_result.get("answers", {}) if isinstance(raw_result, dict) else {}
        primary_criterion = choice_label(
            raw_result, PRIMARY_CRITERION_QUESTION_ID
        )
        none_probability = choice_probability(
            raw_result, PRIMARY_CRITERION_QUESTION_ID, "none"
        )
        witness = (
            witness_override
            if witness_override is not None
            else (
                choice_label(raw_result, WITNESS_QUESTION_ID)
                if witness_candidates
                else None
            )
        )
        witness_confidence = (
            witness_confidence_override
            if witness_confidence_override is not None
            else (
                choice_confidence(raw_result, WITNESS_QUESTION_ID)
                if witness_candidates
                else None
            )
        )
        classification, decision_reason = decide(
            self.config.decision_rule,
            probabilities,
            thresholds,
            primary_criterion,
            none_probability,
            witness=witness,
        )

        return LayaAssessment(
            timestamp=datetime.now().isoformat(timespec="seconds"),
            project_name=state.project_name,
            class_name=state.class_name,
            method_name=state.method_name,
            method_signature=state.method_signature,
            jar_type=state.jar_type,
            model=self.config.model,
            threshold=self.config.threshold,
            max_len=self.config.max_len,
            state_format=self.config.state_format,
            state_digest=state.digest(state_payload),
            source_paths=state.source_paths(),
            missing_branches=state.missing_branches,
            criteria=criteria,
            witness_two_stage=self.config.witness_two_stage,
            allow_baseline_with_witness=self.config.allow_baseline_with_witness,
            negative_instructions=self.config.negative_instructions,
            diagnostic_questions=self.config.diagnostic_questions,
            criterion_thresholds=self.config.criterion_thresholds,
            none_probability=none_probability,
            witness=witness,
            witness_confidence=witness_confidence,
            decision_rule=self.config.decision_rule,
            decision_reason=decision_reason,
            classification_override=classification,
            primary_criterion=primary_criterion,
            primary_criterion_confidence=choice_confidence(
                raw_result, PRIMARY_CRITERION_QUESTION_ID
            ),
            affected_branch=choice_label(
                raw_result, AFFECTED_BRANCH_QUESTION_ID
            ),
            affected_branch_confidence=choice_confidence(
                raw_result, AFFECTED_BRANCH_QUESTION_ID
            ),
            confidence_score=score_value(
                raw_result, CONFIDENCE_QUESTION_ID
            ),
            confidence_label=score_label(
                raw_result, CONFIDENCE_QUESTION_ID
            ),
            routing=routing if isinstance(routing, dict) else {},
            usage=usage if isinstance(usage, dict) else {},
            answers=answers if isinstance(answers, dict) else {},
        )

    def _error_assessment(
        self,
        scenario: MergeScenarioUnderAnalysis,
        class_name: str,
        method_item: Union[str, Dict[str, str]],
        error: Exception,
        state: Optional[LayaMethodState] = None,
        error_traceback: Optional[str] = None,
    ) -> LayaAssessment:
        if state is None:
            method_signature, left_summary, right_summary = parse_method_item(
                method_item
            )
            state = LayaMethodState(
                project_name=scenario.project_name,
                class_name=class_name,
                method_name=method_signature.split("(")[0],
                method_signature=method_signature,
                jar_type=scenario.jar_type,
                left_changes_summary=left_summary,
                right_changes_summary=right_summary,
            )

        criteria = {
            criterion.id: CriterionAssessment(
                criterion_id=criterion.id,
                number=criterion.number,
                title=criterion.title,
                article_definition=criterion.article_definition,
                probability=None,
                threshold=self.config.threshold,
                triggered=False,
            )
            for criterion in CRITERIA
        }

        return LayaAssessment(
            timestamp=datetime.now().isoformat(timespec="seconds"),
            project_name=state.project_name,
            class_name=state.class_name,
            method_name=state.method_name,
            method_signature=state.method_signature,
            jar_type=state.jar_type,
            model=self.config.model,
            threshold=self.config.threshold,
            max_len=self.config.max_len,
            state_format=self.config.state_format,
            state_digest=state.digest(),
            source_paths=state.source_paths(),
            missing_branches=state.missing_branches,
            criteria=criteria,
            witness_two_stage=self.config.witness_two_stage,
            allow_baseline_with_witness=self.config.allow_baseline_with_witness,
            negative_instructions=self.config.negative_instructions,
            diagnostic_questions=self.config.diagnostic_questions,
            criterion_thresholds=self.config.criterion_thresholds,
            decision_rule=self.config.decision_rule,
            error=str(error),
            error_traceback=error_traceback,
        )

    def _write_classification(self, assessment: LayaAssessment) -> None:
        self._classification_count += 1
        class_part = assessment.class_name.split(".")[-1]
        file_name = "_".join(
            [
                f"{self._classification_count:03d}",
                _safe_file_part(assessment.project_name),
                _safe_file_part(class_part),
                _safe_file_part(assessment.method_name),
            ]
        ) + ".json"
        try:
            os.makedirs(self.classification_dir, exist_ok=True)
            with open(
                os.path.join(self.classification_dir, file_name),
                "w",
                encoding="utf-8",
            ) as classification_file:
                json.dump(
                    assessment.classification_dict(self.run_id),
                    classification_file,
                    ensure_ascii=False,
                    indent=2,
                    default=str,
                )
                classification_file.write("\n")
        except OSError as error:
            logging.error(
                "Could not write the Laya classification in %s: %s",
                self.classification_dir,
                error,
            )

    def _write_assessment(self, assessment: LayaAssessment) -> None:
        self._ensure_initialized()
        try:
            with open(self.log_path, "a", encoding="utf-8") as log_file:
                for line in assessment.readable_lines():
                    log_file.write(line + "\n")
            with open(self.jsonl_path, "a", encoding="utf-8") as jsonl_file:
                jsonl_file.write(
                    json.dumps(
                        assessment.to_dict(),
                        ensure_ascii=False,
                        default=str,
                    )
                    + "\n"
                )
        except OSError as error:
            logging.error(
                "Could not write the Laya pre-analysis log in %s: %s",
                self.log_dir,
                error,
            )
