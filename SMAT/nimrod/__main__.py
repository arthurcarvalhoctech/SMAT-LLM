import logging
import os
from typing import Dict, List
from nimrod.dynamic_analysis.behavior_change_checker import BehaviorChangeChecker
from nimrod.dynamic_analysis.criteria.first_semantic_conflict_criteria import FirstSemanticConflictCriteria
from nimrod.dynamic_analysis.criteria.second_semantic_conflict_criteria import SecondSemanticConflictCriteria
from nimrod.core.feature_flags import (
  DYNAMIC_INTERFERENCE_DETECTION_DISABLED_MESSAGE,
  LAYA_INTERFERENCE_DETECTION_DISABLED_MESSAGE,
  LLM_INTERFERENCE_DETECTION_DISABLED_MESSAGE,
  NO_INTERFERENCE_FLOW_ENABLED_MESSAGE,
  is_dynamic_interference_detection_enabled,
  is_laya_interference_detection_enabled,
  is_llm_interference_detection_enabled,
)
from nimrod.dynamic_analysis.main import DynamicAnalysis
from nimrod.core.merge_scenario_under_analysis import MergeScenarioUnderAnalysis
from nimrod.laya_interference import LayaFlowConfig, LayaInterferenceFlow
from nimrod.llm_interference import LlmFlowConfig, LlmInterferenceFlow
from nimrod.output_generation.behavior_change_output_generator import BehaviorChangeOutputGenerator
from nimrod.output_generation.output_generator import OutputGenerator
from nimrod.output_generation.semantic_conflicts_output_generator import SemanticConflictsOutputGenerator
from nimrod.output_generation.test_suites_output_generator import TestSuitesOutputGenerator
from nimrod.pipeline import run_scenarios
from nimrod.scenario_snapshot import persist_merge_scenarios
from nimrod.smat import SMAT
from nimrod.test_suite_generation.main import TestSuiteGeneration
from nimrod.tests.utils import setup_logging, get_config, get_base_output_path
from nimrod.test_suite_generation.generators.test_suite_generator import TestSuiteGenerator
from nimrod.test_suite_generation.generators.randoop_test_suite_generator import RandoopTestSuiteGenerator
from nimrod.test_suite_generation.generators.evosuite_differential_test_suite_generator import EvosuiteDifferentialTestSuiteGenerator
from nimrod.test_suite_generation.generators.evosuite_test_suite_generator import EvosuiteTestSuiteGenerator
from nimrod.test_suite_generation.generators.codellama_test_suite_generator import CodellamaTestSuiteGenerator
from nimrod.test_suite_generation.generators.llm_config import (
  infer_provider_from_env,
  llm_env_configured,
)
from nimrod.test_suite_generation.generators.project_test_suite_generator import ProjectTestSuiteGenerator
from nimrod.test_suites_execution.main import TestSuitesExecution, TestSuiteExecutor
from nimrod.tools.bin import MOD_RANDOOP, RANDOOP
from nimrod.tools.java import Java
from nimrod.tools.jacoco import Jacoco
from nimrod.input_parsing.input_parser import CsvInputParser, JsonInputParser


def get_llm_test_suite_generators(config: Dict[str, str]) -> List[TestSuiteGenerator]:
  """
  Creates test suite generators for the configured LLM.

  When LLM_* environment variables are present, a single generator is created
  from the environment and the api_params entries are ignored. Otherwise, one
  generator is created for each entry in api_params.
  """
  if llm_env_configured():
    model_key = (
        os.environ.get("LLM_MODEL_KEY")
        or os.environ.get("LLM_PROVIDER")
        or infer_provider_from_env()
        or "llm"
    )
    return [CodellamaTestSuiteGenerator(Java(), model_key, {})]

  generators: List[TestSuiteGenerator] = list()
  api_params = config.get('api_params', {})
  
  for model_key, model_config in api_params.items():
    # Create a generator for each configured model
    generator = CodellamaTestSuiteGenerator(Java(), model_key, model_config)
    generators.append(generator)
    
  return generators


def get_test_suite_generators(config: Dict[str, str]) -> List[TestSuiteGenerator]:
  config_generators = config.get(
      'test_suite_generators', ['randoop', 'randoop-modified', 'evosuite', 'evosuite-differential', 'codellama', 'gemini', 'llm', 'project'])
  generators: List[TestSuiteGenerator] = list()
  llm_generator_names = {
      'codellama', 'gemini', 'llm', 'ollama', 'deepseek', 'openai',
      'openai-compatible', 'anthropic',
  }

  if 'randoop' in config_generators:
    generators.append(RandoopTestSuiteGenerator(Java(), RANDOOP, "RANDOOP"))
  if 'randoop-modified' in config_generators:
    generators.append(RandoopTestSuiteGenerator(
        Java(), MOD_RANDOOP, "RANDOOP_MODIFIED"))
  if 'evosuite' in config_generators:
    generators.append(EvosuiteTestSuiteGenerator(Java()))
  if 'evosuite-differential' in config_generators:
    generators.append(EvosuiteDifferentialTestSuiteGenerator(Java()))
  if llm_env_configured() or any(name in config_generators for name in llm_generator_names):
    # Create one generator for the configured LLM (environment or api_params).
    generators.extend(get_llm_test_suite_generators(config))
  if 'project' in config_generators:
    generators.append(ProjectTestSuiteGenerator(Java()))

  return generators


def get_output_generators(config: Dict[str, str]) -> List[OutputGenerator]:
  config_generators = config.get(
      'output_generators', ['behavior_changes', 'semantic_conflicts', 'test_suites'])
  generators: List[OutputGenerator] = list()

  if 'behavior_changes' in config_generators:
    generators.append(BehaviorChangeOutputGenerator())
  if 'semantic_conflicts' in config_generators:
    generators.append(SemanticConflictsOutputGenerator(
        TestSuitesExecution(TestSuiteExecutor(Java(), Jacoco(Java())))))
  if 'test_suites' in config_generators:
    generators.append(TestSuitesOutputGenerator())

  return generators


def resolve_input_path(config: Dict[str, str]) -> str:
    env_path = os.environ.get("SMAT_INPUT_PATH")
    configured_path = config.get('input_path', "")
    if not env_path:
        return configured_path
    if os.path.isfile(env_path):
        return env_path
    if configured_path:
        # The repository is mounted at /app in Docker, so a host path such as
        # /home/user/SMAT-LLM/input-x.json is available as /app/input-x.json.
        container_candidate = os.path.join(
            os.path.dirname(configured_path), os.path.basename(env_path)
        )
        if os.path.isfile(container_candidate):
            return container_candidate
        logging.warning(
            "SMAT_INPUT_PATH=%s does not exist; falling back to input_path=%s.",
            env_path,
            configured_path,
        )
        return configured_path
    return env_path


def parse_scenarios_from_input(config: Dict[str, str]) -> List[MergeScenarioUnderAnalysis]:
    json_input = resolve_input_path(config)
    csv_input_path = config.get('path_hash_csv', "")

    if json_input != "":
        return JsonInputParser().parse_input(json_input)
    elif csv_input_path != "":
        logging.warning(
            'DEPRECATED: Providing input data with `path_hash_csv` is deprecated and will be removed in future versions of SMAT. Use `input_path` instead.')
        return CsvInputParser().parse_input(csv_input_path)
    else:
        logging.fatal('No input file provided')
        exit(1)


def _build_dynamic_flow(config: Dict[str, str]) -> SMAT:
  test_suite_generators = get_test_suite_generators(config)
  test_suite_generation = TestSuiteGeneration(test_suite_generators)
  test_suites_execution = TestSuitesExecution(
      TestSuiteExecutor(Java(), Jacoco(Java())))
  dynamic_analysis = DynamicAnalysis([
      FirstSemanticConflictCriteria(),
      SecondSemanticConflictCriteria()
  ], BehaviorChangeChecker())
  output_generators = get_output_generators(config)

  return SMAT(
      test_suite_generation,
      test_suites_execution,
      dynamic_analysis,
      output_generators,
  )


def _build_laya_flow() -> LayaInterferenceFlow:
  default_log_dir = os.path.join(
      os.path.dirname(get_base_output_path()), "reports", "laya"
  )
  config = LayaFlowConfig.from_env(default_log_dir=default_log_dir)
  return LayaInterferenceFlow(config)


def _build_llm_flow() -> LlmInterferenceFlow:
  default_log_dir = os.path.join(
      os.path.dirname(get_base_output_path()), "reports", "llm_interference"
  )
  config = LlmFlowConfig.from_env(default_log_dir=default_log_dir)
  return LlmInterferenceFlow(config)


def main():
  setup_logging()

  dynamic_enabled = is_dynamic_interference_detection_enabled()
  laya_enabled = is_laya_interference_detection_enabled()
  llm_enabled = is_llm_interference_detection_enabled()

  if not dynamic_enabled:
    logging.warning(DYNAMIC_INTERFERENCE_DETECTION_DISABLED_MESSAGE)
  if not laya_enabled:
    logging.info(LAYA_INTERFERENCE_DETECTION_DISABLED_MESSAGE)
  if not llm_enabled:
    logging.info(LLM_INTERFERENCE_DETECTION_DISABLED_MESSAGE)

  if not dynamic_enabled and not laya_enabled and not llm_enabled:
    logging.warning(NO_INTERFERENCE_FLOW_ENABLED_MESSAGE)
    return

  logging.info(
      "Active interference detection flows: dynamic=%s laya=%s llm=%s",
      dynamic_enabled,
      laya_enabled,
      llm_enabled,
  )

  config = get_config()
  input_path = resolve_input_path(config) or config.get("path_hash_csv", "")
  scenarios = parse_scenarios_from_input(config)

  try:
    persist_merge_scenarios(scenarios, input_path=input_path)
  except Exception as error:
    logging.error("Could not persist merge scenarios: %s", error)

  dynamic_flow = _build_dynamic_flow(config) if dynamic_enabled else None
  laya_flow = _build_laya_flow() if laya_enabled else None
  llm_flow = _build_llm_flow() if llm_enabled else None

  if laya_flow is not None:
    logging.info("Laya pre-analysis logs: %s", laya_flow.log_dir)
  if llm_flow is not None:
    logging.info("LLM pre-analysis logs: %s", llm_flow.log_dir)

  run_scenarios(
      scenarios,
      laya_flow=laya_flow,
      llm_flow=llm_flow,
      dynamic_flow=dynamic_flow,
  )


if __name__ == '__main__':
  main()
