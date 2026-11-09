import Link from "next/link";

import { Badge } from "@/components/ui";
import {
  accuracyTone,
  formatAccuracy,
  formatDate,
  formatNumber,
} from "@/lib/format";
import type { LayaRunSummary } from "@/lib/types";

export function FlowRunGroup({
  title,
  runs,
  basePath,
  emptyText,
}: {
  title: string;
  runs: LayaRunSummary[];
  basePath: "/laya" | "/llm";
  emptyText: string;
}) {
  return (
    <div className="rounded-2xl border border-zinc-200 bg-white p-4">
      <div className="flex items-center justify-between gap-3">
        <h3 className="text-sm font-semibold text-zinc-900">{title}</h3>
        <Badge tone="slate">{formatNumber(runs.length)}</Badge>
      </div>

      {runs.length ? (
        <div className="mt-3 divide-y divide-zinc-200">
          {runs.map((run) => (
            <Link
              key={run.id}
              href={`${basePath}/${encodeURIComponent(run.id)}`}
              className="flex flex-wrap items-center justify-between gap-3 py-3 transition hover:text-red-700"
            >
              <div className="min-w-0">
                <span className="block truncate font-mono text-xs text-zinc-900">
                  {run.runId || run.id}
                </span>
                <span className="mt-0.5 block text-[10px] text-zinc-500">
                  {run.evaluation.dataset ?? "sem dataset"} ·{" "}
                  {formatDate(run.createdAt)}
                </span>
              </div>
              <div className="flex items-center gap-2">
                {run.evaluation.labeled ? (
                  <>
                    <Badge tone={accuracyTone(run.evaluation.accuracy)}>
                      {formatAccuracy(run.evaluation.accuracy)}
                    </Badge>
                    <span className="text-[10px] text-zinc-500">
                      {formatNumber(run.evaluation.correct)}/
                      {formatNumber(run.evaluation.labeled)}
                    </span>
                  </>
                ) : (
                  <span className="text-xs text-zinc-500">—</span>
                )}
                <span className="text-xs font-medium text-red-600">
                  Abrir →
                </span>
              </div>
            </Link>
          ))}
        </div>
      ) : (
        <p className="mt-3 text-xs leading-5 text-zinc-500">{emptyText}</p>
      )}
    </div>
  );
}
