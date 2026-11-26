"""Prepare four behaviour-preserving views of each real mergedataset case.

The study only labels locally observable interference. It does NOT label the
seven questions in criteria.py. Unknown targets remain absent from gold. One
explicit auxiliary question supervises the available scenario-level label.
"""
import argparse
from collections import Counter, defaultdict
import csv
import hashlib
import importlib.util
import json
from pathlib import Path
import random
import re
import sys

ROOT = Path(__file__).resolve().parents[1]
BRANCHES = ("base", "left", "right", "merge")
GLOBAL_ID = "semantic_interference"


def load_criteria():
    path = ROOT / "SMAT/nimrod/laya_interference/criteria.py"
    spec = importlib.util.spec_from_file_location("_colab_criteria", path)
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def walk(node):
    yield node
    for child in node.named_children:
        yield from walk(child)


def text(node, data):
    return data[node.start_byte:node.end_byte].decode("utf-8")


def compact_type(value):
    return re.sub(r"\s+", "", value).replace("java.lang.", "").replace("|", ",")


def split_types(value):
    result, start, depth = [], 0, 0
    for i, char in enumerate(value):
        depth += (char == "<") - (char == ">")
        if char in ",|" and depth == 0:
            result.append(value[start:i])
            start = i + 1
    if value[start:].strip():
        result.append(value[start:])
    return [compact_type(x) for x in result]


def extract(path, class_name, declaration):
    from tree_sitter import Language, Parser
    import tree_sitter_java
    data = path.read_bytes()
    # Dataset sources have mixed encodings. Normalise decoding only, not code.
    try:
        data.decode("utf-8")
    except UnicodeDecodeError:
        data = data.decode("latin-1").encode("utf-8")
    tree = Parser(Language(tree_sitter_java.language())).parse(data)
    simple = class_name.rsplit(".", 1)[-1].split("$")[-1]
    classes = [n for n in walk(tree.root_node)
               if n.type in ("class_declaration", "interface_declaration", "enum_declaration")
               and n.child_by_field_name("name") is not None
               and text(n.child_by_field_name("name"), data) == simple]
    if len(classes) != 1:
        raise ValueError(f"Expected one class {simple}, found {len(classes)}: {path}")
    body = classes[0].child_by_field_name("body")
    members = list(body.named_children)
    fields = [text(n, data) for n in members if n.type in ("field_declaration", "constant_declaration")]
    if not declaration:
        return {"code": text(classes[0], data), "fields": [], "scope": "class", "source": str(path)}
    name = declaration.split("(", 1)[0].strip()
    constructors = name.lower() in ("constructor", "contructor", simple.lower())
    candidates = []
    for node in walk(body):
        member_name = node.child_by_field_name("name")
        if node.type == "constructor_declaration" and constructors:
            candidates.append(node)
        elif node.type == "method_declaration" and member_name and text(member_name, data) == name:
            candidates.append(node)
        elif node.type in ("field_declaration", "constant_declaration"):
            if any(n.type == "variable_declarator" and n.child_by_field_name("name")
                   and text(n.child_by_field_name("name"), data) == name for n in node.named_children):
                candidates.append(node)
    # Match the declared signature, never silently take the first overload.
    if len(candidates) > 1 and "(" in declaration:
        expected = split_types(declaration.split("(", 1)[1].rsplit(")", 1)[0])
        matching = []
        for node in candidates:
            params = node.child_by_field_name("parameters")
            actual = [compact_type(text(p.child_by_field_name("type"), data))
                      for p in params.named_children if p.child_by_field_name("type")]
            if actual == expected:
                matching.append(node)
        # Some study signatures are approximate (e.g. varargs). Preserve all
        # overloads when the signature cannot disambiguate; never pick one.
        if matching:
            candidates = matching
    if not candidates:
        raise ValueError(f"Declaration not found: {class_name}.{declaration}: {path}")
    code = "\n\n".join(text(n, data) for n in candidates)
    # Fields directly read/written by this target, retaining initialisers in
    # each version. No invented summaries or execution results enter the state.
    relevant = []
    for node in walk(body):
        if node.type not in ("field_declaration", "constant_declaration"):
            continue
        names = [text(n.child_by_field_name("name"), data) for n in node.named_children
                 if n.type == "variable_declarator" and n.child_by_field_name("name")]
        if any(re.search(r"\b" + re.escape(n) + r"\b", code) for n in names):
            field = text(node, data)
            if field != code:
                relevant.append(field)
    return {"code": code, "fields": list(dict.fromkeys(relevant)),
            "scope": "declaration" if len(candidates) == 1 else "overload_set",
            "source": str(path)}


def read_catalog():
    path = ROOT / "mergedataset-full/semantic-conflicts/sample-semantic-conflicts.csv"
    with path.open(encoding="utf-8-sig", newline="") as handle:
        records = [{k.strip(): v.strip() for k, v in r.items()} for r in csv.DictReader(handle)]
    for i, row in enumerate(records, 2):
        row["csv_line"] = i
        key = (row["Project"], row["Commit"], row["Class"], row["Declaration"])
        row["id"] = hashlib.sha256(json.dumps(key).encode()).hexdigest()[:16]
    return records


def source_files(root, row):
    # The artifact's project directories have different capitalisation from
    # some project URLs. Match the exact commit and qualified class suffix.
    suffix = target_class(row).replace(".", "/")
    commit_roots = list(root.glob(f"*/{row['Commit']}/source"))
    if len(commit_roots) != 1:
        raise ValueError(f"Missing/ambiguous source root for {row['Commit']}")
    class_dir = commit_roots[0] / suffix
    if not class_dir.is_dir():
        simple = target_class(row).rsplit(".", 1)[-1].split("$")[0]
        matches = [p.parent for p in commit_roots[0].rglob("base.java") if p.parent.name == simple]
        if len(matches) != 1:
            raise ValueError(f"Missing/ambiguous class directory: {class_dir}")
        class_dir = matches[0]
    files = {b: class_dir / f"{b}.java" for b in BRANCHES}
    # Misspelling in the upstream Eureka artifact, not a substituted version.
    if not files["right"].exists() and (class_dir / "rigth.java").is_file():
        files["right"] = class_dir / "rigth.java"
    if not all(p.is_file() for p in files.values()):
        raise ValueError(f"Incomplete B/L/R/M: {class_dir}")
    return files


def target_class(row):
    # The study's MongoDB row appends the method to the Class column.
    method = row["Declaration"].split("(", 1)[0]
    name = row["Class"]
    return name[:-(len(method)+1)] if method and method[0].islower() and name.endswith("." + method) else name


def render_state(case, variant):
    versions = case["versions"]
    title = f"Método: {case['class']}.{case['declaration'] or '(classe completa; declaração não informada)'}"
    orders = (BRANCHES, ("base", "right", "left", "merge"),
              ("merge", "base", "left", "right"), ("left", "right", "base", "merge"))
    headings = {"base": "Corpo da base (B):", "left": "Corpo de Left (L):",
                "right": "Corpo de Right (R):", "merge": "Corpo do merge (M):"}
    lines = [title]
    for branch in orders[variant]:
        info = versions[branch]
        lines.extend([headings[branch], info["code"], f"Atributos de {branch}:",
                      "\n".join(info["fields"]) or "nenhum"])
    lines.extend(["Resumo de Left: não informado", "Resumo de Right: não informado"])
    return "\n".join(lines)


def gold_answer(question, label):
    kind = question["type"]
    if kind == "noul":
        if type(label) is not bool:
            raise ValueError("Noul annotation must be a JSON boolean")
        keys, key = ["false", "true"], str(label).lower()
    elif kind == "score":
        if type(label) is not int or not 0 <= label < len(question["criteria"]):
            raise ValueError("Score annotation must be an integer level in range")
        keys, key = [str(i) for i in range(len(question["criteria"]))], str(label)
    else:
        keys, key = list(question["criteria"]), label
        if key not in keys:
            raise ValueError(f"Unknown choice label {key}")
    return {"label": key, "probabilities": {k: float(k == key) for k in keys}}


def split_groups(cases, seed=42):
    # Group by project AND merge: related methods/classes cannot leak.
    groups = defaultdict(list)
    for case in cases:
        groups[(case["project"], case["commit"])].append(case)
    buckets = defaultdict(list)
    for key, values in sorted(groups.items()):
        buckets[any(c["label"] == "Yes" for c in values)].append(key)
    rng = random.Random(seed)
    assignments = {}
    for keys in buckets.values():
        rng.shuffle(keys)
        n_val = max(1, round(len(keys) * .15))
        n_test = max(1, round(len(keys) * .15))
        for i, key in enumerate(keys):
            assignments[key] = "validation" if i < n_val else "test" if i < n_val+n_test else "train"
    return {c["id"]: assignments[(c["project"], c["commit"])] for c in cases}


def dump(path, value):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def jsonl(path, rows):
    path.write_text("".join(json.dumps(r, ensure_ascii=False) + "\n" for r in rows), encoding="utf-8")


def prepare(source_root, out, annotations_path=None, strict=False):
    criteria = load_criteria()
    project_questions = criteria.build_questions(witness_candidates=criteria.WITNESS_CANDIDATE_DESCRIPTIONS)
    auxiliary = {"type": "noul", "instructions": (
        "Do the left and right changes exhibit locally observable semantic interference "
        "in this real merge scenario, considering base B, left L, right R and merge M? "
        "Semantic interference concerns changed observable behaviour, not textual differences alone. "
        "This is a scenario-level question and does not identify a particular criterion."),
        "criteria": {"false": "No locally observable interference.",
                     "true": "Locally observable interference is present."}}
    questions = {**project_questions, GLOBAL_ID: auxiliary}
    annotations = json.loads(annotations_path.read_text(encoding="utf-8")) if annotations_path else {}
    catalog = read_catalog()
    cases, failures = [], []
    source_index = json.loads((source_root / "index.json").read_text(encoding="utf-8"))
    for row in catalog:
        if row["Locally Observable Interference"] not in ("Yes", "No"):
            continue
        try:
            paths = source_files(source_root, row)
            versions = {b: extract(path, target_class(row), row["Declaration"]) for b, path in paths.items()}
            cases.append({"id": row["id"], "project": row["Project"], "commit": row["Commit"],
                          "class": row["Class"], "declaration": row["Declaration"],
                          "label": row["Locally Observable Interference"], "csv_line": row["csv_line"],
                          "versions": versions})
        except Exception as error:
            failures.append({"id": row["id"], "csv_line": row["csv_line"], "error": str(error)})
    out.mkdir(parents=True, exist_ok=True)
    dump(out / "extraction_failures.json", failures)
    if strict and failures:
        raise ValueError(f"{len(failures)} real cases failed extraction; see {out / 'extraction_failures.json'}")
    assignments = split_groups(cases)
    rows = []
    review = {}
    for case in cases:
        reviewed = annotations.get(case["id"], {})
        targets = reviewed.get("answers", {})
        if targets and not reviewed.get("evidence"):
            raise ValueError(f"Annotation {case['id']} has no evidence/provenance")
        if set(targets) - set(project_questions):
            raise ValueError(f"Unknown annotation questions: {set(targets) - set(project_questions)}")
        gold = {GLOBAL_ID: gold_answer(auxiliary, case["label"] == "Yes")}
        gold.update({qid: gold_answer(project_questions[qid], label) for qid, label in targets.items()})
        review[case["id"]] = {"csv_line": case["csv_line"], "class": case["class"],
                               "declaration": case["declaration"], "scenario_label": case["label"],
                               "answers": targets, "evidence": reviewed.get("evidence", "")}
        for variant in range(4):
            rows.append({"state": render_state(case, variant), "questions": questions, "gold": gold,
                         "_meta": {"id": f"{case['id']}-v{variant}", "case_id": case["id"],
                                   "group_id": case["project"] + "/" + case["commit"],
                                   "split": assignments[case["id"]], "variant": variant,
                                   "label": case["label"], "csv_line": case["csv_line"],
                                   "source_revision": source_index["revision"],
                                   "source_files": {b: str(Path(v["source"]).relative_to(source_root)).replace("\\", "/")
                                                    for b, v in case["versions"].items()},
                                   "source_sha256": {b: hashlib.sha256(Path(v["source"]).read_bytes()).hexdigest()
                                                     for b, v in case["versions"].items()},
                                   "annotation_evidence": reviewed.get("evidence", "")}})
    # Include extracted versions for auditing and adding annotations; paths are
    # repository-relative, never machine-specific.
    for case in cases:
        for version in case["versions"].values():
            version["source"] = str(Path(version["source"]).relative_to(source_root)).replace("\\", "/")
    jsonl(out / "all.jsonl", rows)
    for split in ("train", "validation", "test"):
        selected = [r for r in rows if r["_meta"]["split"] == split]
        # Only train is augmented. Calibration and test score original views,
        # so four views do not pretend to be four independent test cases.
        jsonl(out / f"{split}.jsonl", [r for r in selected if split == "train" or r["_meta"]["variant"] == 0])
    dump(out / "cases.json", cases)
    dump(out / "annotations.json", review)
    dump(out / "questions.json", questions)
    dump(out / "project_questions.json", project_questions)
    dump(out / "source_catalog.json", catalog)
    manifest = {"catalog_rows": len(catalog), "catalog_labels": dict(Counter(r["Locally Observable Interference"] for r in catalog)),
                "real_cases_extracted": len(cases), "views_per_case": 4, "total_views": len(rows),
                "synthetic_cases": 0, "source_revision": source_index["revision"],
                "split_real_cases": dict(Counter(assignments.values())),
                "split_augmented_views": dict(Counter(r["_meta"]["split"] for r in rows)),
                "supervised_question_counts": dict(Counter(q for r in rows for q in r["gold"])),
                "unlabeled_project_questions": [q for q in project_questions if not any(q in r["gold"] for r in rows)],
                "extraction_failures": len(failures), "seed": 42,
                "note": "Only semantic_interference has a corpus target. Yes/No is not a C1/C2/C3, witness, branch or confidence annotation. All variants preserve exact source tokens; only version section order changes. Split by project+merge before augmentation."}
    dump(out / "manifest.json", manifest)
    print(json.dumps(manifest, indent=2, ensure_ascii=False))
    return manifest


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--sources", type=Path, default=ROOT / ".laya_smat/mergedataset_sources")
    parser.add_argument("--out", type=Path, default=ROOT / "laya_training_data/mergedataset_full_colab")
    parser.add_argument("--annotations", type=Path)
    parser.add_argument("--strict", action="store_true")
    args = parser.parse_args()
    prepare(args.sources, args.out, args.annotations, args.strict)


if __name__ == "__main__":
    main()
