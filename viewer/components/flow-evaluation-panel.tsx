import { Badge } from "@/components/ui";
import {
  accuracyTone,
  formatAccuracy,
  formatNumber,
  groundTruthLabel,
} from "@/lib/format";
import type {
  FlowEvaluationSummary,
  FlowRecordEvaluation,
  LayaRecord,
} from "@/lib/types";

function simpleClassName(value?: string | null): string {
  if (!value) return "—";
  return (value.split(".").pop() ?? value).replace(/\$.*$/, "");
}

function methodName(record: LayaRecord): string {
  return record.methodSignature || record.method || "—";
}

function recordTitle(record: LayaRecord): string {
  return record.evaluation?.scenario || record.project || "—";
}

function MethodRow({ record }: { record: LayaRecord }) {
  const evaluation = record.evaluation as FlowRecordEvaluation;
  const status = evaluation.correct
    ? "Acertou"
    : evaluation.predicted
      ? "Errou"
      : "Sem predição";

  return (
    <li className="rounded-xl border border-zinc-200 bg-zinc-50 p-3">
      <div className="flex items-start justify-between gap-3">
        <div className="min-w-0">
          <p className="truncate text-xs font-medium text-zinc-900">
            {recordTitle(record)}
          </p>
          <p className="mt-0.5 break-all font-mono text-[10px] leading-4 text-zinc-500">
            {simpleClassName(record.className)}.{methodName(record).replace(/\(.*$/, "")}
          </p>
        </div>
        <Badge tone={evaluation.correct ? "emerald" : "rose"}>{status}</Badge>
      </div>
      <div className="mt-2 flex flex-wrap gap-x-3 gap-y-1 text-[10px] text-zinc-600">
        <span>
          esperado:{" "}
          <span className="font-medium text-zinc-800">
            {groundTruthLabel(evaluation.expected)}
          </span>
        </span>
        <span>
          previsto:{" "}
          <span className="font-medium text-zinc-800">
            {groundTruthLabel(evaluation.predicted)}
          </span>
        </span>
      </div>
    </li>
  );
}

function MethodList({
  title,
  records,
  tone,
}: {
  title: string;
  records: LayaRecord[];
  tone: "emerald" | "rose";
}) {
  return (
    <div className="rounded-2xl border border-zinc-200 bg-white p-4">
      <div className="flex items-center justify-between gap-3">
        <h3 className="text-sm font-semibold text-zinc-900">{title}</h3>
        <Badge tone={records.length ? tone : "slate"}>
          {formatNumber(records.length)}
        </Badge>
      </div>
      {records.length ? (
        <ul className="mt-3 max-h-[24rem] space-y-2 overflow-auto pr-1">
          {records.map((record, index) => (
            <MethodRow
              key={`${record.className}-${record.method}-${index}`}
              record={record}
            />
          ))}
        </ul>
      ) : (
        <p className="mt-3 text-xs text-zinc-500">Nenhum método nesta lista.</p>
      )}
    </div>
  );
}

export function FlowEvaluationPanel({
  records,
  evaluation,
  flowLabel,
}: {
  records: LayaRecord[];
  evaluation: FlowEvaluationSummary;
  flowLabel: string;
}) {
  const correct = records.filter((record) => record.evaluation?.correct);
  const incorrect = records.filter(
    (record) => record.evaluation && !record.evaluation.correct,
  );

  if (!evaluation.labeled) {
    return (
      <div className="rounded-2xl border border-dashed border-zinc-300 bg-white p-6 text-sm leading-6 text-zinc-600">
        Sem rótulos de referência para esta execução do fluxo {flowLabel}.
        A acurácia só é calculada para execuções dos datasets rotulados.
      </div>
    );
  }

  return (
    <div className="space-y-4">
      <div className="flex flex-wrap items-center gap-3 rounded-2xl border border-zinc-200 bg-white p-5">
        <Badge tone={accuracyTone(evaluation.accuracy)}>
          Acurácia {formatAccuracy(evaluation.accuracy)}
        </Badge>
        <span className="text-sm text-zinc-700">
          {formatNumber(evaluation.correct)} de{" "}
          {formatNumber(evaluation.labeled)} métodos rotulados
        </span>
        {evaluation.dataset ? (
          <Badge tone="slate">{evaluation.dataset}</Badge>
        ) : null}
        <span className="text-xs text-zinc-500">
          Comparação com o rótulo de referência do dataset.
        </span>
      </div>

      <div className="grid gap-4 lg:grid-cols-2">
        <MethodList title="Métodos em que acertou" records={correct} tone="emerald" />
        <MethodList title="Métodos em que errou" records={incorrect} tone="rose" />
      </div>
    </div>
  );
}
