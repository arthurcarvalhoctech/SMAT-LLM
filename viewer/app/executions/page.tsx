import Link from "next/link";

import { ExecutionList } from "@/components/execution-list";
import { Badge, EmptyState, SectionHeading, StatCard } from "@/components/ui";
import { formatNumber } from "@/lib/format";
import { getOutputRoot, listExecutionRuns } from "@/lib/smat-data";

export const dynamic = "force-dynamic";

export default async function ExecutionsPage() {
  const executions = await listExecutionRuns();
  const outputRoot = getOutputRoot();
  const totalScenarios = executions.reduce(
    (total, execution) => total + execution.scenarioCount,
    0,
  );
  const totalMissing = executions.reduce(
    (total, execution) => total + execution.missingSourceCount,
    0,
  );

  return (
    <div className="space-y-8">
      <section className="hero-gradient relative overflow-hidden rounded-[2rem] border border-white/10 p-6 shadow-glow sm:p-8">
        <div className="relative z-10">
          <Badge tone="indigo">Snapshots de merge</Badge>
          <h1 className="mt-4 text-3xl font-semibold tracking-tight text-white sm:text-4xl">
            Execuções
          </h1>
          <p className="mt-3 max-w-3xl text-sm leading-6 text-slate-400">
            Cada linha representa uma execução com uma pasta por cenário de
            merge. Clique em uma execução para abrir o detalhamento e comparar
            os fontes de base, left, right e merge.
          </p>
          <p className="mt-3 break-all font-mono text-[11px] text-slate-500">
            origem: {outputRoot}/scenarios
          </p>
          <div className="mt-5 flex flex-wrap gap-3">
            <Link
              href="/"
              className="rounded-xl border border-white/10 bg-white/[0.03] px-3.5 py-2 text-xs font-medium text-slate-300 transition hover:border-white/20 hover:text-white"
            >
              ← Dashboard
            </Link>
            <Link
              href="/files"
              className="rounded-xl border border-white/10 bg-white/[0.03] px-3.5 py-2 text-xs font-medium text-slate-300 transition hover:border-white/20 hover:text-white"
            >
              Navegar arquivos
            </Link>
          </div>
        </div>
      </section>

      <div className="grid gap-4 sm:grid-cols-3">
        <StatCard
          label="Execuções"
          value={formatNumber(executions.length)}
          hint="snapshots disponíveis"
        />
        <StatCard
          label="Cenários"
          value={formatNumber(totalScenarios)}
          hint="pastas de merge"
          tone="cyan"
        />
        <StatCard
          label="Fontes ausentes"
          value={formatNumber(totalMissing)}
          hint="nos manifestos"
          tone={totalMissing ? "amber" : "emerald"}
        />
      </div>

      <section>
        <SectionHeading
          eyebrow="Lista"
          title="Execuções disponíveis"
          description="Clique em uma linha para ver os cenários, os targets e os fontes das quatro versões."
          action={
            <Link
              href="/files"
              className="text-xs font-medium text-indigo-300 transition hover:text-indigo-200"
            >
              Explorar diretório →
            </Link>
          }
        />
        {executions.length ? (
          <ExecutionList executions={executions} />
        ) : (
          <EmptyState
            title="Nenhuma execução encontrada"
            description={`Não há snapshots em ${outputRoot}/scenarios. Execute o SMAT com pelo menos um fluxo habilitado para gerar a estrutura de cenários.`}
          >
            <Link
              href="/files"
              className="inline-flex rounded-xl border border-white/15 px-4 py-2 text-sm text-slate-200 transition hover:border-white/30"
            >
              Abrir navegador de arquivos
            </Link>
          </EmptyState>
        )}
      </section>
    </div>
  );
}
