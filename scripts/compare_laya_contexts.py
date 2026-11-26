"""Compare context limits on an identical model/data/threshold and common cases."""
import argparse
import json
from pathlib import Path

try:
    from scripts.evaluate_laya_synthetic import binary_metrics
except ModuleNotFoundError:
    from evaluate_laya_synthetic import binary_metrics

ROOT = Path(__file__).resolve().parents[1]


def compare_runs(short, full):
    for key in ("model_sha256", "data_sha256", "question", "threshold"):
        if short[key] != full[key]:
            raise ValueError(f"Not a controlled context comparison: different {key}")
    a = {r["id"]: r for r in short["predictions"] if r["status"] == "ok"}
    b = {r["id"]: r for r in full["predictions"] if r["status"] == "ok"}
    common = sorted(set(a) & set(b))
    if any(a[key]["gold"] != b[key]["gold"] for key in common):
        raise ValueError("Gold labels differ between runs")
    return {
        "threshold": short["threshold"],
        "profiles": [{"max_len": r["max_len"], "metrics": r["metrics"],
                      "partitions": {s: p["metrics"] for s,p in r["partitions"].items()}}
                     for r in (short,full)],
        "common_cases": len(common),
        "common_case_metrics": {str(r["max_len"]): binary_metrics([by_id[k] for k in common], r["threshold"])
                                for r,by_id in ((short,a),(full,b))},
        "changed_decision_ids": [k for k in common if (a[k]["probability"] >= short["threshold"]) != (b[k]["probability"] >= full["threshold"])],
        "max_probability_delta_on_common_cases": max((abs(a[k]["probability"]-b[k]["probability"]) for k in common),default=0.),
        "additional_full_context_cases": [{k: row[k] for k in ("id","class","method","gold","split")}
                                          for key,row in b.items() if key not in a],
        "note": "This isolates context coverage with the trained global detector. It does not run the production .env model alias, criteria questions, state format or dataset path. Pooled metrics contain training cases; compare reserved test and common cases separately. No threshold was fitted on test cases."}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--short", type=Path, default=ROOT/"mergedataset-full/resultados/laya_semantic_global_context_4048.json")
    parser.add_argument("--full", type=Path, default=ROOT/"mergedataset-full/resultados/laya_semantic_global_eval.json")
    parser.add_argument("--out", type=Path, default=ROOT/"mergedataset-full/resultados/laya_context_comparison.json")
    args = parser.parse_args()
    result = compare_runs(json.loads(args.short.read_text()),json.loads(args.full.read_text()))
    args.out.parent.mkdir(parents=True,exist_ok=True)
    args.out.write_text(json.dumps(result,ensure_ascii=False,indent=2)+"\n",encoding="utf-8")
    print(json.dumps(result,ensure_ascii=False,indent=2))


if __name__ == "__main__":
    main()
