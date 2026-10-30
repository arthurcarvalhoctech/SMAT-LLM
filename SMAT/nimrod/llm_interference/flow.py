"""LLM-based interference pre-analysis flow.

For each target method, SMAT builds the base/left/right/merge source state,
asks the configured LLM to assess the three interference criteria from the
article, and writes a readable log, a JSONL file and one classification JSON
per method. The analysis is a triage hypothesis; execution-based SMAT remains
the authoritative detector.
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
from nimrod.llm_interference.client import (
    ApiLlmClient,
    LlmClient,
    LlmUnavailableError,
)
from nimrod.llm_interference.config import LlmFlowConfig
from nimrod.llm_interference.source_context import (
    MethodState,
    build_method_state,
    parse_method_item,
)
from nimrod.laya_interference.criteria import CRITERIA


def _default_log_dir() -> str:
    from nimrod.tests.utils import get_base_output_path

    return os.path.join(
        os.path.dirname(get_base_output_path()),
        "reports",
        "llm_interference",
    )


CLASSIFICATION_POSSIBLE_INTERFERENCE = "possible_interference"
CLASSIFICATION_NO_SIGNAL = "no_signal"
CLASSIFICATION_ERROR = "error"

CLASSIFICATION_NOTE = (
    "LLM triage only. possible_interference is a hypothesis, not a confirmed "
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
    triggered: bool
    evidence: str = ""

    def to_dict(self) -> Dict[str, Any]:
        return {
            "number": self.number,
            "title": self.title,
            "article_definition": self.article_definition,
            "probability": self.probability,
            "triggered": self.triggered,
            "evidence": self.evidence,
        }


@dataclass
class LlmAssessment:
    timestamp: str
    project_name: str
    class_name: str
    method_name: str
    method_signature: str
    jar_type: str
    provider: str
    model: str
    threshold: float
    state_digest: str
    source_paths: Dict[str, str]
    missing_branches: List[str]
    criteria: Dict[str, CriterionAssessment] = field(default_factory=dict)
    primary_criterion: Optional[str] = None
    affected_branch: Optional[str] = None
    confidence: Optional[str] = None
    summary: str = ""
    reasoning: str = ""
    routing: Dict[str, Any] = field(default_factory=dict)
    usage: Dict[str, Any] = field(default_factory=dict)
    raw_response: str = ""
    finish_reason: Optional[str] = None
    attempts: List[Dict[str, Any]] = field(default_factory=list)
    error_metadata: Dict[str, Any] = field(default_factory=dict)
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
            "provider": self.provider,
            "model": self.model,
            "threshold": self.threshold,
            "classification": self.classification,
            "triggered_criteria": self.triggered_criteria,
            "primary_criterion": self.primary_criterion,
            "affected_branch": self.affected_branch,
            "confidence": self.confidence,
            "probabilities": {
                criterion_id: assessment.probability
                for criterion_id, assessment in self.criteria.items()
            },
            "evidence": {
                criterion_id: assessment.evidence
                for criterion_id, assessment in self.criteria.items()
            },
            "summary": self.summary,
            "reasoning": self.reasoning,
            "finish_reason": self.finish_reason,
            "attempts": self.attempts,
            "usage": self.usage,
            "raw_response_preview": (
                self.raw_response[:4000] if self.error else ""
            ),
            "raw_response_length": len(self.raw_response),
            "error": self.error,
            "note": CLASSIFICATION_NOTE,
        }

    def to_dict(self, run_id: Optional[str] = None) -> Dict[str, Any]:
        return {
            "run_id": run_id,
            "timestamp": self.timestamp,
            "project": self.project_name,
            "class": self.class_name,
            "method": self.method_name,
            "method_signature": self.method_signature,
            "jar_type": self.jar_type,
            "provider": self.provider,
            "model": self.model,
            "threshold": self.threshold,
            "state_digest": self.state_digest,
            "source_paths": self.source_paths,
            "missing_branches": self.missing_branches,
            "criteria": {
                criterion_id: assessment.to_dict()
                for criterion_id, assessment in self.criteria.items()
            },
            "triggered_criteria": self.triggered_criteria,
            "primary_criterion": self.primary_criterion,
            "affected_branch": self.affected_branch,
            "confidence": self.confidence,
            "summary": self.summary,
            "reasoning": self.reasoning,
            "routing": self.routing,
            "usage": self.usage,
            "raw_response": self.raw_response,
            "finish_reason": self.finish_reason,
            "attempts": self.attempts,
            "error": self.error,
            "error_metadata": self.error_metadata,
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
            f"  provider={self.provider} model={self.model}",
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
            evidence = (
                assessment.evidence if assessment and assessment.evidence else "-"
            )
            lines.append(f"    evidence: {evidence}")

        lines.append(f"  primary_criterion: {self.primary_criterion or 'n/a'}")
        lines.append(f"  affected_branch: {self.affected_branch or 'n/a'}")
        lines.append(f"  confidence: {self.confidence or 'n/a'}")
        if self.finish_reason:
            lines.append(f"  finish_reason: {self.finish_reason}")
        if self.attempts:
            lines.append(f"  attempts: {len(self.attempts)}")
            for attempt in self.attempts:
                lines.append(
                    "    attempt "
                    f"{attempt.get('attempt', '?')}: "
                    f"model={attempt.get('model', '?')} "
                    f"max_output_tokens={attempt.get('max_output_tokens', '?')} "
                    f"finish_reason={attempt.get('finish_reason', '?')}"
                )
        if self.usage:
            lines.append(
                "  usage: "
                + json.dumps(
                    self.usage,
                    ensure_ascii=False,
                    sort_keys=True,
                    default=str,
                )
            )
        if self.summary:
            lines.append(f"  summary: {self.summary}")
        if self.reasoning:
            lines.append(f"  reasoning: {self.reasoning}")
        if self.error:
            lines.append(f"  error: {self.error}")
            if self.raw_response:
                lines.append("  raw_response_preview:")
                lines.extend(
                    "    " + line
                    for line in self.raw_response[:4000].splitlines()
                )
            if self.error_metadata:
                lines.append(
                    "  error_metadata: "
                    + json.dumps(
                        self.error_metadata,
                        ensure_ascii=False,
                        sort_keys=True,
                        default=str,
                    )[:6000]
                )
        if self.error_traceback:
            lines.append("  traceback:")
            lines.extend(
                "    " + line
                for line in self.error_traceback.rstrip().splitlines()
            )
        return lines


class LlmInterferenceFlow:
    """Run the LLM pre-analysis for every target method in a scenario."""

    def __init__(
        self,
        config: LlmFlowConfig,
        client: Optional[LlmClient] = None,
        log_dir: Optional[str] = None,
    ) -> None:
        self.config = config
        self.client = client if client is not None else ApiLlmClient(config)
        self.log_dir = log_dir or config.log_dir or _default_log_dir()
        run_id = datetime.now().strftime("%Y%m%d_%H%M%S_%f")
        self.log_path = os.path.join(
            self.log_dir, f"llm_interference_{run_id}.log"
        )
        self.jsonl_path = os.path.join(
            self.log_dir, f"llm_interference_{run_id}.jsonl"
        )
        self.run_id = run_id
        self.classification_dir = os.path.join(
            self.log_dir, "classification", f"run_{run_id}"
        )
        self._classification_count = 0
        self._initialized = False
        self._unavailable_reason: Optional[str] = None
        self._logged_errors: set[str] = set()

    def _provider_description(self) -> Dict[str, Any]:
        describe = getattr(self.client, "describe", None)
        if callable(describe):
            try:
                description = describe()
                if isinstance(description, dict):
                    return description
            except Exception:
                pass
        return {}

    def _ensure_initialized(self) -> None:
        if self._initialized:
            return

        try:
            os.makedirs(self.log_dir, exist_ok=True)
            with open(self.log_path, "a", encoding="utf-8") as log_file:
                log_file.write("=" * 80 + "\n")
                log_file.write("LLM interference pre-analysis\n")
                log_file.write(
                    "role=hypothesis-only; execution-based SMAT remains authoritative\n"
                )
                log_file.write(f"threshold={self.config.threshold:.2f}\n")
                log_file.write(
                    f"max_output_tokens={self.config.max_output_tokens}\n"
                )
                log_file.write(
                    f"json_mode={self.config.json_mode} "
                    f"retry_on_length={self.config.retry_on_length}\n"
                )
                log_file.write(
                    "provider_config="
                    + json.dumps(
                        self._provider_description(),
                        ensure_ascii=False,
                        sort_keys=True,
                        default=str,
                    )
                    + "\n"
                )
                log_file.write("=" * 80 + "\n")
            self._initialized = True
        except OSError as error:
            logging.error(
                "Could not create the LLM log files in %s: %s",
                self.log_dir,
                error,
            )
            self._initialized = True

    def run_for_scenario(
        self, scenario: MergeScenarioUnderAnalysis
    ) -> List[LlmAssessment]:
        logging.info(
            "Starting LLM interference pre-analysis for project %s",
            scenario.project_name,
        )
        assessments: List[LlmAssessment] = []

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
            "Finished LLM interference pre-analysis for project %s (%d method(s))",
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
    ) -> LlmAssessment:
        try:
            state = build_method_state(scenario, class_name, method_item)
        except Exception as error:
            logging.error(
                "LLM pre-analysis could not build the source state for %s: %s",
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
                LlmUnavailableError(self._unavailable_reason),
                state=state,
            )

        try:
            result = self.client.analyze(state)
        except LlmUnavailableError as error:
            self._unavailable_reason = str(error)
            logging.error("LLM interference pre-analysis is unavailable: %s", error)
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
                "LLM pre-analysis failed for %s.%s: %s",
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

        return self._assessment_from_result(state, result)

    def _assessment_from_result(
        self, state: MethodState, result: Dict[str, Any]
    ) -> LlmAssessment:
        analysis = result.get("analysis", {})
        analysis_criteria = (
            analysis.get("criteria", {})
            if isinstance(analysis, dict)
            else {}
        )

        criteria: Dict[str, CriterionAssessment] = {}
        for criterion in CRITERIA:
            item = analysis_criteria.get(criterion.id, {})
            if not isinstance(item, dict):
                item = {}
            probability = item.get("probability")
            if probability is not None:
                try:
                    probability = float(probability)
                except (TypeError, ValueError):
                    probability = None
            criteria[criterion.id] = CriterionAssessment(
                criterion_id=criterion.id,
                number=criterion.number,
                title=criterion.title,
                article_definition=criterion.article_definition,
                probability=probability,
                triggered=bool(item.get("triggered", False)),
                evidence=str(item.get("evidence", "") or ""),
            )

        return LlmAssessment(
            timestamp=datetime.now().isoformat(timespec="seconds"),
            project_name=state.project_name,
            class_name=state.class_name,
            method_name=state.method_name,
            method_signature=state.method_signature,
            jar_type=state.jar_type,
            provider=str(result.get("provider") or ""),
            model=str(result.get("model") or ""),
            threshold=self.config.threshold,
            state_digest=state.digest(),
            source_paths=state.source_paths(),
            missing_branches=state.missing_branches,
            criteria=criteria,
            primary_criterion=analysis.get("primary_criterion"),
            affected_branch=analysis.get("affected_branch"),
            confidence=analysis.get("confidence"),
            summary=str(analysis.get("summary", "") or ""),
            reasoning=str(analysis.get("reasoning", "") or ""),
            routing=result.get("routing", {})
            if isinstance(result.get("routing"), dict)
            else {},
            usage=result.get("usage", {})
            if isinstance(result.get("usage"), dict)
            else {},
            raw_response=str(result.get("raw_response", "") or ""),
            finish_reason=result.get("finish_reason"),
            attempts=result.get("attempts", [])
            if isinstance(result.get("attempts"), list)
            else [],
        )

    def _error_assessment(
        self,
        scenario: MergeScenarioUnderAnalysis,
        class_name: str,
        method_item: Union[str, Dict[str, str]],
        error: Exception,
        state: Optional[MethodState] = None,
        error_traceback: Optional[str] = None,
    ) -> LlmAssessment:
        if state is None:
            method_signature, left_summary, right_summary = parse_method_item(
                method_item
            )
            state = MethodState(
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
                triggered=False,
            )
            for criterion in CRITERIA
        }

        description = self._provider_description()
        metadata = getattr(error, "llm_metadata", {})
        if not isinstance(metadata, dict):
            metadata = {}

        return LlmAssessment(
            timestamp=datetime.now().isoformat(timespec="seconds"),
            project_name=state.project_name,
            class_name=state.class_name,
            method_name=state.method_name,
            method_signature=state.method_signature,
            jar_type=state.jar_type,
            provider=str(
                metadata.get("provider")
                or description.get("provider")
                or ""
            ),
            model=str(
                metadata.get("model") or description.get("model") or ""
            ),
            threshold=self.config.threshold,
            state_digest=state.digest(),
            source_paths=state.source_paths(),
            missing_branches=state.missing_branches,
            criteria=criteria,
            finish_reason=metadata.get("finish_reason"),
            attempts=metadata.get("attempts", [])
            if isinstance(metadata.get("attempts"), list)
            else [],
            usage=metadata.get("usage", {})
            if isinstance(metadata.get("usage"), dict)
            else {},
            raw_response=str(metadata.get("raw_response", "") or ""),
            error_metadata=metadata,
            error=str(error),
            error_traceback=error_traceback,
            routing=description,
        )

    def _write_classification(self, assessment: LlmAssessment) -> None:
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
                "Could not write the LLM classification in %s: %s",
                self.classification_dir,
                error,
            )

    def _write_assessment(self, assessment: LlmAssessment) -> None:
        self._ensure_initialized()
        try:
            with open(self.log_path, "a", encoding="utf-8") as log_file:
                for line in assessment.readable_lines():
                    log_file.write(line + "\n")
            with open(self.jsonl_path, "a", encoding="utf-8") as jsonl_file:
                jsonl_file.write(
                    json.dumps(
                        assessment.to_dict(self.run_id),
                        ensure_ascii=False,
                        default=str,
                    )
                    + "\n"
                )
        except OSError as error:
            logging.error(
                "Could not write the LLM pre-analysis log in %s: %s",
                self.log_dir,
                error,
            )
