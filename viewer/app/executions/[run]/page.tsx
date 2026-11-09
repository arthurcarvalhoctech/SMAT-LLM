import Link from "next/link";
import { notFound } from "next/navigation";

import { FlowRunGroup } from "@/components/flow-run-group";
import { JsonViewer } from "@/components/json-viewer";
import { ScenarioList } from "@/components/scenario-list";
import {
  Badge,
  Breadcrumbs,
  EmptyState,
  SectionHeading,
  StatCard,
} from "@/components/ui";
import { formatDate, formatAccuracy, formatNumber } from "@/lib/format";
import {
  getExecution,
  getFlowRunsForExecution,
  getLayaSummariesForScenarios,
  getLlmSummariesForScenarios,
} from "@/lib/smat-data";
import type { LayaScenarioSummary } from "@/lib/types";

export const dynamic = "force-dynamic";

type ExecutionPageProps = {
  params: Promise<{ run: string }>;
};

type FlowStats = {
  accuracy: number | null;
  correct: number;
  labeled: number;
  scenariosCorrect: number;
  scenariosLabeled: number;
};

function summarizeFlow(
  summaries: Record<string, LayaScenarioSummary>,
): FlowStats {
  const evaluated = Object.values(summaries).filter(
    (summary) => summary.evaluation.labeled > 0,
  );
  const correct = evaluated.reduce(
    (total, summary) => total + summary.evaluation.correct,
    0,
  );
  const labeled = evaluated.reduce(
    (total, summary) => total + summary.evaluation.labeled,
    0,
  );

  return {
    accuracy: labeled ? correct / labeled : null,
    correct,
    labeled,
    scenariosCorrect: evaluated.filter(
      (summary) =>
        summary.evaluation.correct === summary.evaluation.labeled,
    ).length,
    scenariosLabeled: evaluated.length,
  };
}

function FlowAccuracyStat({
  label,
  stats,
}: {
  label: string;
  stats: FlowStats;
}) {
  return (
    <div className="rounded-2xl border border-white/10 bg-white/[0.04] p-4">
      <p className="text-[10px] font-medium uppercase tracking-[0.18em] text-slate-500">
        Acurácia {label}
      </p>
      <p className="mt-1 text-3xl font-semibold tracking-tight text-white sm:text-4xl">
        {formatAccuracy(stats.accuracy)}
      </p>
      <p className="mt-2 text-base text-slate-200">
        {formatNumber(stats.correct)}/{formatNumber(stats.labeled)} métodos
      </p>
      <p className="mt-0.5 text-sm text-slate-400">
        {formatNumber(stats.scenariosCorrect)}/
        {formatNumber(stats.scenariosLabeled)} cenários com 100% de acerto
      </p>
    </div>
  );
}

export default async function ExecutionPage({ params }: ExecutionPageProps) {
  const { run } = await params;
  const execution = await getExecution(run);

  if (!execution) notFound();

  const missingSources = execution.scenarios.reduce(
    (total, scenario) => total + scenario.missingSources.length,
    0,
  );
  const executionRunId = execution.summary.runId || execution.summary.id;
  const [layaSummaries, llmSummaries, flowRuns] = await Promise.all([
    getLayaSummariesForScenarios(
      execution.scenarios,
      executionRunId,
      execution.summary.dataset,
    ),
    getLlmSummariesForScenarios(
      execution.scenarios,
      executionRunId,
      execution.summary.dataset,
    ),
    getFlowRunsForExecution(executionRunId),
  ]);
  const layaStats = summarizeFlow(layaSummaries);
  const llmStats = summarizeFlow(llmSummaries);

  return (
    <div className="space-y-8">
      <Breadcrumbs
        items={[
          { href: "/executions", label: "Execuções" },
          { label: execution.summary.dataset },
        ]}
      />

      <section className="panel-gradient rounded-3xl border border-white/10 p-6 sm:p-8">
        <div className="flex flex-wrap items-center gap-2">
          <Badge tone="indigo">{execution.summary.dataset}</Badge>
          <Badge tone={execution.summary.hasManifest ? "emerald" : "amber"}>
            {execution.summary.hasManifest ? "manifest" : "sem manifest"}
          </Badge>
          {missingSources ? (
            <Badge tone="amber">{missingSources} fonte(s) ausente(s)</Badge>
          ) : (
            <Badge tone="emerald">cenários completos</Badge>
          )}
        </div>
        <h1 className="mt-4 break-all font-mono text-2xl font-semibold tracking-tight text-white sm:text-3xl">
          {execution.summary.runId || execution.summary.id}
        </h1>
        <p className="mt-2 text-sm text-slate-400">
          {formatDate(execution.summary.createdAt)} ·{" "}
          {formatNumber(execution.scenarios.length)} cenário(s)
        </p>
        {execution.inputPath ? (
          <p className="mt-4 break-all rounded-xl border border-white/5 bg-slate-950/50 p-3 font-mono text-[11px] text-slate-500">
            input: {execution.inputPath}
          </p>
        ) : null}
        <div className="mt-5 grid gap-3 sm:grid-cols-2">
          <FlowAccuracyStat label="Laya" stats={layaStats} />
          <FlowAccuracyStat label="LLM" stats={llmStats} />
        </div>
        <div className="mt-5 flex flex-wrap gap-3">
          <Link
            href="/executions"
            className="rounded-xl border border-white/10 bg-white/[0.03] px-3.5 py-2 text-xs font-medium text-slate-300 transition hover:border-white/20 hover:text-white"
          >
            ← Voltar às execuções
          </Link>
          <Link
            href={`/files/scenarios/${encodeURIComponent(execution.summary.id)}`}
            className="rounded-xl border border-white/10 bg-white/[0.03] px-3.5 py-2 text-xs font-medium text-slate-300 transition hover:border-white/20 hover:text-white"
          >
            Abrir no navegador de arquivos
          </Link>
        </div>
      </section>

      <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-4">
        <StatCard
          label="Cenários"
          value={formatNumber(execution.scenarios.length)}
          hint="pastas de merge"
        />
        <StatCard
          label="Fontes ausentes"
          value={formatNumber(missingSources)}
          hint="registradas no manifesto"
          tone={missingSources ? "amber" : "emerald"}
        />
        <StatCard
          label="Input"
          value={execution.inputPath ? "disponível" : "—"}
          hint="arquivo de origem"
          tone="cyan"
        />
        <StatCard
          label="Manifesto"
          value={execution.summary.hasManifest ? "sim" : "não"}
          hint="metadados completos"
          tone={execution.summary.hasManifest ? "emerald" : "slate"}
        />
      </div>

      <section>
        <SectionHeading
          eyebrow="Fluxos"
          title="Execuções de classificação"
          description="Laya e LLM executados nesta janela. Cada execução mostra sua acurácia contra os rótulos de referência."
        />
        <div className="grid gap-4 lg:grid-cols-2">
          <FlowRunGroup
            title="Laya"
            runs={flowRuns.laya}
            basePath="/laya"
            emptyText="Nenhuma execução do fluxo Laya foi encontrada nesta janela."
          />
          <FlowRunGroup
            title="LLM"
            runs={flowRuns.llm}
            basePath="/llm"
            emptyText="Nenhuma execução do fluxo LLM foi encontrada nesta janela."
          />
        </div>
      </section>

      <section>
        <SectionHeading
          eyebrow="Cenários"
          title="Versões do merge"
          description="Clique em uma linha para comparar os fontes de base, left, right e merge. Bolas verdes indicam métodos avaliados com acerto; vermelhas, com erro."
        />
        {execution.scenarios.length ? (
          <ScenarioList
            executionId={execution.summary.id}
            scenarios={execution.scenarios}
            layaSummaries={layaSummaries}
            llmSummaries={llmSummaries}
          />
        ) : (
          <EmptyState
            title="Nenhum cenário nesta execução"
            description="O manifesto não contém cenários e não há pastas de cenário no diretório."
          />
        )}
      </section>

      {execution.rawManifest ? (
        <details className="rounded-2xl border border-white/10 bg-white/[0.02] p-4">
          <summary className="cursor-pointer text-sm font-medium text-slate-300">
            Manifesto bruto
          </summary>
          <div className="mt-4">
            <JsonViewer data={execution.rawManifest} />
          </div>
        </details>
      ) : null}
    </div>
  );
}
