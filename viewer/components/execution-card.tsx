import Link from "next/link";

import { Badge } from "@/components/ui";
import { formatDate, formatNumber } from "@/lib/format";
import type { ExecutionSummary } from "@/lib/types";

export function ExecutionCard({
  execution,
}: {
  execution: ExecutionSummary;
}) {
  return (
    <Link
      href={`/executions/${encodeURIComponent(execution.id)}`}
      className="group flex flex-col gap-4 rounded-2xl border border-white/10 bg-white/[0.03] p-5 transition hover:-translate-y-0.5 hover:border-indigo-400/40 hover:bg-indigo-500/[0.06]"
    >
      <div className="flex items-start justify-between gap-3">
        <div className="min-w-0">
          <p className="truncate text-[11px] uppercase tracking-[0.18em] text-slate-500">
            {execution.dataset}
          </p>
          <h3 className="mt-1 truncate font-mono text-sm text-slate-200">
            {execution.runId || execution.id}
          </h3>
        </div>
        <Badge tone={execution.missingSourceCount ? "amber" : "emerald"}>
          {execution.missingSourceCount
            ? `${execution.missingSourceCount} missing`
            : "completo"}
        </Badge>
      </div>

      <div className="flex flex-wrap items-center gap-2 text-xs text-slate-500">
        <span>{formatDate(execution.createdAt)}</span>
        <span className="h-1 w-1 rounded-full bg-slate-700" />
        <span>{formatNumber(execution.scenarioCount)} cenários</span>
        {execution.hasManifest ? (
          <>
            <span className="h-1 w-1 rounded-full bg-slate-700" />
            <span>manifest</span>
          </>
        ) : null}
      </div>

      <span className="mt-auto inline-flex items-center gap-1 text-xs font-medium text-indigo-300 transition group-hover:gap-2">
        Explorar <span aria-hidden>→</span>
      </span>
    </Link>
  );
}
