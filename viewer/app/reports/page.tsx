import Link from "next/link";

import { ReportList } from "@/components/report-list";
import { EmptyState, SectionHeading } from "@/components/ui";
import { getOutputRoot, listReports } from "@/lib/smat-data";

export const dynamic = "force-dynamic";

export default async function ReportsPage() {
  const reports = await listReports();
  const outputRoot = getOutputRoot();

  return (
    <div className="space-y-8">
      <section className="panel-gradient rounded-3xl border border-white/10 p-6 sm:p-8">
        <p className="text-[11px] uppercase tracking-[0.22em] text-indigo-300/80">
          Artefatos
        </p>
        <h1 className="mt-2 text-3xl font-semibold tracking-tight text-white sm:text-4xl">
          Relatórios
        </h1>
        <p className="mt-3 max-w-3xl text-sm leading-6 text-slate-400">
          JSONs gerados pelo SMAT em{" "}
          <code className="font-mono text-slate-300">reports/</code>. Abra um
          arquivo para visualizar o conteúdo formatado.
        </p>
      </section>

      <section>
        <SectionHeading
          eyebrow="Arquivos"
          title="Relatórios disponíveis"
          description={`Lendo ${outputRoot}/reports.`}
        />
        {reports.length ? (
          <ReportList reports={reports} />
        ) : (
          <EmptyState
            title="Nenhum relatório JSON"
            description={`Não há arquivos .json diretamente em ${outputRoot}/reports. Os logs do Laya ficam em reports/laya.`}
          >
            <Link
              href="/laya"
              className="inline-flex rounded-xl border border-white/15 px-4 py-2 text-sm text-slate-200 transition hover:border-white/30"
            >
              Ver logs do Laya
            </Link>
          </EmptyState>
        )}
      </section>
    </div>
  );
}
