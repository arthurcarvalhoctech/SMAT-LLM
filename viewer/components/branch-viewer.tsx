"use client";

import { useState } from "react";

import { Badge } from "@/components/ui";
import { formatBytes, formatNumber } from "@/lib/format";
import type { BranchKey, BranchView } from "@/lib/types";

function CodeBlock({ code }: { code: string }) {
  const lines = code.split("\n");
  return (
    <div className="code-scroll overflow-auto rounded-b-2xl bg-slate-950/80">
      <div className="flex min-w-max">
        <div
          aria-hidden
          className="select-none border-r border-white/5 bg-white/[0.02] px-3 py-4 text-right font-mono text-xs leading-6 text-slate-600"
        >
          {lines.map((_, index) => (
            <div key={index}>{index + 1}</div>
          ))}
        </div>
        <pre className="min-w-0 p-4 font-mono text-xs leading-6 text-slate-200">
          <code>{code}</code>
        </pre>
      </div>
    </div>
  );
}

export function BranchViewer({ branches }: { branches: BranchView[] }) {
  const [activeKey, setActiveKey] = useState<BranchKey>(
    branches[0]?.key ?? "base",
  );
  const [mode, setMode] = useState<"sections" | "raw">("sections");
  const [copied, setCopied] = useState(false);

  const active = branches.find((branch) => branch.key === activeKey) ?? branches[0];

  if (!active) {
    return (
      <div className="rounded-2xl border border-white/10 bg-white/[0.02] p-6 text-sm text-slate-400">
        Nenhum arquivo de branch encontrado.
      </div>
    );
  }

  async function copyActive() {
    try {
      await navigator.clipboard.writeText(active.content);
      setCopied(true);
      window.setTimeout(() => setCopied(false), 1800);
    } catch {
      setCopied(false);
    }
  }

  return (
    <div className="rounded-3xl border border-white/10 bg-white/[0.02]">
      <div className="border-b border-white/5 p-4">
        <div className="flex flex-wrap items-center gap-2">
          {branches.map((branch) => {
            const selected = branch.key === active.key;
            return (
              <button
                key={branch.key}
                type="button"
                aria-pressed={selected}
                onClick={() => {
                  setActiveKey(branch.key);
                  setCopied(false);
                }}
                className={`flex items-center gap-2 rounded-xl border px-3 py-2 text-sm transition ${
                  selected
                    ? "border-indigo-400/50 bg-indigo-500/15 text-white"
                    : "border-white/10 bg-white/[0.02] text-slate-400 hover:border-white/20 hover:text-slate-200"
                }`}
              >
                <span className="font-medium">{branch.label}</span>
                <span className="text-[11px] text-slate-500">
                  {formatNumber(branch.lines)} linhas
                </span>
                {branch.missing ? (
                  <span className="h-1.5 w-1.5 rounded-full bg-amber-400" />
                ) : null}
              </button>
            );
          })}
        </div>

        <div className="mt-4 flex flex-wrap items-center justify-between gap-3">
          <div className="flex flex-wrap items-center gap-2 text-xs text-slate-500">
            <Badge tone="slate">{active.label}</Badge>
            <span>{formatBytes(active.bytes)}</span>
            <span className="h-1 w-1 rounded-full bg-slate-700" />
            <span>{formatNumber(active.sections.length)} seções</span>
            {active.missing ? <Badge tone="amber">fonte ausente</Badge> : null}
          </div>

          <div className="flex flex-wrap items-center gap-2">
            <div className="flex rounded-lg border border-white/10 bg-white/[0.02] p-0.5">
              <button
                type="button"
                onClick={() => setMode("sections")}
                className={`rounded-md px-2.5 py-1.5 text-xs transition ${
                  mode === "sections"
                    ? "bg-white/10 text-white"
                    : "text-slate-500 hover:text-slate-300"
                }`}
              >
                Seções
              </button>
              <button
                type="button"
                onClick={() => setMode("raw")}
                className={`rounded-md px-2.5 py-1.5 text-xs transition ${
                  mode === "raw"
                    ? "bg-white/10 text-white"
                    : "text-slate-500 hover:text-slate-300"
                }`}
              >
                Bruto
              </button>
            </div>

            <button
              type="button"
              onClick={copyActive}
              className="rounded-lg border border-white/10 bg-white/[0.02] px-2.5 py-1.5 text-xs text-slate-300 transition hover:border-white/20 hover:text-white"
            >
              {copied ? "Copiado" : "Copiar"}
            </button>

            <a
              href={active.downloadPath}
              target="_blank"
              rel="noreferrer"
              className="rounded-lg border border-white/10 bg-white/[0.02] px-2.5 py-1.5 text-xs text-slate-300 transition hover:border-white/20 hover:text-white"
            >
              Baixar
            </a>
          </div>
        </div>
      </div>

      {active.missing ? (
        <div className="mx-4 mt-4 rounded-xl border border-amber-400/30 bg-amber-400/10 p-3 text-xs leading-5 text-amber-200">
          Esta branch não tem fontes de todas as classes-alvo. O conteúdo abaixo
          preserva os comentários gravados no snapshot.
        </div>
      ) : null}

      <div className="p-4">
        {mode === "sections" && active.sections.length > 0 ? (
          <div className="space-y-5">
            {active.sections.map((section, index) => (
              <div
                key={`${section.sourcePath}-${index}`}
                className="overflow-hidden rounded-2xl border border-white/10"
              >
                <div className="flex flex-wrap items-start justify-between gap-2 border-b border-white/5 bg-white/[0.02] p-4">
                  <div>
                    <p className="text-[10px] uppercase tracking-[0.2em] text-slate-500">
                      Classes
                    </p>
                    <p className="mt-1 font-mono text-sm text-slate-200">
                      {section.classes.join(", ")}
                    </p>
                  </div>
                  <p className="max-w-full break-all font-mono text-[11px] text-slate-500">
                    {section.sourcePath}
                  </p>
                </div>
                <CodeBlock code={section.code || "// vazio"} />
              </div>
            ))}
          </div>
        ) : (
          <div className="overflow-hidden rounded-2xl border border-white/10">
            <CodeBlock code={active.content || "// vazio"} />
          </div>
        )}
      </div>
    </div>
  );
}
