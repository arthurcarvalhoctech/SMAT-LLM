"""Laya pre-analysis flow for the three interference criteria.

This flow runs before SMAT's execution-based detection. It builds a compact
source state for each target method, asks Laya three independent ``noul``
questions plus one ``choice`` and one ``score`` question, and writes a readable
log and a JSONL file for analysis.

Laya is a hypothesis generator here, not an oracle: it does not execute code and
cannot compute state values. The execution-based SMAT pipeline remains the
authoritative detector.
"""

import json
import logging
import os
import re
import traceback
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, Dict, List, Optional, Union

from nimrod.core.merge_scenario_under_analysis import MergeScenarioUnderAnalysis
from nimrod.laya_interference.client import (
    LayaClient,
    LayaUnavailableError,
    RouterLayaClient,
)
from nimrod.laya_interference.config import LayaFlowConfig
from nimrod.laya_interference.criteria import (
    AFFECTED_BRANCH_QUESTION_ID,
    CONFIDENCE_QUESTION_ID,
    CRITERIA,
    PRIMARY_CRITERION_QUESTION_ID,
    build_questions,
    choice_confidence,
    choice_label,
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


CLASSIFICATION_INTERFERENCE = "interference"
CLASSIFICATION_NO_INTERFERENCE = "no_interference"
CLASSIFICATION_ERROR = "error"

CLASSIFICATION_NOTE = (
    "Laya hypothesis (triage). No triggered criterion does not prove the absence "
    "of interference; execution-based detection remains the reference."
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
        if self.triggered_criteria:
            return CLASSIFICATION_INTERFERENCE
        return CLASSIFICATION_NO_INTERFERENCE

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
            "state_digest": self.state_digest,
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
                f"threshold={self.threshold:.2f} -> {triggered}"
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
            raw_result = self.client.predict(
                state.to_payload(), build_questions()
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

        return self._assessment_from_result(state, raw_result)

    def _assessment_from_result(
        self, state: LayaMethodState, raw_result: Dict[str, Any]
    ) -> LayaAssessment:
        criteria: Dict[str, CriterionAssessment] = {}
        for criterion in CRITERIA:
            probability = noul_probability(raw_result, criterion.id)
            criteria[criterion.id] = CriterionAssessment(
                criterion_id=criterion.id,
                number=criterion.number,
                title=criterion.title,
                article_definition=criterion.article_definition,
                probability=probability,
                threshold=self.config.threshold,
                triggered=(
                    probability is not None
                    and probability >= self.config.threshold
                ),
            )

        routing = raw_result.get("routing", {}) if isinstance(raw_result, dict) else {}
        usage = raw_result.get("usage", {}) if isinstance(raw_result, dict) else {}
        answers = raw_result.get("answers", {}) if isinstance(raw_result, dict) else {}

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
            state_digest=state.digest(),
            source_paths=state.source_paths(),
            missing_branches=state.missing_branches,
            criteria=criteria,
            primary_criterion=choice_label(
                raw_result, PRIMARY_CRITERION_QUESTION_ID
            ),
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
            state_digest=state.digest(),
            source_paths=state.source_paths(),
            missing_branches=state.missing_branches,
            criteria=criteria,
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
