import { Badge } from "@/components/ui";
import {
  classificationLabel,
  classificationTone,
  formatProbability,
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

  return (
    <div className="overflow-x-auto rounded-2xl border border-white/10">
      <table className="min-w-[1050px] w-full border-collapse text-left text-xs">
        <thead className="bg-white/[0.04] text-[10px] uppercase tracking-[0.16em] text-slate-500">
          <tr>
            <th className="px-4 py-3 font-medium">Projeto / classe</th>
            <th className="px-4 py-3 font-medium">Método</th>
            <th className="px-4 py-3 font-medium">Classificação</th>
            <th className="px-4 py-3 font-medium">Critérios acionados</th>
            <th className="px-4 py-3 font-medium">Probabilidades</th>
            <th className="px-4 py-3 font-medium">Primário / branch</th>
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
              </td>
              <td className="px-4 py-3 font-mono text-[11px] text-slate-300">
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
                <p className="font-mono text-[10px] text-slate-300">
                  {record.primaryCriterion || "—"}
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
