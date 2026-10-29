import { promises as fs } from "node:fs";
import type { Dirent, Stats } from "node:fs";
import path from "node:path";

import type {
  BranchView,
  ExecutionDetail,
  ExecutionSummary,
  FileEntry,
  FilePreview,
  LayaLogFile,
  LayaRecord,
  LayaRunDetail,
  LayaRunSummary,
  LayaScenarioSummary,
  ReportSummary,
  ScenarioDetail,
  ScenarioSummary,
  SourceSection,
} from "./types";
import { BRANCH_KEYS, BRANCH_LABELS } from "./types";
import { normalizeTargets } from "./targets";

const DEFAULT_OUTPUT_DIR = path.resolve(
  process.cwd(),
  "..",
  "SMAT",
  "output-test-dest",
);

export function getOutputRoot(): string {
  return path.resolve(
    /* turbopackIgnore: true */
    process.env.SMAT_OUTPUT_DIR || DEFAULT_OUTPUT_DIR,
  );
}

interface ManifestScenario {
  index?: number;
  folder?: string;
  project?: string;
  run_analysis?: boolean;
  jar_type?: string;
  scenario_commits?: Record<string, string>;
  scenario_jars?: Record<string, string>;
  targets?: Record<string, unknown>;
  missing_sources?: string[] | null;
  files?: Record<string, string>;
}

interface Manifest {
  dataset?: string;
  run_id?: string;
  generated_at?: string;
  input_path?: string;
  root?: string;
  scenarios?: ManifestScenario[];
}

interface LayaCriterionJson {
  number?: number;
  title?: string;
  probability?: number | null;
  threshold?: number;
  triggered?: boolean;
}

interface LayaJson {
  run_id?: string;
  runId?: string;
  timestamp?: string;
  project?: string;
  class?: string;
  className?: string;
  method?: string;
  method_signature?: string;
  methodSignature?: string;
  jar_type?: string;
  jarType?: string;
  model?: string;
  max_len?: number;
  maxLen?: number;
  threshold?: number;
  classification?: string;
  triggered_criteria?: string[];
  triggeredCriteria?: string[];
  primary_criterion?: string | null;
  primaryCriterion?: string | null;
  affected_branch?: string | null;
  affectedBranch?: string | null;
  confidence?: string | null;
  confidence_label?: string | null;
  confidence_score?: number | null;
  probabilities?: Record<string, number | null>;
  criteria?: Record<string, LayaCriterionJson>;
  error?: string | null;
  note?: string | null;
}

async function readJson<T>(file: string): Promise<T | null> {
  try {
    return JSON.parse(await fs.readFile(file, "utf8")) as T;
  } catch {
    return null;
  }
}

async function listDir(dir: string): Promise<Dirent[]> {
  try {
    return await fs.readdir(dir, { withFileTypes: true });
  } catch {
    return [];
  }
}

async function statSafe(file: string): Promise<Stats | null> {
  try {
    return await fs.stat(file);
  } catch {
    return null;
  }
}

async function exists(file: string): Promise<boolean> {
  return (await statSafe(file)) !== null;
}

export function encodeSegments(...parts: string[]): string {
  return parts.map((part) => encodeURIComponent(part)).join("/");
}

export function safeResolve(...segments: string[]): string {
  for (const segment of segments) {
    if (
      !segment ||
      segment === "." ||
      segment === ".." ||
      segment.includes("/") ||
      segment.includes("\\") ||
      segment.includes("\0")
    ) {
      throw new Error("Invalid path segment");
    }
  }
  const root = getOutputRoot();
  const resolved = path.resolve(root, ...segments);
  const relative = path.relative(root, resolved);
  if (relative.startsWith("..") || path.isAbsolute(relative)) {
    throw new Error("Path escapes the output directory");
  }
  return resolved;
}

function parseRunName(id: string): { dataset: string; timestamp: string } {
  const match = id.match(/^(.*)_(\d{8}_\d{6}_\d{6})$/);
  if (!match) return { dataset: id, timestamp: "" };
  return { dataset: match[1] || "dataset", timestamp: match[2] };
}

async function buildExecutionSummary(
  id: string,
  dir: string,
  manifest: Manifest | null,
  scenarioCount: number,
): Promise<ExecutionSummary> {
  const parsed = parseRunName(id);
  const dirStat = await statSafe(dir);
  const scenarios = manifest?.scenarios ?? [];
  const missingSourceCount = scenarios.reduce(
    (total, scenario) =>
      total +
      (Array.isArray(scenario.missing_sources)
        ? scenario.missing_sources.length
        : 0),
    0,
  );

  return {
    id,
    dataset: manifest?.dataset || parsed.dataset,
    runId: manifest?.run_id || parsed.timestamp,
    createdAt: manifest?.generated_at || dirStat?.mtime.toISOString() || "",
    scenarioCount,
    missingSourceCount,
    hasManifest: Boolean(manifest),
    inputPath: manifest?.input_path,
  };
}

function scenarioFromManifest(
  raw: ManifestScenario | undefined,
  folder: string,
): ScenarioSummary {
  const indexMatch = folder.match(/^(\d+)/);
  return {
    folder,
    index: raw?.index ?? (indexMatch ? Number(indexMatch[1]) : 0),
    project: raw?.project || folder.replace(/^\d+_/, ""),
    runAnalysis: raw?.run_analysis ?? true,
    jarType: raw?.jar_type || "",
    targets: raw?.targets || {},
    missingSources: Array.isArray(raw?.missing_sources)
      ? raw.missing_sources
      : [],
    scenarioCommits: raw?.scenario_commits || {},
    scenarioJars: raw?.scenario_jars || {},
  };
}

export async function listExecutionRuns(): Promise<ExecutionSummary[]> {
  const root = path.join(getOutputRoot(), "scenarios");
  const entries = (await listDir(root)).filter((entry) => entry.isDirectory());

  const summaries = await Promise.all(
    entries.map(async (entry) => {
      const dir = path.join(root, entry.name);
      const manifest = await readJson<Manifest>(path.join(dir, "manifest.json"));
      const scenarioDirs = (await listDir(dir)).filter((item) =>
        item.isDirectory(),
      ).length;
      return buildExecutionSummary(
        entry.name,
        dir,
        manifest,
        manifest?.scenarios?.length ?? scenarioDirs,
      );
    }),
  );

  return summaries.sort(
    (a, b) =>
      b.createdAt.localeCompare(a.createdAt) || b.id.localeCompare(a.id),
  );
}

export async function getExecution(
  id: string,
): Promise<ExecutionDetail | null> {
  let dir: string;
  try {
    dir = safeResolve("scenarios", id);
  } catch {
    return null;
  }

  const dirStat = await statSafe(dir);
  if (!dirStat?.isDirectory()) return null;

  const manifest = await readJson<Manifest>(path.join(dir, "manifest.json"));
  const scenarioDirs = (await listDir(dir))
    .filter((entry) => entry.isDirectory())
    .map((entry) => entry.name)
    .sort();
  const manifestScenarios = manifest?.scenarios ?? [];
  const byFolder = new Map<string, ManifestScenario>();

  for (const raw of manifestScenarios) {
    const folder =
      raw.folder ||
      `${String(raw.index ?? 0).padStart(3, "0")}_${raw.project ?? "scenario"}`;
    byFolder.set(folder, raw);
  }

  const folders = Array.from(
    new Set([
      ...scenarioDirs,
      ...manifestScenarios.map(
        (raw) =>
          raw.folder ||
          `${String(raw.index ?? 0).padStart(3, "0")}_${raw.project ?? "scenario"}`,
      ),
    ]),
  );

  const scenarios = folders
    .map((folder) => scenarioFromManifest(byFolder.get(folder), folder))
    .sort((a, b) => a.index - b.index || a.folder.localeCompare(b.folder));

  return {
    summary: await buildExecutionSummary(id, dir, manifest, scenarios.length),
    scenarios,
    inputPath: manifest?.input_path,
    root: manifest?.root,
    rawManifest: manifest ?? undefined,
  };
}

function parseSections(content: string): SourceSection[] {
  const sections: SourceSection[] = [];
  let current: SourceSection | null = null;
  let code: string[] = [];

  function flush() {
    if (current) {
      current.code = code.join("\n").replace(/\s+$/, "");
      sections.push(current);
    }
    current = null;
    code = [];
  }

  for (const line of content.split("\n")) {
    if (line.startsWith("// target classes: ")) {
      flush();
      current = {
        classes: line
          .slice("// target classes: ".length)
          .split(",")
          .map((item) => item.trim())
          .filter(Boolean),
        sourcePath: "",
        code: "",
      };
      continue;
    }
    if (current && line.startsWith("// source: ")) {
      current.sourcePath = line.slice("// source: ".length).trim();
      continue;
    }
    if (
      line.startsWith(
        "// ----------------------------------------------------------------------------",
      )
    ) {
      continue;
    }
    if (line.startsWith("// Missing sources:")) {
      flush();
      continue;
    }
    if (current) code.push(line);
  }

  flush();
  return sections;
}

export async function getScenario(
  runId: string,
  folder: string,
): Promise<ScenarioDetail | null> {
  const execution = await getExecution(runId);
  if (!execution) return null;

  const scenario = execution.scenarios.find((item) => item.folder === folder);
  if (!scenario) return null;

  let scenarioDir: string;
  try {
    scenarioDir = safeResolve("scenarios", runId, folder);
  } catch {
    return null;
  }

  const branches: BranchView[] = await Promise.all(
    BRANCH_KEYS.map(async (key) => {
      const file = path.join(scenarioDir, key);
      const stat = await statSafe(file);
      const downloadPath = `/api/file/${encodeSegments(
        "scenarios",
        runId,
        folder,
        key,
      )}`;

      if (!stat?.isFile()) {
        return {
          key,
          label: BRANCH_LABELS[key],
          content: "",
          lines: 0,
          bytes: 0,
          missing: true,
          sections: [],
          downloadPath,
        };
      }

      const content = (await fs.readFile(file, "utf8")).replace(/\r\n/g, "\n");
      const sections = parseSections(content);
      return {
        key,
        label: BRANCH_LABELS[key],
        content,
        lines: content.split("\n").length,
        bytes: stat.size,
        missing:
          sections.length === 0 ||
          content.includes("No source files found for branch"),
        sections,
        downloadPath,
      };
    }),
  );

  return {
    summary: scenario,
    branches,
    runId: execution.summary.runId || runId,
    dataset: execution.summary.dataset,
  };
}

function toLayaRecord(raw: LayaJson): LayaRecord {
  const triggeredCriteria =
    raw.triggered_criteria ?? raw.triggeredCriteria ?? [];
  const probabilities: Record<string, number> = {};

  for (const [criterion, value] of Object.entries(raw.criteria ?? {})) {
    if (typeof value.probability === "number") {
      probabilities[criterion] = value.probability;
    }
  }

  for (const [criterion, value] of Object.entries(raw.probabilities ?? {})) {
    if (typeof value === "number") {
      probabilities[criterion] = value;
    }
  }

  const classification =
    raw.classification ??
    (raw.error
      ? "error"
      : triggeredCriteria.length > 0
        ? "interference"
        : Object.keys(probabilities).length > 0 || raw.criteria
          ? "no_interference"
          : undefined);

  const confidence =
    raw.confidence ??
    raw.confidence_label ??
    (raw.confidence_score != null ? String(raw.confidence_score) : null);

  return {
    runId: raw.run_id ?? raw.runId,
    timestamp: raw.timestamp,
    project: raw.project,
    className: raw.class ?? raw.className,
    method: raw.method,
    methodSignature: raw.method_signature ?? raw.methodSignature,
    jarType: raw.jar_type ?? raw.jarType,
    model: raw.model,
    maxLen: raw.max_len ?? raw.maxLen,
    threshold: raw.threshold,
    classification,
    triggeredCriteria,
    primaryCriterion:
      raw.primary_criterion ?? raw.primaryCriterion ?? null,
    affectedBranch:
      raw.affected_branch ?? raw.affectedBranch ?? null,
    confidence,
    probabilities,
    error: raw.error ?? null,
    note: raw.note ?? null,
  };
}

async function buildLayaSummary(
  id: string,
  dir: string,
  records: LayaRecord[],
  fileCount: number,
): Promise<LayaRunSummary> {
  const dirStat = await statSafe(dir);
  const timestamps = records
    .map((record) => record.timestamp)
    .filter((value): value is string => Boolean(value))
    .sort();
  return {
    id,
    runId:
      records.find((record) => record.runId)?.runId ||
      id.replace(/^run_/, ""),
    fileCount,
    interference: records.filter(
      (record) => record.classification === "interference",
    ).length,
    noInterference: records.filter(
      (record) => record.classification === "no_interference",
    ).length,
    errors: records.filter(
      (record) => record.classification === "error" || record.error,
    ).length,
    createdAt:
      timestamps[timestamps.length - 1] ||
      dirStat?.mtime.toISOString() ||
      "",
  };
}

export async function listLayaRuns(): Promise<LayaRunSummary[]> {
  const root = path.join(getOutputRoot(), "reports", "laya", "classification");
  const entries = (await listDir(root)).filter(
    (entry) => entry.isDirectory() && entry.name.startsWith("run_"),
  );

  const runs = await Promise.all(
    entries.map(async (entry) => {
      const dir = path.join(root, entry.name);
      const files = (await listDir(dir))
        .filter((item) => item.isFile() && item.name.endsWith(".json"))
        .map((item) => item.name);
      const records = (
        await Promise.all(
          files.map((file) => readJson<LayaJson>(path.join(dir, file))),
        )
      )
        .filter((record): record is LayaJson => Boolean(record))
        .map(toLayaRecord);
      return buildLayaSummary(entry.name, dir, records, files.length);
    }),
  );

  return runs.sort(
    (a, b) =>
      b.createdAt.localeCompare(a.createdAt) || b.id.localeCompare(a.id),
  );
}

export async function getLayaRun(
  id: string,
): Promise<LayaRunDetail | null> {
  let dir: string;
  try {
    dir = safeResolve("reports", "laya", "classification", id);
  } catch {
    return null;
  }

  const stat = await statSafe(dir);
  if (!stat?.isDirectory()) return null;

  const files = (await listDir(dir))
    .filter((entry) => entry.isFile() && entry.name.endsWith(".json"))
    .map((entry) => entry.name);
  const records = (
    await Promise.all(
      files.map((file) => readJson<LayaJson>(path.join(dir, file))),
    )
  )
    .filter((record): record is LayaJson => Boolean(record))
    .map(toLayaRecord);

  const summary = await buildLayaSummary(id, dir, records, files.length);
  const logFile = `laya_interference_${summary.runId}.log`;
  const jsonlFile = `laya_interference_${summary.runId}.jsonl`;
  const logPath = path.join(getOutputRoot(), "reports", "laya", logFile);
  const jsonlPath = path.join(getOutputRoot(), "reports", "laya", jsonlFile);

  return {
    summary,
    records,
    logFile: (await exists(logPath)) ? logFile : undefined,
    jsonlFile: (await exists(jsonlPath)) ? jsonlFile : undefined,
  };
}

export async function listLayaLogs(): Promise<LayaLogFile[]> {
  const root = path.join(getOutputRoot(), "reports", "laya");
  const entries = (await listDir(root)).filter(
    (entry) =>
      entry.isFile() &&
      (entry.name.endsWith(".log") || entry.name.endsWith(".jsonl")),
  );

  const files = await Promise.all(
    entries.map(async (entry) => {
      const stat = await statSafe(path.join(root, entry.name));
      return {
        name: entry.name,
        kind: entry.name.endsWith(".jsonl")
          ? ("jsonl" as const)
          : ("log" as const),
        bytes: stat?.size ?? 0,
        modified: stat?.mtime.toISOString() ?? "",
      };
    }),
  );

  return files.sort((a, b) => b.modified.localeCompare(a.modified));
}

async function readJsonl(file: string): Promise<LayaJson[]> {
  try {
    const text = await fs.readFile(file, "utf8");
    const runId = path
      .basename(file)
      .replace(/^laya_interference_/, "")
      .replace(/\.jsonl$/, "");

    return text.split(/\r?\n/).flatMap((line) => {
      if (!line.trim()) return [];
      try {
        const raw = JSON.parse(line) as LayaJson;
        return [{ ...raw, run_id: raw.run_id ?? raw.runId ?? runId }];
      } catch {
        return [];
      }
    });
  } catch {
    return [];
  }
}

async function loadAllLayaRecords(): Promise<LayaRecord[]> {
  const root = path.join(getOutputRoot(), "reports", "laya");
  const records: LayaRecord[] = [];
  const classificationRoot = path.join(root, "classification");

  const runDirs = (await listDir(classificationRoot)).filter(
    (entry) => entry.isDirectory() && entry.name.startsWith("run_"),
  );

  for (const runDir of runDirs) {
    const dir = path.join(classificationRoot, runDir.name);
    const files = (await listDir(dir)).filter(
      (entry) => entry.isFile() && entry.name.endsWith(".json"),
    );
    const parsed = await Promise.all(
      files.map((file) => readJson<LayaJson>(path.join(dir, file.name))),
    );
    for (const raw of parsed) {
      if (raw) records.push(toLayaRecord(raw));
    }
  }

  const logFiles = (await listDir(root)).filter(
    (entry) => entry.isFile() && entry.name.endsWith(".jsonl"),
  );

  for (const logFile of logFiles) {
    const parsed = await readJsonl(path.join(root, logFile.name));
    for (const raw of parsed) records.push(toLayaRecord(raw));
  }

  const seen = new Set<string>();
  return records.filter((record) => {
    const key = [
      record.runId ?? "",
      record.timestamp ?? "",
      record.project ?? "",
      record.className ?? "",
      record.method ?? "",
      record.methodSignature ?? "",
    ].join("|");

    if (seen.has(key)) return false;
    seen.add(key);
    return true;
  });
}

function simpleClassName(value?: string | null): string {
  if (!value) return "";
  return (value.split(".").pop() ?? value).replace(/\$.*$/, "");
}

function simpleMethodName(value?: string | null): string {
  return (value ?? "").replace(/\(.*$/, "").trim();
}

function matchesScenario(
  record: LayaRecord,
  scenario: ScenarioSummary,
): boolean {
  const targets = normalizeTargets(scenario.targets);
  const recordClass = simpleClassName(record.className);
  const recordMethod = simpleMethodName(
    record.method || record.methodSignature,
  );
  const projectMatches =
    !record.project ||
    !scenario.project ||
    record.project.toLowerCase() === scenario.project.toLowerCase();

  const classMatches =
    Boolean(recordClass) &&
    targets.some(
      (target) => simpleClassName(target.className) === recordClass,
    );

  const methodMatches =
    Boolean(recordMethod) &&
    targets.some((target) =>
      target.methods.some(
        (method) => simpleMethodName(method.name) === recordMethod,
      ),
    );

  if (classMatches) return true;
  if (methodMatches) return projectMatches;
  if (targets.length === 0) return projectMatches;
  return false;
}

function summarizeLayaRecords(
  records: LayaRecord[],
): LayaScenarioSummary {
  const interference = records.some(
    (record) => record.classification === "interference",
  );
  const noInterference = records.some(
    (record) => record.classification === "no_interference",
  );
  const errorRecords = records.filter(
    (record) => record.classification === "error" || record.error,
  );

  const criteriaSet = new Set<string>();
  const primarySet = new Set<string>();

  for (const record of records) {
    if (record.classification === "error" || record.error) continue;

    for (const criterion of record.triggeredCriteria) {
      criteriaSet.add(criterion);
    }

    if (record.primaryCriterion && record.primaryCriterion !== "none") {
      criteriaSet.add(record.primaryCriterion);
      primarySet.add(record.primaryCriterion);
    }
  }

  const runIds = Array.from(
    new Set(
      records
        .map((record) => record.runId)
        .filter((value): value is string => Boolean(value)),
    ),
  );

  const confidence =
    records.find((record) => record.confidence)?.confidence ?? null;

  return {
    status: interference
      ? "interference"
      : noInterference
        ? "no_interference"
        : errorRecords.length > 0
          ? "error"
          : "no_data",
    criteria: Array.from(criteriaSet),
    primaryCriteria: Array.from(primarySet),
    records,
    recordCount: records.length,
    errorCount: errorRecords.length,
    runIds,
    confidence,
  };
}

export async function getLayaSummariesForScenarios(
  scenarios: ScenarioSummary[],
): Promise<Record<string, LayaScenarioSummary>> {
  const records = await loadAllLayaRecords();
  const summaries: Record<string, LayaScenarioSummary> = {};

  for (const scenario of scenarios) {
    const matched = records.filter((record) =>
      matchesScenario(record, scenario),
    );
    summaries[scenario.folder] = summarizeLayaRecords(matched);
  }

  return summaries;
}

export async function getLayaSummaryForScenario(
  scenario: ScenarioSummary,
): Promise<LayaScenarioSummary> {
  const records = await loadAllLayaRecords();
  return summarizeLayaRecords(
    records.filter((record) => matchesScenario(record, scenario)),
  );
}

export async function listReports(): Promise<ReportSummary[]> {
  const root = path.join(getOutputRoot(), "reports");
  const entries = (await listDir(root)).filter(
    (entry) => entry.isFile() && entry.name.endsWith(".json"),
  );

  const reports = await Promise.all(
    entries.map(async (entry) => {
      const stat = await statSafe(path.join(root, entry.name));
      return {
        name: entry.name,
        bytes: stat?.size ?? 0,
        modified: stat?.mtime.toISOString() ?? "",
      };
    }),
  );

  return reports.sort((a, b) => b.modified.localeCompare(a.modified));
}

export async function getReport(name: string): Promise<{
  name: string;
  bytes: number;
  modified: string;
  data: unknown;
} | null> {
  if (!name.endsWith(".json")) return null;

  let file: string;
  try {
    file = safeResolve("reports", name);
  } catch {
    return null;
  }

  const stat = await statSafe(file);
  if (!stat?.isFile()) return null;

  return {
    name,
    bytes: stat.size,
    modified: stat.mtime.toISOString(),
    data: await readJson<unknown>(file),
  };
}

export async function listFiles(
  segments: string[],
): Promise<FilePreview | null> {
  let target: string;
  try {
    target = segments.length ? safeResolve(...segments) : getOutputRoot();
  } catch {
    return null;
  }

  const stat = await statSafe(target);
  if (!stat) return null;

  const relative = path
    .relative(getOutputRoot(), target)
    .split(path.sep)
    .filter(Boolean);

  if (stat.isDirectory()) {
    const entries: FileEntry[] = await Promise.all(
      (await listDir(target)).map(async (entry) => {
        const entryStat = await statSafe(path.join(target, entry.name));
        return {
          name: entry.name,
          path: [...relative, entry.name].join("/"),
          kind: entry.isDirectory()
            ? ("directory" as const)
            : ("file" as const),
          bytes: entryStat?.size ?? 0,
          modified: entryStat?.mtime.toISOString() ?? "",
        };
      }),
    );

    entries.sort((a, b) =>
      a.kind === b.kind
        ? a.name.localeCompare(b.name)
        : a.kind === "directory"
          ? -1
          : 1,
    );

    return {
      path: relative.join("/"),
      name: relative.length ? relative[relative.length - 1] : "output-test-dest",
      isDirectory: true,
      entries,
      bytes: 0,
      modified: stat.mtime.toISOString(),
      contentType: "",
    };
  }

  const extension = path.extname(target).toLowerCase();
  const textExtensions = new Set([
    "",
    ".csv",
    ".java",
    ".json",
    ".jsonl",
    ".log",
    ".md",
    ".properties",
    ".py",
    ".sh",
    ".ts",
    ".tsx",
    ".txt",
    ".xml",
    ".yaml",
    ".yml",
  ]);
  const isText = textExtensions.has(extension);
  let text: string | undefined;
  let truncated = false;

  if (isText) {
    const buffer = await fs.readFile(target);
    const preview = buffer.subarray(0, 200_000);
    text = preview.toString("utf8");
    truncated = buffer.length > preview.length;
  }

  return {
    path: relative.join("/"),
    name: path.basename(target),
    isDirectory: false,
    text,
    truncated,
    bytes: stat.size,
    modified: stat.mtime.toISOString(),
    contentType:
      extension === ".json"
        ? "application/json; charset=utf-8"
        : isText
          ? "text/plain; charset=utf-8"
          : "application/octet-stream",
  };
}
