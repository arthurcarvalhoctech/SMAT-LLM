import Link from "next/link";

import { MobileLabel } from "@/components/mobile-label";
import { Badge } from "@/components/ui";
import { formatDate, formatNumber } from "@/lib/format";
import type { LayaRunSummary } from "@/lib/types";

export function LayaRunList({ runs }: { runs: LayaRunSummary[] }) {
  return (
    <div className="overflow-hidden rounded-2xl border border-zinc-200 bg-white">
      <div className="hidden grid-cols-[1.6fr_1fr_auto_auto_auto_auto_auto] gap-4 border-b border-zinc-200 bg-zinc-100 px-4 py-3 text-[10px] font-medium uppercase tracking-[0.16em] text-zinc-600 sm:grid">
        <span>Execução</span>
        <span>Data</span>
        <span>Arquivos</span>
        <span>Interferências</span>
        <span>Sem interf.</span>
        <span>Erros</span>
        <span className="sr-only">Abrir</span>
      </div>

      <div className="divide-y divide-zinc-200">
        {runs.map((run) => (
          <Link
            key={run.id}
            href={`/laya/${encodeURIComponent(run.id)}`}
            className="grid gap-2 px-4 py-4 transition hover:bg-zinc-50 sm:grid-cols-[1.6fr_1fr_auto_auto_auto_auto_auto] sm:items-center sm:gap-4"
          >
            <div className="min-w-0">
              <MobileLabel>Execução</MobileLabel>
              <span className="block truncate font-mono text-sm text-zinc-900">
                {run.runId || run.id}
              </span>
            </div>

            <div>
              <MobileLabel>Data</MobileLabel>
              <span className="text-xs text-zinc-600">
                {formatDate(run.createdAt)}
              </span>
            </div>

            <div>
              <MobileLabel>Arquivos</MobileLabel>
              <span className="text-xs text-zinc-700">
                {formatNumber(run.fileCount)}
              </span>
            </div>

            <div>
              <MobileLabel>Interferências</MobileLabel>
              <Badge tone={run.interference ? "rose" : "emerald"}>
                {formatNumber(run.interference)}
              </Badge>
            </div>

            <div>
              <MobileLabel>Sem interf.</MobileLabel>
              <span className="text-xs text-zinc-700">
                {formatNumber(run.noInterference)}
              </span>
            </div>

            <div>
              <MobileLabel>Erros</MobileLabel>
              <Badge tone={run.errors ? "amber" : "emerald"}>
                {formatNumber(run.errors)}
              </Badge>
            </div>

            <span className="text-xs font-medium text-red-600 sm:text-right">
              Abrir →
            </span>
          </Link>
        ))}
      </div>
    </div>
  );
}
