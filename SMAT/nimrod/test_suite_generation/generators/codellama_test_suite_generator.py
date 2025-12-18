import json
import logging
import os
from typing import List, Dict, Union, Any, Optional
import re
from time import time

import tree_sitter_java as tsjava
from tree_sitter import Language, Parser, QueryCursor

from nimrod.core.merge_scenario_under_analysis import MergeScenarioUnderAnalysis
from nimrod.test_suite_generation.generators.test_suite_generator import TestSuiteGenerator
from nimrod.test_suite_generation.generators.prompt_manager import PromptManager
from nimrod.tests.utils import get_config
from nimrod.utils import load_json, save_json

from google import genai
from google.genai import types as genai_types


class GeminiApi:
    
    def __init__(self, api_key: str, timeout_seconds: int, temperature: float, model: str) -> None:
        self.api_key = api_key
        self.timeout_seconds = timeout_seconds
        self.temperature = temperature
        self.model = model
        self.client = genai.Client(api_key=api_key)
        self.branch: Optional[str] = None
        
        logging.debug(f"Gemini API initialized with model: {model}, temperature: {temperature}")
    
    def set_branch(self, branch: str) -> None:
        """Sets the branch to be used in the API requests."""
        self.branch = branch

    def generate_output(self, messages: List[Dict[str, str]]) -> Dict[str, Any]:
        """Generates output by sending messages to the Gemini API."""
        start_time = time()

        content = self._convert_messages_to_gemini_format(messages)
        generation_config = genai_types.GenerateContentConfig(
            temperature=self.temperature,
            seed=666,
            max_output_tokens=8192,
        )

        response = self.client.models.generate_content(
            model=self.model,
            contents=[content],
            config=generation_config,
        )

        end_time = time()
        duration_ns = int((end_time - start_time) * 1_000_000_000)
        response_text = response.text if hasattr(response, 'text') else str(response)

        return {
            "response": response_text,
            "total_duration": duration_ns,
        }
    
    def _convert_messages_to_gemini_format(self, messages: List[Dict[str, str]]) -> str:
        content_parts = []
        
        for msg in messages:
            role = msg.get("role", "")
            content = msg.get("content", "")
            
            if role == "system":
                content_parts.append(f"System: {content}")
            elif role == "user":
                content_parts.append(content)
            elif role == "assistant":
                content_parts.append(f"Assistant: {content}")
        
        return "\n\n".join(content_parts)
        

class CodellamaTestSuiteGenerator(TestSuiteGenerator):

    def __init__(self, java_tool, model_key: str = "codellama", model_config: Dict[str, Any] = None):
        super().__init__(java_tool)
        self.model_key = model_key
        self.model_config = model_config or {}
        self.api = None
        self.prompt_manager = PromptManager()

        # Loads global configurations
        global_config = get_config()

        # Prompt configurations (priority: model_config > global_config > default)
        self.prompt_template = (
            self.model_config.get("prompt_template") or 
            global_config.get("prompt_template") or 
            "zero_shot"
        )
        
        logging.info(f"Inicializado {self.model_key} com template: {self.prompt_template}")
    
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
            template_name=self.prompt_template
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
        """Initializes the API if it has not been initialized yet."""
        if self.api is not None:
            return

        config = get_config()
        api_params = config["api_params"]
        model_params = self.model_config or api_params[self.model_key]
        api_key = model_params["api_key"]

        self.api = GeminiApi(
            api_key=api_key,
            timeout_seconds=model_params.get("timeout_seconds", 60),
            temperature=model_params.get("temperature", 0),
            model=model_params.get("model", "gemini-2.5-flash-lite"),
        )

    def get_generator_tool_name(self) -> str:
        self._ensure_api_initialized()
        config_suffix = self._generate_config_suffix()
        return f"{self.model_key.upper()}{config_suffix}"
    
    def _generate_config_suffix(self) -> str:
        """Generates a suffix with configuration information for folder identification"""
        if not self.api:
            return ""

        # Prompt format: ZS (zero-shot) or 1S (one-shot)
        prompt_code = "ZS" if self.prompt_template == "zero_shot" else "1S"

        # Temperature: T00, T05, T07, etc. (always with 2 digits)
        temp_value = int(self.api.temperature * 100)  # 0.7 -> 70, 0.05 -> 5, 0 -> 0
        temp_code = f"T{temp_value:02d}"  # Formats with 2 digits: T00, T05, T07
        
        return f"_{prompt_code}_{temp_code}"

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
        JAVA_LANGUAGE = Language(tsjava.language())
        parser = Parser(JAVA_LANGUAGE)
        with open(source_code_path, 'r') as f:
            source_code = f.read()
        tree = parser.parse(bytes(source_code, "utf8"))
        return JAVA_LANGUAGE, source_code, tree

    def extract_snippet(self, source_code: str, start_byte: int, end_byte: int) -> str:
        """Extracts a snippet of code from the source code using the start and end byte offsets"""
        # Convert string to bytes, extract the snippet, then convert back to string
        source_bytes = source_code.encode('utf-8')
        snippet_bytes = source_bytes[start_byte:end_byte]
        return snippet_bytes.decode('utf-8')

    def extract_class_info(self, source_code_path: str, full_method_name: str, full_class_name: str) -> tuple:
        """
        Extracts the class fields, constructor, and body of the method under test from the source code
        using the generated AST to query the information
        """
        try:
            class_name = full_class_name.split('.')[-1]
            method_name = full_method_name.split('(')[0]
            JAVA_LANGUAGE, source_code, tree = self.parse_code(source_code_path)

            query_text = f"""
                (class_declaration
                    name: (identifier) @class_name
                    body: (class_body
                        [
                        (field_declaration) @field_declaration
                        (constructor_declaration
                            name: (identifier) @constructor_name) @constructor_declaration
                        (method_declaration
                            name: (identifier) @method_name) @method_def
                        (class_declaration) @nested_class
                        (#eq? @method_name "{method_name}")
                        (#eq? @constructor_name "{class_name}")
                        ]
                    )
                    (#eq? @class_name "{class_name}")
                )

                ; Searches for methods in any class (including nested ones)
                (method_declaration
                    name: (identifier) @any_method_name
                    (#eq? @any_method_name "{method_name}")
                ) @any_method_def

                ; Searches for fields in any class (including nested ones)
                (field_declaration) @any_field_declaration
            """
            query = JAVA_LANGUAGE.query(query_text)
            cursor = QueryCursor(query)
            captures_dict = cursor.captures(tree.root_node)

            captures = []
            for capture_name, nodes in captures_dict.items():
                for node in nodes:
                    captures.append((node, capture_name))

            if not captures:
                raise Exception(f"No captures found for the class '{class_name}' in '{source_code_path}'")

            class_fields: List[str] = []
            class_constructors: List[str] = []
            class_method: str = ""

            for node, capture_name in captures:
                captured_text = self.extract_snippet(source_code, node.start_byte, node.end_byte)

                if capture_name == "field_declaration":
                    class_fields.append(captured_text)
                elif capture_name == "constructor_declaration":
                    class_constructors.append(captured_text)
                elif capture_name == "method_def":
                    class_method = captured_text
                elif capture_name == "any_method_def" and not class_method:
                    class_method = captured_text
                elif capture_name == "any_field_declaration" and method_name in captured_text and not class_method:
                    class_method = captured_text

            if not class_method:
                logging.debug(f"Method/field '{method_name}' not found with main query, trying broader field search")

                # More specific query for fields with exact name (including in nested classes)
                field_query_text = f"""
                    (field_declaration
                        declarator: (variable_declarator
                            name: (identifier) @field_name
                        )
                        (#eq? @field_name "{method_name}")
                    ) @target_field_declaration
                """
                
                field_query = JAVA_LANGUAGE.query(field_query_text)
                field_cursor = QueryCursor(field_query)
                field_captures_dict = field_cursor.captures(tree.root_node)
                
                for capture_name, nodes in field_captures_dict.items():
                    for node in nodes:
                        if capture_name == "target_field_declaration":
                            class_method = self.extract_snippet(source_code, node.start_byte, node.end_byte)
                            logging.debug(f"Found field '{method_name}' as target: {class_method[:100]}...")
                            break

            return class_fields, class_constructors, class_method

        except Exception as e:
            logging.error(f"An error occurred while extracting class info for '{full_class_name}': {e}")
            raise e

    def save_scenario_infos(self, scenario_infos_path: str, class_name: str, methods: Union[List[str], List[Dict[str, str]]], source_code_path: str) -> None:
        """Stores relevant scenario information (for each class and method) in a JSON file"""
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
        """Finds the source code files for the given class name in the specified JAR path"""
        from nimrod.tests.utils import get_base_output_path
        base_output = get_base_output_path()
        base_path = os.path.join(os.path.dirname((os.path.dirname(os.path.dirname(base_output)))), "jar_files")

        return {
            "left": os.path.join(base_path, "left.java"),
            "right": os.path.join(base_path, "right.java"),
            "base": "",
            "merge": "",
        }

    def fetch_source_code_branch(self, input_jar: str, jar_type: str, class_name: str, project_name: str) -> tuple:
        """Retrieves the source code path and branch for the given JAR path"""
        source_code_paths = self.find_source_code_paths(input_jar, jar_type, class_name.split('.')[-1], project_name)
        branches = ["base", "left", "right", "merge"]
        branch = next(b for b in branches if b in input_jar)
        return source_code_paths.get(branch), branch, source_code_paths

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
        duration_filename = f"{self.model_key}{config_suffix}_time_duration.json"
        
        time_duration_path = os.path.join(
            os.path.dirname(
                os.path.dirname(
                    os.path.dirname(output_path))), "reports", duration_filename)

        project_name = scenario.project_name
        targets = scenario.targets
        jar_type = scenario.jar_type

        # Fetch the source code paths for each class and save the associated scenario information and import data
        for class_name, methods in targets.items():
            source_code_path, branch, source_paths = self.fetch_source_code_branch(input_jar, jar_type, class_name, project_name)
            self.save_scenario_infos(scenario_infos_path, class_name, methods, source_code_path)
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
                                      i=i, time_duration_path=time_duration_path, project_name=project_name)

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
