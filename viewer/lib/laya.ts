import type { LayaScenarioStatus } from "./types";

export const LAYA_CRITERIA = [
  {
    id: "criterion_1_global_divergence",
    short: "C1",
    label: "Divergência global",
  },
  {
    id: "criterion_2_parent_change_loss",
    short: "C2",
    label: "Perda de alteração do pai",
  },
  {
    id: "criterion_3_merge_new_effect",
    short: "C3",
    label: "Efeito colateral inesperado do merge",
  },
] as const;

export function criterionLabel(id: string): string {
  return LAYA_CRITERIA.find((criterion) => criterion.id === id)?.label ?? id;
}

export function criterionShort(id: string): string {
  return LAYA_CRITERIA.find((criterion) => criterion.id === id)?.short ?? id;
}

export function layaStatusLabel(status: LayaScenarioStatus): string {
  switch (status) {
    case "interference":
      return "Interferência detectada";
    case "no_interference":
      return "Sem interferência";
    case "error":
      return "Erro na análise Laya";
    default:
      return "Sem análise Laya";
  }
}

export function layaStatusShort(status: LayaScenarioStatus): string {
  switch (status) {
    case "interference":
      return "Interferência";
    case "no_interference":
      return "Sem interf.";
    case "error":
      return "Erro";
    default:
      return "—";
  }
}

export function layaStatusTone(
  status: LayaScenarioStatus,
): "rose" | "emerald" | "amber" | "slate" {
  switch (status) {
    case "interference":
      return "rose";
    case "no_interference":
      return "emerald";
    case "error":
      return "amber";
    default:
      return "slate";
  }
}
