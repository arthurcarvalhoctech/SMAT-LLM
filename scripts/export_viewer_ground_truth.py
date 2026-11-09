#!/usr/bin/env python3
"""Export the labeled cases used by the viewer's accuracy indicators.

The viewer reads a static JSON file so it works both locally and in the
standalone Docker image (which only mounts SMAT/output-test-dest).

Sources:
- dataset-sintetico/resultados/probe_t1.json (synthetic + mergedataset labels)
- mergedataset-full/semantic-conflicts/sample-semantic-conflicts.csv (full labels)
- the latest scenario manifests for case -> class/method mapping
"""

from __future__ import annotations

import csv
import glob
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "viewer" / "data" / "ground-truth.json"


def norm_method(value: str | None) -> str:
    return (value or "").strip().split("(")[0].strip()


def simple_class(value: str | None) -> str:
    return (value or "").strip().split(".")[-1]


def latest_manifest(pattern: str) -> dict:
    paths = sorted(glob.glob(str(ROOT / pattern)))
    if not paths:
        raise SystemExit(f"manifest not found: {pattern}")
    with open(paths[-1], encoding="utf-8") as handle:
        return json.load(handle)


def main() -> None:
    with open(ROOT / "dataset-sintetico/resultados/probe_t1.json", encoding="utf-8") as handle:
        probe = json.load(handle)

    synthetic_labels = {
        row["id"]: row["label"]
        for row in probe
        if row.get("set") == "sintetico" and row.get("label") in ("Yes", "No")
    }
    mergedataset_labels = {
        row["id"]: row["label"]
        for row in probe
        if row.get("set") == "mergedataset" and row.get("label") in ("Yes", "No")
    }

    synthetic_manifest = latest_manifest(
        "SMAT/output-test-dest/scenarios/input-smat-sintetico_*/manifest.json"
    )
    synthetic: list[dict[str, str]] = []
    for scenario in synthetic_manifest.get("scenarios", []):
        case = (scenario.get("scenario_commits") or {}).get("merge", "")
        label = synthetic_labels.get(case)
        if label is None:
            continue
        for class_name, methods in (scenario.get("targets") or {}).items():
            for method in methods or []:
                synthetic.append(
                    {
                        "scenario": case,
                        "class": simple_class(class_name),
                        "method": norm_method((method or {}).get("method")),
                        "label": label,
                    }
                )

    merge_manifest = latest_manifest(
        "SMAT/output-test-dest/scenarios/input-smat-mergedataset_*/manifest.json"
    )
    merge_targets: dict[tuple[str, str], tuple[str, str, str]] = {}
    for scenario in merge_manifest.get("scenarios", []):
        for class_name, methods in (scenario.get("targets") or {}).items():
            for method in methods or []:
                name = norm_method((method or {}).get("method"))
                merge_targets[(simple_class(class_name), name)] = (
                    scenario.get("project", ""),
                    simple_class(class_name),
                    name,
                )

    mergedataset: list[dict[str, str]] = []
    for identifier, label in mergedataset_labels.items():
        tail = identifier.split("/", 1)[1] if "/" in identifier else identifier
        class_name, method = (tail.split(".", 1) + [""])[:2]
        key = (class_name.strip(), norm_method(method))
        project, simple, method_name = merge_targets.get(
            key, ("", key[0], key[1])
        )
        mergedataset.append(
            {
                "project": project,
                "class": simple,
                "method": method_name,
                "label": label,
            }
        )

    full: dict[tuple[str, str, str], str] = {}
    csv_path = ROOT / "mergedataset-full/semantic-conflicts/sample-semantic-conflicts.csv"
    with open(csv_path, newline="", encoding="utf-8-sig") as handle:
        for raw in csv.DictReader(handle):
            row = {(key or "").strip(): (value or "").strip() for key, value in raw.items()}
            label = row.get("Locally Observable Interference", "")
            if label not in ("Yes", "No"):
                continue
            project = row.get("Project", "").rstrip("/").split("/")[-1]
            class_name = simple_class(row.get("Class"))
            method = norm_method(row.get("Declaration"))
            if not project or not class_name or not method:
                continue
            full[(project, class_name, method)] = label

    payload = {
        "meta": {
            "generatedBy": "scripts/export_viewer_ground_truth.py",
            "note": "Labels are positive for interference (Yes) and negative for no interference (No).",
        },
        "sintetico": sorted(synthetic, key=lambda row: (row["scenario"], row["class"], row["method"])),
        "mergedataset": sorted(mergedataset, key=lambda row: (row["project"], row["class"], row["method"])),
        "mergedataset-full": [
            {
                "project": project,
                "class": class_name,
                "method": method,
                "label": label,
            }
            for (project, class_name, method), label in sorted(full.items())
        ],
    }

    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps(payload, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    print(
        f"wrote {OUT}: {len(payload['sintetico'])} synthetic, "
        f"{len(payload['mergedataset'])} mergedataset, "
        f"{len(payload['mergedataset-full'])} mergedataset-full labels"
    )


if __name__ == "__main__":
    main()
