import { notFound } from "next/navigation";

import { JsonViewer } from "@/components/json-viewer";
import { Badge, Breadcrumbs } from "@/components/ui";
import { formatBytes, formatDate } from "@/lib/format";
import { getReport } from "@/lib/smat-data";

export const dynamic = "force-dynamic";

type ReportPageProps = {
  params: Promise<{ name: string }>;
};

export default async function ReportPage({ params }: ReportPageProps) {
  const { name } = await params;
  const report = await getReport(name);

  if (!report) notFound();

  return (
    <div className="space-y-8">
      <Breadcrumbs
        items={[
          { href: "/executions", label: "Execuções" },
          { href: "/reports", label: "Relatórios" },
          { label: report.name },
        ]}
      />

      <section className="panel-gradient rounded-3xl border border-white/10 p-6 sm:p-8">
        <div className="flex flex-wrap items-center gap-2">
          <Badge tone="indigo">JSON</Badge>
          <Badge tone="slate">{formatBytes(report.bytes)}</Badge>
          <Badge tone="slate">{formatDate(report.modified)}</Badge>
        </div>
        <h1 className="mt-4 break-all font-mono text-2xl font-semibold tracking-tight text-white sm:text-3xl">
          {report.name}
        </h1>
        <a
          href={`/api/file/reports/${encodeURIComponent(report.name)}`}
          target="_blank"
          rel="noreferrer"
          className="mt-5 inline-flex rounded-xl border border-white/10 bg-white/[0.03] px-3.5 py-2 text-xs font-medium text-slate-300 transition hover:border-white/20 hover:text-white"
        >
          Baixar JSON bruto
        </a>
      </section>

      {report.data === null ? (
        <div className="rounded-2xl border border-amber-400/30 bg-amber-400/10 p-4 text-sm text-amber-200">
          Não foi possível interpretar este arquivo como JSON. Use o download
          para inspecionar o conteúdo bruto.
        </div>
      ) : (
        <JsonViewer data={report.data} />
      )}
    </div>
  );
}
