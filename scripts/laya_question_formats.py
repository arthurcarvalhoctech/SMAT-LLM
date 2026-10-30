#!/usr/bin/env python3
"""Compara formatos de pergunta para os 3 critérios de interferência no Laya.

O README do Laya avisa que o `noul` pode seguir o texto das opções (`false:` / `true:`) em vez do
estado, e sugere como contornos o mapeamento `labels` (A/B), um `choice` com chaves neutras, ou o
`noul` sem `criteria`. Este script mede cada um, com dois estados:

  smat    o dicionário que o SMAT envia hoje (LayaMethodState.to_payload)
  treino  o texto no formato do smat_dataset (corpo de B, L, R e M, resumos, atributos)

Formatos de pergunta (um por critério):
  f0  noul + criteria {false, true}        (atual do SMAT)
  f1  choice com chaves A (sim) e B (não)
  f2  noul + criteria + labels {true: A, false: B}
  f3  noul sem criteria

Roda no container: PYTHONPATH=/app/SMAT python3 scripts/laya_question_formats.py --out <json>
"""
import argparse
import json
import os
import re
import sys
from types import SimpleNamespace

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from laya_t1_probe import (BRANCHES, build_state, method_body, used_fields,  # noqa: E402
                           with_field_inits)


def questions_for(fmt, criteria):
    out = {}
    for c in criteria:
        base = {"type": "noul", "instructions": c.laya_instruction}
        if fmt == "f0":
            q = dict(base, criteria={"false": c.laya_false, "true": c.laya_true})
        elif fmt == "f1":
            q = {"type": "choice", "instructions": c.laya_instruction,
                 "criteria": {"A": "yes, " + c.laya_true[0].lower() + c.laya_true[1:],
                              "B": "no, " + c.laya_false[0].lower() + c.laya_false[1:]}}
        elif fmt == "f2":
            q = dict(base, criteria={"false": c.laya_false, "true": c.laya_true}, labels={"true": "A", "false": "B"})
        else:
            q = base
        out[c.id] = q
    return out


def read(answer, fmt):
    return float(answer["probabilities"]["A"] if fmt == "f1" else answer["noul"])


def scenarios(synthetic_input, synthetic_gold, merge_input, merge_gold, dataset_root):
    gold = json.load(open(synthetic_gold))
    flat = []
    for scen, g in zip(json.load(open(synthetic_input)), gold):
        flat.append((scen, "sintetico", g["commit"], "Yes" if g["interference"] else "No", g["criteria"], scen["scenarioJars"]))
    glabel = {(m["commit"], m["class"], m["method"]): m["label"] for m in json.load(open(merge_gold))["methods"]}
    for scen in json.load(open(merge_input)):
        jars = {b: v.replace("${PATH_DATASET}", dataset_root) for b, v in scen["scenarioJars"].items()}
        commit = re.search(r"/([0-9a-f]{40})/", jars["merge"]).group(1)
        flat.append((scen, "mergedataset", commit, None, [], jars))
    for scen, kind, ident, label, crit, jars in flat:
        for cls, items in scen["targets"].items():
            for item in items:
                if kind == "mergedataset":
                    lab = glabel.get((ident, cls, item["method"]), "-")
                    cid = ident[:7] + "/" + cls.split(".")[-1] + "." + item["method"]
                else:
                    lab, cid = label, ident
                yield dict(set=kind, id=cid, label=lab, criteria=crit, scen=scen, jars=jars, cls=cls, item=item)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", required=True)
    ap.add_argument("--max-len", type=int, default=4000)
    ap.add_argument("--ft", default="/laya_smat/laya_finetuned_smat_multilingual")
    ap.add_argument("--dataset-root", default=os.environ.get("PATH_DATASET", ""))
    args = ap.parse_args()

    from laya import Router, load
    from nimrod.laya_interference.criteria import CRITERIA
    from nimrod.laya_interference.source_context import build_method_state
    from nimrod.source_code import find_source_code_paths

    models = {"ajustado": load(args.ft), "base": Router()}
    results = []
    for case in scenarios("/app/dataset-sintetico/input-smat-sintetico.json", "/app/dataset-sintetico/gold-sintetico.json",
                          "/app/input-smat-mergedataset.json", "/app/template/gold-13-methods.json", args.dataset_root):
        scen, item, cls, jars = case["scen"], case["item"], case["cls"], case["jars"]
        sj = SimpleNamespace(**{b: jars[b] for b in BRANCHES})
        scenario = SimpleNamespace(project_name=scen["projectName"], jar_type=scen["jarType"], scenario_jars=sj)
        smat_state = build_method_state(scenario, cls, item).to_payload()

        paths = find_source_code_paths(jars["left"] or jars["right"], scen["jarType"], cls)
        src = {b: open(paths[b], errors="replace").read() for b in BRANCHES}
        raw = {b: method_body(src[b], item["method"]) for b in BRANCHES}
        flds = {b: used_fields(src[b], raw[b]) for b in BRANCHES}
        bodies = {b: with_field_inits(raw[b], flds[b]) for b in BRANCHES}
        label = "%s.%s" % (cls.split(".")[-1], item["method"])
        train_state = build_state(label, bodies, item.get("leftChangesSummary", ""), item.get("rightChangesSummary", ""),
                                  flds["base"], True)
        row = {k: case[k] for k in ("set", "id", "label", "criteria")}
        for sname, state in (("smat", smat_state), ("treino", train_state)):
            for fmt in ("f0", "f1", "f2", "f3"):
                questions = questions_for(fmt, CRITERIA)
                for mname, model in models.items():
                    if mname == "base":
                        res = model.predict(state, questions, model="multilingual", max_len=args.max_len)
                    else:
                        res = model.predict(state, questions, max_len=args.max_len)
                    row["%s/%s/%s" % (sname, fmt, mname)] = {q: round(read(a, fmt), 4) for q, a in res["answers"].items()}
        results.append(row)
        print(row["id"], row["label"], flush=True)
    json.dump(results, open(args.out, "w"), indent=1)


if __name__ == "__main__":
    main()
