#!/usr/bin/env python3
"""Monta o input do SMAT (só triagem Laya) e o gabarito a partir do mergedataset.

Fonte: `semantic-conflicts/sample-semantic-conflicts.csv` (uma linha por classe/método alvo).

A triagem Laya lê o código de `<cenário>/source/` e usa os caminhos de JAR apenas para localizar
a pasta do cenário. Por isso este script não precisa dos JARs e grava um caminho de JAR fictício
(`<cenário>/original/<branch>/<branch>.jar`). Esse input não serve para a detecção dinâmica, que
executa os JARs.

Saídas:
- input do SMAT (JSON): um item por cenário (projeto, commit do merge) com `source/` local;
- gabarito (JSON): uma entrada por método alvo, na mesma ordem em que o SMAT processa o input.
"""
import argparse
import csv
import json
import os
from collections import OrderedDict

BRANCHES = ("base", "left", "right", "merge")
LABELS = {"yes": True, "no": False}


def read_rows(csv_path):
    rows = list(csv.reader(open(csv_path, encoding="utf-8", errors="replace")))
    header = [c.strip() for c in rows[0]]
    index = {name: header.index(name) for name in
             ("Locally Observable Interference", "Commit", "Project", "Class", "Declaration")}
    out = []
    for row in rows[1:]:
        if len(row) <= max(index.values()):
            continue
        cells = [c.strip() for c in row]
        out.append({
            "project_dir": cells[index["Project"]].rstrip("/").split("/")[-1],
            "commit": cells[index["Commit"]],
            "class": cells[index["Class"]],
            "method": cells[index["Declaration"]],
            "label": cells[index["Locally Observable Interference"]],
        })
    return out


def find_scenario_dir(dataset_root, project_dir, commit):
    """O repositório usa o nome do projeto em minúsculas ou com a caixa original."""
    for name in os.listdir(dataset_root):
        if name.lower() == project_dir.lower() and os.path.isdir(os.path.join(dataset_root, name, commit, "source")):
            return name
    return None


def build(rows, dataset_root):
    scenarios = OrderedDict()
    skipped = OrderedDict()
    for row in rows:
        key = (row["project_dir"].lower(), row["commit"])
        folder = find_scenario_dir(dataset_root, row["project_dir"], row["commit"])
        if folder is None:
            skipped[key] = "sem source/ local"
            continue
        if key not in scenarios:
            prefix = "${PATH_DATASET}/%s/%s/original" % (folder, row["commit"])
            scenarios[key] = {
                "projectName": folder,
                "runAnalysis": True,
                "scenarioCommits": {"base": "", "left": "", "right": "", "merge": row["commit"]},
                "targets": OrderedDict(),
                "scenarioJars": {b: "%s/%s/%s.jar" % (prefix, b, b) for b in BRANCHES},
                "jarType": "original",
            }
        methods = scenarios[key]["targets"].setdefault(row["class"], [])
        if not any(m["method"] == row["method"] for m in methods):
            methods.append({"method": row["method"]})
    return scenarios, skipped


def gold_in_order(scenarios, rows):
    labels = {}
    for row in rows:
        labels[(row["project_dir"].lower(), row["commit"], row["class"], row["method"])] = row["label"]
    gold = []
    for (proj, commit), scenario in scenarios.items():
        for class_name, methods in scenario["targets"].items():
            for item in methods:
                raw = labels.get((proj, commit, class_name, item["method"]), "-")
                gold.append({
                    "project": scenario["projectName"], "commit": commit, "class": class_name,
                    "method": item["method"], "label": raw,
                    "interference": LABELS.get(raw.lower()),
                })
    return gold


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--csv", required=True)
    ap.add_argument("--dataset-root", required=True)
    ap.add_argument("--output", required=True, help="input do SMAT")
    ap.add_argument("--gold-output", required=True, help="gabarito, na ordem de processamento do SMAT")
    args = ap.parse_args()

    rows = read_rows(args.csv)
    scenarios, skipped = build(rows, args.dataset_root)
    gold = gold_in_order(scenarios, rows)

    with open(args.output, "w", encoding="utf-8") as f:
        json.dump(list(scenarios.values()), f, indent=2, ensure_ascii=False)
        f.write("\n")
    with open(args.gold_output, "w", encoding="utf-8") as f:
        json.dump(gold, f, indent=2, ensure_ascii=False)
        f.write("\n")

    labeled = [g for g in gold if g["interference"] is not None]
    print(f"Linhas do CSV: {len(rows)} | cenários no input: {len(scenarios)} | cenários sem source: {len(skipped)}")
    print(f"Métodos alvo: {len(gold)} | rotulados: {len(labeled)} "
          f"(Yes {sum(g['interference'] for g in labeled)}, No {sum(not g['interference'] for g in labeled)})")
    for key, why in skipped.items():
        print(f"  ignorado {key[0]}/{key[1][:8]}: {why}")


if __name__ == "__main__":
    main()
