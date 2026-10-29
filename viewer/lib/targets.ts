import type { TargetClass, TargetMethod } from "./types";

export function normalizeTargets(
  targets: Record<string, unknown>,
): TargetClass[] {
  return Object.entries(targets).map(([className, value]) => {
    const items = Array.isArray(value) ? value : [];
    const methods: TargetMethod[] = items.map((item) => {
      if (typeof item === "string") return { name: item };
      if (item && typeof item === "object") {
        const record = item as Record<string, unknown>;
        return {
          name: String(record.method ?? ""),
          leftSummary: record.leftChangesSummary
            ? String(record.leftChangesSummary)
            : undefined,
          rightSummary: record.rightChangesSummary
            ? String(record.rightChangesSummary)
            : undefined,
        };
      }
      return { name: String(item) };
    });
    return { className, methods };
  });
}
