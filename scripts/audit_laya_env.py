"""Read only non-secret Laya settings; audit compatibility with this checkpoint."""
import argparse
from collections import Counter
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
ALLOWED = {
    "INSTALL_LAYA", "PATH_DATASET", "LAYA_SMAT_DIR",
    "SMAT_LAYA_INTERFERENCE_DETECTION", "SMAT_LAYA_MODEL", "SMAT_LAYA_THRESHOLD",
    "SMAT_LAYA_MAX_LEN", "SMAT_LAYA_THRESHOLDS", "SMAT_LAYA_DECISION_RULE",
    "SMAT_LAYA_STATE_FORMAT", "SMAT_LAYA_WITNESS", "SMAT_LAYA_WITNESS_TWO_STAGE",
    "SMAT_LAYA_NEGATIVE_INSTRUCTIONS", "SMAT_LAYA_DIAGNOSTIC_QUESTIONS",
    "SMAT_DYNAMIC_INTERFERENCE_DETECTION", "SMAT_LLM_INTERFERENCE_DETECTION",
}


def read_public_settings(path):
    result = {}
    for line in path.read_text(encoding="utf-8-sig").splitlines():
        stripped = line.strip()
        if not stripped or stripped.startswith("#") or "=" not in stripped:
            continue
        key, value = stripped.split("=", 1)
        key, value = key.strip(), value.strip()
        if key not in ALLOWED:
            continue
        if len(value) >= 2 and value[0] == value[-1] and value[0] in "\"'":
            value = value[1:-1]
        result[key] = value
    return result


def audit(settings, cfg, previous):
    context = int(settings.get("SMAT_LAYA_MAX_LEN", "512"))
    head = int(cfg["head_max_len"])
    estimates = {}
    for limit in sorted({context, int(cfg["max_len"])}):
        kept = [p for p in previous["predictions"] if p["source_tokens"] + head + 32 <= limit]
        estimates[str(limit)] = {"available_cases": len(previous["predictions"]), "fit_cases": len(kept),
                                 "labels": {"Yes": sum(p["gold"] for p in kept), "No": sum(not p["gold"] for p in kept)},
                                 "partitions": dict(Counter(p["split"] for p in kept))}
    findings = []
    if settings.get("SMAT_LAYA_MODEL", "english") in {"english", "multilingual", "typed-decisions"}:
        findings.append("SMAT_LAYA_MODEL selects a base alias, not the locally fine-tuned checkpoint.")
    if "dataset-sintetico" in settings.get("PATH_DATASET", "").replace("\\", "/").split("/"):
        findings.append("PATH_DATASET points to the synthetic dataset, not the real corpus sources.")
    if context != cfg["max_len"]:
        findings.append("SMAT_LAYA_MAX_LEN differs from the training context; compare coverage and a common cohort.")
    findings.append("The production flow asks C1/C2/C3. The trained checkpoint was supervised only for semantic_interference; changing model paths alone does not integrate that task.")
    return {"public_env_settings": settings, "inference_defaults_if_unset": {
                "decision_rule": settings.get("SMAT_LAYA_DECISION_RULE", "baseline"),
                "state_format": settings.get("SMAT_LAYA_STATE_FORMAT", "json"),
                "witness": settings.get("SMAT_LAYA_WITNESS", "false")},
            "checkpoint_max_len": cfg["max_len"], "checkpoint_head_max_len": head,
            "findings": findings, "context_coverage_estimates": estimates,
            "note": "No secrets or credentials are included. Coverage reuses token lengths from the same checkpoint's previous real-corpus evaluation. The controlled global evaluator does not load production .env, production questions or PATH_DATASET. The original .env is not modified."}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--env", type=Path, default=ROOT / ".env")
    parser.add_argument("--out", type=Path, default=ROOT / "mergedataset-full/resultados/laya_env_audit.json")
    args = parser.parse_args()
    cfg = json.loads((ROOT / "laya_checkpoints/laya_semantic_global/rl_agent_config.json").read_text())
    previous = json.loads((ROOT / "mergedataset-full/resultados/laya_semantic_global_eval.json").read_text())
    result = audit(read_public_settings(args.env), cfg, previous)
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(result, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
