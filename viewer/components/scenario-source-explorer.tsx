"use client";

import { useState } from "react";

import { BranchViewer } from "@/components/branch-viewer";
import { MergeDiffViewer } from "@/components/merge-diff-viewer";
import { ThreeWayDiffViewer } from "@/components/three-way-diff-viewer";
import type { BranchView } from "@/lib/types";

type SourceView = "diff" | "three-way" | "sources";

export function ScenarioSourceExplorer({
  branches,
}: {
  branches: BranchView[];
}) {
  const [view, setView] = useState<SourceView>("diff");

  return (
    <div className="space-y-4">
      <div className="inline-flex rounded-xl border border-zinc-300 bg-white p-1">
        <button
          type="button"
          onClick={() => setView("diff")}
          className={`rounded-lg px-3 py-1.5 text-xs font-medium transition ${
            view === "diff"
              ? "bg-red-50 text-red-700"
              : "text-zinc-600 hover:text-zinc-900"
          }`}
        >
          Diff 2 vias
        </button>
        <button
          type="button"
          onClick={() => setView("three-way")}
          className={`rounded-lg px-3 py-1.5 text-xs font-medium transition ${
            view === "three-way"
              ? "bg-red-50 text-red-700"
              : "text-zinc-600 hover:text-zinc-900"
          }`}
        >
          Diff 3 vias
        </button>
        <button
          type="button"
          onClick={() => setView("sources")}
          className={`rounded-lg px-3 py-1.5 text-xs font-medium transition ${
            view === "sources"
              ? "bg-red-50 text-red-700"
              : "text-zinc-600 hover:text-zinc-900"
          }`}
        >
          Fontes
        </button>
      </div>

      {view === "diff" ? (
        <MergeDiffViewer branches={branches} />
      ) : view === "three-way" ? (
        <ThreeWayDiffViewer branches={branches} />
      ) : (
        <BranchViewer branches={branches} />
      )}
    </div>
  );
}
