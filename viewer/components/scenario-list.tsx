import Link from "next/link";

import { LayaScenarioBadges } from "@/components/laya-scenario-summary";
import { MobileLabel } from "@/components/mobile-label";
import { Badge } from "@/components/ui";
import { normalizeTargets } from "@/lib/targets";
import type { LayaScenarioSummary, ScenarioSummary } from "@/lib/types";

export function ScenarioList({
  executionId,
  scenarios,
  layaSummaries,
}: {
  executionId: string;
  scenarios: ScenarioSummary[];
  layaSummaries?: Record<string, LayaScenarioSummary>;
}) {
  return (
    <div className="overflow-hidden rounded-2xl border border-zinc-200 bg-white">
      <div className="hidden grid-cols-[0.5fr_1.2fr_1fr_0.7fr_1.2fr_auto_auto] gap-4 border-b border-zinc-200 bg-zinc-100 px-4 py-3 text-[10px] font-medium uppercase tracking-[0.16em] text-zinc-600 sm:grid">
        <span>Cenário</span>
        <span>Projeto</span>
        <span>Targets</span>
        <span>Tipo</span>
        <span>Laya</span>
        <span>Status</span>
        <span className="sr-only">Abrir</span>
      </div>

      <div className="divide-y divide-zinc-200">
        {scenarios.map((scenario) => {
          const targets = normalizeTargets(scenario.targets);
          const methodCount = targets.reduce(
            (total, target) => total + target.methods.length,
            0,
          );

          return (
            <Link
              key={scenario.folder}
              href={`/executions/${encodeURIComponent(executionId)}/${encodeURIComponent(scenario.folder)}`}
              className="grid gap-2 px-4 py-4 transition hover:bg-zinc-50 sm:grid-cols-[0.5fr_1.2fr_1fr_0.7fr_1.2fr_auto_auto] sm:items-center sm:gap-4"
            >
              <div>
                <MobileLabel>Cenário</MobileLabel>
                <span className="font-mono text-xs text-zinc-500">
                  {String(scenario.index).padStart(3, "0")}
                </span>
              </div>

              <div className="min-w-0">
                <MobileLabel>Projeto</MobileLabel>
                <span className="block truncate text-sm font-medium text-zinc-900">
                  {scenario.project}
                </span>
                <span className="block truncate font-mono text-[10px] text-zinc-500">
                  {scenario.folder}
                </span>
              </div>

              <div>
                <MobileLabel>Targets</MobileLabel>
                <span className="text-xs text-zinc-600">
                  {targets.length} classes · {methodCount} métodos
                </span>
              </div>

              <div>
                <MobileLabel>Tipo</MobileLabel>
                <span className="text-xs text-zinc-600">
                  {scenario.jarType || "—"}
                </span>
              </div>

              <div>
                <MobileLabel>Laya</MobileLabel>
                <LayaScenarioBadges
                  summary={layaSummaries?.[scenario.folder]}
                />
              </div>

              <div className="flex flex-wrap items-center gap-2">
                <MobileLabel>Status</MobileLabel>
                <Badge tone={scenario.runAnalysis ? "emerald" : "slate"}>
                  {scenario.runAnalysis ? "analisado" : "ignorado"}
                </Badge>
                {scenario.missingSources.length ? (
                  <Badge tone="amber">
                    {scenario.missingSources.length} missing
                  </Badge>
                ) : null}
              </div>

              <span className="text-xs font-medium text-red-600 sm:text-right">
                Abrir →
              </span>
            </Link>
          );
        })}
      </div>
    </div>
  );
}
