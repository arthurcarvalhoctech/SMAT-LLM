import { Badge } from "@/components/ui";
import {
  classificationLabel,
  classificationTone,
  formatProbability,
  groundTruthLabel,
} from "@/lib/format";
import type { LayaRecord } from "@/lib/types";

const criterionShort: Record<string, string> = {
  criterion_1_global_divergence: "C1",
  criterion_2_parent_change_loss: "C2",
  criterion_3_merge_new_effect: "C3",
};

export function LayaTable({ records }: { records: LayaRecord[] }) {
  if (records.length === 0) {
    return (
      <div className="rounded-2xl border border-white/10 bg-white/[0.02] p-6 text-sm text-slate-400">
        Nenhuma classificação encontrada nesta execução.
      </div>
    );
  }

  const showEvaluation = records.some((record) => record.evaluation);

  return (
    <div className="overflow-x-auto rounded-2xl border border-white/10">
      <table className="min-w-[1200px] w-full table-fixed border-collapse text-left text-xs">
        <colgroup>
          <col style={{ width: "240px" }} />
          <col style={{ width: "260px" }} />
          <col style={{ width: "130px" }} />
          {showEvaluation ? <col style={{ width: "150px" }} /> : null}
          <col style={{ width: "90px" }} />
          <col style={{ width: "100px" }} />
          <col style={{ width: "120px" }} />
          <col style={{ width: "80px" }} />
        </colgroup>
        <thead className="bg-white/[0.04] text-[10px] uppercase tracking-[0.16em] text-slate-500">
          <tr>
            <th className="px-4 py-3 font-medium">Projeto / classe</th>
            <th className="px-4 py-3 font-medium">Método</th>
            <th className="px-4 py-3 font-medium">Classificação</th>
            {showEvaluation ? (
              <th className="px-4 py-3 font-medium">Avaliação</th>
            ) : null}
            <th className="px-4 py-3 font-medium">Critérios</th>
            <th className="px-4 py-3 font-medium">Prob.</th>
            <th className="px-4 py-3 font-medium">Primário</th>
            <th className="px-4 py-3 font-medium">Confiança</th>
          </tr>
        </thead>
        <tbody className="divide-y divide-white/5">
          {records.map((record, index) => (
            <tr
              key={`${record.className}-${record.method}-${index}`}
              className="align-top transition hover:bg-white/[0.02]"
            >
              <td className="px-4 py-3">
                <p className="font-medium text-slate-200">{record.project}</p>
                <p className="mt-0.5 break-all font-mono text-[11px] text-slate-500">
                  {record.className}
                </p>
                {record.evaluation?.scenario ? (
                  <p className="mt-1 font-mono text-[10px] text-slate-500">
                    {record.evaluation.scenario}
                  </p>
                ) : null}
              </td>
              <td className="break-all px-4 py-3 font-mono text-[11px] text-slate-300">
                {record.methodSignature || record.method || "—"}
              </td>
              <td className="px-4 py-3">
                <Badge tone={classificationTone(record.classification)}>
                  {classificationLabel(record.classification)}
                </Badge>
                {record.error ? (
                  <p className="mt-1 max-w-[220px] break-words text-[10px] text-rose-300">
                    {record.error}
                  </p>
                ) : null}
              </td>
              {showEvaluation ? (
                <td className="px-4 py-3">
                  {record.evaluation ? (
                    <div className="space-y-1">
                      <Badge
                        tone={
                          record.evaluation.correct ? "emerald" : "rose"
                        }
                      >
                        {record.evaluation.correct
                          ? "Acertou"
                          : record.evaluation.predicted
                            ? "Errou"
                            : "Sem predição"}
                      </Badge>
                      <p className="text-[10px] text-slate-500">
                        esperado: {groundTruthLabel(record.evaluation.expected)}
                      </p>
                      <p className="text-[10px] text-slate-500">
                        previsto: {groundTruthLabel(record.evaluation.predicted)}
                      </p>
                    </div>
                  ) : (
                    <span className="text-slate-600">—</span>
                  )}
                </td>
              ) : null}
              <td className="px-4 py-3">
                {record.triggeredCriteria.length ? (
                  <div className="flex flex-wrap gap-1">
                    {record.triggeredCriteria.map((criterion) => (
                      <span
                        key={criterion}
                        title={criterion}
                        className="rounded border border-indigo-400/20 bg-indigo-400/10 px-1.5 py-0.5 font-mono text-[10px] text-indigo-200"
                      >
                        {criterionShort[criterion] ?? criterion}
                      </span>
                    ))}
                  </div>
                ) : (
                  <span className="text-slate-600">—</span>
                )}
              </td>
              <td className="px-4 py-3">
                <div className="space-y-1">
                  {Object.entries(record.probabilities)
                    .sort(([a], [b]) => a.localeCompare(b))
                    .map(([criterion, probability]) => (
                      <div
                        key={criterion}
                        className="flex items-center justify-between gap-3 font-mono text-[10px] text-slate-400"
                      >
                        <span title={criterion}>
                          {criterionShort[criterion] ?? criterion}
                        </span>
                        <span className="text-slate-200">
                          {formatProbability(probability)}
                        </span>
                      </div>
                    ))}
                  {Object.keys(record.probabilities).length === 0 ? (
                    <span className="text-slate-600">—</span>
                  ) : null}
                </div>
              </td>
              <td className="px-4 py-3">
                <p
                  className="font-mono text-[10px] text-slate-300"
                  title={record.primaryCriterion ?? undefined}
                >
                  {record.primaryCriterion
                    ? criterionShort[record.primaryCriterion] ??
                      record.primaryCriterion
                    : "—"}
                </p>
                <p className="mt-0.5 text-[10px] text-slate-500">
                  branch: {record.affectedBranch || "—"}
                </p>
              </td>
              <td className="px-4 py-3 text-[11px] text-slate-400">
                {record.confidence || "—"}
              </td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}
