import { LayaLogList } from "@/components/laya-log-list";
import { LayaRunList } from "@/components/laya-run-list";
import { Badge, EmptyState, SectionHeading, StatCard } from "@/components/ui";
import { formatNumber } from "@/lib/format";
import {
  getOutputRoot,
  listLayaLogs,
  listLayaRuns,
} from "@/lib/smat-data";

export const dynamic = "force-dynamic";

export default async function LayaPage() {
  const [runs, logs] = await Promise.all([listLayaRuns(), listLayaLogs()]);
  const outputRoot = getOutputRoot();
  const interference = runs.reduce((total, run) => total + run.interference, 0);
  const errors = runs.reduce((total, run) => total + run.errors, 0);

  return (
    <div className="space-y-10">
      <section className="panel-gradient rounded-3xl border border-white/10 p-6 sm:p-8">
        <Badge tone="emerald">Laya</Badge>
        <h1 className="mt-4 text-3xl font-semibold tracking-tight text-white sm:text-4xl">
          Classificações de interferência
        </h1>
        <p className="mt-3 max-w-3xl text-sm leading-6 text-slate-400">
          Hipóteses de triagem produzidas pelo Laya para os três critérios do
          artigo, além dos logs legíveis e JSONL. A detecção por execução
          continua sendo a referência.
        </p>
      </section>

      <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-4">
        <StatCard
          label="Execuções Laya"
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
          title="Execuções de pré-análise"
          description={`Classificações em ${outputRoot}/reports/laya/classification.`}
        />
        {runs.length ? (
          <LayaRunList runs={runs} />
        ) : (
          <EmptyState
            title="Nenhuma classificação Laya"
            description={`Não há pastas run_* em ${outputRoot}/reports/laya/classification. Habilite SMAT_LAYA_INTERFERENCE_DETECTION=true e execute o SMAT para gerar as classificações.`}
          />
        )}
      </section>

      <section>
        <SectionHeading
          eyebrow="Logs"
          title="Logs legíveis e JSONL"
          description="Arquivos brutos produzidos pela pré-análise Laya."
        />
        {logs.length ? (
          <LayaLogList logs={logs} />
        ) : (
          <EmptyState
            title="Nenhum log Laya"
            description={`Não há arquivos .log ou .jsonl em ${outputRoot}/reports/laya.`}
          />
        )}
      </section>
    </div>
  );
}
