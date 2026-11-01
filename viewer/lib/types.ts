export type BranchKey = "base" | "left" | "right" | "merge";

export const BRANCH_KEYS: readonly BranchKey[] = [
  "base",
  "left",
  "right",
  "merge",
];

export const BRANCH_LABELS: Record<BranchKey, string> = {
  base: "Base",
  left: "Left",
  right: "Right",
  merge: "Merge",
};

export interface SourceSection {
  classes: string[];
  sourcePath: string;
  code: string;
}

export interface BranchView {
  key: BranchKey;
  label: string;
  content: string;
  lines: number;
  bytes: number;
  missing: boolean;
  sections: SourceSection[];
  downloadPath: string;
}

export interface ScenarioSummary {
  folder: string;
  index: number;
  project: string;
  runAnalysis: boolean;
  jarType: string;
  targets: Record<string, unknown>;
  missingSources: string[];
  scenarioCommits: Record<string, string>;
  scenarioJars: Record<string, string>;
}

export interface ExecutionSummary {
  id: string;
  dataset: string;
  runId: string;
  createdAt: string;
  scenarioCount: number;
  missingSourceCount: number;
  hasManifest: boolean;
  inputPath?: string;
}

export interface ExecutionDetail {
  summary: ExecutionSummary;
  scenarios: ScenarioSummary[];
  inputPath?: string;
  root?: string;
  rawManifest?: unknown;
}

export interface ScenarioDetail {
  summary: ScenarioSummary;
  branches: BranchView[];
  runId: string;
  dataset: string;
}

export interface TargetMethod {
  name: string;
  leftSummary?: string;
  rightSummary?: string;
}

export interface TargetClass {
  className: string;
  methods: TargetMethod[];
}

export interface LayaRecord {
  runId?: string;
  timestamp?: string;
  project?: string;
  className?: string;
  method?: string;
  methodSignature?: string;
  jarType?: string;
  model?: string;
  maxLen?: number;
  threshold?: number;
  stateFormat?: string;
  decisionRule?: string;
  criterionThresholds?: number[];
  witness?: string | null;
  witnessTwoStage?: boolean;
  allowBaselineWithWitness?: boolean;
  negativeInstructions?: boolean;
  diagnosticQuestions?: boolean;
  classification?: string;
  triggeredCriteria: string[];
  primaryCriterion?: string | null;
  affectedBranch?: string | null;
  confidence?: string | null;
  probabilities: Record<string, number>;
  evidence?: Record<string, string>;
  summary?: string;
  reasoning?: string;
  provider?: string;
  primaryModel?: string;
  fallbackModel?: string;
  maxOutputTokens?: number;
  jsonMode?: boolean;
  retryOnLength?: boolean;
  attempts?: Array<{
    attempt?: number;
    model?: string;
    maxOutputTokens?: number;
    finishReason?: string;
  }>;
  error?: string | null;
  note?: string | null;
}

export type LayaScenarioStatus =
  | "interference"
  | "possible_interference"
  | "no_interference"
  | "uncertain"
  | "no_signal"
  | "error"
  | "no_data";

export interface LayaScenarioSummary {
  status: LayaScenarioStatus;
  criteria: string[];
  primaryCriteria: string[];
  records: LayaRecord[];
  recordCount: number;
  errorCount: number;
  runIds: string[];
  confidence?: string | null;
}

export interface LayaRunSummary {
  id: string;
  runId: string;
  fileCount: number;
  interference: number;
  noInterference: number;
  errors: number;
  createdAt: string;
}

export interface LayaRunDetail {
  summary: LayaRunSummary;
  records: LayaRecord[];
  logFile?: string;
  jsonlFile?: string;
}

export interface LayaLogFile {
  name: string;
  kind: "log" | "jsonl";
  bytes: number;
  modified: string;
}

export interface ReportSummary {
  name: string;
  bytes: number;
  modified: string;
}

export interface FileEntry {
  name: string;
  path: string;
  kind: "directory" | "file";
  bytes: number;
  modified: string;
}

export interface FilePreview {
  path: string;
  name: string;
  isDirectory: boolean;
  entries?: FileEntry[];
  text?: string;
  truncated?: boolean;
  bytes: number;
  modified: string;
  contentType: string;
}
