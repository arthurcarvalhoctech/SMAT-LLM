import Link from "next/link";

import { Badge } from "@/components/ui";
import { normalizeTargets } from "@/lib/targets";
import type { ScenarioSummary } from "@/lib/types";

export function ScenarioCard({
  executionId,
  scenario,
}: {
  executionId: string;
  scenario: ScenarioSummary;
}) {
  const targets = normalizeTargets(scenario.targets);
  const methodCount = targets.reduce(
    (total, target) => total + target.methods.length,
    0,
  );

  return (
    <Link
      href={`/executions/${encodeURIComponent(executionId)}/${encodeURIComponent(scenario.folder)}`}
      className="group flex flex-col gap-3 rounded-2xl border border-white/10 bg-white/[0.03] p-5 transition hover:border-cyan-400/40 hover:bg-cyan-500/[0.05]"
    >
      <div className="flex items-center justify-between gap-2">
        <span className="font-mono text-xs text-slate-500">
          {String(scenario.index).padStart(3, "0")}
        </span>
        <Badge tone={scenario.runAnalysis ? "indigo" : "slate"}>
          {scenario.runAnalysis ? "analisado" : "ignorado"}
        </Badge>
      </div>

      <h3 className="text-base font-semibold text-white">
        {scenario.project}
      </h3>

      <div className="flex flex-wrap items-center gap-2 text-xs text-slate-500">
        <span>{targets.length} classes</span>
        <span className="h-1 w-1 rounded-full bg-slate-700" />
        <span>{methodCount} métodos</span>
        {scenario.jarType ? (
          <>
            <span className="h-1 w-1 rounded-full bg-slate-700" />
            <span>{scenario.jarType}</span>
          </>
        ) : null}
      </div>

      {scenario.missingSources.length ? (
        <p className="text-xs text-amber-300">
          {scenario.missingSources.length} fonte(s) ausente(s)
        </p>
      ) : null}

      <span className="mt-auto text-xs font-medium text-cyan-300 transition group-hover:underline">
        Ver base / left / right / merge →
      </span>
    </Link>
  );
}
