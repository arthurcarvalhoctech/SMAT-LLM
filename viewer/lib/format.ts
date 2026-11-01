export function formatDate(value?: string | null): string {
  if (!value) return "—";
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) return value;
  return new Intl.DateTimeFormat("pt-BR", {
    dateStyle: "medium",
    timeStyle: "short",
  }).format(date);
}

export function formatBytes(bytes: number): string {
  if (!Number.isFinite(bytes) || bytes <= 0) return "0 B";
  const units = ["B", "KB", "MB", "GB", "TB"];
  const index = Math.min(
    Math.floor(Math.log(bytes) / Math.log(1024)),
    units.length - 1,
  );
  const value = bytes / 1024 ** index;
  return `${value.toFixed(index === 0 ? 0 : 1)} ${units[index]}`;
}

export function formatNumber(value: number): string {
  return new Intl.NumberFormat("pt-BR").format(value);
}

export function formatProbability(value?: number | null): string {
  return typeof value === "number" ? value.toFixed(3) : "—";
}

export function pluralize(
  count: number,
  singular: string,
  plural: string,
): string {
  return `${formatNumber(count)} ${count === 1 ? singular : plural}`;
}

export function classificationTone(
  classification?: string | null,
): "rose" | "emerald" | "amber" | "slate" {
  switch (classification) {
    case "interference":
    case "possible_interference":
      return "rose";
    case "no_interference":
      return "emerald";
    case "uncertain":
      return "amber";
    case "no_signal":
      return "slate";
    case "error":
      return "amber";
    default:
      return "slate";
  }
}

export function classificationLabel(classification?: string | null): string {
  switch (classification) {
    case "interference":
      return "Interferência";
    case "possible_interference":
      return "Possível interferência";
    case "no_interference":
      return "Sem interferência";
    case "uncertain":
      return "Inconclusivo";
    case "no_signal":
      return "Sem sinal";
    case "error":
      return "Erro";
    default:
      return "—";
  }
}

export function encodePath(...parts: string[]): string {
  return parts.map((part) => encodeURIComponent(part)).join("/");
}
