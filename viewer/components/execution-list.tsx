import Link from "next/link";

import { Badge } from "@/components/ui";
import { formatDate, formatNumber } from "@/lib/format";
import type { ExecutionSummary } from "@/lib/types";

export function ExecutionList({
  executions,
}: {
  executions: ExecutionSummary[];
}) {
  return (
    <div className="overflow-hidden rounded-2xl border border-zinc-200 bg-white">
      <div className="hidden grid-cols-[1.1fr_1.5fr_1fr_auto_auto_auto] gap-4 border-b border-zinc-200 bg-zinc-100 px-4 py-3 text-[10px] font-medium uppercase tracking-[0.16em] text-zinc-600 sm:grid">
        <span>Dataset</span>
        <span>Execução</span>
        <span>Data</span>
        <span>Cenários</span>
        <span>Status</span>
        <span className="sr-only">Abrir</span>
      </div>

      <div className="divide-y divide-zinc-200">
        {executions.map((execution) => (
          <Link
            key={execution.id}
            href={`/executions/${encodeURIComponent(execution.id)}`}
            className="grid gap-2 px-4 py-4 transition hover:bg-zinc-50 sm:grid-cols-[1.1fr_1.5fr_1fr_auto_auto_auto] sm:items-center sm:gap-4"
          >
            <div className="min-w-0">
              <span className="mb-1 block text-[10px] uppercase tracking-[0.16em] text-zinc-500 sm:hidden">
                Dataset
              </span>
              <span className="block truncate text-[11px] uppercase tracking-[0.14em] text-zinc-600">
                {execution.dataset}
              </span>
            </div>

            <div className="min-w-0">
              <span className="mb-1 block text-[10px] uppercase tracking-[0.16em] text-zinc-500 sm:hidden">
                Execução
              </span>
              <span className="block truncate font-mono text-sm text-zinc-900">
                {execution.runId || execution.id}
              </span>
              {execution.hasManifest ? (
                <span className="mt-0.5 block text-[10px] text-zinc-500">
                  manifest
                </span>
              ) : null}
            </div>

            <div>
              <span className="mb-1 block text-[10px] uppercase tracking-[0.16em] text-zinc-500 sm:hidden">
                Data
              </span>
              <span className="text-xs text-zinc-600">
                {formatDate(execution.createdAt)}
              </span>
            </div>

            <div>
              <span className="mb-1 block text-[10px] uppercase tracking-[0.16em] text-zinc-500 sm:hidden">
                Cenários
              </span>
              <span className="text-xs text-zinc-700">
                {formatNumber(execution.scenarioCount)}
              </span>
            </div>

            <div>
              <span className="mb-1 block text-[10px] uppercase tracking-[0.16em] text-zinc-500 sm:hidden">
                Status
              </span>
              <Badge
                tone={execution.missingSourceCount ? "amber" : "emerald"}
              >
                {execution.missingSourceCount
                  ? `${execution.missingSourceCount} missing`
                  : "completo"}
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
