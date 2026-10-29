"use client";

import { diffLines } from "diff";
import { useMemo, useState } from "react";

import { Badge } from "@/components/ui";
import { formatNumber } from "@/lib/format";
import type { BranchKey, BranchView } from "@/lib/types";

type DiffRow = {
  type: "context" | "added" | "removed";
  oldLine: number | null;
  newLine: number | null;
  text: string;
};

type DiffGroup = {
  key: string;
  title: string;
  sourcePath: string;
  rows: DiffRow[];
  added: number;
  removed: number;
  hasChanges: boolean;
};

type ClassBlock = {
  name: string;
  code: string;
  start: number;
  end: number;
};

type ClassEntry = {
  key: string;
  name: string;
  code: string;
  sourcePath: string;
};

function branchCode(branch: BranchView): string {
  if (branch.sections.length === 0) return branch.content;
  return branch.sections
    .map(
      (section) =>
        `// ${section.classes.join(", ")}\n${section.code}`,
    )
    .join("\n\n");
}

/**
 * Replaces comments and string/char literals with spaces while preserving
 * offsets and newlines, so class and brace detection ignores braces that are
 * not Java code.
 */
function maskJava(code: string): string {
  const chars = code.split("");
  let index = 0;
  let state: "normal" | "line" | "block" | "string" | "char" = "normal";

  while (index < code.length) {
    const char = code[index];
    const next = code[index + 1];

    if (state === "line") {
      if (char === "\n") {
        state = "normal";
      } else {
        chars[index] = " ";
      }
      index += 1;
      continue;
    }

    if (state === "block") {
      if (char === "*" && next === "/") {
        chars[index] = " ";
        chars[index + 1] = " ";
        index += 2;
        state = "normal";
      } else {
        if (char !== "\n" && char !== "\r") chars[index] = " ";
        index += 1;
      }
      continue;
    }

    if (state === "string" || state === "char") {
      if (char === "\\") {
        chars[index] = " ";
        if (index + 1 < code.length) chars[index + 1] = " ";
        index += 2;
        continue;
      }

      const terminator = state === "string" ? '"' : "'";
      if (char === terminator) {
        chars[index] = " ";
        index += 1;
        state = "normal";
        continue;
      }

      if (char === "\n" || char === "\r") {
        state = "normal";
        index += 1;
        continue;
      }

      chars[index] = " ";
      index += 1;
      continue;
    }

    if (char === "/" && next === "/") {
      chars[index] = " ";
      chars[index + 1] = " ";
      index += 2;
      state = "line";
      continue;
    }

    if (char === "/" && next === "*") {
      chars[index] = " ";
      chars[index + 1] = " ";
      index += 2;
      state = "block";
      continue;
    }

    if (char === '"') {
      chars[index] = " ";
      index += 1;
      state = "string";
      continue;
    }

    if (char === "'") {
      chars[index] = " ";
      index += 1;
      state = "char";
      continue;
    }

    index += 1;
  }

  return chars.join("");
}

function findMatchingBrace(masked: string, open: number): number {
  let depth = 0;

  for (let index = open; index < masked.length; index += 1) {
    if (masked[index] === "{") depth += 1;
    if (masked[index] === "}") {
      depth -= 1;
      if (depth === 0) return index;
    }
  }

  return -1;
}

/** Extracts top-level class/interface/enum/record blocks from a Java source. */
function extractClassBlocks(code: string): ClassBlock[] {
  const masked = maskJava(code);
  const regex = /\b(?:class|interface|enum|record)\s+([A-Za-z_$][\w$]*)/g;
  const candidates: ClassBlock[] = [];
  let match: RegExpExecArray | null;

  while ((match = regex.exec(masked)) !== null) {
    const name = match[1];
    const open = masked.indexOf("{", match.index + match[0].length);
    if (open === -1) continue;

    const close = findMatchingBrace(masked, open);
    if (close === -1) continue;

    const lineStart = code.lastIndexOf("\n", match.index) + 1;
    candidates.push({
      name,
      code: code.slice(lineStart, close + 1),
      start: lineStart,
      end: close + 1,
    });
  }

  const blocks: ClassBlock[] = [];
  for (const candidate of candidates.sort((a, b) => a.start - b.start)) {
    const nested = blocks.some(
      (block) => candidate.start >= block.start && candidate.start < block.end,
    );
    if (!nested) blocks.push(candidate);
  }

  return blocks;
}

/**
 * Maps fully qualified target names to extracted class blocks. Pairing is by
 * class name, not by original source path, because left/right snapshot paths
 * end with different branch suffixes.
 */
function collectClasses(branch: BranchView): Map<string, ClassEntry> {
  const entries = new Map<string, ClassEntry>();

  branch.sections.forEach((section) => {
    const blocks = extractClassBlocks(section.code);

    if (blocks.length > 0) {
      for (const block of blocks) {
        const qualifiedName = section.classes.find(
          (name) => name.split(".").pop() === block.name,
        );
        const key = qualifiedName ?? block.name;

        if (!entries.has(key)) {
          entries.set(key, {
            key,
            name: block.name,
            code: block.code,
            sourcePath: section.sourcePath,
          });
        }
      }
      return;
    }

    const fallbackNames =
      section.classes.length > 0
        ? section.classes
        : [section.sourcePath || "Arquivo"];

    for (const name of fallbackNames) {
      if (!entries.has(name)) {
        entries.set(name, {
          key: name,
          name: name.split(".").pop() || name,
          code: section.code,
          sourcePath: section.sourcePath,
        });
      }
    }
  });

  return entries;
}

function buildRows(leftText: string, rightText: string): DiffRow[] {
  const changes = diffLines(leftText, rightText);
  const rows: DiffRow[] = [];
  let oldLine = 1;
  let newLine = 1;

  for (const change of changes) {
    const lines = change.value.split("\n");
    if (lines.length > 1 && lines[lines.length - 1] === "") {
      lines.pop();
    }

    for (const text of lines) {
      if (change.added) {
        rows.push({ type: "added", oldLine: null, newLine, text });
        newLine += 1;
      } else if (change.removed) {
        rows.push({ type: "removed", oldLine, newLine: null, text });
        oldLine += 1;
      } else {
        rows.push({ type: "context", oldLine, newLine, text });
        oldLine += 1;
        newLine += 1;
      }
    }
  }

  return rows;
}

function createGroup(
  key: string,
  title: string,
  sourcePath: string,
  leftCode: string,
  rightCode: string,
): DiffGroup {
  const rows = buildRows(leftCode, rightCode);
  const added = rows.filter((row) => row.type === "added").length;
  const removed = rows.filter((row) => row.type === "removed").length;

  return {
    key,
    title,
    sourcePath,
    rows,
    added,
    removed,
    hasChanges: added > 0 || removed > 0,
  };
}

function buildGroups(
  leftBranch: BranchView,
  rightBranch: BranchView,
): DiffGroup[] {
  if (
    leftBranch.sections.length === 0 ||
    rightBranch.sections.length === 0
  ) {
    return [
      createGroup(
        "__file__",
        "Arquivo completo",
        "",
        branchCode(leftBranch),
        branchCode(rightBranch),
      ),
    ];
  }

  const leftClasses = collectClasses(leftBranch);
  const rightClasses = collectClasses(rightBranch);

  if (leftClasses.size === 0 || rightClasses.size === 0) {
    return [
      createGroup(
        "__file__",
        "Arquivo completo",
        "",
        branchCode(leftBranch),
        branchCode(rightBranch),
      ),
    ];
  }

  const keys = [
    ...leftClasses.keys(),
    ...[...rightClasses.keys()].filter((key) => !leftClasses.has(key)),
  ];

  return keys.map((key) => {
    const leftClass = leftClasses.get(key);
    const rightClass = rightClasses.get(key);

    return createGroup(
      `class::${key}`,
      leftClass?.name ?? rightClass?.name ?? key,
      leftClass?.sourcePath || rightClass?.sourcePath || "",
      leftClass?.code ?? "",
      rightClass?.code ?? "",
    );
  });
}

function DiffTable({ rows }: { rows: DiffRow[] }) {
  return (
    <div className="max-h-[70vh] overflow-auto rounded-2xl border border-zinc-200 bg-zinc-50">
      <div className="min-w-[900px]">
        <div className="grid grid-cols-[3.5rem_3.5rem_2rem_1fr] border-b border-zinc-200 bg-zinc-100 px-3 py-2 text-[10px] uppercase tracking-[0.16em] text-zinc-600">
          <span>old</span>
          <span>new</span>
          <span />
          <span>código</span>
        </div>
        {rows.map((row, index) => (
          <div
            key={`${row.type}-${row.oldLine}-${row.newLine}-${index}`}
            className={`grid grid-cols-[3.5rem_3.5rem_2rem_1fr] border-l-2 font-mono text-xs leading-6 ${
              row.type === "removed"
                ? "border-red-500 bg-red-50"
                : row.type === "added"
                  ? "border-zinc-400 bg-zinc-100"
                  : "border-transparent"
            }`}
          >
            <span className="select-none border-r border-zinc-200 px-2 text-right text-zinc-400">
              {row.oldLine ?? ""}
            </span>
            <span className="select-none border-r border-zinc-200 px-2 text-right text-zinc-400">
              {row.newLine ?? ""}
            </span>
            <span
              className={`select-none px-2 text-center ${
                row.type === "removed"
                  ? "text-red-600"
                  : row.type === "added"
                    ? "text-zinc-700"
                    : "text-zinc-400"
              }`}
            >
              {row.type === "added"
                ? "+"
                : row.type === "removed"
                  ? "-"
                  : " "}
            </span>
            <pre
              className={`whitespace-pre px-2 ${
                row.type === "removed"
                  ? "text-red-700"
                  : row.type === "added"
                    ? "text-zinc-900"
                    : "text-zinc-600"
              }`}
            >
              {row.text || " "}
            </pre>
          </div>
        ))}
      </div>
    </div>
  );
}

const presets: Array<[BranchKey, BranchKey, string]> = [
  ["left", "right", "Left ↔ Right"],
  ["base", "left", "Base ↔ Left"],
  ["base", "right", "Base ↔ Right"],
  ["left", "merge", "Left ↔ Merge"],
  ["right", "merge", "Right ↔ Merge"],
];

export function MergeDiffViewer({ branches }: { branches: BranchView[] }) {
  const [leftKey, setLeftKey] = useState<BranchKey>("left");
  const [rightKey, setRightKey] = useState<BranchKey>("right");

  const leftBranch =
    branches.find((branch) => branch.key === leftKey) ?? branches[0];
  const rightBranch =
    branches.find((branch) => branch.key === rightKey) ?? branches[1];

  const groups = useMemo(() => {
    if (!leftBranch || !rightBranch) return [];
    return buildGroups(leftBranch, rightBranch);
  }, [leftBranch, rightBranch]);

  if (!leftBranch || !rightBranch) {
    return (
      <div className="rounded-2xl border border-zinc-200 bg-white p-6 text-sm text-zinc-600">
        Não há branches suficientes para comparar.
      </div>
    );
  }

  const added = groups.reduce((total, group) => total + group.added, 0);
  const removed = groups.reduce((total, group) => total + group.removed, 0);
  const hasChanges = added > 0 || removed > 0;
  const changedClasses = groups.filter((group) => group.hasChanges).length;

  function swapBranches() {
    setLeftKey(rightKey);
    setRightKey(leftKey);
  }

  return (
    <div className="rounded-3xl border border-zinc-200 bg-white">
      <div className="border-b border-zinc-200 p-4">
        <div className="flex flex-wrap items-end gap-3">
          <label className="flex flex-col gap-1 text-[10px] uppercase tracking-[0.16em] text-zinc-600">
            Comparar
            <select
              value={leftKey}
              onChange={(event) =>
                setLeftKey(event.target.value as BranchKey)
              }
              className="rounded-lg border border-zinc-300 bg-white px-3 py-2 font-mono text-xs text-zinc-900 outline-none transition focus:border-red-500"
            >
              {branches.map((branch) => (
                <option key={branch.key} value={branch.key}>
                  {branch.label} · {branch.lines} linhas
                </option>
              ))}
            </select>
          </label>

          <button
            type="button"
            onClick={swapBranches}
            aria-label="Trocar branches"
            className="rounded-lg border border-zinc-300 bg-white px-3 py-2 text-sm text-zinc-700 transition hover:border-red-400 hover:text-red-700"
          >
            ⇄
          </button>

          <label className="flex flex-col gap-1 text-[10px] uppercase tracking-[0.16em] text-zinc-600">
            com
            <select
              value={rightKey}
              onChange={(event) =>
                setRightKey(event.target.value as BranchKey)
              }
              className="rounded-lg border border-zinc-300 bg-white px-3 py-2 font-mono text-xs text-zinc-900 outline-none transition focus:border-red-500"
            >
              {branches.map((branch) => (
                <option key={branch.key} value={branch.key}>
                  {branch.label} · {branch.lines} linhas
                </option>
              ))}
            </select>
          </label>

          <div className="ml-auto flex items-center gap-2">
            <Badge tone="rose">−{formatNumber(removed)}</Badge>
            <Badge tone="slate">+{formatNumber(added)}</Badge>
            <Badge tone="slate">
              {formatNumber(changedClasses)} classe(s) alterada(s)
            </Badge>
          </div>
        </div>

        <div className="mt-3 flex flex-wrap gap-2">
          {presets.map(([presetLeft, presetRight, label]) => {
            const active =
              leftKey === presetLeft && rightKey === presetRight;
            return (
              <button
                key={label}
                type="button"
                onClick={() => {
                  setLeftKey(presetLeft);
                  setRightKey(presetRight);
                }}
                className={`rounded-lg border px-2.5 py-1.5 text-[11px] transition ${
                  active
                    ? "border-red-300 bg-red-50 text-red-700"
                    : "border-zinc-300 bg-white text-zinc-600 hover:border-zinc-400 hover:text-zinc-900"
                }`}
              >
                {label}
              </button>
            );
          })}
        </div>
      </div>

      <div className="p-4">
        {leftKey === rightKey ? (
          <div className="rounded-xl border border-red-200 bg-red-50 p-4 text-xs text-red-700">
            Selecione duas branches diferentes para visualizar o diff.
          </div>
        ) : !hasChanges ? (
          <div className="rounded-xl border border-zinc-200 bg-zinc-50 p-4 text-xs text-zinc-600">
            Nenhuma diferença textual entre {leftBranch.label} e{" "}
            {rightBranch.label}.
          </div>
        ) : (
          <div className="space-y-3">
            {groups.map((group) => (
              <details
                key={group.key}
                open={group.hasChanges}
                className="overflow-hidden rounded-2xl border border-zinc-200 bg-white"
              >
                <summary className="flex cursor-pointer list-none flex-wrap items-center justify-between gap-3 px-4 py-3 [&::-webkit-details-marker]:hidden">
                  <div className="min-w-0">
                    <p className="truncate text-sm font-semibold text-zinc-900">
                      {group.title}
                    </p>
                    {group.sourcePath ? (
                      <p className="truncate font-mono text-[10px] text-zinc-500">
                        {group.sourcePath}
                      </p>
                    ) : null}
                  </div>
                  <div className="flex shrink-0 items-center gap-2">
                    {group.hasChanges ? (
                      <>
                        <Badge tone="rose">
                          −{formatNumber(group.removed)}
                        </Badge>
                        <Badge tone="slate">
                          +{formatNumber(group.added)}
                        </Badge>
                      </>
                    ) : (
                      <Badge tone="emerald">sem alterações</Badge>
                    )}
                  </div>
                </summary>

                <div className="border-t border-zinc-200 p-3">
                  {group.hasChanges ? (
                    <DiffTable rows={group.rows} />
                  ) : (
                    <p className="rounded-xl border border-zinc-200 bg-zinc-50 p-4 text-xs text-zinc-600">
                      Sem diferenças nesta classe entre {leftBranch.label} e{" "}
                      {rightBranch.label}.
                    </p>
                  )}
                </div>
              </details>
            ))}
          </div>
        )}

        <p className="mt-3 text-[11px] leading-5 text-zinc-500">
          Diffs separados por classe extraída do conteúdo, pareados por nome
          entre as branches selecionadas. Linhas removidas aparecem em
          vermelho; adicionadas em cinza.
        </p>
      </div>
    </div>
  );
}
