"""Reusable Java source discovery and Tree-sitter extraction.

These helpers were extracted from the LLM test-suite generator so that both the
generator and the Laya pre-analysis flow use exactly the same source layout and
the same method/field/constructor snippets.
"""

import logging
import os
from pathlib import Path
from typing import Dict, List, Tuple

import tree_sitter_java as tsjava
from tree_sitter import Language, Parser, QueryCursor


def find_source_code_paths(input_jar: str, jar_type: str, class_name: str) -> Dict[str, str]:
    """Find the source files for a target class in a merge scenario.

    Supported layouts:
      - <scenario>/transformed/<branch>/*.jar + <scenario>/source/<Class>_<branch>.java
      - <scenario>/transformed/<branch>/*.jar + <scenario>/source/<Class>/<branch>.java
      - <scenario>/transformed/<branch>/*.jar + <scenario>/source/<branch>.java
      - Legacy <repo>/jar_files/{left,right}.java (toy scenarios)

    Returns a dict with ``base``, ``left``, ``right`` and ``merge`` keys. The
    value is an empty string when that version has no matching source file.
    """
    class_name = class_name.split(".")[-1]
    first_jar = input_jar.split(":")[0]
    path_parts = Path(first_jar).parts

    if jar_type in path_parts:
        type_index = path_parts.index(jar_type)
        scenario_root = Path(*path_parts[:type_index])
    else:
        scenario_root = Path(first_jar).parent

    source_root = scenario_root / "source"

    if source_root.is_dir():
        found: Dict[str, str] = {b: "" for b in ("base", "left", "right", "merge")}
        scores: Dict[str, int] = {b: 0 for b in found}

        for root, _, files in os.walk(source_root):
            root_name = os.path.basename(root)
            for file_name in files:
                if not file_name.endswith(".java"):
                    continue
                stem = file_name[:-len(".java")]
                for branch in found:
                    if stem == branch:
                        score = 2 if root_name == class_name else 1
                    elif stem == f"{class_name}_{branch}":
                        score = 2
                    elif stem.endswith(f"_{branch}") and class_name in stem:
                        score = 1
                    else:
                        continue

                    if score > scores[branch]:
                        found[branch] = str(Path(root) / file_name)
                        scores[branch] = score

        # Some datasets (e.g. ASTER) have only one source version.
        if not found["left"] or not found["right"]:
            for root, _, files in os.walk(source_root):
                generic = os.path.join(root, f"{class_name}.java")
                if os.path.isfile(generic):
                    if not found["left"]:
                        found["left"] = generic
                    if not found["right"]:
                        found["right"] = generic
                    break

        missing = [b for b in ("left", "right") if not found[b]]
        if missing:
            raise FileNotFoundError(
                f"Could not find source files for {missing} of class '{class_name}' "
                f"under '{source_root}'. Expected <Class>_<branch>.java, "
                f"<Class>/<branch>.java, <branch>.java or <Class>.java."
            )

        return found

    # Legacy layout used by the toy Discount scenario. Only apply it when the
    # scenario jar itself lives under a `jar_files` directory. Applying it to a
    # real dataset whose `source/` directory is missing would silently reuse
    # unrelated toy sources for every class and hide a wrong PATH_DATASET.
    if "jar_files" in Path(first_jar).parts:
        from nimrod.tests.utils import get_base_output_path

        base_output = get_base_output_path()
        legacy_root = os.path.join(
            os.path.dirname(os.path.dirname(os.path.dirname(base_output))),
            "jar_files",
        )
        legacy_left = os.path.join(legacy_root, "left.java")
        legacy_right = os.path.join(legacy_root, "right.java")

        if os.path.isfile(legacy_left) and os.path.isfile(legacy_right):
            logging.warning(
                "Source directory '%s' not found; falling back to legacy sources in '%s'.",
                source_root,
                legacy_root,
            )
            return {"left": legacy_left, "right": legacy_right, "base": "", "merge": ""}

        raise FileNotFoundError(
            f"Source directory '{source_root}' not found and legacy sources were not "
            f"available in '{legacy_root}'."
        )

    raise FileNotFoundError(
        f"Source directory '{source_root}' not found for scenario jar '{first_jar}'. "
        "Check PATH_DATASET and the dataset layout; base/left/right/merge sources "
        "must be under '<scenario>/source/'."
    )


def parse_java_code(source_code_path: str) -> Tuple[Language, str, object]:
    """Parse Java source with Tree-sitter.

    Returns ``(language, source_code, tree)``.
    """
    language = Language(tsjava.language())
    parser = Parser(language)
    with open(source_code_path, "r") as source_file:
        source_code = source_file.read()
    tree = parser.parse(bytes(source_code, "utf8"))
    return language, source_code, tree


def extract_java_snippet(source_code: str, start_byte: int, end_byte: int) -> str:
    """Extract a byte-offset snippet from Java source."""
    source_bytes = source_code.encode("utf-8")
    snippet_bytes = source_bytes[start_byte:end_byte]
    return snippet_bytes.decode("utf-8")


def extract_java_class_info(
    source_code_path: str,
    full_method_name: str,
    full_class_name: str,
) -> Tuple[List[str], List[str], str]:
    """Extract class fields, constructors, and the target method body.

    The method matches by name (not by full signature). Overloaded methods are a
    known limitation of the original extractor.
    """
    try:
        class_name = full_class_name.split(".")[-1]
        method_name = full_method_name.split("(")[0]
        language, source_code, tree = parse_java_code(source_code_path)

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
        query = language.query(query_text)
        cursor = QueryCursor(query)
        captures_dict = cursor.captures(tree.root_node)

        captures = []
        for capture_name, nodes in captures_dict.items():
            for node in nodes:
                captures.append((node, capture_name))

        if not captures:
            raise Exception(
                f"No captures found for the class '{class_name}' in '{source_code_path}'"
            )

        class_fields: List[str] = []
        class_constructors: List[str] = []
        class_method: str = ""

        for node, capture_name in captures:
            captured_text = extract_java_snippet(
                source_code, node.start_byte, node.end_byte
            )

            if capture_name == "field_declaration":
                class_fields.append(captured_text)
            elif capture_name == "constructor_declaration":
                class_constructors.append(captured_text)
            elif capture_name == "method_def":
                class_method = captured_text
            elif capture_name == "any_method_def" and not class_method:
                class_method = captured_text
            elif (
                capture_name == "any_field_declaration"
                and method_name in captured_text
                and not class_method
            ):
                class_method = captured_text

        if not class_method:
            logging.debug(
                "Method/field '%s' not found with main query, trying broader field search",
                method_name,
            )

            field_query_text = f"""
                (field_declaration
                    declarator: (variable_declarator
                        name: (identifier) @field_name
                    )
                    (#eq? @field_name "{method_name}")
                ) @target_field_declaration
            """

            field_query = language.query(field_query_text)
            field_cursor = QueryCursor(field_query)
            field_captures_dict = field_cursor.captures(tree.root_node)

            for capture_name, nodes in field_captures_dict.items():
                for node in nodes:
                    if capture_name == "target_field_declaration":
                        class_method = extract_java_snippet(
                            source_code, node.start_byte, node.end_byte
                        )
                        logging.debug(
                            "Found field '%s' as target: %s...",
                            method_name,
                            class_method[:100],
                        )
                        break

        return class_fields, class_constructors, class_method

    except Exception as error:
        logging.error(
            "An error occurred while extracting class info for '%s': %s",
            full_class_name,
            error,
        )
        raise
