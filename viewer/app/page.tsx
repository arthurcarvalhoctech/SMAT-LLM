import Link from "next/link";

import { ExecutionList } from "@/components/execution-list";
import { LayaLogList } from "@/components/laya-log-list";
import { LayaRunList } from "@/components/laya-run-list";
import { ReportList } from "@/components/report-list";
import { Badge, EmptyState, SectionHeading, StatCard } from "@/components/ui";
import { formatNumber } from "@/lib/format";
import {
  getOutputRoot,
  listExecutionRuns,
  listLayaLogs,
  listLayaRuns,
  listReports,
} from "@/lib/smat-data";

export const dynamic = "force-dynamic";

export default async function HomePage() {
  const [executions, layaRuns, layaLogs, reports] = await Promise.all([
    listExecutionRuns(),
    listLayaRuns(),
    listLayaLogs(),
    listReports(),
  ]);

  const totalScenarios = executions.reduce(
    (total, execution) => total + execution.scenarioCount,
    0,
  );
  const totalMissing = executions.reduce(
    (total, execution) => total + execution.missingSourceCount,
    0,
  );
  const outputRoot = getOutputRoot();

  return (
    <div className="space-y-14">
      <section className="hero-gradient relative overflow-hidden rounded-[2rem] border border-white/10 p-8 shadow-glow sm:p-12">
        <div className="relative z-10 max-w-3xl">
          <Badge tone="indigo">SMAT-LLM · observabilidade</Badge>
          <h1 className="mt-5 text-4xl font-semibold tracking-tight text-white sm:text-6xl">
            Scenario Explorer
          </h1>
          <p className="mt-4 max-w-2xl text-base leading-7 text-slate-300">
            Explore as execuções de merge, compare as versões{" "}
            <span className="font-mono text-slate-200">
              base / left / right / merge
            </span>{" "}
            e navegue pelos artefatos produzidos pelo SMAT e pelo Laya.
          </p>
          <div className="mt-7 flex flex-wrap gap-3">
            <Link
              href="/executions"
              className="rounded-xl bg-indigo-500 px-4 py-2.5 text-sm font-medium text-white transition hover:bg-indigo-400"
            >
              Ver execuções
            </Link>
            <Link
              href="/files"
              className="rounded-xl border border-white/15 bg-white/[0.03] px-4 py-2.5 text-sm font-medium text-slate-200 transition hover:border-white/30 hover:bg-white/[0.06]"
            >
              Navegar arquivos
            </Link>
          </div>
        </div>
        <div className="pointer-events-none absolute -right-20 -top-20 h-64 w-64 rounded-full bg-indigo-500/20 blur-3xl" />
        <div className="pointer-events-none absolute -bottom-24 right-24 h-52 w-52 rounded-full bg-cyan-400/10 blur-3xl" />
      </section>

      <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-4">
        <StatCard
          label="Execuções"
          value={formatNumber(executions.length)}
          hint="snapshots de cenários"
        />
        <StatCard
          label="Cenários"
          value={formatNumber(totalScenarios)}
          hint="pastas de merge"
          tone="cyan"
        />
        <StatCard
          label="Classificações Laya"
          value={formatNumber(layaRuns.length)}
          hint="execuções de pré-análise"
          tone="emerald"
        />
        <StatCard
          label="Fontes ausentes"
          value={formatNumber(totalMissing)}
          hint="nos manifestos"
          tone={totalMissing ? "amber" : "slate"}
        />
      </div>

      <section id="execucoes">
        <SectionHeading
          eyebrow="Snapshots"
          title="Execuções disponíveis"
          description={`Lendo ${outputRoot}. Cada execução contém uma pasta por cenário com os arquivos base, left, right e merge.`}
          action={
            <Link
              href="/executions"
              className="text-xs font-medium text-indigo-300 transition hover:text-indigo-200"
            >
              Ver todas →
            </Link>
          }
        />
        {executions.length ? (
          <ExecutionList executions={executions.slice(0, 6)} />
        ) : (
          <EmptyState
            title="Nenhuma execução encontrada"
            description={`Não há snapshots em ${outputRoot}/scenarios. Execute o SMAT (./start.sh) com pelo menos um fluxo habilitado para gerar a estrutura de cenários.`}
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

      <section>
        <SectionHeading
          eyebrow="Análise"
          title="Laya"
          description="Classificações de interferência e logs da pré-análise."
          action={
            <Link
              href="/laya"
              className="text-xs font-medium text-indigo-300 transition hover:text-indigo-200"
            >
              Ver tudo →
            </Link>
          }
        />
        {layaRuns.length ? (
          <LayaRunList runs={layaRuns.slice(0, 4)} />
        ) : (
          <div className="rounded-2xl border border-zinc-200 bg-white p-5 text-sm leading-6 text-zinc-600">
            Nenhuma classificação encontrada em{" "}
            <span className="font-mono text-zinc-500">
              reports/laya/classification
            </span>
            .
          </div>
        )}

        <div className="mt-6">
          <div className="mb-3 flex items-center justify-between gap-3">
            <h3 className="text-sm font-semibold text-zinc-900">
              Logs recentes
            </h3>
            <Badge tone="slate">{formatNumber(layaLogs.length)}</Badge>
          </div>
          {layaLogs.length ? (
            <LayaLogList logs={layaLogs.slice(0, 4)} />
          ) : (
            <p className="text-sm leading-6 text-zinc-500">
              Nenhum log encontrado em{" "}
              <span className="font-mono text-zinc-500">reports/laya</span>.
            </p>
          )}
        </div>
      </section>

      <section>
        <SectionHeading
          eyebrow="Artefatos"
          title="Relatórios"
          description="JSONs de conflitos semânticos, mudanças de comportamento, suítes e compilação."
          action={
            <Link
              href="/reports"
              className="text-xs font-medium text-indigo-300 transition hover:text-indigo-200"
            >
              Abrir relatórios →
            </Link>
          }
        />
        {reports.length ? (
          <ReportList reports={reports.slice(0, 6)} />
        ) : (
          <div className="rounded-2xl border border-zinc-200 bg-white p-5 text-sm leading-6 text-zinc-600">
            Nenhum JSON de relatório encontrado em{" "}
            <span className="font-mono text-zinc-500">reports</span>.
          </div>
        )}
      </section>
    </div>
  );
}
