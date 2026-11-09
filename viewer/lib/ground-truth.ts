import groundTruthJson from "@/data/ground-truth.json";

import type {
  FlowEvaluationSummary,
  FlowRecordEvaluation,
  GroundTruthDataset,
  GroundTruthLabel,
  LayaRecord,
} from "./types";

interface GroundTruthEntry {
  scenario?: string;
  project?: string;
  class: string;
  method: string;
  label: GroundTruthLabel;
}

interface GroundTruthFile {
  sintetico: GroundTruthEntry[];
  mergedataset: GroundTruthEntry[];
  "mergedataset-full": GroundTruthEntry[];
}

const groundTruth = groundTruthJson as GroundTruthFile;

const DATASETS: GroundTruthDataset[] = [
  "sintetico",
  "mergedataset",
  "mergedataset-full",
];

function simpleClassName(value?: string | null): string {
  if (!value) return "";
  return (value.split(".").pop() ?? value).replace(/\$.*$/, "");
}

function simpleMethodName(value?: string | null): string {
  return (value ?? "").replace(/\(.*$/, "").trim();
}

function datasetKey(value?: string | null): GroundTruthDataset | null {
  const normalized = (value ?? "").toLowerCase();
  if (normalized.includes("mergedataset-full")) return "mergedataset-full";
  if (normalized.includes("sintetico")) return "sintetico";
  if (normalized.includes("mergedataset")) return "mergedataset";
  return null;
}

function entryKey(dataset: GroundTruthDataset, entry: GroundTruthEntry): string {
  if (dataset === "sintetico") {
    return `${simpleClassName(entry.class)}|${simpleMethodName(entry.method)}`;
  }
  return `${(entry.project ?? "").toLowerCase()}|${simpleClassName(entry.class)}|${simpleMethodName(entry.method)}`;
}

function recordKey(dataset: GroundTruthDataset, record: LayaRecord): string {
  if (dataset === "sintetico") {
    return `${simpleClassName(record.className)}|${simpleMethodName(record.method || record.methodSignature)}`;
  }
  return `${(record.project ?? "").toLowerCase()}|${simpleClassName(record.className)}|${simpleMethodName(record.method || record.methodSignature)}`;
}

const indexes = new Map<GroundTruthDataset, Map<string, GroundTruthEntry>>();
const totals = new Map<GroundTruthDataset, number>();

for (const dataset of DATASETS) {
  const entries = groundTruth[dataset] ?? [];
  const index = new Map<string, GroundTruthEntry>();
  for (const entry of entries) {
    if (entry.label === "Yes" || entry.label === "No") {
      index.set(entryKey(dataset, entry), entry);
    }
  }
  indexes.set(dataset, index);
  totals.set(dataset, entries.length);
}

function inferDataset(records: LayaRecord[]): GroundTruthDataset | null {
  if (records.length === 0) return null;

  const projects = new Set(
    records
      .map((record) => (record.project ?? "").toLowerCase())
      .filter(Boolean),
  );

  if (projects.size === 1 && projects.has("sintetico")) return "sintetico";
  if (records.length > 30 || projects.size > 3) return "mergedataset-full";
  return "mergedataset";
}

function predictedLabel(classification?: string | null): GroundTruthLabel | null {
  switch (classification) {
    case "interference":
    case "possible_interference":
      return "Yes";
    case "no_interference":
    case "no_signal":
      return "No";
    default:
      return null;
  }
}

export function evaluateFlowRecords(
  records: LayaRecord[],
  datasetHint?: string | null,
): { records: LayaRecord[]; summary: FlowEvaluationSummary } {
  const dataset = datasetKey(datasetHint) ?? inferDataset(records);
  if (!dataset) {
    return {
      records,
      summary: { dataset: null, labeled: 0, correct: 0, accuracy: null },
    };
  }

  const index = indexes.get(dataset);
  const seen = new Set<string>();
  const uniqueRecords = records.filter((record) => {
    const key = recordKey(dataset, record);
    if (seen.has(key)) return false;
    seen.add(key);
    return true;
  });

  const evaluated = uniqueRecords.map((record) => {
    const entry = index?.get(recordKey(dataset, record));
    if (!entry) return record;

    const predicted = predictedLabel(record.classification);
    const evaluation: FlowRecordEvaluation = {
      dataset,
      expected: entry.label,
      predicted,
      correct: predicted === entry.label,
      scenario: entry.scenario,
    };

    return { ...record, evaluation };
  });

  const withLabels = evaluated.filter(
    (record): record is LayaRecord & { evaluation: FlowRecordEvaluation } =>
      Boolean(record.evaluation),
  );
  const correct = withLabels.filter(
    (record) => record.evaluation.correct,
  ).length;

  return {
    records: evaluated,
    summary: {
      dataset,
      labeled: withLabels.length,
      correct,
      accuracy: withLabels.length ? correct / withLabels.length : null,
    },
  };
}

export function groundTruthTotal(dataset: GroundTruthDataset | null): number {
  return dataset ? totals.get(dataset) ?? 0 : 0;
}
