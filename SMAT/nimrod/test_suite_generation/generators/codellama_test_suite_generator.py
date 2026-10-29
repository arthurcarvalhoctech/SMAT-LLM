import json
import logging
import os
from typing import List, Dict, Union, Any
import re

from tree_sitter import QueryCursor

from nimrod.core.merge_scenario_under_analysis import MergeScenarioUnderAnalysis
from nimrod.source_code import (
    extract_java_class_info,
    extract_java_snippet,
    find_source_code_paths as find_java_source_code_paths,
    parse_java_code,
)
from nimrod.test_suite_generation.generators.context_filter import (
    context_filter_enabled,
    filter_context,
)
from nimrod.test_suite_generation.generators.test_suite_generator import TestSuiteGenerator
from nimrod.test_suite_generation.generators.prompt_manager import PromptManager
from nimrod.test_suite_generation.generators.llm_api import create_llm_api
from nimrod.test_suite_generation.generators.llm_config import (
    llm_env_configured,
    resolve_llm_config,
)
from nimrod.tests.utils import get_base_output_path, get_config
from nimrod.utils import load_json, save_json


class CodellamaTestSuiteGenerator(TestSuiteGenerator):

    def __init__(self, java_tool, model_key: str = "codellama", model_config: Dict[str, Any] = None):
        super().__init__(java_tool)
        self.model_key = model_key
        self.model_config = model_config or {}
        self.api = None
        self.prompt_manager = PromptManager()

        # Environment variables take precedence over env-config.json. When the
        # LLM_* variables are present, ignore the api_params model entry.
        global_config = get_config()
        if not llm_env_configured():
            global_model_config = (global_config.get("api_params", {}) or {}).get(model_key, {})
            self.model_config = {**global_model_config, **self.model_config}

        self.llm_config = resolve_llm_config(model_key, self.model_config)
        self.num_outputs = self.llm_config.num_outputs
        self.prompt_keys = self.llm_config.prompt_keys
        self.output_label = self.llm_config.output_label

        # Prompt configurations (priority: environment > model_config > global_config > default)
        self.prompt_template = (
            os.environ.get("LLM_PROMPT_TEMPLATE")
            or self.model_config.get("prompt_template") or 
            global_config.get("prompt_template") or 
            "zero_shot"
        )
        
        logging.info(
            "Inicializado %s (provider=%s, model=%s, template=%s)",
            self.output_label,
            self.llm_config.provider,
            self.llm_config.model,
            self.prompt_template,
        )
    
    def generate_messages_list(self, method_info: Dict[str, str], full_class_name: str,
                               branch: str, output_path: str) -> Dict[str, List[Dict[str, str]]]:
        """
        Generates messages for API requests using the configurable prompt system.
        Supports different templates (zero-shot, one-shot) and context combinations.
        """
        self.api.set_branch(branch)  # Set the branch
        class_name = full_class_name.split('.')[-1]
        method_name = method_info.get("method_name", "")
        
        logging.debug(f"Generating messages for {class_name}.{method_name} using template: {self.prompt_template}")

        # Generates messages using the PromptManager
        messages_dict = self.prompt_manager.generate_all_combinations(
            method_info=method_info,
            class_name=class_name,
            branch=branch,
            template_name=self.prompt_template,
            prompt_keys=self.prompt_keys,
        )
        
        # Saves generated messages
        self.prompt_manager.save_generated_messages(
            messages_dict=messages_dict,
            output_path=output_path,
            class_name=class_name,
            method_name=method_name
        )
        
        logging.info(f"Generated {len(messages_dict)} prompt variations for {class_name}.{method_name}")

        return messages_dict
    
    def _ensure_api_initialized(self) -> None:
        """Initializes the provider client if it has not been initialized yet."""
        if self.api is not None:
            return

        self.api = create_llm_api(self.llm_config)

    def get_generator_tool_name(self) -> str:
        self._ensure_api_initialized()
        config_suffix = self._generate_config_suffix()
        return f"{self.output_label.upper()}{config_suffix}"
    
    def _generate_config_suffix(self) -> str:
        """Generates a suffix with configuration information for folder identification"""
        if not self.api:
            return ""

        # Prompt format: ZS (zero-shot) or 1S (one-shot)
        prompt_code = "ZS" if self.prompt_template == "zero_shot" else "1S"

        # Temperature: T00, T05, T07, etc. (always with 2 digits)
        temp_value = int(round(self.api.temperature * 100))  # 0.7 -> 70, 0.05 -> 5, 0 -> 0
        temp_code = f"T{temp_value:02d}"  # Formats with 2 digits: T00, T05, T07

        # Seed: S42, S123, etc.
        seed_code = f"S{self.api.seed}"
        
        return f"_{prompt_code}_{temp_code}_{seed_code}"

    def _get_test_suite_class_paths(self, path: str) -> List[str]:
        paths: List[str] = []
        for root, _, files in os.walk(path):
            paths.extend(os.path.join(root, file) for file in files if file.endswith(".java"))
        return paths

    def _get_test_suite_class_names(self, test_suite_path: str) -> List[str]:
        return [os.path.basename(path).replace(".java", "") for path in self._get_test_suite_class_paths(test_suite_path)]

    def save_output(self, test_template: str, output: str, dir: str, output_file_name: str) -> None:
        """Saves the output generated by the model to a file, replacing #TEST_METHODS# in the template."""
        # Remove content between <think> tags
        output = re.sub(r'<think>.*?</think>', '', output, flags=re.DOTALL)

        # Extract only the content inside ``` blocks (excluding the ``` markers)
        matches = re.findall(r'```(?:\w+)?\n?(.*?)```', output, flags=re.DOTALL)
        output = '\n'.join(matches).strip()

        # Remove lines starting with "number. <text>" (e.g., "1. public void test() {...}")
        output = re.sub(r"^\d+\.\s.*$", "", output, flags=re.MULTILINE)

        # Look for @Before, @BeforeClass first; fallback to @Test if none are found
        markers = ["@Before", "@BeforeClass", "@Test"]
        index = min((output.find(marker) for marker in markers if marker in output), default=-1)

        # Keep only the content starting from the first found annotation
        output = output[index:] if index != -1 else output

        llm_outputs_dir = os.path.join(dir, "llm_outputs")
        output_file_path = os.path.join(llm_outputs_dir, f"{output_file_name}.txt")
        filled_template = test_template.replace("#TEST_METHODS#", output)

        os.makedirs(llm_outputs_dir, exist_ok=True)
        with open(output_file_path, "w") as file:
            file.write(filled_template)

    def parse_code(self, source_code_path: str) -> tuple:
        """Parses the Java source code using the Tree-sitter parser and return the language, source code, and generated AST"""
        return parse_java_code(source_code_path)

    def extract_snippet(self, source_code: str, start_byte: int, end_byte: int) -> str:
        """Extracts a snippet of code from the source code using the start and end byte offsets"""
        return extract_java_snippet(source_code, start_byte, end_byte)

    def extract_class_info(self, source_code_path: str, full_method_name: str, full_class_name: str) -> tuple:
        """
        Extracts the class fields, constructor, and body of the method under test from the source code
        using the generated AST to query the information
        """
        return extract_java_class_info(
            source_code_path, full_method_name, full_class_name
        )

    def save_scenario_infos(self, scenario_infos_path: str, class_name: str, methods: Union[List[str], List[Dict[str, str]]], source_code_path: str, base_source_code_path: str = "") -> None:
        """Stores relevant scenario information (for each class and method) in a JSON file

        When ``SMAT_CONTEXT_FILTER`` is enabled and the base source is known, the
        class fields are filtered by the change (see ``context_filter``).
        """
        apply_filter = bool(base_source_code_path) and context_filter_enabled()
        base_text = ""
        branch_text = ""
        if apply_filter:
            with open(base_source_code_path, "r", encoding="utf-8", errors="replace") as file:
                base_text = file.read()
            with open(source_code_path, "r", encoding="utf-8", errors="replace") as file:
                branch_text = file.read()
        if os.path.exists(scenario_infos_path):
            scenario_infos_dict = load_json(scenario_infos_path)
        else:
            scenario_infos_dict = {}

        # Always reset the class entry to avoid accumulating entries from multiple branches
        scenario_infos_dict[class_name] = []

        """
        method_item ->
        {
          "method": "methodname()",
          "leftChangesSummary": "Left does...",
          "rightChangesSummary": "Right does..."
        }

        method_item -> "methodname()"
        """
        for method_item in methods:
            if not isinstance(method_item, dict):
                method = method_item
                left_changes_summary = ""
                right_changes_summary = ""
            else:
                method = method_item.get("method", "")
                left_changes_summary = method_item.get("leftChangesSummary", "")
                right_changes_summary = method_item.get("rightChangesSummary", "")

            method = re.sub(r'\|', ',', method)
            class_fields, constructor_codes, method_code = self.extract_class_info(source_code_path, method, class_name)
            if apply_filter and class_fields:
                class_fields = filter_context(class_fields, method_code or "", base_text, branch_text)

            scenario_infos_dict[class_name].append({
                'class_fields': class_fields if class_fields else [],
                'constructor_codes': constructor_codes if constructor_codes else [],
                'method_name': method,
                'method_code': method_code if method_code else "",
                'left_changes_summary': left_changes_summary,
                'right_changes_summary': right_changes_summary,
                'test_template': (
                    "import org.junit.Test;\n"
                    "import org.junit.Before;\n"
                    "import org.junit.BeforeClass;\n"
                    "import static org.junit.Assert.*;\n\n"
                    f"public class {class_name.split('.')[-1]}_{method.split('(')[0]}Test {{\n"
                    "#TEST_METHODS#\n"
                    "}"
                )
            })

        save_json(scenario_infos_path, scenario_infos_dict)

    def save_imports(self, class_name: str, source_code_path: str, imports_path: str) -> None:
        """Extracts import statements from the Java source code and stores them in a JSON file"""
        JAVA_LANGUAGE, source_code, tree = self.parse_code(source_code_path)

        query_text = """
        (import_declaration) @import
        (package_declaration) @package
        """
        query = JAVA_LANGUAGE.query(query_text)
        cursor = QueryCursor(query)
        captures_dict = cursor.captures(tree.root_node)
        
        captures = []
        for capture_name, nodes in captures_dict.items():
            for node in nodes:
                captures.append((node, capture_name))

        if os.path.exists(imports_path):
            imports_dict = load_json(imports_path)
        else:
            imports_dict = {}

        class_imports = imports_dict.setdefault(class_name, [])

        for node, capture_name in captures:
            start_byte, end_byte = node.start_byte, node.end_byte
            captured_text = source_code[start_byte:end_byte].strip()

            if capture_name == "import":
                class_imports.append(f'{captured_text}\n')
            elif capture_name == "package":
                package_name = captured_text.split()[1].rstrip(';')
                class_imports.append(f'import {package_name}.*;\n')

        save_json(imports_path, imports_dict)

    def extract_individual_tests(self, output_path: str, test_template: str, class_name: str, imports: List[str], i: int, j: int, prompt_key: str, branch: str) -> None:
        """Extracts individual tests from the generated test suite and saves them to separate files"""
        llm_outputs_path = os.path.join(output_path, "llm_outputs")
        counter = 0

        def classify_annotations(captures: List[tuple], source_code: str) -> tuple:
            """Classifies annotations in the captured snippets as 'before' or 'test' blocks"""
            before_block: List[Dict[str, str]] = []
            test_block: List[Dict[str, str]] = []

            for node, _ in captures:
                captured_text = self.extract_snippet(source_code, node.start_byte, node.end_byte)
                if "@Test" in captured_text:
                    test_block.append({"snippet": captured_text})
                elif any(annotation in captured_text for annotation in ["@Before", "@BeforeClass"]):
                    before_block.append({"snippet": captured_text})

            return before_block, test_block

        # Format: {i}{j}_{branch}_{class_name.split('.')[-1]}_{prompt_key}.txt
        pattern = rf"^{i}{j}_(left|right)_{re.escape(class_name.split('.')[-1])}_{prompt_key}\.txt$"
        
        files_found = [f for f in os.listdir(llm_outputs_path) if re.match(pattern, f)]

        for file in files_found:
            source_code_path = os.path.join(llm_outputs_path, file)
            JAVA_LANGUAGE, source_code, tree = self.parse_code(source_code_path)

            # Tree-sitter query to find method definitions with annotations
            query_text = """
            (method_declaration
                (modifiers [
                    (annotation)
                    (marker_annotation)
                    ]
                    )) @method_def
            """
            query = JAVA_LANGUAGE.query(query_text)
            cursor = QueryCursor(query)
            captures_dict = cursor.captures(tree.root_node)
            
            captures = []
            for capture_name, nodes in captures_dict.items():
                for node in nodes:
                    captures.append((node, capture_name))

            before_block, test_block = classify_annotations(captures, source_code)
            
            for test in test_block:
                method_name = f"{class_name.split('.')[-1]}Test_{branch}_{prompt_key}_{j}_{i}_{counter}"
                output_file_path = os.path.join(output_path, f"{method_name}.java")

                new_template = test_template.split("public class")[0] + f"public class {method_name} {{\n"
                full_template = "".join(imports) + new_template

                if before_block:
                    full_template += "".join(before['snippet'] for before in before_block)

                snippet = test['snippet']
                public_index = snippet.find('public')
                if public_index == -1:
                    public_index = snippet.find('void')
                    if public_index != -1:
                        snippet = snippet[:public_index] + 'public ' + snippet[public_index:]
                        public_index = snippet.find('public')
                
                if public_index != -1:
                    test_method_name = snippet[public_index:].split('(')[0].split()[-1]
                    new_snippet = snippet.replace(test_method_name, f"test{i}{counter}")

                    with open(output_file_path, "w") as f:
                        f.write(full_template + new_snippet + "\n}")
                    
                    counter += 1
                

    def find_source_code_paths(self, input_jar: str, jar_type: str, class_name: str, project_name: str) -> Dict[str, str]:
        """Finds the source code files for the target class.

        Supported layouts:
          - <scenario>/transformed/<branch>/*.jar + <scenario>/source/<Class>_<branch>.java
          - <scenario>/transformed/<branch>/*.jar + <scenario>/source/<Class>/<branch>.java
          - <scenario>/transformed/<branch>/*.jar + <scenario>/source/<branch>.java
          - Legacy <repo>/jar_files/{left,right}.java (toy scenarios)
        """
        return find_java_source_code_paths(input_jar, jar_type, class_name)

    def fetch_source_code_branch(self, input_jar: str, jar_type: str, class_name: str, project_name: str) -> tuple:
        """Retrieves the source code path and branch for the given JAR path."""
        source_code_paths = self.find_source_code_paths(
            input_jar, jar_type, class_name.split('.')[-1], project_name
        )

        branches = ["base", "left", "right", "merge"]
        first_jar = input_jar.split(":")[0]
        parent_dir = os.path.basename(os.path.dirname(first_jar))
        jar_stem = os.path.splitext(os.path.basename(first_jar))[0]

        branch = parent_dir if parent_dir in branches else None
        if branch is None:
            branch = next(
                (b for b in branches if jar_stem == b or jar_stem.endswith(f"_{b}")),
                None,
            )
        if branch is None:
            branch = next((b for b in branches if b in input_jar), None)

        if branch is None:
            raise ValueError(
                f"Could not determine the branch from JAR path '{input_jar}'. "
                f"Expected a path containing one of {branches}."
            )

        source_code_path = source_code_paths.get(branch, "")
        if not source_code_path:
            raise FileNotFoundError(
                f"Source code for branch '{branch}' of class '{class_name}' was not found."
            )

        return source_code_path, branch, source_code_paths

    def record_output_duration(self, time_duration_path: str, output_path: str, class_name: str,
                               output_file_name: str, total_duration: int, project_name: str) -> None:
        """Records the duration of output generation for the given class and output file"""
        os.makedirs(os.path.dirname(time_duration_path), exist_ok=True)

        if not os.path.exists(time_duration_path):
            with open(time_duration_path, "w") as file:
                json.dump({}, file)

        time_duration_dict = load_json(time_duration_path)

        project_data = time_duration_dict.setdefault(project_name, {})
        class_data = project_data.setdefault(class_name, {"total_duration": 0, "outputs": {}})

        key_name = output_path.split(os.sep)[-1] + '_' + output_file_name

        total_duration_seconds = total_duration / 1_000_000_000

        duration_rounded = round(total_duration_seconds, 2)
        class_data["outputs"][key_name] = duration_rounded
        class_data["total_duration"] = round(class_data["total_duration"] + duration_rounded, 2)

        save_json(time_duration_path, time_duration_dict)

    def _execute_tool_for_tests_generation(self, input_jar: str, output_path: str, scenario: MergeScenarioUnderAnalysis, use_determinism: bool) -> None:
        self._ensure_api_initialized()

        # Define paths for storing scenario information (for prompt generation),
        # importing data (to be extracted from source code), and recording time duration (for each output)
        scenario_infos_path = os.path.join(output_path, "scenario_infos.json")
        imports_path = os.path.join(output_path, "imports.json")
        # Save time duration data in the 'reports' folder, located next to the 'projects' folder
        # Generates config suffix for the duration file
        config_suffix = self._generate_config_suffix().replace("_", "") if hasattr(self, '_generate_config_suffix') else ""
        duration_filename = f"{self.output_label}{config_suffix}_time_duration.json"
        
        time_duration_path = os.path.join(
            os.path.dirname(get_base_output_path()), "reports", duration_filename
        )

        project_name = scenario.project_name
        targets = scenario.targets
        jar_type = scenario.jar_type

        # Fetch the source code paths for each class and save the associated scenario information and import data
        for class_name, methods in targets.items():
            source_code_path, branch, source_paths = self.fetch_source_code_branch(input_jar, jar_type, class_name, project_name)
            self.save_scenario_infos(
                scenario_infos_path,
                class_name,
                methods,
                source_code_path,
                base_source_code_path=source_paths.get("base", ""),
            )
            self.save_imports(class_name, source_code_path, imports_path)

        # Load scenario information and import data into dictionaries
        scenario_infos_dict = load_json(scenario_infos_path)
        imports_dict = load_json(imports_path)

        # Generate tests for each method in every class and save the results
        for class_name, scenario_infos_list in scenario_infos_dict.items():
            logging.debug("Generating tests for target methods in class '%s'", class_name)
            for i, method_info in enumerate(scenario_infos_list):
                messages_list = self.generate_messages_list(method_info, class_name, branch, output_path)
                test_template = method_info.get("test_template", "")
                self._process_prompts(messages_list=messages_list, test_template=test_template, output_path=output_path,
                                      branch=branch, class_name=class_name, imports=imports_dict.get(class_name, []),
                                      i=i, time_duration_path=time_duration_path, project_name=project_name,
                                      num_outputs=self.num_outputs)

    def _process_prompts(self, messages_list: Dict[str, List[Dict[str, str]]], test_template: str, output_path: str, branch: str,
                         class_name: str, imports: List[str], i: int, time_duration_path: str, project_name: str,
                         num_outputs: int = 1) -> None:
        for j in range(num_outputs):
            for prompt_key, messages in messages_list.items():
                output_file_name = f"{i}{j}_{branch}_{class_name.split('.')[-1]}_{prompt_key}"
                self._process_single_prompt(messages, test_template, output_path, branch, class_name, imports, i, j, time_duration_path, project_name, output_file_name, prompt_key)

    def _process_single_prompt(self, messages: List[Dict[str, str]], test_template: str, output_path: str, branch: str,
                               class_name: str, imports: List[str], i: int, j: int, time_duration_path: str,
                               project_name: str, output_file_name: str, prompt_key: str) -> None:
        output = self.api.generate_output(messages)
        response = output.get("response", "Response not found.")
        total_duration = int(output.get("total_duration", self.api.timeout_seconds * 1_000_000_000))
        self.save_output(test_template, response, output_path, output_file_name)
        self.record_output_duration(time_duration_path, output_path, class_name, output_file_name, total_duration, project_name)
        self.extract_individual_tests(output_path, test_template, class_name, imports, i, j, prompt_key, branch)
