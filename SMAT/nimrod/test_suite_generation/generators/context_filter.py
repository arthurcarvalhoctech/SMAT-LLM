"""Diff-based filter for the class context sent to the LLM test generator.

The class fields extracted from the source are filtered so that only the
fields that matter for the change reach the prompt:

- a field used by the target method is kept;
- a field whose name appears on a line changed between the base and the branch
  version is kept, even if the target method does not use it.

Constructors and the target method body are not filtered: constructors are
needed to build objects in the generated tests, and the method body is the
subject of the test.

The filter is deterministic and name-based. It is enabled with the environment
variable ``SMAT_CONTEXT_FILTER`` (default: disabled).
"""

import difflib
import logging
import os
import re
from typing import Iterable, List, Set

CONTEXT_FILTER_ENV_VAR = "SMAT_CONTEXT_FILTER"

_IDENTIFIER_PATTERN = re.compile(r"[A-Za-z_]\w*")
_FALSE_VALUES = {"", "0", "false", "no", "off"}


def context_filter_enabled() -> bool:
    value = os.environ.get(CONTEXT_FILTER_ENV_VAR, "false").strip().lower()
    return value not in _FALSE_VALUES


def identifiers(text: str) -> Set[str]:
    return set(_IDENTIFIER_PATTERN.findall(text))


def declared_field_names(declaration: str) -> List[str]:
    """Names declared by a field declaration.

    ``private int count = 0;`` -> ``["count"]``
    ``int a, b;`` -> ``["a", "b"]``
    """
    head = declaration.split("=")[0].rstrip().rstrip(";")
    if "," in head and "<" not in head:
        parts = [part.strip() for part in head.split(",")]
        names = [re.findall(r"[A-Za-z_]\w*", part)[-1] for part in parts if re.findall(r"[A-Za-z_]\w*", part)]
        return names
    words = _IDENTIFIER_PATTERN.findall(head)
    return [words[-1]] if words else []


def changed_identifiers(base_text: str, branch_text: str) -> Set[str]:
    """Identifiers that appear on lines changed between base and branch."""
    changed: Set[str] = set()
    diff = difflib.unified_diff(
        base_text.splitlines(), branch_text.splitlines(), lineterm=""
    )
    for line in diff:
        if line.startswith(("+++", "---")):
            continue
        if line.startswith(("+", "-")):
            changed |= identifiers(line[1:])
    return changed


def filter_class_fields(
    fields: Iterable[str], method_code: str, changed_ids: Set[str]
) -> List[str]:
    """Keep the fields used by the method or touched by the change.

    A field whose name cannot be read is kept, so the filter never drops
    something it does not understand.
    """
    relevant = identifiers(method_code) | changed_ids
    kept: List[str] = []
    for declaration in fields:
        names = declared_field_names(declaration)
        if not names or any(name in relevant for name in names):
            kept.append(declaration)
    return kept


def filter_context(
    fields: List[str],
    method_code: str,
    base_text: str,
    branch_text: str,
) -> List[str]:
    """Filtered field list for one branch. Logs how many fields were dropped."""
    changed = changed_identifiers(base_text, branch_text)
    kept = filter_class_fields(fields, method_code, changed)
    if len(kept) != len(fields):
        logging.info(
            "Context filter kept %d of %d class field(s)", len(kept), len(fields)
        )
    return kept
