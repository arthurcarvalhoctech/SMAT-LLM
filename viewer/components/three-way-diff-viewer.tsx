"use client";

import { diffLines } from "diff";
import { useMemo } from "react";

import { Badge } from "@/components/ui";
import { formatNumber } from "@/lib/format";
import type { BranchView } from "@/lib/types";

type Side = "left" | "merge" | "right";
type CellType = "context" | "added" | "removed";

interface Cell {
  type: CellType;
  text: string;
  lineNumber: number | null;
}

interface Row {
  base: Cell | null;
  left: Cell | null;
  right: Cell | null;
  merge: Cell | null;
}

interface Alignment {
  context: Map<number, { lineNumber: number; text: string }>;
  removed: Map<number, string>;
  additions: Map<number, Array<{ lineNumber: number; text: string }>>;
}

interface ClassEntry {
  key: string;
  name: string;
  code: string;
  sourcePath: string;
}

interface ClassGroup {
  key: string;
  name: string;
  sourcePath: string;
  rows: Row[];
  hasChanges: boolean;
  changedLeft: number;
  changedRight: number;
  changedMerge: number;
}

function splitLines(text: string): string[] {
  const lines = text.split("\n");
  if (lines.length > 1 && lines[lines.length - 1] === "") lines.pop();
  return lines;
}

function branchCode(branch: BranchView): string {
  if (branch.sections.length === 0) return branch.content;
  return branch.sections
    .map(
      (section) =>
        `// ${section.classes.join(", ")}\n${section.code}`,
    )
    .join("\n\n");
}

function classEntries(branch: BranchView): Map<string, ClassEntry> {
  const entries = new Map<string, ClassEntry>();

  for (const section of branch.sections) {
    const key =
      section.classes.join("|") || section.sourcePath || "Arquivo";
    if (entries.has(key)) continue;
    entries.set(key, {
      key,
      name: section.classes.join(", ") || section.sourcePath || "Arquivo",
      code: section.code,
      sourcePath: section.sourcePath,
    });
  }

  if (entries.size === 0) {
    entries.set("__file__", {
      key: "__file__",
      name: "Arquivo completo",
      code: branchCode(branch),
      sourcePath: "",
    });
  }

  return entries;
}

/** Alinha as linhas de uma branch com a base e guarda adições/remoções. */
function alignToBase(baseText: string, branchText: string): Alignment {
  const context = new Map<number, { lineNumber: number; text: string }>();
  const removed = new Map<number, string>();
  const additions = new Map<
    number,
    Array<{ lineNumber: number; text: string }>
  >();

  let baseLine = 1;
  let branchLine = 1;

  for (const change of diffLines(baseText, branchText)) {
    for (const text of splitLines(change.value)) {
      if (change.added) {
        const anchor = baseLine - 1;
        const list = additions.get(anchor) ?? [];
        list.push({ lineNumber: branchLine, text });
        additions.set(anchor, list);
        branchLine += 1;
      } else if (change.removed) {
        removed.set(baseLine, text);
        baseLine += 1;
      } else {
        context.set(baseLine, { lineNumber: branchLine, text });
        baseLine += 1;
        branchLine += 1;
      }
    }
  }

  return { context, removed, additions };
}

function contextCell(alignment: Alignment, baseLine: number): Cell | null {
  const context = alignment.context.get(baseLine);
  if (context) {
    return {
      type: "context",
      text: context.text,
      lineNumber: context.lineNumber,
    };
  }

  const removed = alignment.removed.get(baseLine);
  if (removed !== undefined) {
    return { type: "removed", text: removed, lineNumber: null };
  }

  return null;
}

function addedCell(
  line: { lineNumber: number; text: string } | undefined,
): Cell | null {
  return line
    ? { type: "added", text: line.text, lineNumber: line.lineNumber }
    : null;
}

function buildRows(
  baseCode: string,
  leftCode: string,
  rightCode: string,
  mergeCode: string,
): Row[] {
  const baseLines = splitLines(baseCode);
  const left = alignToBase(baseCode, leftCode);
  const right = alignToBase(baseCode, rightCode);
  const merge = alignToBase(baseCode, mergeCode);
  const rows: Row[] = [];

  function pushAdditions(anchor: number) {
    const leftAdds = left.additions.get(anchor) ?? [];
    const rightAdds = right.additions.get(anchor) ?? [];
    const mergeAdds = merge.additions.get(anchor) ?? [];
    const count = Math.max(
      leftAdds.length,
      rightAdds.length,
      mergeAdds.length,
    );

    for (let index = 0; index < count; index += 1) {
      rows.push({
        base: null,
        left: addedCell(leftAdds[index]),
        right: addedCell(rightAdds[index]),
        merge: addedCell(mergeAdds[index]),
      });
    }
  }

  pushAdditions(0);
  for (let baseLine = 1; baseLine <= baseLines.length; baseLine += 1) {
    rows.push({
      base: {
        type: "context",
        text: baseLines[baseLine - 1],
        lineNumber: baseLine,
      },
      left: contextCell(left, baseLine),
      right: contextCell(right, baseLine),
      merge: contextCell(merge, baseLine),
    });
    pushAdditions(baseLine);
  }

  return rows;
}

function countChanges(rows: Row[], side: "left" | "right" | "merge"): number {
  return rows.reduce((total, row) => {
    const cell = row[side];
    return total + (cell && cell.type !== "context" ? 1 : 0);
  }, 0);
}

function buildGroups(branches: BranchView[]): ClassGroup[] {
  const base = branches.find((branch) => branch.key === "base");
  const left = branches.find((branch) => branch.key === "left");
  const right = branches.find((branch) => branch.key === "right");
  const merge = branches.find((branch) => branch.key === "merge");

  if (!base || !left || !right || !merge) return [];

  const baseEntries = classEntries(base);
  const leftEntries = classEntries(left);
  const rightEntries = classEntries(right);
  const mergeEntries = classEntries(merge);
  const keys = [
    ...new Set([
      ...baseEntries.keys(),
      ...leftEntries.keys(),
      ...rightEntries.keys(),
      ...mergeEntries.keys(),
    ]),
  ];

  return keys.map((key) => {
    const baseEntry = baseEntries.get(key);
    const leftEntry = leftEntries.get(key);
    const rightEntry = rightEntries.get(key);
    const mergeEntry = mergeEntries.get(key);
    const baseCode = baseEntry?.code ?? "";
    const leftCode = leftEntry?.code ?? "";
    const rightCode = rightEntry?.code ?? "";
    const mergeCode = mergeEntry?.code ?? "";
    const rows = buildRows(baseCode, leftCode, rightCode, mergeCode);

    return {
      key,
      name:
        baseEntry?.name ??
        leftEntry?.name ??
        rightEntry?.name ??
        mergeEntry?.name ??
        key,
      sourcePath:
        baseEntry?.sourcePath ??
        leftEntry?.sourcePath ??
        rightEntry?.sourcePath ??
        mergeEntry?.sourcePath ??
        "",
      rows,
      hasChanges:
        leftCode !== baseCode ||
        rightCode !== baseCode ||
        mergeCode !== baseCode,
      changedLeft: countChanges(rows, "left"),
      changedRight: countChanges(rows, "right"),
      changedMerge: countChanges(rows, "merge"),
    };
  });
}

const cellStyles: Record<Side, Record<CellType, string>> = {
  left: {
    context: "border-l-2 border-transparent bg-white text-zinc-700",
    added: "border-l-2 border-red-500 bg-red-100 text-red-900",
    removed: "border-l-2 border-red-200 bg-red-50 text-red-400",
  },
  merge: {
    context: "border-l-2 border-transparent bg-white text-zinc-700",
    added: "border-l-2 border-green-600 bg-green-100 text-green-900",
    removed: "border-l-2 border-green-200 bg-green-50 text-green-400",
  },
  right: {
    context: "border-l-2 border-transparent bg-white text-zinc-700",
    added: "border-l-2 border-blue-500 bg-blue-100 text-blue-900",
    removed: "border-l-2 border-blue-200 bg-blue-50 text-blue-400",
  },
};

function ChangeBadge({
  label,
  count,
  className,
}: {
  label: string;
  count: number;
  className: string;
}) {
  return (
    <span
      className={`inline-flex items-center gap-1 rounded-full border px-2.5 py-1 text-[11px] font-medium ${className}`}
    >
      {label} {formatNumber(count)}
    </span>
  );
}

function DiffCell({ cell, side }: { cell: Cell | null; side: Side }) {
  const style = cell
    ? cellStyles[side][cell.type]
    : "border-l-2 border-transparent bg-white";

  return (
    <div className={`flex min-w-0 border-r border-zinc-200 ${style}`}>
      <span className="w-10 shrink-0 select-none border-r border-zinc-200 px-2 text-right font-mono text-[10px] leading-5 text-zinc-400">
        {cell?.type === "removed" ? "−" : cell?.lineNumber ?? ""}
      </span>
      <pre
        className={`min-w-0 flex-1 whitespace-pre-wrap px-2 font-mono text-[11px] leading-5 [overflow-wrap:anywhere] ${
          cell?.type === "removed" ? "line-through" : ""
        }`}
      >
        {cell?.text || " "}
      </pre>
    </div>
  );
}

function Legend() {
  return (
    <div className="flex flex-wrap items-center gap-3 text-[11px] text-zinc-600">
      <span className="inline-flex items-center gap-1.5">
        <span className="h-2.5 w-2.5 rounded-sm border border-red-500 bg-red-100" />
        left
      </span>
      <span className="inline-flex items-center gap-1.5">
        <span className="h-2.5 w-2.5 rounded-sm border border-green-600 bg-green-100" />
        merge
      </span>
      <span className="inline-flex items-center gap-1.5">
        <span className="h-2.5 w-2.5 rounded-sm border border-blue-500 bg-blue-100" />
        right
      </span>
      <span className="inline-flex items-center gap-1.5">
        <span className="h-2.5 w-2.5 rounded-sm border border-zinc-300 bg-white" />
        inalterado
      </span>
    </div>
  );
}

export function ThreeWayDiffViewer({ branches }: { branches: BranchView[] }) {
  const groups = useMemo(() => buildGroups(branches), [branches]);
  const changedGroups = groups.filter((group) => group.hasChanges);

  if (groups.length === 0) {
    return (
      <div className="rounded-2xl border border-zinc-200 bg-white p-6 text-sm text-zinc-600">
        Não há as quatro versões (base, left, right e merge) para montar o diff
        de três vias.
      </div>
    );
  }

  return (
    <div className="rounded-3xl border border-zinc-200 bg-white">
      <div className="border-b border-zinc-200 p-4">
        <div className="flex flex-wrap items-start justify-between gap-3">
          <div>
            <div className="flex flex-wrap items-center gap-2">
              <Badge tone="rose">Diff 3 vias</Badge>
              <Badge tone="slate">
                {formatNumber(changedGroups.length)} classe(s) com alterações
              </Badge>
            </div>
            <p className="mt-2 max-w-3xl text-xs leading-5 text-zinc-600">
              A base é usada apenas para alinhamento e não é exibida. Linhas
              brancas estão inalteradas. Alterações de left aparecem em
              vermelho, merge em verde e right em azul; linhas riscadas são
              remoções, em tom mais claro.
            </p>
          </div>
          <Legend />
        </div>
      </div>

      <div className="space-y-3 p-4">
        {changedGroups.length === 0 ? (
          <div className="rounded-xl border border-zinc-200 bg-zinc-50 p-4 text-xs text-zinc-600">
            Nenhuma diferença em relação à base nas quatro versões.
          </div>
        ) : (
          groups
            .filter((group) => group.hasChanges)
            .map((group) => (
              <details
                key={group.key}
                open
                className="overflow-hidden rounded-2xl border border-zinc-200 bg-white"
              >
                <summary className="flex cursor-pointer list-none flex-wrap items-center justify-between gap-3 px-4 py-3 [&::-webkit-details-marker]:hidden">
                  <div className="min-w-0">
                    <p className="truncate text-sm font-semibold text-zinc-900">
                      {group.name}
                    </p>
                    {group.sourcePath ? (
                      <p className="truncate font-mono text-[10px] text-zinc-500">
                        {group.sourcePath}
                      </p>
                    ) : null}
                  </div>
                  <div className="flex shrink-0 flex-wrap items-center gap-2">
                    <ChangeBadge
                      label="left"
                      count={group.changedLeft}
                      className="border-red-200 bg-red-50 text-red-700"
                    />
                    <ChangeBadge
                      label="merge"
                      count={group.changedMerge}
                      className="border-green-300 bg-green-50 text-green-800"
                    />
                    <ChangeBadge
                      label="right"
                      count={group.changedRight}
                      className="border-blue-200 bg-blue-50 text-blue-700"
                    />
                  </div>
                </summary>

                <div className="border-t border-zinc-200 p-3">
                  <div className="max-h-[70vh] overflow-auto rounded-xl border border-zinc-200">
                    <div className="min-w-[960px]">
                      <div className="sticky top-0 z-10 grid grid-cols-[repeat(3,minmax(300px,1fr))] border-b border-zinc-200 bg-zinc-100 px-1 py-2 text-[10px] uppercase tracking-[0.16em] text-zinc-600">
                        <span>Left</span>
                        <span>Merge</span>
                        <span>Right</span>
                      </div>
                      {group.rows.map((row, index) => (
                        <div
                          key={`${group.key}-${index}`}
                          className="grid grid-cols-[repeat(3,minmax(300px,1fr))] border-t border-zinc-200"
                        >
                          <DiffCell cell={row.left} side="left" />
                          <DiffCell cell={row.merge} side="merge" />
                          <DiffCell cell={row.right} side="right" />
                        </div>
                      ))}
                    </div>
                  </div>
                </div>
              </details>
            ))
        )}
      </div>
    </div>
  );
}
