export function JsonViewer({ data }: { data: unknown }) {
  return (
    <pre className="code-scroll overflow-auto rounded-2xl border border-white/10 bg-slate-950/80 p-5 font-mono text-xs leading-6 text-slate-300">
      {JSON.stringify(data, null, 2)}
    </pre>
  );
}
