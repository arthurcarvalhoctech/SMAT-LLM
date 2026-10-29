import Link from "next/link";
import { notFound } from "next/navigation";

import { LayaTable } from "@/components/laya-table";
import {
  Badge,
  Breadcrumbs,
  SectionHeading,
  StatCard,
} from "@/components/ui";
import { formatDate, formatNumber } from "@/lib/format";
import { getLayaRun } from "@/lib/smat-data";

export const dynamic = "force-dynamic";

type LayaRunPageProps = {
  params: Promise<{ run: string }>;
};

export default async function LayaRunPage({ params }: LayaRunPageProps) {
  const { run } = await params;
  const detail = await getLayaRun(run);

  if (!detail) notFound();

  const first = detail.records[0];
  return (
    <div className="space-y-8">
      <Breadcrumbs
        items={[
          { href: "/executions", label: "Execuções" },
          { href: "/laya", label: "Laya" },
          { label: detail.summary.runId },
        ]}
      />

      <section className="panel-gradient rounded-3xl border border-white/10 p-6 sm:p-8">
        <div className="flex flex-wrap items-center gap-2">
          <Badge tone="emerald">Laya</Badge>
          {first?.model ? <Badge tone="indigo">{first.model}</Badge> : null}
          {first?.threshold !== undefined ? (
            <Badge tone="slate">threshold {first.threshold}</Badge>
          ) : null}
          {first?.maxLen ? (
            <Badge tone="slate">max_len {first.maxLen}</Badge>
          ) : null}
        </div>
        <h1 className="mt-4 break-all font-mono text-2xl font-semibold tracking-tight text-white sm:text-3xl">
          {detail.summary.runId}
        </h1>
        <p className="mt-2 text-sm text-slate-400">
          {formatDate(detail.summary.createdAt)} ·{" "}
          {formatNumber(detail.summary.fileCount)} arquivo(s)
        </p>
        <div className="mt-5 flex flex-wrap gap-3">
          <Link
            href="/laya"
            className="rounded-xl border border-white/10 bg-white/[0.03] px-3.5 py-2 text-xs font-medium text-slate-300 transition hover:border-white/20 hover:text-white"
          >
            ← Voltar ao Laya
          </Link>
          {detail.logFile ? (
            <a
              href={`/api/file/reports/laya/${encodeURIComponent(detail.logFile)}`}
              target="_blank"
              rel="noreferrer"
              className="rounded-xl border border-white/10 bg-white/[0.03] px-3.5 py-2 text-xs font-medium text-slate-300 transition hover:border-white/20 hover:text-white"
            >
              Log legível
            </a>
          ) : null}
          {detail.jsonlFile ? (
            <a
              href={`/api/file/reports/laya/${encodeURIComponent(detail.jsonlFile)}`}
              target="_blank"
              rel="noreferrer"
              className="rounded-xl border border-white/10 bg-white/[0.03] px-3.5 py-2 text-xs font-medium text-slate-300 transition hover:border-white/20 hover:text-white"
            >
              JSONL
            </a>
          ) : null}
        </div>
      </section>

      <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-4">
        <StatCard
          label="Interferências"
          value={formatNumber(detail.summary.interference)}
          hint="classificação interference"
          tone="rose"
        />
        <StatCard
          label="Sem interferência"
          value={formatNumber(detail.summary.noInterference)}
          hint="classificação no_interference"
          tone="emerald"
        />
        <StatCard
          label="Erros"
          value={formatNumber(detail.summary.errors)}
          hint="classificação error"
          tone={detail.summary.errors ? "amber" : "slate"}
        />
        <StatCard
          label="Arquivos"
          value={formatNumber(detail.summary.fileCount)}
          hint="JSONs de classificação"
          tone="cyan"
        />
      </div>

      <section>
        <SectionHeading
          eyebrow="Resultados"
          title="Classificações por método"
          description="Probabilidades dos três critérios, critério principal, branch afetado e confiança."
        />
        <LayaTable records={detail.records} />
      </section>
    </div>
  );
}
