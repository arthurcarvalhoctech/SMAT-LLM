import Link from "next/link";
import { notFound } from "next/navigation";

import { LayaScenarioPanel } from "@/components/laya-scenario-summary";
import { ScenarioSourceExplorer } from "@/components/scenario-source-explorer";
import {
  Badge,
  Breadcrumbs,
  EmptyState,
  SectionHeading,
  StatCard,
} from "@/components/ui";
import { formatNumber } from "@/lib/format";
import { getLayaSummaryForScenario, getScenario } from "@/lib/smat-data";
import { normalizeTargets } from "@/lib/targets";

export const dynamic = "force-dynamic";

type ScenarioPageProps = {
  params: Promise<{ run: string; scenario: string }>;
};

export default async function ScenarioPage({ params }: ScenarioPageProps) {
  const { run, scenario: scenarioFolder } = await params;
  const detail = await getScenario(run, scenarioFolder);

  if (!detail) notFound();

  const layaSummary = await getLayaSummaryForScenario(detail.summary);
  const targets = normalizeTargets(detail.summary.targets);
  const methodCount = targets.reduce(
    (total, target) => total + target.methods.length,
    0,
  );

  return (
    <div className="space-y-8">
      <Breadcrumbs
        items={[
          { href: "/executions", label: "Execuções" },
          {
            href: `/executions/${encodeURIComponent(run)}`,
            label: detail.dataset,
          },
          { label: detail.summary.project },
        ]}
      />

      <section className="panel-gradient rounded-3xl border border-white/10 p-6 sm:p-8">
        <div className="flex flex-wrap items-center gap-2">
          <Badge tone="cyan">{detail.dataset}</Badge>
          <Badge tone="slate">cenário {String(detail.summary.index).padStart(3, "0")}</Badge>
          {detail.summary.jarType ? (
            <Badge tone="indigo">{detail.summary.jarType}</Badge>
          ) : null}
          {detail.summary.runAnalysis ? (
            <Badge tone="emerald">analisado</Badge>
          ) : (
            <Badge tone="slate">ignorado</Badge>
          )}
        </div>
        <h1 className="mt-4 text-3xl font-semibold tracking-tight text-white sm:text-4xl">
          {detail.summary.project}
        </h1>
        <p className="mt-2 break-all font-mono text-xs text-slate-500">
          {detail.summary.folder} · run {detail.runId}
        </p>
        <div className="mt-5 flex flex-wrap gap-3">
          <Link
            href={`/executions/${encodeURIComponent(run)}`}
            className="rounded-xl border border-white/10 bg-white/[0.03] px-3.5 py-2 text-xs font-medium text-slate-300 transition hover:border-white/20 hover:text-white"
          >
            ← Voltar à execução
          </Link>
          <Link
            href={`/files/scenarios/${encodeURIComponent(run)}/${encodeURIComponent(detail.summary.folder)}`}
            className="rounded-xl border border-white/10 bg-white/[0.03] px-3.5 py-2 text-xs font-medium text-slate-300 transition hover:border-white/20 hover:text-white"
          >
            Abrir pasta do cenário
          </Link>
        </div>
      </section>

      <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-4">
        <StatCard
          label="Classes-alvo"
          value={formatNumber(targets.length)}
          hint="no manifesto"
        />
        <StatCard
          label="Métodos-alvo"
          value={formatNumber(methodCount)}
          hint="distribuídos nas classes"
          tone="cyan"
        />
        <StatCard
          label="Fontes ausentes"
          value={formatNumber(detail.summary.missingSources.length)}
          hint="por branch"
          tone={detail.summary.missingSources.length ? "amber" : "emerald"}
        />
        <StatCard
          label="Branches"
          value={formatNumber(detail.branches.length)}
          hint="base / left / right / merge"
          tone="indigo"
        />
      </div>

      {detail.summary.missingSources.length ? (
        <div className="rounded-2xl border border-amber-400/30 bg-amber-400/10 p-4">
          <p className="text-sm font-medium text-amber-200">
            Fontes ausentes registradas no manifesto
          </p>
          <ul className="mt-2 space-y-1 text-xs leading-5 text-amber-200/80">
            {detail.summary.missingSources.map((item) => (
              <li key={item} className="font-mono">
                {item}
              </li>
            ))}
          </ul>
        </div>
      ) : null}

      <section>
        <SectionHeading
          eyebrow="Targets"
          title="Classes e métodos-alvo"
          description="Alvos usados para orientar a geração de testes e a análise."
        />
        {targets.length ? (
          <div className="grid gap-4 lg:grid-cols-2">
            {targets.map((target) => (
              <div
                key={target.className}
                className="rounded-2xl border border-white/10 bg-white/[0.02] p-5"
              >
                <p className="break-all font-mono text-sm text-slate-200">
                  {target.className}
                </p>
                <div className="mt-4 space-y-3">
                  {target.methods.length ? (
                    target.methods.map((method, index) => (
                      <div
                        key={`${method.name}-${index}`}
                        className="rounded-xl border border-white/5 bg-slate-950/40 p-3"
                      >
                        <p className="break-all font-mono text-xs text-cyan-200">
                          {method.name || "—"}
                        </p>
                        {method.leftSummary || method.rightSummary ? (
                          <div className="mt-2 grid gap-2 text-[11px] leading-5 text-slate-500 sm:grid-cols-2">
                            <p>
                              <span className="text-slate-400">left:</span>{" "}
                              {method.leftSummary || "—"}
                            </p>
                            <p>
                              <span className="text-slate-400">right:</span>{" "}
                              {method.rightSummary || "—"}
                            </p>
                          </div>
                        ) : null}
                      </div>
                    ))
                  ) : (
                    <p className="text-xs text-slate-500">
                      Nenhum método listado.
                    </p>
                  )}
                </div>
              </div>
            ))}
          </div>
        ) : (
          <EmptyState
            title="Sem targets"
            description="O manifesto não registra classes ou métodos-alvo para este cenário."
          />
        )}
      </section>

      <section>
        <SectionHeading
          eyebrow="Laya"
          title="Resultado da pré-análise"
          description="Hipótese do Laya para os três critérios de interferência. A detecção por execução continua sendo a referência."
        />
        <LayaScenarioPanel summary={layaSummary} />
      </section>

      <section>
        <SectionHeading
          eyebrow="Sources"
          title="Versões do cenário"
          description="Alterne entre o diff textual e as fontes completas. No diff, escolha os pares base/left/right/merge; no modo Fontes, use as abas por branch."
        />
        <ScenarioSourceExplorer branches={detail.branches} />
      </section>

      <details className="rounded-2xl border border-white/10 bg-white/[0.02] p-4">
        <summary className="cursor-pointer text-sm font-medium text-slate-300">
          Commits e jars do cenário
        </summary>
        <div className="mt-4 grid gap-4 lg:grid-cols-2">
          <div>
            <p className="mb-2 text-[11px] uppercase tracking-[0.18em] text-slate-500">
              Commits
            </p>
            <pre className="code-scroll overflow-auto rounded-xl border border-white/5 bg-slate-950/60 p-3 font-mono text-[11px] leading-5 text-slate-400">
              {JSON.stringify(detail.summary.scenarioCommits, null, 2)}
            </pre>
          </div>
          <div>
            <p className="mb-2 text-[11px] uppercase tracking-[0.18em] text-slate-500">
              Jars
            </p>
            <pre className="code-scroll overflow-auto rounded-xl border border-white/5 bg-slate-950/60 p-3 font-mono text-[11px] leading-5 text-slate-400">
              {JSON.stringify(detail.summary.scenarioJars, null, 2)}
            </pre>
          </div>
        </div>
      </details>
    </div>
  );
}
