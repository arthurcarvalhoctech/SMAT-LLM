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

export function LlmScenarioBadges({
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
        title={`${summary.recordCount} registro(s) LLM; ${summary.errorCount} com erro`}
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

export function LlmScenarioPanel({
  summary,
}: {
  summary: LayaScenarioSummary;
}) {
  if (summary.status === "no_data" || summary.recordCount === 0) {
    return (
      <div className="rounded-2xl border border-dashed border-zinc-300 bg-white p-6 text-sm leading-6 text-zinc-600">
        Nenhum registro LLM encontrado para este cenário. Verifique se{" "}
        <span className="font-mono text-zinc-500">
          SMAT_LLM_INTERFERENCE_DETECTION
        </span>{" "}
        está habilitado e se há logs em{" "}
        <span className="font-mono text-zinc-500">
          reports/llm_interference
        </span>
        .
      </div>
    );
  }

  const criteria = new Set(summary.criteria);
  const summaryText = summary.records.find((record) => record.summary)?.summary;
  const reasoning = summary.records.find(
    (record) => record.reasoning,
  )?.reasoning;

  return (
    <div className="space-y-4">
      <div className="rounded-2xl border border-zinc-200 bg-white p-5">
        <div className="flex flex-wrap items-center gap-2">
          <Badge tone={layaStatusTone(summary.status)}>
            {layaStatusLabel(summary.status)}
          </Badge>
          <span className="text-xs text-zinc-600">
            {summary.recordCount} registro(s) LLM
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

        {summaryText ? (
          <p className="mt-4 rounded-xl border border-zinc-200 bg-zinc-50 p-3 text-xs leading-5 text-zinc-700">
            {summaryText}
          </p>
        ) : null}

        {reasoning ? (
          <details className="mt-3 rounded-xl border border-zinc-200 bg-zinc-50 p-3">
            <summary className="cursor-pointer text-xs font-medium text-zinc-700">
              Raciocínio do modelo
            </summary>
            <p className="mt-2 whitespace-pre-wrap text-xs leading-5 text-zinc-600">
              {reasoning}
            </p>
          </details>
        ) : null}

        {summary.status === "error" && summary.criteria.length === 0 ? (
          <p className="mt-3 text-[11px] leading-5 text-red-700">
            A chamada ao LLM falhou para este cenário; os critérios não foram
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
          Registros LLM do cenário
        </h3>
        <LayaTable records={summary.records} />
      </div>
    </div>
  );
}
