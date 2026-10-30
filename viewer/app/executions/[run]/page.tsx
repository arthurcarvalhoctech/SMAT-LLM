import Link from "next/link";
import { notFound } from "next/navigation";

import { JsonViewer } from "@/components/json-viewer";
import { ScenarioList } from "@/components/scenario-list";
import {
  Badge,
  Breadcrumbs,
  EmptyState,
  SectionHeading,
  StatCard,
} from "@/components/ui";
import { formatDate, formatNumber } from "@/lib/format";
import {
  getExecution,
  getLayaSummariesForScenarios,
  getLlmSummariesForScenarios,
} from "@/lib/smat-data";

export const dynamic = "force-dynamic";

type ExecutionPageProps = {
  params: Promise<{ run: string }>;
};

export default async function ExecutionPage({ params }: ExecutionPageProps) {
  const { run } = await params;
  const execution = await getExecution(run);

  if (!execution) notFound();

  const missingSources = execution.scenarios.reduce(
    (total, scenario) => total + scenario.missingSources.length,
    0,
  );
  const executionRunId = execution.summary.runId || execution.summary.id;
  const [layaSummaries, llmSummaries] = await Promise.all([
    getLayaSummariesForScenarios(execution.scenarios, executionRunId),
    getLlmSummariesForScenarios(execution.scenarios, executionRunId),
  ]);

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
          eyebrow="Cenários"
          title="Versões do merge"
          description="Clique em uma linha para comparar os fontes de base, left, right e merge."
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
