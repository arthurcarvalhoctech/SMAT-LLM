import { ExecutionCard } from "@/components/execution-card";
import type { ExecutionSummary } from "@/lib/types";

export function ExecutionGrid({
  executions,
}: {
  executions: ExecutionSummary[];
}) {
  return (
    <div className="grid gap-4 sm:grid-cols-2 xl:grid-cols-3">
      {executions.map((execution) => (
        <ExecutionCard key={execution.id} execution={execution} />
      ))}
    </div>
  );
}
