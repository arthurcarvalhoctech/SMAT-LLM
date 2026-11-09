import { LayaLogList } from "@/components/laya-log-list";
import { LayaRunList } from "@/components/laya-run-list";
import { Badge, EmptyState, SectionHeading, StatCard } from "@/components/ui";
import { accuracyTone, formatAccuracy, formatNumber } from "@/lib/format";
import {
  getOutputRoot,
  listLlmLogs,
  listLlmRuns,
} from "@/lib/smat-data";

export const dynamic = "force-dynamic";

export default async function LlmPage() {
  const [runs, logs] = await Promise.all([listLlmRuns(), listLlmLogs()]);
  const outputRoot = getOutputRoot();
  const interference = runs.reduce((total, run) => total + run.interference, 0);
  const errors = runs.reduce((total, run) => total + run.errors, 0);
  const labeled = runs.reduce(
    (total, run) => total + run.evaluation.labeled,
    0,
  );
  const correct = runs.reduce(
    (total, run) => total + run.evaluation.correct,
    0,
  );
  const accuracy = labeled ? correct / labeled : null;

  return (
    <div className="space-y-10">
      <section className="panel-gradient rounded-3xl border border-white/10 p-6 sm:p-8">
        <Badge tone="indigo">LLM</Badge>
        <h1 className="mt-4 text-3xl font-semibold tracking-tight text-white sm:text-4xl">
          Classificações LLM
        </h1>
        <p className="mt-3 max-w-3xl text-sm leading-6 text-slate-400">
          Hipóteses produzidas pelo fluxo de pré-análise com LLM para os três
          critérios do artigo. A acurácia é comparada com os rótulos de
          referência dos datasets.
        </p>
      </section>

      <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-5">
        <StatCard
          label="Execuções LLM"
          value={formatNumber(runs.length)}
          hint="pastas classification/run_*"
        />
        <StatCard
          label="Interferências"
          value={formatNumber(interference)}
          hint="classificadas como interference"
          tone="rose"
        />
        <StatCard
          label="Acurácia média"
          value={formatAccuracy(accuracy)}
          hint={`${formatNumber(correct)}/${formatNumber(labeled)} métodos rotulados`}
          tone={accuracyTone(accuracy)}
        />
        <StatCard
          label="Erros"
          value={formatNumber(errors)}
          hint="registros com error"
          tone={errors ? "amber" : "slate"}
        />
        <StatCard
          label="Logs"
          value={formatNumber(logs.length)}
          hint=".log e .jsonl"
          tone="cyan"
        />
      </div>

      <section>
        <SectionHeading
          eyebrow="Classificações"
          title="Execuções de pré-análise LLM"
          description={`Classificações em ${outputRoot}/reports/llm_interference/classification.`}
        />
        {runs.length ? (
          <LayaRunList runs={runs} basePath="/llm" />
        ) : (
          <EmptyState
            title="Nenhuma classificação LLM"
            description={`Não há pastas run_* em ${outputRoot}/reports/llm_interference/classification. Habilite o fluxo LLM e execute o SMAT para gerar as classificações.`}
          />
        )}
      </section>

      <section>
        <SectionHeading
          eyebrow="Logs"
          title="Logs legíveis e JSONL"
          description="Arquivos brutos produzidos pela pré-análise LLM."
        />
        {logs.length ? (
          <LayaLogList
            logs={logs}
            basePath="reports/llm_interference"
          />
        ) : (
          <EmptyState
            title="Nenhum log LLM"
            description={`Não há arquivos .log ou .jsonl em ${outputRoot}/reports/llm_interference.`}
          />
        )}
      </section>
    </div>
  );
}
