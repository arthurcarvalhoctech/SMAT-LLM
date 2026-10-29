import Link from "next/link";

export default function NotFound() {
  return (
    <div className="rounded-3xl border border-white/10 bg-white/[0.02] p-10 text-center">
      <p className="text-[11px] uppercase tracking-[0.22em] text-indigo-300/80">
        404
      </p>
      <h1 className="mt-2 text-3xl font-semibold text-white">
        Conteúdo não encontrado
      </h1>
      <p className="mx-auto mt-3 max-w-lg text-sm leading-6 text-slate-400">
        O cenário, execução ou arquivo solicitado não existe em{" "}
        <code className="font-mono text-slate-300">
          SMAT/output-test-dest
        </code>
        .
      </p>
      <Link
        href="/executions"
        className="mt-6 inline-flex rounded-xl bg-indigo-500 px-4 py-2 text-sm font-medium text-white transition hover:bg-indigo-400"
      >
        Voltar para execuções
      </Link>
    </div>
  );
}
