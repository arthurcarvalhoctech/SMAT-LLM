import { LayaTable } from "@/components/laya-table";
import { Badge } from "@/components/ui";
import {
  LAYA_CRITERIA,
  criterionLabel,
  criterionShort,
  layaStatusLabel,
  layaStatusShort,
  layaStatusTone,
} from "@/lib/laya";
import type { LayaScenarioSummary } from "@/lib/types";

export function LayaScenarioBadges({
  summary,
}: {
  summary?: LayaScenarioSummary;
}) {
  if (!summary || summary.recordCount === 0 || summary.status === "no_data") {
    return <span className="text-xs text-zinc-500">—</span>;
  }

  return (
    <div className="flex flex-wrap items-center gap-1">
      <span
        title={`${summary.recordCount} registro(s) Laya; ${summary.errorCount} com erro`}
      >
        <Badge tone={layaStatusTone(summary.status)}>
          {layaStatusShort(summary.status)}
        </Badge>
      </span>
      {summary.criteria.map((criterion) => (
        <span
          key={criterion}
          title={criterionLabel(criterion)}
          className="rounded border border-zinc-300 bg-zinc-100 px-1.5 py-0.5 font-mono text-[10px] text-zinc-700"
        >
          {criterionShort(criterion)}
        </span>
      ))}
    </div>
  );
}

export function LayaScenarioPanel({
  summary,
}: {
  summary: LayaScenarioSummary;
}) {
  if (summary.status === "no_data" || summary.recordCount === 0) {
    return (
      <div className="rounded-2xl border border-dashed border-zinc-300 bg-white p-6 text-sm leading-6 text-zinc-600">
        Nenhum registro Laya encontrado para este cenário. Verifique se o
        fluxo Laya foi habilitado e se há logs em{" "}
        <span className="font-mono text-zinc-500">reports/laya</span>.
      </div>
    );
  }

  const criteria = new Set(summary.criteria);

  return (
    <div className="space-y-4">
      <div className="rounded-2xl border border-zinc-200 bg-white p-5">
        <div className="flex flex-wrap items-center gap-2">
          <Badge tone={layaStatusTone(summary.status)}>
            {layaStatusLabel(summary.status)}
          </Badge>
          <span className="text-xs text-zinc-600">
            {summary.recordCount} registro(s) Laya
          </span>
          {summary.errorCount ? (
            <span className="text-xs text-red-700">
              {summary.errorCount} com erro
            </span>
          ) : null}
          {summary.runIds.length ? (
            <span className="font-mono text-[10px] text-zinc-500">
              runs: {summary.runIds.join(", ")}
            </span>
          ) : null}
        </div>

        <div className="mt-4 grid gap-2 sm:grid-cols-3">
          {LAYA_CRITERIA.map((criterion) => {
            const triggered = criteria.has(criterion.id);
            return (
              <div
                key={criterion.id}
                className={`rounded-xl border p-3 ${
                  triggered
                    ? "border-red-200 bg-red-50"
                    : "border-zinc-200 bg-zinc-50"
                }`}
              >
                <div className="flex items-center justify-between gap-2">
                  <span
                    className={`font-mono text-xs ${
                      triggered ? "text-red-700" : "text-zinc-500"
                    }`}
                  >
                    {criterion.short}
                  </span>
                  <Badge tone={triggered ? "rose" : "slate"}>
                    {triggered ? "acionado" : "não acionado"}
                  </Badge>
                </div>
                <p
                  className={`mt-2 text-xs ${
                    triggered ? "text-red-800" : "text-zinc-600"
                  }`}
                >
                  {criterion.label}
                </p>
              </div>
            );
          })}
        </div>

        {summary.status === "error" && summary.criteria.length === 0 ? (
          <p className="mt-3 text-[11px] leading-5 text-red-700">
            A análise Laya falhou para este cenário; os critérios não foram
            avaliados.
          </p>
        ) : null}

        {summary.confidence ? (
          <p className="mt-3 text-[11px] text-zinc-500">
            Confiança informada: {summary.confidence}
          </p>
        ) : null}
      </div>

      <div>
        <h3 className="mb-2 text-sm font-semibold text-zinc-900">
          Registros Laya do cenário
        </h3>
        <LayaTable records={summary.records} />
      </div>
    </div>
  );
}
