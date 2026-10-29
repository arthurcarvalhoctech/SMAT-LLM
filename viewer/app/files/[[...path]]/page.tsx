import Link from "next/link";
import { notFound } from "next/navigation";

import { Badge, Breadcrumbs, EmptyState, SectionHeading } from "@/components/ui";
import { formatBytes, formatDate } from "@/lib/format";
import { encodeSegments, listFiles } from "@/lib/smat-data";

export const dynamic = "force-dynamic";

type FilesPageProps = {
  params: Promise<{ path?: string[] }>;
};

export default async function FilesPage({ params }: FilesPageProps) {
  const { path: rawPath } = await params;
  const pathParts = rawPath ?? [];
  const preview = await listFiles(pathParts);

  if (!preview) notFound();

  const crumbs = [
    { href: "/files", label: "Arquivos" },
    ...pathParts.map((part, index) => ({
      href: `/files/${encodeSegments(...pathParts.slice(0, index + 1))}`,
      label: part,
    })),
  ];

  return (
    <div className="space-y-8">
      <Breadcrumbs items={crumbs} />

      <section className="panel-gradient rounded-3xl border border-white/10 p-6 sm:p-8">
        <div className="flex flex-wrap items-center gap-2">
          <Badge tone="cyan">
            {preview.isDirectory ? "diretório" : "arquivo"}
          </Badge>
          {preview.isDirectory ? (
            <Badge tone="slate">
              {preview.entries?.length ?? 0} entradas
            </Badge>
          ) : (
            <Badge tone="slate">{formatBytes(preview.bytes)}</Badge>
          )}
          <Badge tone="slate">{formatDate(preview.modified)}</Badge>
        </div>
        <h1 className="mt-4 break-all font-mono text-2xl font-semibold tracking-tight text-white sm:text-3xl">
          /{preview.path || "output-test-dest"}
        </h1>
        {!preview.isDirectory ? (
          <div className="mt-5 flex flex-wrap gap-3">
            <a
              href={`/api/file/${encodeSegments(...pathParts)}`}
              target="_blank"
              rel="noreferrer"
              className="rounded-xl border border-white/10 bg-white/[0.03] px-3.5 py-2 text-xs font-medium text-slate-300 transition hover:border-white/20 hover:text-white"
            >
              Baixar arquivo bruto
            </a>
            <Link
              href={`/files/${encodeSegments(
                ...pathParts.slice(0, Math.max(0, pathParts.length - 1)),
              )}`}
              className="rounded-xl border border-white/10 bg-white/[0.03] px-3.5 py-2 text-xs font-medium text-slate-300 transition hover:border-white/20 hover:text-white"
            >
              ← Diretório pai
            </Link>
          </div>
        ) : null}
      </section>

      {preview.isDirectory ? (
        <section>
          <SectionHeading
            eyebrow="Navegador"
            title="Conteúdo do diretório"
            description="Navegue por scenarios, projects, reports e qualquer outro artefato em SMAT/output-test-dest."
          />
          {preview.entries?.length ? (
            <div className="divide-y divide-white/5 overflow-hidden rounded-2xl border border-white/10">
              {preview.entries.map((entry) => (
                <Link
                  key={entry.path}
                  href={`/files/${encodeSegments(...entry.path.split("/"))}`}
                  className="flex flex-wrap items-center justify-between gap-3 px-4 py-3 text-xs transition hover:bg-white/[0.03]"
                >
                  <span className="flex min-w-0 items-center gap-3">
                    <span
                      className={`flex h-7 w-7 shrink-0 items-center justify-center rounded-lg border text-[10px] font-semibold ${
                        entry.kind === "directory"
                          ? "border-indigo-400/20 bg-indigo-400/10 text-indigo-200"
                          : "border-white/10 bg-white/[0.03] text-slate-400"
                      }`}
                    >
                      {entry.kind === "directory" ? "DIR" : "FILE"}
                    </span>
                    <span className="truncate font-mono text-slate-300">
                      {entry.name}
                      {entry.kind === "directory" ? "/" : ""}
                    </span>
                  </span>
                  <span className="flex shrink-0 items-center gap-3 text-slate-500">
                    {entry.kind === "file" ? (
                      <span>{formatBytes(entry.bytes)}</span>
                    ) : null}
                    <span>{formatDate(entry.modified)}</span>
                  </span>
                </Link>
              ))}
            </div>
          ) : (
            <EmptyState
              title="Diretório vazio"
              description="Não há arquivos ou subdiretórios neste ponto de SMAT/output-test-dest."
            />
          )}
        </section>
      ) : (
        <section>
          <SectionHeading
            eyebrow="Prévia"
            title="Conteúdo do arquivo"
            description={
              preview.text !== undefined
                ? "Prévia de até 200 KB."
                : "Prévia indisponível para este tipo de arquivo."
            }
          />
          {preview.text !== undefined ? (
            <div className="overflow-hidden rounded-2xl border border-white/10">
              <pre className="code-scroll overflow-auto bg-slate-950/80 p-5 font-mono text-xs leading-6 text-slate-300">
                {preview.text}
              </pre>
              {preview.truncated ? (
                <p className="border-t border-white/5 px-4 py-2 text-[11px] text-amber-300">
                  Prévia limitada a 200 KB. Use o download para ver o arquivo
                  completo.
                </p>
              ) : null}
            </div>
          ) : (
            <div className="rounded-2xl border border-white/10 bg-white/[0.02] p-6 text-sm text-slate-400">
              Arquivo binário ou formato não textual. Use o botão de download
              para inspecioná-lo.
            </div>
          )}
        </section>
      )}
    </div>
  );
}
